import copy
import hashlib
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from tests.test_objects import detector_package, object_fixture


class DesktopFeatureTests(unittest.TestCase):
    def qt(self):
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        from PySide6.QtWidgets import QApplication
        return QApplication.instance() or QApplication([])

    def wait_until(self, predicate):
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + 6
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
            time.sleep(.001)  # Permitir que Python avance también en el QThread simulado.
        self.assertTrue(predicate())

    def test_bulk_whole_image_labels_sizes_selection_idempotence_and_undo(self):
        app = self.qt()
        from PySide6.QtCore import Qt
        from aula_ia.object_desktop import ObjectWindow
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            window = ObjectWindow()
            window.project = object_fixture(folder)
            window.path = folder/'proyecto.json'
            window.project['classes'].append('Pelota')
            rows = window.project['images']
            for row in rows[:2]:
                row.update(boxes=[], box_labels=[], reviewed=False)
            Image.new('RGB', (48, 96), 'blue').save(rows[1]['path'])
            rows[1]['sha256'] = hashlib.sha256(Path(rows[1]['path']).read_bytes()).hexdigest()
            rows[1]['excluded'] = True
            original = copy.deepcopy(rows)
            window.refresh()
            window.auto_next.setChecked(True)
            for index in (0, 1):
                window.images.item(index).setCheckState(Qt.CheckState.Checked)
            with patch('aula_ia.object_desktop.QInputDialog.getItem', return_value=('Pelota', True)), \
                    patch('aula_ia.object_desktop.QMessageBox.question') as question:
                window.label_whole_images()
                question.assert_not_called()
                self.assertEqual(window.current, 0)
                self.assertEqual(window._bulk_indexes(), [0, 1])
                self.assertEqual(rows[0]['boxes'], [[0, 0, 120, 80]])
                self.assertEqual(rows[1]['boxes'], [[0, 0, 48, 96]])
                self.assertTrue(all(r['box_labels'] == ['Pelota'] and r['reviewed'] for r in rows[:2]))
                self.assertEqual(rows[2:], original[2:])
                self.assertTrue(rows[1]['excluded'])
                self.assertEqual([r['group'] for r in rows], [r['group'] for r in original])
                self.assertEqual(window.canvas.boxes, rows[0]['boxes'])
                self.assertEqual(window.class_choice.currentText(), 'Pelota')
                window.label_whole_images()
                question.assert_not_called()
                self.assertEqual(len(window.undo_boxes[0]), 1)
            window.undo()
            self.assertEqual(rows[0]['boxes'], [])
            self.assertFalse(rows[0]['reviewed'])
            self.assertEqual(rows[1]['box_labels'], ['Pelota'])
            window.close()
        app.processEvents()

    def test_whole_image_labels_cancel_read_error_and_save_failure_are_atomic(self):
        app = self.qt()
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QMessageBox
        from aula_ia.object_desktop import ObjectWindow
        with tempfile.TemporaryDirectory() as folder:
            window = ObjectWindow()
            window.project = object_fixture(folder)
            window.path = Path(folder)/'proyecto.json'
            window.refresh()
            for index in (0, 1):
                window.images.item(index).setCheckState(Qt.CheckState.Checked)
            before = copy.deepcopy(window.project)
            with patch('aula_ia.object_desktop.QInputDialog.getItem', return_value=('objeto', True)):
                with patch('aula_ia.object_desktop.QMessageBox.question', return_value=QMessageBox.StandardButton.No):
                    window.label_whole_images()
                    self.assertEqual(window.project, before)
                with patch('aula_ia.object_desktop.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes), \
                        patch.object(window, 'save', side_effect=OSError('Disco lleno')), patch.object(window, 'error') as error:
                    window.label_whole_images()
                    error.assert_called_once()
                    self.assertEqual(window.project, before)
                    self.assertEqual(window.undo_boxes, {})
                window.project['images'][1]['path'] = str(Path(folder)/'no-existe.png')
                unreadable = copy.deepcopy(window.project)
                with patch.object(window, 'error') as error:
                    window.label_whole_images()
                    error.assert_called_once()
                    self.assertEqual(window.project, unreadable)
            window.close()
        app.processEvents()

    def test_pc_camera_live_preview_settings_snapshots_and_release(self):
        app = self.qt()
        from PySide6.QtWidgets import QFileDialog
        from aula_ia.pc_camera import PCCameraDialog
        devices = []

        class Capture:
            def __init__(self):
                self.released = False
                self.properties = {}
            def isOpened(self): return True
            def set(self, key, value): self.properties[key] = value
            def read(self):
                array = np.zeros((80, 120, 3), dtype=np.uint8)
                array[:, :60] = [0, 0, 255]
                array[:, 60:] = [255, 0, 0]
                return True, array
            def release(self): self.released = True

        def capture(index):
            self.assertEqual(index, 2)
            device = Capture()
            devices.append(device)
            return device

        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder)/'modelo.zip'
            package.write_bytes(detector_package())
            dialog = PCCameraDialog(package)
            dialog.camera.setCurrentIndex(2)
            dialog.resolution.setCurrentIndex(2)
            dialog.fps.setValue(10)
            dialog.show()
            try:
                with patch('aula_ia.pc_camera.open_capture', side_effect=capture):
                    dialog.start()
                    self.wait_until(lambda: dialog.last_image is not None or dialog.status.text().startswith('Error:'))
                    self.assertIsNotNone(dialog.last_image, dialog.status.text())
                    self.assertEqual(dialog.last_image.getpixel((0, 0)), (255, 0, 0))
                    self.assertEqual(dialog.last_image.size, (120, 80))
                    self.assertIn('120 × 80', dialog.status.text())
                    self.assertIn('inferencia', dialog.stats.text())
                    self.assertFalse(dialog.start_button.isEnabled())
                    self.assertTrue(dialog.stop_button.isEnabled())
                    import cv2
                    self.assertEqual(devices[0].properties[cv2.CAP_PROP_FRAME_WIDTH], 1280)
                    self.assertEqual(devices[0].properties[cv2.CAP_PROP_FRAME_HEIGHT], 720)
                    dialog.mirror.setChecked(True)
                    self.wait_until(lambda: dialog.last_image.getpixel((0, 0)) == (0, 0, 255))
                    dialog.threshold.setValue(.99)
                    self.assertEqual(dialog.worker.threshold, .99)
                    self.wait_until(lambda: 'ninguno' in dialog.stats.text())
                    dialog.stop()
                    self.wait_until(lambda: not dialog.worker.isRunning() and dialog.start_button.isEnabled())
                    self.assertTrue(devices[0].released)
                    raw, annotated = Path(folder)/'original.png', Path(folder)/'anotada.png'
                    with patch.object(QFileDialog, 'getSaveFileName', side_effect=[(str(raw), ''), (str(annotated), '')]):
                        dialog.save_snapshot(False)
                        dialog.save_snapshot(True)
                    with Image.open(raw) as image:
                        self.assertEqual(image.size, (120, 80))
                    with Image.open(annotated) as image:
                        self.assertEqual(image.size, (120, 80))
                    dialog.start()
                    self.wait_until(lambda: len(devices) == 2)
                    dialog.reject()
                    self.wait_until(lambda: not dialog.worker.isRunning())
                    self.assertTrue(devices[1].released)
            finally:
                if dialog.worker and dialog.worker.isRunning():
                    dialog.worker.stop.set()
                    dialog.worker.wait(5000)
                app.processEvents()
                dialog.close()

    def test_pc_camera_scan_and_read_failure_release_devices(self):
        app = self.qt()
        from aula_ia.pc_camera import PCCameraDialog
        devices = []
        class Capture:
            def __init__(self, index):
                self.index, self.released = index, False
            def isOpened(self): return self.index in (1, 3)
            def set(self, *args): pass
            def read(self): return False, None
            def release(self): self.released = True
        def capture(index):
            device = Capture(index)
            devices.append(device)
            return device
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder)/'modelo.zip'
            package.write_bytes(detector_package())
            dialog = PCCameraDialog(package)
            try:
                with patch('aula_ia.pc_camera.open_capture', side_effect=capture):
                    dialog.scan()
                    self.wait_until(lambda: not dialog.worker.isRunning() and dialog.start_button.isEnabled())
                    self.assertEqual([dialog.camera.itemData(i) for i in range(dialog.camera.count())], [1, 3])
                    self.assertTrue(all(d.released for d in devices))
                    dialog.start()
                    self.wait_until(lambda: not dialog.worker.isRunning() and dialog.start_button.isEnabled())
                    self.assertIn('dejó de entregar', dialog.status.text())
                    self.assertTrue(devices[-1].released)
            finally:
                if dialog.worker and dialog.worker.isRunning():
                    dialog.worker.stop.set()
                    dialog.worker.wait(5000)
                app.processEvents()
                dialog.close()


if __name__ == '__main__':
    unittest.main()
