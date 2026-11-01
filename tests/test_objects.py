import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
from PIL import Image

from aula_ia.project import detection_split, import_cvat, rotated_bounds
from aula_ia.inference import DETECTION_PREPROCESS, Predictor, decode_detections
from aula_ia.project import save_project
from aula_ia.web import create_app


def detector_package(multiclass=False):
    import onnx
    from onnx import TensorProto, helper, numpy_helper
    boxes = np.array([[[0, 0, 100, 100], [1, 1, 101, 101], [200, 200, 300, 300]]], dtype=np.float32)
    scores = np.array([[[.9], [.8], [.7]]], dtype=np.float32)
    if multiclass:
        scores = np.array([[[.9, .1], [.1, .95], [.01, .01]]], dtype=np.float32)
    graph = helper.make_graph([
        helper.make_node('Identity', ['box_values'], ['boxes']),
        helper.make_node('Identity', ['score_values'], ['scores'])], 'fixture',
        [helper.make_tensor_value_info('image', TensorProto.FLOAT, [1, 3, 320, 320])],
        [helper.make_tensor_value_info('boxes', TensorProto.FLOAT, [1, 3, 4]),
         helper.make_tensor_value_info('scores', TensorProto.FLOAT, list(scores.shape))],
        [numpy_helper.from_array(boxes, 'box_values'), numpy_helper.from_array(scores, 'score_values')])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 17)], ir_version=9)
    manifest = {'format_version': 1, 'name': 'Detector de prueba', 'classes': ['Objeto'],
                'task': 'object_detection', 'preprocess': DETECTION_PREPROCESS, 'output': 'ssd_boxes_scores'}
    if multiclass:
        manifest.update(task='object_detection', classes=['Pelota', 'Célula'])
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        archive.writestr('model.onnx', model.SerializeToString())
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('metrics.json', '{}')
    return data.getvalue()


def object_fixture(folder):
    folder = Path(folder)
    xml = ['<annotations>']
    for index in range(9):
        Image.new('RGB', (120, 80), (index*20, 100, 150)).save(folder/f'{index}.png')
        xml.append(f'<image id="{index}" name="{index}.png" width="120" height="80">'
                   '<box label="objeto" xtl="20" ytl="15" xbr="70" ybr="65" rotation="0"/></image>')
    xml.append('</annotations>')
    (folder/'annotations.xml').write_text(''.join(xml), encoding='utf-8')
    return import_cvat(folder/'annotations.xml')


class FakeCamera:
    def __init__(self):
        self.open = False
    def start(self):
        self.open = True
        return {'active': True, 'kind': 'simulada'}
    def frame(self):
        if not self.open:
            raise ValueError('Cámara detenida')
        return Image.new('RGB', (640, 480), 'red')
    def close(self):
        self.open = False


class ObjectTests(unittest.TestCase):
    def test_partition_choice_follows_new_images_without_overwriting_assignments(self):
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        from PySide6.QtWidgets import QApplication
        from aula_ia.object_desktop import ObjectWindow
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            window = ObjectWindow()
            window.project = object_fixture(folder)
            window.path = folder/'proyecto.json'
            rows = window.project['images']
            rows[3]['group'] = 'test-reservado'
            window.refresh()
            window.partition_combo.setCurrentIndex(1)
            window.move(1)
            self.assertEqual(window.partition_combo.currentIndex(), 1)
            self.assertTrue(rows[1]['group'].startswith('train-'))
            window.auto_next.setChecked(True)
            window.update_boxes({'boxes': [[20, 15, 70, 65]], 'box_labels': ['objeto'], 'added': True})
            self.assertEqual(window.current, 2)
            self.assertEqual(window.partition_combo.currentIndex(), 1)
            window.partition_combo.setCurrentIndex(2)
            window.move(1)
            self.assertEqual(window.partition_combo.currentIndex(), 3)
            self.assertEqual(rows[3]['group'], 'test-reservado')
            window.move(1)
            self.assertEqual(window.partition_combo.currentIndex(), 2)
            self.assertTrue(rows[4]['group'].startswith('val-'))
            window.partition_combo.setCurrentIndex(0)
            automatic_group = rows[4]['group']
            window.select(1)
            self.assertEqual(window.partition_combo.currentIndex(), 1)
            self.assertEqual(window.project['preferred_partition'], 0)
            window.partition_combo.setCurrentIndex(2)
            window.select(4)
            self.assertEqual(window.partition_combo.currentIndex(), 0)
            self.assertEqual(rows[4]['group'], automatic_group)
            window.load_path(window.path)
            window.select(5)
            self.assertEqual(window.partition_combo.currentIndex(), 2)
            self.assertTrue(window.project['images'][5]['group'].startswith('val-'))
            unvisited = window.project['images'][6]['group']
            new_photo = folder/'nueva.png'
            Image.new('RGB', (80, 80), 'yellow').save(new_photo)
            window.import_photos([str(new_photo)])
            self.assertEqual(window.partition_combo.currentIndex(), 2)
            self.assertTrue(window.project['images'][-1]['group'].startswith('val-'))
            self.assertEqual(window.project['images'][6]['group'], unvisited)
            saved = json.loads(window.path.read_text(encoding='utf-8'))
            self.assertEqual(saved['preferred_partition'], 2)
            self.assertTrue(saved['images'][-1]['partition_assigned'])
            window.close()
        app.processEvents()

    def test_training_stays_responsive_during_loading_and_reports_outcome(self):
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        import builtins
        import threading
        import time
        from types import SimpleNamespace
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from aula_ia.object_desktop import ObjectWindow
        app = QApplication.instance() or QApplication([])
        original_import = builtins.__import__
        gui_thread = threading.get_ident()

        def wait_until(predicate):
            deadline = time.monotonic() + 5
            while not predicate() and time.monotonic() < deadline:
                QTest.qWait(10)
            self.assertTrue(predicate())

        with tempfile.TemporaryDirectory() as folder:
            for outcome in ('Completado', 'Error', 'Cancelado'):
                with self.subTest(outcome=outcome):
                    loading, release = threading.Event(), threading.Event()
                    window = ObjectWindow()
                    window.project = object_fixture(folder)
                    window.path = Path(folder)/'proyecto.json'
                    window.show()

                    def train(project, output, epochs, rate, report, stop):
                        self.assertNotEqual(threading.get_ident(), gui_thread)
                        if outcome == 'Error':
                            raise RuntimeError('Fallo de entrenamiento simulado')
                        report(f'Época 1/{epochs} · lote 1/2 · 4/8 imágenes procesadas')
                        return Path(folder)/'detector.zip', {}

                    def slow_import(name, *args, **kwargs):
                        if name == 'aula_ia.object_training':
                            self.assertNotEqual(threading.get_ident(), gui_thread)
                            loading.set()
                            if not release.wait(5):
                                raise RuntimeError('Tiempo de prueba agotado')
                            return SimpleNamespace(train_objects=train)
                        return original_import(name, *args, **kwargs)

                    try:
                        with patch('builtins.__import__', side_effect=slow_import), patch.object(window, 'error') as error:
                            window.start_train()
                            wait_until(loading.is_set)
                            self.assertEqual(window.train_progress.maximum(), 0)
                            self.assertIn('Entrenando', window.train_button.text())
                            self.assertFalse(window.train_button.isEnabled())
                            self.assertTrue(window.cancel_button.isEnabled())
                            worker = window.worker
                            window.start_train()
                            self.assertIs(window.worker, worker)
                            QTest.qWait(1100)
                            self.assertIn('00:01', window.train_status.text())
                            self.assertIn('Cargando PyTorch', window.train_status.text())
                            if outcome == 'Cancelado':
                                window.cancel()
                                self.assertIn('Cancelación solicitada', window.train_status.text())
                            release.set()
                            wait_until(lambda: not window.worker.isRunning() and not window._activity_timer.isActive())
                            self.assertIn(outcome, window.train_status.text())
                            self.assertEqual(window.train_progress.format(), outcome)
                            self.assertTrue(window.train_button.isEnabled())
                            self.assertFalse(window.cancel_button.isEnabled())
                            self.assertEqual(error.call_count, int(outcome == 'Error'))
                    finally:
                        release.set()
                        if window.worker:
                            window.worker.wait(6000)
                        app.processEvents()
                        window.close()

    def test_empty_canvas_click_selects_photos_and_drop_imports_one_file(self):
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt, QPoint, QPointF, QMimeData, QUrl
        from PySide6.QtGui import QDragEnterEvent, QDropEvent
        from aula_ia.object_desktop import ObjectWindow
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            first, second = folder/'primera.png', folder/'segunda.png'
            Image.new('RGB', (100, 80), 'red').save(first)
            Image.new('RGB', (100, 80), 'blue').save(second)
            project_path = folder/'proyecto.json'
            window = ObjectWindow()
            window.show()
            app.processEvents()
            with patch('aula_ia.object_desktop.QFileDialog.getOpenFileNames', return_value=([str(first)], '')) as picker, \
                    patch('aula_ia.object_desktop.QFileDialog.getSaveFileName', return_value=(str(project_path), '')):
                QTest.mouseClick(window.canvas, Qt.MouseButton.LeftButton, pos=window.canvas.rect().center())
                picker.assert_called_once()
            self.assertEqual(len(window.project['images']), 1)
            self.assertEqual(window.project['images'][window.current]['path'], str(first.resolve()))
            self.assertIsNotNone(window.canvas.pixmap)
            self.assertEqual(window.project['classes'], [])
            window.project['classes'] = ['Objeto']
            row = window.project['images'][0]
            row.update(boxes=[[10, 10, 40, 40]], box_labels=['Objeto'], reviewed=True)
            window.save()
            window.import_photos([str(first)])
            self.assertEqual(len(window.project['images']), 1)
            self.assertEqual(window.project['images'][0]['boxes'], [[10, 10, 40, 40]])
            window.partition_tabs.setCurrentIndex(1)
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(second))])
            enter = QDragEnterEvent(QPoint(20, 20), Qt.DropAction.CopyAction, mime,
                                   Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            app.sendEvent(window.canvas, enter)
            self.assertTrue(enter.isAccepted())
            drop = QDropEvent(QPointF(20, 20), Qt.DropAction.CopyAction, mime,
                             Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            app.sendEvent(window.canvas, drop)
            self.assertTrue(drop.isAccepted())
            self.assertEqual(len(window.project['images']), 2)
            self.assertEqual(window.project['images'][window.current]['path'], str(second.resolve()))
            self.assertTrue(window.project['images'][window.current]['group'].startswith('train-'))
            saved = json.loads(project_path.read_text(encoding='utf-8'))
            self.assertEqual(len(saved['images']), 2)
            window.import_photos([str(first)])
            self.assertEqual(window.partition_tabs.currentIndex(), 0)
            self.assertEqual(window.project['images'][window.current]['path'], str(first.resolve()))
            window.close()
        app.processEvents()

    def test_new_project_has_no_labels_and_can_reopen(self):
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        from PySide6.QtWidgets import QApplication
        from aula_ia.object_desktop import ObjectWindow
        from aula_ia.project import load_project
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'vacio.json'
            window = ObjectWindow()
            with patch('aula_ia.object_desktop.QFileDialog.getSaveFileName', return_value=(str(path), '')):
                window.new_project()
            self.assertEqual(window.project['classes'], [])
            self.assertEqual(window.class_choice.count(), 0)
            self.assertEqual(window.canvas.current_label, '')
            self.assertEqual(load_project(path)['classes'], [])
            with self.assertRaisesRegex(ValueError, 'Añade al menos una etiqueta'):
                detection_split(window.project)
            with patch('aula_ia.object_desktop.QInputDialog.getText', return_value=('Tornillo', True)):
                window.add_class()
            self.assertEqual(window.project['classes'], ['Tornillo'])
            self.assertEqual(window.canvas.current_label, 'Tornillo')
            self.assertEqual(load_project(path)['classes'], ['Tornillo'])
            window.close()
        app.processEvents()

    def test_cvat_rotation_split_and_path_escape(self):
        box = rotated_bounds({'xtl': '30', 'ytl': '30', 'xbr': '70', 'ybr': '50', 'rotation': '90'}, 100, 100)
        np.testing.assert_allclose(box, [40, 20, 60, 60])
        with tempfile.TemporaryDirectory() as folder:
            project = object_fixture(folder)
            self.assertEqual(len(project['images']), 9)
            self.assertEqual(project['images'][0]['boxes'], [[20, 15, 70, 65]])
            parts = detection_split(project)
            sets = [{row['group'] for row in rows} for rows in parts.values()]
            self.assertFalse(sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
            xml = Path(folder)/'annotations.xml'
            xml.write_text('<annotations><image name="../fuera.jpg" width="100" height="100"><box label="objeto"/></image></annotations>')
            with self.assertRaisesRegex(ValueError, 'sale de la carpeta'):
                import_cvat(xml)

    def test_nms_scaling_and_precision_recall(self):
        result = Predictor(detector_package()).predict(Image.new('RGB', (640, 480)), .5)
        self.assertEqual(len(result['detections']), 2)
        np.testing.assert_allclose(result['detections'][0]['box'], [0, 0, 200, 150])
        result = Predictor(detector_package()).predict(Image.new('RGB', (320, 320)), .99)
        self.assertEqual(result['detections'], [])
        from aula_ia.object_training import detection_metrics
        metrics = detection_metrics([([{'box': [0, 0, 10, 10], 'score': .9, 'label': 'Objeto'},
                                       {'box': [0, 0, 10, 10], 'score': .8, 'label': 'Objeto'}],
                                       [{'box': [0, 0, 10, 10], 'label': 'Objeto'}])], classes=['Objeto'])
        self.assertEqual(metrics['ap50'], 1)
        self.assertEqual(metrics['precision'], .5)
        self.assertEqual(metrics['recall'], 1)
        self.assertEqual(metrics['false_positives'], 1)

    def test_multiclass_labels_nms_and_wrong_class_metrics(self):
        result = Predictor(detector_package(multiclass=True)).predict(Image.new('RGB', (320, 320)), .5)
        self.assertEqual({item['label'] for item in result['detections']}, {'Pelota', 'Célula'})
        # Cajas casi idénticas de clases diferentes no se suprimen entre sí.
        self.assertEqual(len(result['detections']), 2)
        from aula_ia.object_training import detection_metrics
        metrics = detection_metrics([([{'box': [0, 0, 10, 10], 'score': .9, 'label': 'Célula'}],
                                      [{'box': [0, 0, 10, 10], 'label': 'Pelota'}])], classes=['Pelota', 'Célula'])
        self.assertEqual(metrics['true_positives'], 0)
        self.assertEqual(metrics['false_positives'], 1)
        self.assertEqual(metrics['false_negatives'], 1)

    def test_camera_and_annotated_upload_api_with_fake_camera(self):
        from fastapi.testclient import TestClient
        camera = FakeCamera()
        headers = {'X-Aula-Token': 'prueba-objetos-123456'}
        with tempfile.TemporaryDirectory() as folder:
            with TestClient(create_app(folder, headers['X-Aula-Token'], camera)) as client:
                self.assertEqual(client.post('/api/camera/start', headers=headers).status_code, 409)
                self.assertEqual(client.post('/api/camera/start').status_code, 401)
                response = client.post('/api/model', headers=headers, files={'file': ('detector.zip', detector_package(multiclass=True))})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(client.post('/api/camera/start', headers=headers).status_code, 200)
                response = client.post('/api/camera/frame', headers=headers)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.headers['content-type'], 'image/jpeg')
                self.assertEqual(response.headers['X-Object-Count'], '2')
                self.assertEqual(json.loads(response.headers['X-Object-Counts']), {'0': 1, '1': 1})
                self.assertEqual(response.headers['X-Frame-Width'], '640')
                self.assertEqual(response.headers['X-Frame-Height'], '480')
                self.assertGreaterEqual(float(response.headers['X-Frame-Ms']), 0)
                self.assertEqual(response.headers['X-Model-Id'], client.get('/api/status').json()['model_id'])
                with Image.open(io.BytesIO(response.content)) as image:
                    self.assertEqual(image.size, (640, 480))
                buffer = io.BytesIO()
                Image.new('RGB', (320, 320)).save(buffer, format='PNG')
                response = client.post('/api/predict', headers=headers, files={'file': ('image.png', buffer.getvalue())})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(len(response.json()['detections']), 2)
                self.assertEqual(response.json()['task'], 'object_detection')
                self.assertEqual({r['label'] for r in response.json()['detections']}, {'Pelota', 'Célula'})
                self.assertIn('annotated_image', response.json())
                client.post('/api/camera/stop', headers=headers)
                self.assertFalse(camera.open)
                self.assertEqual(client.post('/api/camera/frame', headers=headers).status_code, 400)
            self.assertFalse(camera.open)

    def test_rejected_upload_preserves_model_and_restart(self):
        from fastapi.testclient import TestClient
        token = 'prueba-api-objetos-123456'
        headers = {'X-Aula-Token': token}
        with tempfile.TemporaryDirectory() as folder:
            with TestClient(create_app(folder, token, FakeCamera())) as client:
                package = detector_package(multiclass=True)
                self.assertEqual(client.post('/api/model', files={'file': ('model.zip', package)}).status_code, 401)
                self.assertEqual(client.post('/api/model', headers=headers, files={'file': ('model.zip', package)}).status_code, 200)
                self.assertEqual(client.post('/api/model', headers=headers, files={'file': ('bad.zip', b'bad')}).status_code, 400)
                self.assertTrue(client.get('/api/status').json()['ready'])
                self.assertEqual(client.post('/api/predict', headers=headers, files={'file': ('bad.png', b'bad')}).status_code, 400)
                self.assertEqual(client.post('/api/predict', headers=headers,
                    files={'file': ('large.png', b'x'*(11*1024*1024))}).status_code, 413)
            with TestClient(create_app(folder, token, FakeCamera())) as restarted:
                self.assertTrue(restarted.get('/api/status').json()['ready'])

    def test_usb_backend_colors_and_release_without_hardware(self):
        from aula_ia.camera import Camera
        class Device:
            released = False
            def isOpened(self): return True
            def set(self, *args): pass
            def read(self): return True, np.array([[[0, 0, 255]]], dtype=np.uint8)
            def release(self): self.released = True
        device = Device()
        with patch.dict(os.environ, {'AULA_CAMERA': 'usb'}), patch('cv2.VideoCapture', return_value=device):
            camera = Camera()
            try:
                camera.start()
                self.assertEqual(camera.frame().getpixel((0, 0)), (255, 0, 0))
            finally:
                camera.close()
            self.assertTrue(device.released)

    def test_training_export_with_no_download(self):
        from aula_ia.object_training import train_objects
        with tempfile.TemporaryDirectory() as folder:
            project = object_fixture(folder)
            package, metrics = train_objects(project, Path(folder)/'results', epochs=1, pretrained=False)
            self.assertEqual(len(metrics['history']), 1)
            self.assertEqual(metrics['test_detection']['objects'], metrics['split_counts']['test'])
            self.assertEqual(Predictor(Path(package).read_bytes()).manifest['task'], 'object_detection')
            self.assertLess(metrics['export_max_error']['score'], .001)

    def test_multiclass_training_export(self):
        from aula_ia.object_training import train_objects
        with tempfile.TemporaryDirectory() as folder:
            project = object_fixture(folder)
            project['classes'] = ['Pelota', 'Célula']
            for row in project['images']:
                row['boxes'].append([75, 10, 110, 50])
                row['box_labels'] = ['Pelota', 'Célula']
            package, metrics = train_objects(project, Path(folder)/'results', epochs=1, pretrained=False)
            predictor = Predictor(Path(package).read_bytes())
            self.assertEqual(predictor.manifest['classes'], ['Pelota', 'Célula'])
            self.assertEqual(predictor.session.get_outputs()[1].shape, [1, 3234, 2])
            self.assertEqual(set(metrics['test_detection']['per_class']), {'Pelota', 'Célula'})

    def test_reviewed_negative_image_produces_background_gradient(self):
        import torch
        from aula_ia.object_training import build_detector
        model = build_detector(False, class_count=2)
        model.train()
        for module in model.modules():
            if isinstance(module, torch.nn.BatchNorm2d):
                module.eval()
        losses = model([torch.zeros(3, 320, 320)],
                       [{'boxes': torch.zeros(0, 4), 'labels': torch.zeros(0, dtype=torch.long)}])
        self.assertGreater(float(losses['classification'].detach()), 0)
        sum(losses.values()).backward()
        self.assertTrue(any(p.grad is not None and bool(p.grad.abs().sum() > 0)
                            for p in model.head.classification_head.parameters()))

    def test_qt_draw_save_undo_and_empty_image(self):
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QFontDatabase
        from aula_ia.object_desktop import ObjectWindow
        app = QApplication.instance() or QApplication([])
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'project.json'
            save_project(path, object_fixture(folder))
            window = ObjectWindow()
            window.load_path(path)
            window.show()
            app.processEvents()
            self.assertFalse(window.grab().isNull())
            rect = window.canvas.display_rect()
            start = QPoint(int(rect.x()+rect.width()*.1), int(rect.y()+rect.height()*.1))
            end = QPoint(int(rect.x()+rect.width()*.4), int(rect.y()+rect.height()*.4))
            QTest.mousePress(window.canvas, Qt.MouseButton.LeftButton, pos=start)
            QTest.mouseMove(window.canvas, end)
            QTest.mouseRelease(window.canvas, Qt.MouseButton.LeftButton, pos=end)
            saved = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(len(saved['images'][0]['boxes']), 2)
            window.project['classes'].append('Pelota')
            window.class_choice.addItem('Pelota')
            window.class_choice.setCurrentText('Pelota')
            window.canvas.relabel_selected()
            saved = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(saved['images'][0]['box_labels'][1], 'Pelota')
            window.undo()
            self.assertEqual(window.project['images'][0]['box_labels'][1], 'objeto')
            window.undo()
            self.assertEqual(len(window.project['images'][0]['boxes']), 1)
            window.mark_empty()
            saved = json.loads(path.read_text(encoding='utf-8'))
            self.assertTrue(saved['images'][0]['reviewed'])
            self.assertEqual(saved['images'][0]['boxes'], [])
            self.assertFalse(window.auto_next.isChecked())
            window.auto_next.setChecked(True)
            QTest.mousePress(window.canvas, Qt.MouseButton.LeftButton, pos=start)
            QTest.mouseMove(window.canvas, end)
            QTest.mouseRelease(window.canvas, Qt.MouseButton.LeftButton, pos=end)
            self.assertEqual(window.current, 1)
            saved = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(len(saved['images'][0]['boxes']), 1)
            window.canvas.selected = 0
            window.canvas.relabel_selected()
            self.assertEqual(window.current, 1)
            window.canvas.delete_selected()
            self.assertEqual(window.current, 1)
            with patch('aula_ia.object_desktop.save_project', side_effect=OSError('Disco lleno')), patch.object(window, 'error') as error:
                QTest.mousePress(window.canvas, Qt.MouseButton.LeftButton, pos=start)
                QTest.mouseMove(window.canvas, end)
                QTest.mouseRelease(window.canvas, Qt.MouseButton.LeftButton, pos=end)
                self.assertEqual(window.current, 1)
                error.assert_called_once()
            window.images.setCurrentRow(len(window.project['images'])-1)
            QTest.mousePress(window.canvas, Qt.MouseButton.LeftButton, pos=start)
            QTest.mouseMove(window.canvas, end)
            QTest.mouseRelease(window.canvas, Qt.MouseButton.LeftButton, pos=end)
            self.assertEqual(window.current, len(window.project['images'])-1)
            window.close()
        app.processEvents()


if __name__ == '__main__':
    unittest.main()
