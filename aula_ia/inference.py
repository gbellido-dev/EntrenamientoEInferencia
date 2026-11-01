"""Contrato único de detección de objetos para Windows y Raspberry Pi."""
import io
import hashlib
import json
import math
import time
import warnings
import zipfile

import numpy as np
from PIL import Image

MAX_PACKAGE = 64 * 1024 * 1024
MAX_IMAGE = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 64_000_000
DETECTION_PREPROCESS = {'size': 320, 'resize': 'stretch', 'color': 'RGB', 'layout': 'NCHW',
                        'scale': 255.0, 'orientation': 'raw_pixels', 'normalization': 'inside_model'}


def detection_tensor(source, max_pixels=20_000_000):
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        if isinstance(source, Image.Image):
            if source.width*source.height > max_pixels:
                raise ValueError(f'La imagen supera los {max_pixels//1_000_000} millones de píxeles.')
            image = source.convert('RGB')
        else:
            with Image.open(source) as original:
                if original.width*original.height > max_pixels:
                    raise ValueError(f'La imagen supera los {max_pixels//1_000_000} millones de píxeles.')
                image = original.convert('RGB')
        width, height = image.size
        image = image.resize((320, 320), Image.Resampling.BILINEAR)
        array = np.asarray(image, dtype=np.float32)/np.float32(255)
    return np.ascontiguousarray(array.transpose(2, 0, 1)[None]), width, height


def box_iou(box, others):
    others = np.asarray(others, dtype=np.float32).reshape(-1, 4)
    intersection = np.maximum(0, np.minimum(box[2:], others[:, 2:])-np.maximum(box[:2], others[:, :2])).prod(1)
    area = np.maximum(0, box[2:]-box[:2]).prod()
    areas = np.maximum(0, others[:, 2:]-others[:, :2]).prod(1)
    return intersection/np.maximum(area+areas-intersection, 1e-8)


def decode_detections(boxes, scores, width, height, threshold=.5, classes=None):
    boxes = np.asarray(boxes, dtype=np.float32).reshape(-1, 4).copy()
    scores = np.asarray(scores, dtype=np.float32)
    if not classes or scores.ndim != 2 or scores.shape[1] != len(classes):
        raise ValueError('Las puntuaciones no coinciden con las etiquetas del detector.')
    if len(boxes) != len(scores) or not np.isfinite(boxes).all() or not np.isfinite(scores).all():
        raise ValueError('El detector ha devuelto valores inválidos.')
    if np.any(scores < 0) or np.any(scores > 1):
        raise ValueError('Las puntuaciones deben estar entre 0 y 1.')
    boxes = np.clip(boxes, 0, 320)
    scale = np.array([width/320, height/320, width/320, height/320])
    results = []
    for class_id, label in enumerate(classes):
        values = scores[:, class_id]
        valid = np.flatnonzero((values >= threshold) & (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1]))
        order = valid[np.argsort(-values[valid], kind='stable')[:200]]
        keep = []
        while len(order) and len(keep) < 100:
            selected = int(order[0])
            keep.append(selected)
            order = order[1:][box_iou(boxes[selected], boxes[order[1:]]) <= .4]
        results.extend({'label': label, 'class_id': class_id, 'score': float(values[i]),
                        'box': (boxes[i]*scale).tolist()} for i in keep)
    return sorted(results, key=lambda item: item['score'], reverse=True)[:100]


def validate_metrics(metrics):
    if not isinstance(metrics, dict):
        raise ValueError('Las métricas deben ser un objeto JSON.')
    result = metrics.get('test_detection')
    if result is None:
        return
    try:
        def check_result(item):
            for key in ('ap50', 'precision', 'recall', 'threshold'):
                value = item[key]
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError('Puntuación no válida.')
            for key in ('true_positives', 'false_positives', 'false_negatives'):
                if type(item[key]) is not int or item[key] < 0:
                    raise ValueError('Recuento no válido.')
        check_result(result)
        for item in result.get('per_class', {}).values():
            check_result(item)
        if not isinstance(metrics.get('grouping_note', ''), str):
            raise ValueError('Nota de agrupación inválida.')
    except (AttributeError, TypeError, KeyError, ValueError) as error:
        raise ValueError('El informe de detección no es válido.') from error


def read_package(data):
    if len(data) > MAX_PACKAGE:
        raise ValueError('El paquete supera los 64 MiB.')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(set(names)) != len(names) or set(names) != {'model.onnx', 'manifest.json', 'metrics.json'}:
                raise ValueError('El ZIP debe contener model.onnx, manifest.json y metrics.json, sin carpetas.')
            if sum(item.file_size for item in infos) > MAX_PACKAGE:
                raise ValueError('El contenido descomprimido supera los 64 MiB.')
            if archive.getinfo('manifest.json').file_size > 64*1024 or archive.getinfo('metrics.json').file_size > 2*1024*1024:
                raise ValueError('Los metadatos son demasiado grandes.')
            manifest = json.loads(archive.read('manifest.json'))
            labels = manifest.get('classes')
            if (manifest.get('format_version') != 1 or manifest.get('task') != 'object_detection'
                    or manifest.get('preprocess') != DETECTION_PREPROCESS or manifest.get('output') != 'ssd_boxes_scores'
                    or not isinstance(labels, list) or not 1 <= len(labels) <= 100
                    or any(not isinstance(label, str) or not label.strip() or len(label) > 80 for label in labels)
                    or len(set(labels)) != len(labels)
                    or not isinstance(manifest.get('name'), str) or not 1 <= len(manifest['name']) <= 100):
                raise ValueError('Se requiere un paquete de detección de objetos Aula IA v1.')
            metrics = json.loads(archive.read('metrics.json'))
            validate_metrics(metrics)
            return archive.read('model.onnx'), manifest, metrics
    except (zipfile.BadZipFile, KeyError, TypeError, AttributeError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('Paquete inválido o metadatos dañados.') from error


class Predictor:
    def __init__(self, data):
        import onnxruntime as ort
        model, self.manifest, self.metrics = read_package(data)
        self.model_id = hashlib.sha256(data).hexdigest()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.enable_mem_pattern = False
        self.session = ort.InferenceSession(model, sess_options=options, providers=['CPUExecutionProvider'])
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if (len(inputs) != 1 or inputs[0].type != 'tensor(float)' or inputs[0].shape != [1, 3, 320, 320]
                or len(outputs) != 2 or outputs[0].name != 'boxes' or outputs[1].name != 'scores'
                or any(output.type != 'tensor(float)' for output in outputs)):
            raise ValueError('El detector necesita entrada float32 [1,3,320,320] y salidas boxes, scores.')
        self.input_name = inputs[0].name
        boxes, scores = self.session.run(None, {self.input_name: np.zeros((1, 3, 320, 320), dtype=np.float32)})
        if (boxes.ndim != 3 or boxes.shape[0] != 1 or boxes.shape[2] != 4
                or scores.shape != (*boxes.shape[:2], len(self.manifest['classes']))):
            raise ValueError('Salidas incompatibles: boxes [1,N,4], scores [1,N,C].')
        decode_detections(boxes[0], scores[0], 320, 320, classes=self.manifest['classes'])

    def predict(self, source, threshold=.5):
        if not math.isfinite(threshold) or not .01 <= threshold <= 1:
            raise ValueError('El umbral debe estar entre 0,01 y 1.')
        start = time.perf_counter()
        tensor, width, height = detection_tensor(source)
        ready = time.perf_counter()
        boxes, scores = self.session.run(None, {self.input_name: tensor})
        detections = decode_detections(boxes[0], scores[0], width, height, threshold, self.manifest['classes'])
        end = time.perf_counter()
        return {'task': 'object_detection', 'detections': detections, 'image_width': width, 'image_height': height,
                'inference_ms': round((end-ready)*1000, 2), 'processing_ms': round((end-start)*1000, 2)}
