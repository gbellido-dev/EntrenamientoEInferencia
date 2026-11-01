"""Editor, entrenamiento y prueba de detección de objetos con etiquetas propias."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys

from PIL import Image
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox,
    QPushButton, QSpinBox, QSplitter, QTabWidget, QTextBrowser, QTextEdit, QVBoxLayout, QWidget, QComboBox)

from aula_ia.workers import Worker
from aula_ia.project import detection_split, import_cvat, validate_project
from aula_ia.inference import Predictor
from aula_ia.project import EXTENSIONS, save_project


class BoxCanvas(QWidget):
    changed = Signal(object)

    def __init__(self, editable=True):
        super().__init__()
        self.editable = editable
        self.pixmap = None
        self.boxes = []
        self.box_labels = []
        self.current_label = ''
        self.original_size = (1, 1)
        self.start = None
        self.end = None
        self.selected = -1
        self.setMinimumSize(360, 270)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_image(self, path, boxes, labels=None):
        with Image.open(path) as image:
            self.original_size = image.size
            image = image.convert('RGB')
            image.thumbnail((1400, 1000))
            qimage = QImage(image.tobytes(), image.width, image.height, image.width*3, QImage.Format.Format_RGB888).copy()
        self.pixmap = QPixmap.fromImage(qimage)
        self.boxes = copy.deepcopy(boxes)
        self.box_labels = list(labels) if labels is not None else [self.current_label]*len(boxes)
        self.selected = -1
        self.start = self.end = None
        self.update()

    def display_rect(self):
        w, h = self.original_size
        scale = min(self.width()/w, self.height()/h)
        return QRectF((self.width()-w*scale)/2, (self.height()-h*scale)/2, w*scale, h*scale)

    def image_point(self, position):
        rectangle = self.display_rect()
        w, h = self.original_size
        return [max(0., min(float(w), (position.x()-rectangle.x())*w/rectangle.width())),
                max(0., min(float(h), (position.y()-rectangle.y())*h/rectangle.height()))]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#142b25'))
        if self.pixmap is None:
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Selecciona una fotografía')
            return
        rectangle = self.display_rect()
        painter.drawPixmap(rectangle, self.pixmap, QRectF(self.pixmap.rect()))
        w, h = self.original_size
        sx, sy = rectangle.width()/w, rectangle.height()/h
        for index, box in enumerate(self.boxes):
            painter.setPen(QPen(QColor('#ffce55' if index == self.selected else '#00e895'), 2))
            painter.drawRect(QRectF(rectangle.x()+box[0]*sx, rectangle.y()+box[1]*sy,
                                     (box[2]-box[0])*sx, (box[3]-box[1])*sy))
            painter.drawText(QPointF(rectangle.x()+box[0]*sx+3, rectangle.y()+box[1]*sy+15), f'{self.box_labels[index]} {index+1}')
        if self.start is not None and self.end is not None:
            painter.setPen(QPen(QColor('#ffce55'), 2, Qt.PenStyle.DashLine))
            a, b = self.start, self.end
            painter.drawRect(QRectF(QPointF(rectangle.x()+a[0]*sx, rectangle.y()+a[1]*sy),
                                   QPointF(rectangle.x()+b[0]*sx, rectangle.y()+b[1]*sy)).normalized())

    def mousePressEvent(self, event):
        if not self.editable or not self.current_label or self.pixmap is None or event.button() != Qt.MouseButton.LeftButton:
            return
        if not self.display_rect().contains(event.position()):
            return
        self.setFocus()
        self.start = self.end = self.image_point(event.position())

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.end = self.image_point(event.position())
            self.update()

    def mouseReleaseEvent(self, event):
        if self.start is None:
            return
        a, b = self.start, self.image_point(event.position())
        box = [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]
        self.start = self.end = None
        rectangle = self.display_rect()
        if ((box[2]-box[0])*rectangle.width()/self.original_size[0] >= 5
                and (box[3]-box[1])*rectangle.height()/self.original_size[1] >= 5):
            self.boxes.append(box)
            self.box_labels.append(self.current_label)
            self.selected = len(self.boxes)-1
            self.emit_annotations()
        else:
            candidates = [(index, (item[2]-item[0])*(item[3]-item[1])) for index, item in enumerate(self.boxes)
                          if item[0] <= a[0] <= item[2] and item[1] <= a[1] <= item[3]]
            self.selected = min(candidates, key=lambda item: item[1])[0] if candidates else -1
        self.update()

    def delete_selected(self):
        if self.editable and 0 <= self.selected < len(self.boxes):
            del self.boxes[self.selected]
            del self.box_labels[self.selected]
            self.selected = -1
            self.emit_annotations()
            self.update()

    def emit_annotations(self):
        self.changed.emit({'boxes': copy.deepcopy(self.boxes), 'box_labels': self.box_labels.copy()})

    def relabel_selected(self):
        if self.editable and 0 <= self.selected < len(self.boxes):
            self.box_labels[self.selected] = self.current_label
            self.emit_annotations()
            self.update()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
        else:
            super().keyPressEvent(event)


class ObjectWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = None
        self.path = None
        self.package = None
        self.worker = None
        self.current = -1
        self.undo_boxes = {}
        self.resize(1180, 850)
        self.setWindowTitle('Aula IA · Detectar objetos')
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.build_editor()
        self.build_train()
        self.build_test()
        help_view = QTextBrowser()
        help_view.setHtml(OBJECT_HELP)
        self.tabs.addTab(help_view, '4 · Aprende detección')
        self.setStyleSheet('QWidget{font-family:Segoe UI;font-size:13px} QPushButton{padding:9px} QTabBar::tab{padding:12px}')

    def button(self, layout, title, callback):
        button = QPushButton(title)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def error(self, text):
        QMessageBox.warning(self, 'Detector de objetos', str(text))

    def build_editor(self):
        self.editor = QWidget()
        layout = QVBoxLayout(self.editor)
        intro = QLabel('Elige una clase y arrastra un rectángulo alrededor de cada objeto. Clic para seleccionar y Supr para borrar. '
                       'Se guarda automáticamente. Las fotos relacionadas deben compartir grupo.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        bar = QHBoxLayout()
        self.button(bar, 'Nuevo proyecto', self.new_project)
        self.button(bar, 'Abrir proyecto', self.open_project)
        self.button(bar, 'Importar CVAT XML', self.import_xml)
        self.button(bar, 'Añadir fotos', self.add_images)
        layout.addLayout(bar)
        self.summary = QLabel('Crea un proyecto con tus clases, abre uno existente o importa un CVAT XML.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        split = QSplitter()
        self.images = QListWidget()
        self.images.currentRowChanged.connect(self.select)
        split.addWidget(self.images)
        right = QWidget()
        detail = QVBoxLayout(right)
        self.canvas = BoxCanvas()
        self.canvas.changed.connect(self.update_boxes)
        class_bar = QHBoxLayout()
        class_bar.addWidget(QLabel('Etiqueta del rectángulo:'))
        self.class_choice = QComboBox()
        self.class_choice.setPlaceholderText('Añade tu primera etiqueta')
        self.class_choice.currentTextChanged.connect(lambda value: setattr(self.canvas, 'current_label', value))
        class_bar.addWidget(self.class_choice, 1)
        self.button(class_bar, 'Añadir etiqueta', self.add_class)
        self.button(class_bar, 'Aplicar al seleccionado', self.canvas.relabel_selected)
        detail.addLayout(class_bar)
        detail.addWidget(self.canvas, 1)
        self.filename = QLabel('')
        self.filename.setWordWrap(True)
        detail.addWidget(self.filename)
        form = QFormLayout()
        self.group = QLineEdit()
        self.group.editingFinished.connect(self.change_group)
        form.addRow('Grupo / sesión:', self.group)
        detail.addLayout(form)
        self.excluded = QCheckBox('Descartar esta imagen')
        self.excluded.toggled.connect(self.exclude)
        detail.addWidget(self.excluded)
        actions = QHBoxLayout()
        self.button(actions, 'Borrar seleccionado', self.canvas.delete_selected)
        self.button(actions, 'Deshacer rectángulos', self.undo)
        self.button(actions, 'Confirmar sin objetos', self.mark_empty)
        detail.addLayout(actions)
        nav = QHBoxLayout()
        self.button(nav, '← Anterior', lambda: self.move(-1))
        self.button(nav, 'Confirmar revisión', self.mark_reviewed)
        self.button(nav, 'Siguiente →', lambda: self.move(1))
        detail.addLayout(nav)
        split.addWidget(right)
        split.setStretchFactor(1, 3)
        layout.addWidget(split, 1)
        self.tabs.addTab(self.editor, '1 · Imágenes y etiquetas')

    def build_train(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        text = QLabel('Entrenamos las cabezas de clasificación y de rectángulos de SSDLite MobileNetV3. '
                      'El extractor y las estadísticas de normalización quedan congelados. CPU, lotes de 4. '
                      'La validación elige la mejor época por AP50; la prueba se reserva hasta el final.')
        text.setWordWrap(True)
        layout.addWidget(text)
        form = QFormLayout()
        self.epochs = QSpinBox()
        self.epochs.setRange(1, 100)
        self.epochs.setValue(15)
        form.addRow('Épocas:', self.epochs)
        self.rate = QDoubleSpinBox()
        self.rate.setDecimals(5)
        self.rate.setRange(.00001, 1.)
        self.rate.setValue(.001)
        self.rate.setSingleStep(.001)
        form.addRow('Tasa de aprendizaje:', self.rate)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.train_button = self.button(actions, 'Entrenar detector y exportar', self.start_train)
        self.cancel_button = self.button(actions, 'Cancelar', self.cancel)
        self.cancel_button.setEnabled(False)
        self.export_button = self.button(actions, 'Copiar detector para la Pi', self.export_package)
        layout.addLayout(actions)
        self.report = QTextEdit()
        self.report.setReadOnly(True)
        layout.addWidget(self.report, 1)
        self.tabs.addTab(page, '2 · Entrena y evalúa')

    def build_test(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        text = QLabel('Selecciona un paquete detector-objetos.zip y una foto nueva. El motor es el mismo que en la Pi. '
                      'Para cámara en directo utiliza la web del servidor y una cámara conectada a ese servidor.')
        text.setWordWrap(True)
        layout.addWidget(text)
        bar = QHBoxLayout()
        self.model_button = self.button(bar, 'Abrir detector ZIP', self.open_model)
        self.test_button = self.button(bar, 'Detectar en una imagen', self.test_image)
        layout.addLayout(bar)
        form = QFormLayout()
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(.01, 1)
        self.threshold.setSingleStep(.05)
        self.threshold.setValue(.5)
        form.addRow('Umbral de detección:', self.threshold)
        layout.addLayout(form)
        self.test_canvas = BoxCanvas(editable=False)
        layout.addWidget(self.test_canvas, 1)
        self.test_result = QLabel('Sin modelo seleccionado.')
        self.test_result.setWordWrap(True)
        layout.addWidget(self.test_result)
        self.tabs.addTab(page, '3 · Prueba el detector')

    def valid(self):
        return self.project is not None and 0 <= self.current < len(self.project['images'])

    def save(self):
        if self.project and self.path:
            save_project(self.path, self.project)
            self.statusBar().showMessage(f'Guardado: {self.path}')

    def new_project(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Proyecto de objetos', 'projects/objetos/proyecto.json', 'Proyecto (*.json)')
        if path:
            self.project = {'version': 1, 'task': 'object_detection', 'name': Path(path).stem, 'classes': [], 'images': []}
            self.path = Path(path)
            self.package = None
            self.save()
            self.refresh()

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Proyecto de objetos', 'projects', 'Proyecto (*.json)')
        if path:
            self.load_path(path)

    def load_path(self, path):
        try:
            project = validate_project(json.loads(Path(path).read_text(encoding='utf-8')), path)
            self.project, self.path, self.package = project, Path(path), None
            self.refresh()
        except Exception as error:
            self.error(error)

    def import_xml(self):
        source, _ = QFileDialog.getOpenFileName(self, 'CVAT XML de objetos', 'datasets', 'CVAT (*.xml)')
        if not source:
            return
        try:
            project = import_cvat(source)
            path, _ = QFileDialog.getSaveFileName(self, 'Guardar proyecto convertido', 'projects/caras/proyecto.json', 'Proyecto (*.json)')
            if path:
                save_project(path, project)
                self.project, self.path, self.package = project, Path(path), None
                self.refresh()
        except Exception as error:
            self.error(error)

    def add_images(self):
        if not self.project:
            return self.error('Crea o abre un proyecto primero.')
        folder = QFileDialog.getExistingDirectory(self, 'Carpeta de fotografías originales')
        if not folder:
            return
        group, ok = QInputDialog.getText(self, 'Grupo', 'Sesión u objeto/persona relacionado:', text='sesion-1')
        if not ok or not group.strip():
            return
        try:
            known = {row['sha256'] for row in self.project['images']}
            for path in sorted(Path(folder).rglob('*')):
                if path.is_file() and path.suffix.lower() in EXTENSIONS:
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    if digest not in known:
                        self.project['images'].append({'path': str(path.resolve()), 'sha256': digest,
                            'group': group.strip(), 'boxes': [], 'box_labels': [], 'reviewed': False, 'excluded': False})
                        known.add(digest)
            self.save()
            self.refresh()
        except Exception as error:
            self.error(error)

    def row_text(self, row):
        state = 'DESCARTADA' if row.get('excluded') else 'Revisada' if row.get('reviewed') else 'PENDIENTE'
        return f'{state} · {Path(row["path"]).name} · {len(row["boxes"])} objetos'

    def refresh(self):
        self.undo_boxes.clear()
        self.class_choice.clear()
        self.class_choice.addItems(self.project['classes'])
        if self.project['classes']:
            self.class_choice.setCurrentIndex(0)
        self.images.blockSignals(True)
        self.images.clear()
        self.images.addItems([self.row_text(row) for row in self.project['images']])
        self.images.blockSignals(False)
        self.current = -1
        self.summary.setText(f'{self.project["name"]} · {len(self.project["images"])} fotos · '
            f'{sum(len(row["boxes"]) for row in self.project["images"])} rectángulos. '
            + self.project.get('grouping_note', 'Revisa que los grupos sean independientes.'))
        self.canvas.pixmap = None
        self.canvas.update()
        self.filename.clear()
        self.group.clear()
        if self.project['images']:
            self.images.setCurrentRow(0)

    def select(self, index):
        self.current = index
        if not self.valid():
            return
        row = self.project['images'][index]
        try:
            self.canvas.set_image(row['path'], row['boxes'], row['box_labels'])
        except Exception as error:
            self.canvas.pixmap = None
            self.canvas.update()
            self.error(error)
        self.filename.setText(f'{index+1}/{len(self.project["images"])} · {row["path"]} · {len(row["boxes"])} objetos')
        self.group.setText(row['group'])
        self.excluded.blockSignals(True)
        self.excluded.setChecked(row.get('excluded', False))
        self.excluded.blockSignals(False)

    def update_row(self):
        self.images.item(self.current).setText(self.row_text(self.project['images'][self.current]))
        self.summary.setText(f'{self.project["name"]} · {len(self.project["images"])} fotos · '
            f'{sum(len(row["boxes"]) for row in self.project["images"])} rectángulos. '
            + self.project.get('grouping_note', 'Revisa que los grupos sean independientes.'))
        row = self.project['images'][self.current]
        self.filename.setText(f'{self.current+1}/{len(self.project["images"])} · {row["path"]} · {len(row["boxes"])} objetos')
        try:
            self.save()
        except Exception as error:
            self.error(error)

    def update_boxes(self, boxes):
        if self.valid():
            row = self.project['images'][self.current]
            self.undo_boxes.setdefault(self.current, []).append((copy.deepcopy(row['boxes']), row['box_labels'].copy(), row.get('reviewed', False)))
            if isinstance(boxes, dict):
                row['boxes'], row['box_labels'] = boxes['boxes'], boxes['box_labels']
            else:
                row['boxes'], row['box_labels'] = boxes, [self.canvas.current_label]*len(boxes)
            row['reviewed'] = True
            self.update_row()

    def undo(self):
        if self.valid() and self.undo_boxes.get(self.current):
            row = self.project['images'][self.current]
            row['boxes'], row['box_labels'], row['reviewed'] = self.undo_boxes[self.current].pop()
            self.update_row()
            self.select(self.current)

    def mark_empty(self):
        self.update_boxes([])
        if self.valid():
            self.select(self.current)

    def add_class(self):
        if not self.project:
            return self.error('Crea o abre un proyecto primero.')
        label, ok = QInputDialog.getText(self, 'Añadir etiqueta', 'Nombre de la nueva etiqueta:')
        label = label.strip()
        if not ok or not label:
            return
        if label in self.project['classes'] or len(label) > 80 or len(self.project['classes']) >= 100:
            return self.error('Usa un nombre nuevo de hasta 80 caracteres; máximo 100 clases.')
        self.project['classes'].append(label)
        self.project['task'] = 'object_detection'
        self.package = None
        self.class_choice.addItem(label)
        self.class_choice.setCurrentText(label)
        self.save()
        self.test_result.setText('Clases modificadas. Entrena un modelo nuevo para incluir la nueva clase.')

    def mark_reviewed(self):
        if self.valid():
            self.project['images'][self.current]['reviewed'] = True
            self.update_row()

    def change_group(self):
        if self.valid():
            row = self.project['images'][self.current]
            row['group'] = self.group.text().strip() or row['group']
            self.update_row()

    def exclude(self, value):
        if self.valid():
            self.project['images'][self.current]['excluded'] = value
            self.update_row()

    def move(self, delta):
        if self.project and self.project['images']:
            self.images.setCurrentRow(max(0, min(self.current+delta, len(self.project['images'])-1)))

    def run_worker(self, function, ready):
        if self.worker and self.worker.isRunning():
            return
        self.worker = Worker(function)
        self.worker.message.connect(self.report.append)
        self.worker.failed.connect(self.error)
        self.worker.result.connect(ready)
        self.worker.finished.connect(self.finished)
        self.editor.setEnabled(False)
        for button in (self.train_button, self.test_button, self.model_button, self.export_button):
            button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.worker.start()

    def finished(self):
        self.editor.setEnabled(True)
        for button in (self.train_button, self.test_button, self.model_button, self.export_button):
            button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def start_train(self):
        if not self.project:
            return self.error('Abre un proyecto de detección.')
        try:
            self.save()
            detection_split(self.project)
            from aula_ia.object_training import train_objects
            project = copy.deepcopy(self.project)
            output = self.path.parent/'resultados'
            epochs, rate = self.epochs.value(), self.rate.value()
            self.report.clear()
            def ready(result):
                path, metrics = result
                self.package = Path(path)
                self.show_metrics(metrics)
            self.run_worker(lambda report, stop: train_objects(project, output, epochs, rate, report, stop), ready)
        except Exception as error:
            self.error(error)

    def show_metrics(self, metrics):
        result = metrics.get('test_detection')
        if result:
            self.report.append('\nPRUEBA RESERVADA · AP50: '+f'{result["ap50"]:.1%}'
                + f' · Precisión: {result["precision"]:.1%} · Recuperación: {result["recall"]:.1%}'
                + f'\nObjetos acertados: {result["true_positives"]}; falsas alarmas: {result["false_positives"]}; '
                + f'objetos omitidos: {result["false_negatives"]}. Umbral {result["threshold"]}.'
                + '\n'+metrics.get('grouping_note', ''))
            for label, item in result.get('per_class', {}).items():
                self.report.append(f'{label}: AP50 {item["ap50"]:.1%} · precisión {item["precision"]:.1%} · recuperación {item["recall"]:.1%}')
        if self.package:
            self.report.append(f'Paquete: {self.package}')
            self.test_result.setText(f'Detector seleccionado: {self.package}')

    def cancel(self):
        if self.worker:
            self.worker.stop.set()
            self.report.append('Cancelación solicitada; espera a completar la operación actual.')

    def open_model(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Detector de objetos', 'projects', 'Modelo (*.zip)')
        if path:
            self.load_model_path(path)

    def load_model_path(self, path):
        def work(report, stop):
            predictor = Predictor(Path(path).read_bytes())
            return predictor.metrics
        def ready(metrics):
            self.package = Path(path)
            self.show_metrics(metrics)
        self.run_worker(work, ready)

    def test_image(self):
        if not self.package:
            return self.error('Abre o entrena primero un detector.')
        path, _ = QFileDialog.getOpenFileName(self, 'Fotografía de prueba', '', 'Imagen (*.jpg *.jpeg *.png *.webp *.bmp)')
        if not path:
            return
        package, threshold = self.package, self.threshold.value()
        def ready(result):
            self.test_canvas.set_image(path, [r['box'] for r in result['detections']], [r['label'] for r in result['detections']])
            self.test_result.setText(f'{len(result["detections"])} objetos · {result["inference_ms"]} ms · '
                                    + ' · '.join(f'{item["label"]}: {item["score"]:.1%}' for item in result['detections']))
        self.run_worker(lambda report, stop: Predictor(package.read_bytes()).predict(path, threshold), ready)

    def export_package(self):
        if not self.package:
            return self.error('Abre o entrena primero un detector.')
        path, _ = QFileDialog.getSaveFileName(self, 'Paquete para la Raspberry Pi', 'detector-objetos.zip', 'Modelo (*.zip)')
        if path:
            try:
                if Path(path).resolve() != self.package.resolve():
                    shutil.copyfile(self.package, path)
            except Exception as error:
                self.error(error)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.cancel()
            event.ignore()
        else:
            event.accept()


OBJECT_HELP = '''<h1>Enseñar a localizar y etiquetar objetos</h1>
<p>Elige qué quieres detectar: caras, pelotas, células u otras clases que puedas marcar con rectángulos. Una imagen puede tener cero, uno o varios objetos, incluso de clases distintas.</p>
<h2>El recorrido</h2><ol><li>Crea un proyecto vacío y añade tus propias etiquetas.</li><li>Añade fotografías originales.</li><li>Selecciona una clase y dibuja un rectángulo ajustado alrededor de cada objeto de esa clase.</li><li>Repite con todos los objetos de las clases del proyecto. Confirma la revisión o marca la imagen «sin objetos».</li><li>Revisa los grupos, entrena y evalúa.</li><li>Exporta el ZIP y úsalo con imágenes nuevas o la cámara en la Raspberry Pi.</li></ol>
<h2>Corregir etiquetas</h2><p>Haz clic en un rectángulo, elige otra clase y pulsa «Aplicar al seleccionado». Para corregir su tamaño, bórralo con Supr y dibújalo de nuevo. Puedes deshacer cambios durante la sesión. «Añadir etiqueta» amplía el proyecto; después debes entrenar un modelo nuevo.</p>
<h2>Qué aprende</h2><p>El modelo aprende las clases y las ubicaciones que le enseñas; no reconoce automáticamente cualquier objeto posible. Reutilizamos un extractor visual SSDLite MobileNetV3 y entrenamos las cabezas de clasificación y coordenadas. El fondo es interno: no debes dibujar rectángulos de fondo.</p>
<h2>Evaluar sin engañarnos</h2><p>Mantén las fotos de una misma sesión, objeto, persona o muestra microscópica en un grupo. No repartas fotos casi iguales entre entrenamiento y prueba. Cada clase necesita ejemplos de varios grupos y todos sus objetos visibles deben estar anotados.</p>
<p>Precisión: de los rectángulos predichos, cuántos tienen clase y posición correctas. Recuperación: de los objetos reales, cuántos encontró. IoU mide el solapamiento. AP50 se calcula por clase con IoU mínimo 0,5; se muestra también su media entre clases.</p>
<h2>Prueba con la cámara</h2><p>Comprueba escenas nuevas, varios objetos y escenas sin objetos de tus clases. Cambia distancia, fondo e iluminación. Baja el umbral y compara objetos recuperados y falsas alarmas. Compara los tiempos en Windows y en la Pi con el mismo ZIP.</p>
<p>Esta versión reduce las imágenes a 320 × 320 para la Pi 4. Objetos muy pequeños o células diminutas en imágenes grandes pueden requerir recortes, más resolución y otro ajuste del modelo. La cámara debe mostrar imágenes comparables a las usadas para entrenar.</p>'''


def main():
    app = QApplication(sys.argv)
    window = ObjectWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
