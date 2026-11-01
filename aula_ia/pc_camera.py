"""Prueba de cámara del PC: captura e inferencia fuera del hilo de la ventana."""
from collections import Counter
from pathlib import Path
import sys
import threading
import time

from PIL import Image, ImageOps
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout,
)

from aula_ia.camera import annotated_image
from aula_ia.inference import Predictor


def open_capture(index):
    import cv2
    return cv2.VideoCapture(index, cv2.CAP_DSHOW) if sys.platform == 'win32' else cv2.VideoCapture(index)


class CameraScan(QThread):
    found = Signal(object)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stop = threading.Event()

    def run(self):
        available = []
        try:
            for index in range(10):
                if self.stop.is_set():
                    return
                device = open_capture(index)
                try:
                    if device.isOpened():
                        available.append(index)
                finally:
                    device.release()
            self.found.emit(available)
        except Exception as error:
            self.failed.emit(str(error))


class CameraStream(QThread):
    frame_ready = Signal(object)
    status = Signal(str)
    failed = Signal(str)

    def __init__(self, package, index, resolution, fps, threshold, mirror, parent=None):
        super().__init__(parent)
        self.package, self.index = Path(package), index
        self.resolution, self.fps = resolution, fps
        self.threshold, self.mirror = threshold, mirror
        self.stop = threading.Event()
        self.acknowledged = threading.Event()

    def run(self):
        device = None
        try:
            self.status.emit('Cargando las herramientas de cámara y el modelo…')
            import cv2
            self.status.emit('Cargando el modelo…')
            predictor = Predictor(self.package.read_bytes())
            if self.stop.is_set():
                return
            self.status.emit(f'Abriendo cámara {self.index}…')
            device = open_capture(self.index)
            if not device.isOpened():
                raise ValueError('No se pudo abrir la cámara. Revisa el índice, la conexión y los permisos '
                                 'de cámara para aplicaciones de escritorio en Windows. Cierra otras aplicaciones que la usen.')
            width, height = self.resolution
            device.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            device.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            device.set(cv2.CAP_PROP_FPS, self.fps)
            device.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            previous, count = None, 0
            while not self.stop.is_set():
                start = time.perf_counter()
                ok, array = device.read()
                if not ok or array is None:
                    raise ValueError('La cámara dejó de entregar imágenes. Comprueba su conexión y vuelve a iniciar.')
                image = Image.fromarray(cv2.cvtColor(array, cv2.COLOR_BGR2RGB))
                if self.mirror:
                    image = ImageOps.mirror(image)
                result = predictor.predict(image, self.threshold)
                if self.stop.is_set():
                    break
                now = time.perf_counter()
                count += 1
                result.update(image=image, frame=count, fps=1/(now-previous) if previous else 0.)
                previous = now
                self.acknowledged.clear()
                self.frame_ready.emit(result)
                # Como máximo un fotograma pendiente en la interfaz; no acumular vídeo viejo.
                while not self.acknowledged.wait(.05):
                    if self.stop.is_set():
                        break
                self.stop.wait(max(0., 1/self.fps - (time.perf_counter()-start)))
        except Exception as error:
            if not self.stop.is_set():
                self.failed.emit(str(error))
        finally:
            if device is not None:
                device.release()


class CameraPreview(QLabel):
    def __init__(self):
        super().__init__('Pulsa «Iniciar cámara» para ver las detecciones.')
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 240)
        self._frame = None

    def set_frame(self, image):
        image = image.convert('RGB')
        data = QImage(image.tobytes(), image.width, image.height, image.width*3,
                      QImage.Format.Format_RGB888).copy()
        self._frame = QPixmap.fromImage(data)
        self._render()

    def _render(self):
        if self._frame is not None:
            self.setPixmap(self._frame.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()


class PCCameraDialog(QDialog):
    def __init__(self, package, threshold=.5, parent=None):
        super().__init__(parent)
        self.package = Path(package)
        self.worker = None
        self._closing = False
        self.last_image = self.last_annotated = None
        self.setWindowTitle(f'Cámara del PC · {self.package.name}')
        self.resize(1050, 720)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        cameras = QHBoxLayout()
        self.camera = QComboBox()
        for index in range(10):
            self.camera.addItem(f'Cámara {index}', index)
        self.scan_button = QPushButton('Buscar cámaras')
        self.scan_button.clicked.connect(self.scan)
        cameras.addWidget(self.camera)
        cameras.addWidget(self.scan_button)
        form.addRow('Cámara:', cameras)
        self.resolution = QComboBox()
        for width, height in ((320, 240), (640, 480), (1280, 720), (1920, 1080)):
            self.resolution.addItem(f'{width} × {height}', (width, height))
        self.resolution.setCurrentIndex(1)
        self.resolution.setToolTip('Empieza con 640 × 480. La cámara puede ajustar la resolución solicitada. '
                                   'El detector reduce la imagen a 320 × 320; subir la captura no cambia ese tamaño.')
        form.addRow('Resolución solicitada:', self.resolution)
        self.fps = QSpinBox()
        self.fps.setRange(1, 15)
        self.fps.setValue(5)
        self.fps.setSuffix(' FPS')
        self.fps.setToolTip('Límite de fotogramas procesados por segundo. La velocidad real depende del PC y del modelo.')
        form.addRow('Límite de velocidad:', self.fps)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(.01, 1.)
        self.threshold.setSingleStep(.05)
        self.threshold.setValue(threshold)
        self.threshold.valueChanged.connect(self._threshold_changed)
        form.addRow('Confianza mínima:', self.threshold)
        self.mirror = QCheckBox('Vista en espejo')
        self.mirror.toggled.connect(self._mirror_changed)
        form.addRow('', self.mirror)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.start_button = QPushButton('Iniciar cámara')
        self.start_button.clicked.connect(self.start)
        self.stop_button = QPushButton('Detener')
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setEnabled(False)
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        layout.addLayout(actions)
        self.status = QLabel('Cámara detenida. Elige la cámara y pulsa Iniciar.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.preview = CameraPreview()
        layout.addWidget(self.preview, 1)
        self.stats = QLabel('Sin fotogramas.')
        self.stats.setWordWrap(True)
        layout.addWidget(self.stats)
        snapshots = QHBoxLayout()
        self.save_raw = QPushButton('Guardar foto original…')
        self.save_annotated = QPushButton('Guardar foto con detecciones…')
        self.save_raw.clicked.connect(lambda: self.save_snapshot(False))
        self.save_annotated.clicked.connect(lambda: self.save_snapshot(True))
        self.save_raw.setEnabled(False)
        self.save_annotated.setEnabled(False)
        snapshots.addWidget(self.save_raw)
        snapshots.addWidget(self.save_annotated)
        close = QPushButton('Cerrar')
        close.clicked.connect(self.reject)
        snapshots.addWidget(close)
        layout.addLayout(snapshots)

    def _busy(self, value):
        for widget in (self.camera, self.resolution, self.fps, self.scan_button, self.start_button):
            widget.setEnabled(not value)
        self.stop_button.setEnabled(value)

    def scan(self):
        if self.worker and self.worker.isRunning():
            return
        self.status.setText('Buscando cámaras 0–9… Puede tardar unos segundos.')
        self.worker = CameraScan(self)
        self.worker.found.connect(self._found)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._finished)
        self._busy(True)
        self.worker.start()

    def _found(self, indexes):
        if indexes:
            selected = self.camera.currentData()
            self.camera.clear()
            for index in indexes:
                self.camera.addItem(f'Cámara {index}', index)
            position = self.camera.findData(selected)
            self.camera.setCurrentIndex(max(0, position))
            self.status.setText(f'{len(indexes)} cámaras disponibles. Selecciona una e inicia la prueba.')
        else:
            self.status.setText('No se encontraron cámaras disponibles. Comprueba la conexión y los permisos de Windows.')

    def start(self):
        if self.worker and self.worker.isRunning():
            return
        self.worker = CameraStream(self.package, self.camera.currentData(), self.resolution.currentData(),
                                   self.fps.value(), self.threshold.value(), self.mirror.isChecked(), self)
        self.worker.status.connect(self.status.setText)
        self.worker.failed.connect(self._failed)
        self.worker.frame_ready.connect(self._frame)
        self.worker.finished.connect(self._finished)
        self._busy(True)
        self.status.setText('Iniciando la prueba en vivo…')
        self.worker.start()

    def _frame(self, result):
        try:
            self.last_image = result['image']
            self.last_annotated = annotated_image(self.last_image, result['detections'])
            self.preview.set_frame(self.last_annotated)
            counts = Counter(item['label'] for item in result['detections'])
            labels = ', '.join(f'{label}: {count}' for label, count in counts.items()) or 'ninguno'
            width, height = self.last_image.size
            self.status.setText(f'Cámara en vivo · resolución real {width} × {height}')
            self.stats.setText(f"Fotograma {result['frame']} · {result['fps']:.1f} FPS · "
                               f"inferencia {result['inference_ms']} ms\nObjetos en este fotograma: {labels}")
            self.save_raw.setEnabled(True)
            self.save_annotated.setEnabled(True)
        except Exception as error:
            self._failed(str(error))
            self.stop()
        finally:
            self.worker.acknowledged.set()

    def _threshold_changed(self, value):
        if isinstance(self.worker, CameraStream):
            self.worker.threshold = value

    def _mirror_changed(self, value):
        if isinstance(self.worker, CameraStream):
            self.worker.mirror = value

    def _failed(self, text):
        self.status.setText(f'Error: {text}')

    def stop(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop.set()
            self.stop_button.setEnabled(False)
            self.status.setText('Deteniendo… Se libera la cámara al terminar la operación actual.')

    def _finished(self):
        self._busy(False)
        if self.worker.stop.is_set():
            self.status.setText('Cámara detenida. Puedes guardar la última imagen o volver a iniciar.')
        if self._closing:
            self.accept()

    def save_snapshot(self, annotated):
        image = self.last_annotated if annotated else self.last_image
        if image is None:
            return
        image = image.copy()
        path, _ = QFileDialog.getSaveFileName(self, 'Guardar fotograma',
                                             'detecciones.png' if annotated else 'captura.png',
                                             'PNG (*.png);;JPEG (*.jpg)')
        if path:
            try:
                image.save(path)
            except Exception as error:
                self.status.setText(f'No se pudo guardar la foto: {error}')

    def reject(self):
        if self.worker and self.worker.isRunning():
            self._closing = True
            self.stop()
        else:
            super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self._closing = True
            self.stop()
            event.ignore()
        else:
            event.accept()
