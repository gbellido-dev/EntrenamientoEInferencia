"""Ajustar SSDLite a las etiquetas del proyecto y exportarlo a ONNX."""
import copy
from datetime import datetime, timezone
from functools import lru_cache, partial
import json
from pathlib import Path
import tempfile
import uuid
import zipfile

import numpy as np
import torch
from torchvision.models.detection import ssdlite320_mobilenet_v3_large, SSDLite320_MobileNet_V3_Large_Weights
from torchvision.models.detection.ssdlite import SSDLiteClassificationHead
from torchvision.models.detection.ssd import SSD
from torchvision.models.detection.image_list import ImageList

from aula_ia.project import detection_split
from aula_ia.inference import DETECTION_PREPROCESS, Predictor, box_iou, decode_detections, detection_tensor
from aula_ia.errors import Cancelled


class ClassroomSSD(SSD):
    """Conservar señal de fondo en imágenes revisadas que no contienen objetos."""
    def compute_loss(self, targets, head_outputs, anchors, matched_idxs):
        losses = super().compute_loss(targets, head_outputs, anchors, matched_idxs)
        empty = [index for index, target in enumerate(targets) if len(target['boxes']) == 0]
        if empty:
            logits = head_outputs['cls_logits'][empty]
            background = torch.zeros(logits.shape[:2], dtype=torch.long, device=logits.device)
            per_anchor = torch.nn.functional.cross_entropy(logits.transpose(1, 2), background, reduction='none')
            losses['classification'] = losses['classification'] + .5*per_anchor.topk(min(32, per_anchor.shape[1]), dim=1).values.mean()
        return losses


def build_detector(pretrained=True, class_count=1):
    torch.set_num_threads(2)
    torch.hub.set_dir(str(Path(__file__).resolve().parent.parent/'.cache'/'torch'))
    model = ssdlite320_mobilenet_v3_large(
        weights=SSDLite320_MobileNet_V3_Large_Weights.DEFAULT if pretrained else None,
        weights_backbone=None)
    channels = [block[0][0].in_channels for block in model.head.classification_head.module_list]
    model.head.classification_head = SSDLiteClassificationHead(channels,
        model.anchor_generator.num_anchors_per_location(), class_count+1,
        partial(torch.nn.BatchNorm2d, eps=.001, momentum=.03))
    model = ClassroomSSD(model.backbone, model.anchor_generator, (320, 320), class_count+1,
                         image_mean=model.transform.image_mean, image_std=model.transform.image_std, head=model.head)
    for parameter in model.backbone.parameters():
        parameter.requires_grad = False
    return model


class RawDetector(torch.nn.Module):
    """Entrada 0..1; normalización dentro del grafo, cajas en píxeles de 320x320."""
    def __init__(self, model):
        super().__init__()
        self.model = model.eval()
        self.register_buffer('mean', torch.tensor(model.transform.image_mean).view(1, 3, 1, 1))
        self.register_buffer('std', torch.tensor(model.transform.image_std).view(1, 3, 1, 1))
        with torch.no_grad():
            sample = torch.zeros(1, 3, 320, 320)
            features = list(model.backbone((sample-self.mean)/self.std).values())
            anchors = model.anchor_generator(ImageList(sample, [(320, 320)]), features)[0]
        self.register_buffer('anchors', anchors)
        self.eval()

    def forward(self, image):
        features = list(self.model.backbone((image-self.mean)/self.std).values())
        outputs = self.model.head(features)
        boxes = self.model.box_coder.decode_single(outputs['bbox_regression'][0], self.anchors)
        probabilities = torch.softmax(outputs['cls_logits'], dim=-1)
        scores = probabilities[:, :, 1:]
        return boxes.unsqueeze(0), scores


def _single_class_metrics(samples, threshold=.5):
    """AP50 de una clase e interpolación de precisión; emparejamiento 1 a 1 por foto."""
    total_truth = sum(len(truth) for _, truth in samples)
    records = []
    for predictions, truth in samples:
        used = set()
        truth = np.asarray(truth, dtype=np.float32).reshape(-1, 4)
        for prediction in sorted(predictions, key=lambda item: item['score'], reverse=True):
            overlaps = box_iou(np.asarray(prediction['box']), truth)
            for index in used:
                overlaps[index] = -1
            best = int(overlaps.argmax()) if len(overlaps) else -1
            hit = best >= 0 and overlaps[best] >= .5
            if hit:
                used.add(best)
            records.append((prediction['score'], int(hit)))
    records.sort(key=lambda item: item[0], reverse=True)
    hits = np.cumsum([r[1] for r in records], dtype=float)
    precision = hits/np.arange(1, len(records)+1)
    recall = hits/max(1, total_truth)
    # Integral de la envolvente monótona (AP50, no mAP de varios IoU).
    r = np.concatenate(([0.], recall, [1.]))
    p = np.concatenate(([0.], precision, [0.]))
    p = np.maximum.accumulate(p[::-1])[::-1]
    indices = np.flatnonzero(r[1:] != r[:-1])
    ap = float(np.sum((r[indices+1]-r[indices])*p[indices+1])) if total_truth else 0.
    selected = [record for record in records if record[0] >= threshold]
    tp = sum(item[1] for item in selected)
    fp, fn = len(selected)-tp, total_truth-tp
    prec, rec = tp/max(1, tp+fp), tp/max(1, total_truth)
    return {'ap50': ap, 'precision': prec, 'recall': rec, 'f1': 2*prec*rec/max(1e-8, prec+rec),
            'true_positives': tp, 'false_positives': fp, 'false_negatives': fn,
            'threshold': threshold, 'iou': .5, 'images': len(samples), 'objects': total_truth}


def detection_metrics(samples, classes, threshold=.5):
    per_class = {}
    for label in classes:
        filtered = []
        for predictions, truth in samples:
            filtered.append(([p for p in predictions if p['label'] == label],
                             [item['box'] for item in truth if item['label'] == label]))
        per_class[label] = _single_class_metrics(filtered, threshold)
    tp = sum(m['true_positives'] for m in per_class.values())
    fp = sum(m['false_positives'] for m in per_class.values())
    fn = sum(m['false_negatives'] for m in per_class.values())
    precision, recall = tp/max(1, tp+fp), tp/max(1, tp+fn)
    return {'ap50': sum(m['ap50'] for m in per_class.values())/len(classes),
            'precision': precision, 'recall': recall, 'f1': 2*precision*recall/max(1e-8, precision+recall),
            'true_positives': tp, 'false_positives': fp, 'false_negatives': fn,
            'threshold': threshold, 'iou': .5, 'images': len(samples), 'objects': tp+fn,
            'per_class': per_class}


def train_objects(project, output_dir, epochs=15, learning_rate=.001,
                report=lambda text: None, cancelled=lambda: False, pretrained=True):
    if not 1 <= epochs <= 100 or not 0 < learning_rate <= 1:
        raise ValueError('Épocas o tasa de aprendizaje no válidas.')
    def check():
        if cancelled():
            raise Cancelled('Detección cancelada; se conserva el paquete anterior.')
    parts = detection_split(project)
    classes = project['classes']
    report('Reparto: '+', '.join(f'{key}: {len(rows)} fotos' for key, rows in parts.items()))
    report(project.get('grouping_note', 'Comprueba que fotos relacionadas compartan grupo.'))
    report('Cargando SSDLite MobileNetV3. La primera vez se descargan pesos oficiales.')
    torch.manual_seed(42)
    check()
    model = build_detector(pretrained, len(classes))
    optimizer = torch.optim.AdamW(model.head.parameters(), lr=learning_rate, weight_decay=.0001)
    # Caché acotada: hasta ~150 MiB de imágenes de 320x320, no fotos originales.
    @lru_cache(maxsize=128)
    def image_data(path):
        return detection_tensor(path, max_pixels=64_000_000)

    def sample(row):
        tensor, width, height = image_data(row['path'])
        boxes = np.asarray(row['boxes'], dtype=np.float32).reshape(-1, 4)
        if len(boxes) and (np.any(boxes[:, [0, 2]] > width) or np.any(boxes[:, [1, 3]] > height)):
            raise ValueError(f'Hay cajas fuera de la imagen {Path(row["path"]).name}.')
        scaled = boxes*np.array([320/width, 320/height, 320/width, 320/height], dtype=np.float32)
        return torch.from_numpy(tensor[0]), {'boxes': torch.from_numpy(scaled),
                    'labels': torch.tensor([classes.index(label)+1 for label in row['box_labels']], dtype=torch.int64)}

    def evaluate(rows):
        raw = RawDetector(model)
        samples = []
        with torch.inference_mode():
            for row in rows:
                check()
                tensor, width, height = image_data(row['path'])
                boxes, scores = raw(torch.from_numpy(tensor))
                predicted = decode_detections(boxes[0].numpy(), scores[0].numpy(), width, height, .01, classes)
                samples.append((predicted, [{'box': box, 'label': label} for box, label in zip(row['boxes'], row['box_labels'])]))
        return detection_metrics(samples, classes=classes)

    history, best_ap, best_state = [], -1., None
    for epoch in range(epochs):
        check()
        batches = (len(parts['train']) + 3) // 4
        report(f'Época {epoch+1}/{epochs} · preparando {batches} lotes de imágenes…')
        model.train()
        model.backbone.eval()
        # BN congelada, incluso en las cabezas: evita estadísticas inestables
        # y permite lotes pequeños en un PC de aula.
        for module in model.modules():
            if isinstance(module, torch.nn.BatchNorm2d):
                module.eval()
        order = torch.randperm(len(parts['train'])).tolist()
        total, count = 0., 0
        for start in range(0, len(order), 4):
            check()
            batch = [sample(parts['train'][index]) for index in order[start:start+4]]
            images = [item[0] for item in batch]
            targets = [item[1] for item in batch]
            optimizer.zero_grad()
            losses = model(images, targets)
            loss = sum(losses.values())
            if not torch.isfinite(loss):
                raise ValueError('Pérdida no finita; revisa rectángulos y tasa de aprendizaje.')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.head.parameters(), 10.)
            optimizer.step()
            total += loss.item()*len(batch)
            count += len(batch)
            report(f'Época {epoch+1}/{epochs} · lote {start//4+1}/{batches} · '
                   f'{count}/{len(order)} imágenes procesadas')
        report(f'Época {epoch+1}/{epochs} · evaluando las imágenes de validación…')
        validation = evaluate(parts['val'])
        history.append({'epoch': epoch+1, 'loss': total/count, 'validation': validation})
        report(f'Época {epoch+1}/{epochs} · pérdida {total/count:.3f} · '
               f'AP50 validación {validation["ap50"]:.1%} · precisión {validation["precision"]:.1%} · '
               f'recuperación {validation["recall"]:.1%}')
        if validation['ap50'] > best_ap:
            best_ap, best_state = validation['ap50'], copy.deepcopy(model.state_dict())
    model.load_state_dict(best_state)
    model.eval()
    selected_epoch = max(history, key=lambda row: row['validation']['ap50'])['epoch']
    report('Evaluando el detector elegido con las imágenes de prueba…')
    test = evaluate(parts['test'])
    metrics = {'task': project['task'], 'classes': classes, 'history': history, 'test_detection': test,
               'selected_epoch': selected_epoch, 'epochs': epochs, 'learning_rate': learning_rate, 'seed': 42,
               'split_counts': {key: len(rows) for key, rows in parts.items()},
               'split': {key: [{'sha256': row['sha256'], 'group': row['group']} for row in rows] for key, rows in parts.items()},
               'grouping_note': project.get('grouping_note', ''), 'torch_version': torch.__version__,
               'note': 'AP50 media entre clases; NMS por clase IoU 0.4, evaluación IoU 0.5. Precisión/recuperación a umbral 0.5.'}
    manifest = {'format_version': 1, 'task': project['task'], 'name': project['name'], 'classes': classes,
                'architecture': 'ssdlite320_mobilenet_v3_large', 'preprocess': DETECTION_PREPROCESS,
                'output': 'ssd_boxes_scores', 'created_utc': datetime.now(timezone.utc).isoformat()}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = RawDetector(model)
    filename = 'detector-objetos.zip'
    with tempfile.TemporaryDirectory(dir=output_dir) as temporary:
        temporary = Path(temporary)
        check()
        tensor = torch.from_numpy(image_data(parts['test'][0]['path'])[0])
        report('Exportando detector ONNX; se comprueban cajas y puntuaciones contra PyTorch…')
        torch.onnx.export(raw, tensor, str(temporary/'model.onnx'), opset_version=17, dynamo=False,
                          input_names=['image'], output_names=['boxes', 'scores'])
        def package():
            with zipfile.ZipFile(temporary/'detector.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.write(temporary/'model.onnx', 'model.onnx')
                archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
                archive.writestr('metrics.json', json.dumps(metrics, ensure_ascii=False))
        package()
        predictor = Predictor((temporary/'detector.zip').read_bytes())
        errors = [0., 0.]
        for row in parts['test'][:5]:
            check()
            tensor = torch.from_numpy(image_data(row['path'])[0])
            with torch.inference_mode():
                expected = raw(tensor)
            actual = predictor.session.run(None, {predictor.input_name: tensor.numpy()})
            for index, (a, b) in enumerate(zip(expected, actual)):
                a = a.numpy()
                if not np.allclose(a, b, atol=.01 if index == 0 else 1e-4, rtol=1e-3):
                    raise ValueError('La salida ONNX no coincide con PyTorch; no se publica el paquete.')
                errors[index] = max(errors[index], float(np.abs(a-b).max()))
        metrics['export_max_error'] = {'box_pixels_320': errors[0], 'score': errors[1]}
        package()
        check()
        staging = output_dir/f'.detector-{uuid.uuid4().hex}.tmp'
        try:
            staging.write_bytes((temporary/'detector.zip').read_bytes())
            staging.replace(output_dir/filename)
        finally:
            staging.unlink(missing_ok=True)
    report(f'Prueba reservada: AP50={test["ap50"]:.1%}, precisión={test["precision"]:.1%}, recuperación={test["recall"]:.1%}')
    return str(output_dir/filename), metrics
