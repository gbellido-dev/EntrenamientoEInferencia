"""Editor, entrenamiento y prueba de detección de objetos con etiquetas propias.

Organización de secciones:
  1. Importaciones y constantes de color
  2. QSS (stylesheet) profesional oscuro
  3. BoxCanvas — widget de dibujo con colores por etiqueta
  4. ObjectWindow — ventana principal con tabs mejorados
     4a. build_editor  — Tab 1
     4b. build_train   — Tab 2
     4c. build_test    — Tab 3
  5. OBJECT_HELP HTML
  6. main()
"""

# ─────────────────────────────────────────────────────────────
# 1. Importaciones y constantes
# ─────────────────────────────────────────────────────────────
import copy
import hashlib
import json
import re
from pathlib import Path
import shutil
import sys
import time

from PIL import Image
from PySide6.QtCore import Qt, QRectF, QPointF, QSize, Signal, QMimeData, QTimer, QItemSelectionModel
from PySide6.QtGui import (
    QColor, QImage, QPainter, QPen, QPixmap, QBrush, QFont,
    QShortcut, QKeySequence, QFontMetrics,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox, QSplitter,
    QTabWidget, QTextBrowser, QTextEdit, QToolBar, QVBoxLayout, QWidget,
    QComboBox, QAbstractItemView, QStyle, QStyleOptionViewItem,
)

from aula_ia.workers import Worker
from aula_ia.project import detection_split, import_cvat, validate_project
from aula_ia.inference import Predictor
from aula_ia.project import EXTENSIONS, save_project

# Paleta de colores distinguibles WCAG (máx 20 etiquetas)
LABEL_COLORS = [
    '#3dd68c', '#f59e0b', '#60a5fa', '#f87171', '#a78bfa',
    '#fb923c', '#34d399', '#e879f9', '#fbbf24', '#38bdf8',
    '#4ade80', '#f472b6', '#c084fc', '#facc15', '#a3e635',
    '#fb7185', '#94a3b8', '#67e8f9', '#86efac', '#fda4af',
]

# ─────────────────────────────────────────────────────────────
# 2. QSS profesional — paleta oscura con acento verde #3dd68c
# ─────────────────────────────────────────────────────────────
DARK_QSS = """
/* === Base === */
QMainWindow, QDialog, QWidget {
    background-color: #1a1d27;
    color: #e2e8f0;
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 13px;
}

/* === TabWidget === */
QTabWidget::pane {
    border: 1px solid #2a2f45;
    border-radius: 6px;
    background: #22263a;
    margin-top: -1px;
}
QTabBar::tab {
    background: #22263a;
    color: #94a3b8;
    padding: 10px 22px;
    border: 1px solid transparent;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
    min-width: 120px;
}
QTabBar::tab:selected {
    background: #2a2f45;
    color: #3dd68c;
    border-color: #2a2f45;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    background: #252a3e;
    color: #e2e8f0;
}

/* === Buttons === */
QPushButton {
    background-color: #2a2f45;
    color: #e2e8f0;
    border: 1px solid #3d4464;
    border-radius: 6px;
    padding: 7px 14px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #333a56;
    border-color: #3dd68c;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #1e2235;
}
QPushButton:disabled {
    background-color: #1e2235;
    color: #4b5563;
    border-color: #252940;
}
QPushButton.primary {
    background-color: #3dd68c;
    color: #0f1520;
    border: none;
    font-weight: 700;
}
QPushButton.primary:hover {
    background-color: #4eeea0;
    border: none;
}
QPushButton.primary:pressed {
    background-color: #2abf78;
}
QPushButton.primary:disabled {
    background-color: #1e4d38;
    color: #2d7a57;
    border: none;
}
QPushButton.danger {
    background-color: #7f1d1d;
    color: #fca5a5;
    border: 1px solid #991b1b;
}
QPushButton.danger:hover {
    background-color: #991b1b;
    color: #ffffff;
}
QPushButton.danger:disabled {
    background-color: #1a1d27;
    color: #4b5563;
    border-color: #252940;
}

/* === Inputs === */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #22263a;
    color: #e2e8f0;
    border: 1px solid #3d4464;
    border-radius: 5px;
    padding: 5px 8px;
    selection-background-color: #3dd68c;
    selection-color: #0f1520;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #3dd68c;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox::down-arrow {
    width: 10px;
    height: 10px;
}
QComboBox QAbstractItemView {
    background-color: #22263a;
    color: #e2e8f0;
    selection-background-color: #2d4a3e;
    border: 1px solid #3d4464;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background: #2a2f45;
    border: none;
    width: 16px;
}

/* === Lists === */
QListWidget, QListView {
    background-color: #22263a;
    color: #e2e8f0;
    border: 1px solid #2a2f45;
    border-radius: 5px;
    outline: none;
}
QListWidget::item, QListView::item {
    padding: 5px 8px;
    border-radius: 3px;
}
QListWidget::item:hover, QListView::item:hover {
    background-color: #2d3250;
}
QListWidget::item:selected, QListView::item:selected {
    background-color: #1e4d38;
    color: #3dd68c;
}

/* === GroupBox === */
QGroupBox {
    background-color: #22263a;
    border: 1px solid #2a2f45;
    border-radius: 8px;
    margin-top: 20px;
    padding: 10px 8px 8px 8px;
    font-weight: 600;
    color: #94a3b8;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    top: -2px;
    padding: 0 6px;
    color: #94a3b8;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* === TextEdit / TextBrowser === */
QTextEdit, QTextBrowser {
    background-color: #141720;
    color: #a3e635;
    border: 1px solid #2a2f45;
    border-radius: 6px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
    padding: 6px;
}

/* === CheckBox === */
QCheckBox {
    color: #cbd5e1;
    spacing: 7px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #3d4464;
    border-radius: 4px;
    background: #22263a;
}
QCheckBox::indicator:checked {
    background-color: #3dd68c;
    border-color: #3dd68c;
}
QCheckBox::indicator:hover {
    border-color: #3dd68c;
}

/* === ProgressBar === */
QProgressBar {
    background-color: #22263a;
    border: 1px solid #2a2f45;
    border-radius: 5px;
    height: 12px;
    text-align: center;
    color: #e2e8f0;
    font-size: 11px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #3dd68c, stop:1 #4eeea0);
    border-radius: 5px;
}

/* === Splitter === */
QSplitter::handle {
    background-color: #2a2f45;
}
QSplitter::handle:horizontal {
    width: 3px;
}
QSplitter::handle:vertical {
    height: 3px;
}
QSplitter::handle:hover {
    background-color: #3dd68c;
}

/* === Scrollbar === */
QScrollBar:vertical {
    background: #1a1d27;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #3d4464;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #3dd68c;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: #1a1d27;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #3d4464;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background: #3dd68c;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* === StatusBar === */
QStatusBar {
    background: #141720;
    border-top: 1px solid #2a2f45;
    color: #64748b;
    font-size: 12px;
}
QStatusBar::item {
    border: none;
}

/* === Slider === */
QSlider::groove:horizontal {
    background: #2a2f45;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #3dd68c;
    width: 16px;
    height: 16px;
    border-radius: 8px;
    margin: -5px 0;
}
QSlider::sub-page:horizontal {
    background: #3dd68c;
    border-radius: 3px;
}

/* === Labels === */
QLabel {
    color: #cbd5e1;
}

/* === ToolBar === */
QToolBar {
    background: #1a1d27;
    border: none;
    spacing: 4px;
    padding: 4px;
}
"""


# ─────────────────────────────────────────────────────────────
# 3. BoxCanvas — widget de dibujo
# ─────────────────────────────────────────────────────────────
class PhotoList(QListWidget):
    """Distinguir marcar casillas de avanzar para anotar una foto."""
    selecting_batch = False

    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        checkbox = False
        if item:
            option = QStyleOptionViewItem()
            self.itemDelegate().initStyleOption(option, self.indexFromItem(item))
            option.rect = self.visualItemRect(item)
            check_rect = self.style().subElementRect(
                QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, self)
            checkbox = check_rect.contains(event.position().toPoint())
        self.selecting_batch = checkbox or bool(event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
        try:
            super().mousePressEvent(event)
        finally:
            self.selecting_batch = False


class BoxCanvas(QWidget):
    """Widget interactivo para dibujar y visualizar bounding boxes."""

    changed = Signal(object)
    image_requested = Signal()
    files_dropped = Signal(object)

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
        self._label_color_cache: dict[str, QColor] = {}
        self._color_index = 0
        self.setMinimumSize(360, 270)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.setStyleSheet('BoxCanvas { border-radius: 8px; }')
        self._update_cursor()

    # ── helpers ──────────────────────────────────────────────

    def _label_color(self, label: str) -> QColor:
        """Devuelve un QColor único y consistente para cada etiqueta."""
        if label not in self._label_color_cache:
            hex_color = LABEL_COLORS[self._color_index % len(LABEL_COLORS)]
            self._label_color_cache[label] = QColor(hex_color)
            self._color_index += 1
        return self._label_color_cache[label]

    def _update_cursor(self):
        if self.pixmap is None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif self.editable and self.current_label:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    # ── API pública ──────────────────────────────────────────

    def set_image(self, path, boxes, labels=None):
        """Carga una imagen y sus anotaciones en el canvas."""
        with Image.open(path) as image:
            self.original_size = image.size
            image = image.convert('RGB')
            image.thumbnail((1400, 1000))
            qimage = QImage(
                image.tobytes(), image.width, image.height,
                image.width * 3, QImage.Format.Format_RGB888
            ).copy()
        self.pixmap = QPixmap.fromImage(qimage)
        self.boxes = copy.deepcopy(boxes)
        self.box_labels = list(labels) if labels is not None else [self.current_label] * len(boxes)
        self.selected = -1
        self.start = self.end = None
        self._update_cursor()
        self.update()

    def display_rect(self) -> QRectF:
        w, h = self.original_size
        scale = min(self.width() / w, self.height() / h)
        return QRectF(
            (self.width() - w * scale) / 2,
            (self.height() - h * scale) / 2,
            w * scale, h * scale,
        )

    def image_point(self, position) -> list:
        rectangle = self.display_rect()
        w, h = self.original_size
        return [
            max(0., min(float(w), (position.x() - rectangle.x()) * w / rectangle.width())),
            max(0., min(float(h), (position.y() - rectangle.y()) * h / rectangle.height())),
        ]

    def delete_selected(self):
        if self.editable and 0 <= self.selected < len(self.boxes):
            del self.boxes[self.selected]
            del self.box_labels[self.selected]
            self.selected = -1
            self.emit_annotations()
            self.update()

    def relabel_selected(self):
        if self.editable and 0 <= self.selected < len(self.boxes):
            self.box_labels[self.selected] = self.current_label
            self.emit_annotations()
            self.update()

    def emit_annotations(self, added=False):
        self.changed.emit({
            'boxes': copy.deepcopy(self.boxes),
            'box_labels': self.box_labels.copy(),
            'added': added,
        })

    # ── paint ────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor('#111420'))

        if self.pixmap is None:
            self._draw_placeholder(painter)
            return

        rectangle = self.display_rect()
        painter.drawPixmap(rectangle, self.pixmap, QRectF(self.pixmap.rect()))

        w, h = self.original_size
        sx, sy = rectangle.width() / w, rectangle.height() / h
        font = QFont('Segoe UI', 10, QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)

        for index, box in enumerate(self.boxes):
            label = self.box_labels[index] if index < len(self.box_labels) else ''
            color = self._label_color(label)
            is_selected = (index == self.selected)

            # Rectángulo del box
            pen = QPen(color if not is_selected else QColor('#ffffff'), 2 if not is_selected else 3)
            painter.setPen(pen)
            bx = QRectF(
                rectangle.x() + box[0] * sx,
                rectangle.y() + box[1] * sy,
                (box[2] - box[0]) * sx,
                (box[3] - box[1]) * sy,
            )
            painter.drawRect(bx)

            # Etiqueta con fondo sólido
            display_text = f'{label} {index + 1}'
            text_rect = fm.boundingRect(display_text)
            lx = int(bx.x())
            ly = int(bx.y()) - text_rect.height() - 4
            if ly < 0:
                ly = int(bx.y()) + 2
            bg = QColor(color)
            bg.setAlpha(220)
            painter.fillRect(lx, ly, text_rect.width() + 10, text_rect.height() + 6, bg)
            painter.setPen(QColor('#000000') if color.lightness() > 128 else QColor('#ffffff'))
            painter.drawText(lx + 5, ly + text_rect.height() + 1, display_text)

        # Rectángulo en construcción
        if self.start is not None and self.end is not None:
            painter.setPen(QPen(QColor('#f59e0b'), 2, Qt.PenStyle.DashLine))
            a, b = self.start, self.end
            painter.drawRect(QRectF(
                QPointF(rectangle.x() + a[0] * sx, rectangle.y() + a[1] * sy),
                QPointF(rectangle.x() + b[0] * sx, rectangle.y() + b[1] * sy),
            ).normalized())

    def _draw_placeholder(self, painter: QPainter):
        """Dibuja el placeholder cuando no hay imagen cargada."""
        cx, cy = self.width() // 2, self.height() // 2
        # Cuadrado exterior
        painter.setPen(QPen(QColor('#2a2f45'), 2, Qt.PenStyle.DashLine))
        side = min(self.width(), self.height()) // 3
        painter.drawRect(cx - side // 2, cy - side // 2, side, side)
        # Cruz "+"
        painter.setPen(QPen(QColor('#3dd68c'), 3))
        painter.drawLine(cx, cy - 16, cx, cy + 16)
        painter.drawLine(cx - 16, cy, cx + 16, cy)
        # Texto
        painter.setPen(QColor('#94a3b8'))
        painter.setFont(QFont('Segoe UI', 11))
        painter.drawText(
            self.rect().adjusted(0, side // 2 + 20, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            'Haz clic para seleccionar una foto o arrástrala aquí',
        )

    # ── eventos de ratón ─────────────────────────────────────

    def mousePressEvent(self, event):
        if self.pixmap is None and event.button() == Qt.MouseButton.LeftButton:
            self.image_requested.emit()
            event.accept()
            return
        if (not self.editable or not self.current_label or
                self.pixmap is None or event.button() != Qt.MouseButton.LeftButton):
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
        if ((box[2] - box[0]) * rectangle.width() / self.original_size[0] >= 5
                and (box[3] - box[1]) * rectangle.height() / self.original_size[1] >= 5):
            self.boxes.append(box)
            self.box_labels.append(self.current_label)
            self.selected = len(self.boxes) - 1
            self.emit_annotations(added=True)
        else:
            candidates = [
                (i, (item[2] - item[0]) * (item[3] - item[1]))
                for i, item in enumerate(self.boxes)
                if item[0] <= a[0] <= item[2] and item[1] <= a[1] <= item[3]
            ]
            self.selected = min(candidates, key=lambda x: x[1])[0] if candidates else -1
        self.update()

    # ── teclado ──────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
        else:
            super().keyPressEvent(event)

    # ── drag & drop ──────────────────────────────────────────

    def dragEnterEvent(self, event):
        if any(url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in EXTENSIONS
               for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls()
                 if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in EXTENSIONS]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()


# ─────────────────────────────────────────────────────────────
# 4. ObjectWindow — ventana principal
# ─────────────────────────────────────────────────────────────
class ObjectWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = None
        self.path = None
        self.package = None
        self.worker = None
        self.current = -1
        self.undo_boxes = {}
        self._predictor = None        # Predictor cacheado para pruebas
        self._metrics_card = None     # QFrame de resultado de entrenamiento
        self._current_partition = 'all'  # 'all', 'train', 'val', 'test'
        self._filtered_indices = []      # Índices mapeados a self.project['images']
        self._updating_lists = False     # Bandera para evitar rebotes de eventos

        self.resize(1240, 880)
        self.setWindowTitle('Aula IA · Detectar objetos')
        self.setAcceptDrops(True)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.setStyleSheet(DARK_QSS)

        self.build_editor()
        self.build_train()
        self.build_test()

        help_view = QTextBrowser()
        help_view.setHtml(OBJECT_HELP)
        self.tabs.addTab(help_view, '4 · Aprende detección')

        self._build_statusbar()
        self._setup_shortcuts()
        self._update_status()

    # ─── helpers generales ───────────────────────────────────

    def _make_button(self, title: str, callback, css_class: str = '') -> QPushButton:
        btn = QPushButton(title)
        if css_class:
            btn.setProperty('class', css_class)
        btn.clicked.connect(callback)
        return btn

    def button(self, layout, title, callback):
        """Compatibilidad con API interna original."""
        btn = self._make_button(title, callback)
        layout.addWidget(btn)
        return btn

    def error(self, text):
        QMessageBox.warning(self, 'Detector de objetos', str(text))

    def _build_statusbar(self):
        sb = self.statusBar()
        self._sb_project = QLabel('Sin proyecto')
        self._sb_image = QLabel('')
        self._sb_mode = QLabel('Edición')
        for lbl in (self._sb_project, self._sb_image, self._sb_mode):
            lbl.setStyleSheet('color:#64748b; padding:0 8px;')
            sb.addPermanentWidget(lbl)
        sb.showMessage('Listo')

    def _update_status(self, mode: str = ''):
        proj = self.project['name'] if self.project else 'Sin proyecto'
        self._sb_project.setText(f'📁 {proj}')
        if self.valid():
            row = self.project['images'][self.current]
            self._sb_image.setText(f'🖼 {Path(row["path"]).name}')
        else:
            self._sb_image.setText('')
        if mode:
            self._sb_mode.setText(f'⚙ {mode}')

    def _setup_shortcuts(self):
        QShortcut(QKeySequence('Ctrl+Z'), self).activated.connect(self.undo)
        QShortcut(QKeySequence('Ctrl+S'), self).activated.connect(self.save)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self).activated.connect(lambda: self.move(1))
        QShortcut(QKeySequence(Qt.Key.Key_Left), self).activated.connect(lambda: self.move(-1))
        QShortcut(QKeySequence(Qt.Key.Key_Space), self).activated.connect(self.mark_reviewed)
        QShortcut(QKeySequence(Qt.Key.Key_E), self).activated.connect(self.mark_empty)

    # ─── Drag & Drop en ventana principal ───────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith('.json'):
                self.load_path(path)
                return

    # ─────────────────────────────────────────────────────────
    # 4a. Tab 1 — Editor
    # ─────────────────────────────────────────────────────────
    def build_editor(self):
        self.editor = QWidget()
        layout = QVBoxLayout(self.editor)
        layout.setSpacing(8)

        # ── Toolbar de proyecto ──
        toolbar_row = QHBoxLayout()
        toolbar_row.setSpacing(6)

        btn_new = self._make_button('＋ Nuevo', self.new_project)
        btn_open = self._make_button('📂 Abrir', self.open_project)
        btn_import = self._make_button('📥 Importar CVAT', self.import_xml)
        btn_add = self._make_button('🖼 Añadir fotos', self.add_images)
        for btn in (btn_new, btn_open, btn_import, btn_add):
            btn.setFixedHeight(34)
            toolbar_row.addWidget(btn)
        toolbar_row.addStretch()
        layout.addLayout(toolbar_row)

        # ── Barra de estado del proyecto ──
        self.summary = QLabel('Crea un proyecto con tus clases, abre uno existente o importa un CVAT XML.')
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet(
            'background:#22263a; border:1px solid #2a2f45; border-radius:6px;'
            'padding:6px 10px; color:#94a3b8; font-size:12px;'
        )
        layout.addWidget(self.summary)

        # ── Splitter lista / detalle ──
        split = QSplitter()

        # Panel izquierdo con pestañas de conjuntos: Todas, Entrenamiento, Validación, Prueba
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self.partition_tabs = QTabWidget()
        self.partition_tabs.setStyleSheet("""
            QTabBar::tab { font-size: 11px; padding: 6px 8px; min-width: 55px; }
            QTabBar::tab:selected { color: #3dd68c; }
        """)

        # Lista general compatible con API existente (self.images)
        self.images = PhotoList()
        self.images.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.images.itemSelectionChanged.connect(self._update_bulk_selection)
        self.images.itemChanged.connect(self._update_bulk_selection)
        self.images.currentRowChanged.connect(lambda idx: self._on_list_row_changed('all', idx))

        self.images_train = QListWidget()
        self.images_train.currentRowChanged.connect(lambda idx: self._on_list_row_changed('train', idx))

        self.images_val = QListWidget()
        self.images_val.currentRowChanged.connect(lambda idx: self._on_list_row_changed('val', idx))

        self.images_test = QListWidget()
        self.images_test.currentRowChanged.connect(lambda idx: self._on_list_row_changed('test', idx))

        self.partition_tabs.addTab(self.images, 'Todas (0)')
        self.partition_tabs.addTab(self.images_train, '🔵 Train (0)')
        self.partition_tabs.addTab(self.images_val, '🟡 Val (0)')
        self.partition_tabs.addTab(self.images_test, '🟣 Test (0)')
        self.partition_tabs.currentChanged.connect(self._on_partition_tab_changed)
        left_layout.addWidget(self.partition_tabs, 1)

        self.bulk_panel = QWidget()
        bulk_layout = QVBoxLayout(self.bulk_panel)
        bulk_layout.setContentsMargins(0, 0, 0, 0)
        self.bulk_count = QLabel('0 fotos seleccionadas')
        self.bulk_count.setWordWrap(True)
        self.bulk_count.setToolTip(
            'Marca casillas o selecciona con Ctrl+clic y Shift+clic. '
            'Si hay casillas marcadas, se usan esas fotos; si no, la selección resaltada.'
        )
        bulk_layout.addWidget(self.bulk_count)
        bulk_row = QHBoxLayout()
        self.bulk_partition_combo = QComboBox()
        self.bulk_partition_combo.addItems(['Automático / Otro', '🔵 Train', '🟡 Val', '🟣 Test'])
        bulk_row.addWidget(self.bulk_partition_combo)
        self.bulk_move_button = self._make_button('Mover seleccionadas', self.move_selected_partition)
        self.bulk_move_button.setEnabled(False)
        bulk_row.addWidget(self.bulk_move_button)
        bulk_layout.addLayout(bulk_row)
        bulk_layout.addWidget(self._make_button('Limpiar selección', self.clear_bulk_selection))
        left_layout.addWidget(self.bulk_panel)

        # Botones rápidos para añadir fotos directamente a la partición activa o seleccionada
        add_part_row = QHBoxLayout()
        add_part_row.setSpacing(4)
        btn_add_train = self._make_button('＋ Train', lambda: self.add_images_partition('train'))
        btn_add_val = self._make_button('＋ Val', lambda: self.add_images_partition('val'))
        btn_add_test = self._make_button('＋ Test', lambda: self.add_images_partition('test'))
        for b in (btn_add_train, btn_add_val, btn_add_test):
            b.setFixedHeight(26)
            b.setStyleSheet('font-size: 11px; padding: 2px 4px;')
            add_part_row.addWidget(b)
        left_layout.addLayout(add_part_row)

        left_panel.setMinimumWidth(230)
        split.addWidget(left_panel)

        # Panel derecho
        right = QWidget()
        detail = QVBoxLayout(right)
        detail.setSpacing(6)
        detail.setContentsMargins(4, 0, 0, 0)

        # Barra de etiqueta
        class_bar = QHBoxLayout()
        class_bar.setSpacing(4)
        lbl_class = QLabel('Etiqueta:')
        lbl_class.setFixedWidth(60)
        class_bar.addWidget(lbl_class)
        self.class_choice = QComboBox()
        self.class_choice.setPlaceholderText('Añade tu primera etiqueta')
        self.class_choice.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.class_choice.currentTextChanged.connect(self._on_class_changed)
        class_bar.addWidget(self.class_choice)
        btn_add_class = self._make_button('＋ Añadir etiqueta', self.add_class)
        self.rename_class_button = self._make_button('Renombrar', self.rename_class)
        self.delete_class_button = self._make_button('Eliminar etiqueta', self.delete_class)
        self.rename_class_button.setToolTip('Cambiar el nombre de esta etiqueta en todo el proyecto.')
        self.delete_class_button.setToolTip('Eliminar esta etiqueta del proyecto y sus rectángulos, previa confirmación.')
        for button in (btn_add_class, self.rename_class_button, self.delete_class_button):
            button.setFixedHeight(30)
            class_bar.addWidget(button)
        detail.addLayout(class_bar)

        # Auto-avance
        self.auto_next = QCheckBox('Avance automático al dibujar un rectángulo')
        self.auto_next.setToolTip('Útil para fotos con un solo objeto.')
        detail.addWidget(self.auto_next)

        # Canvas principal
        self.canvas = BoxCanvas(editable=True)
        self.canvas.changed.connect(self.update_boxes)
        self.canvas.image_requested.connect(self.select_photos)
        self.canvas.files_dropped.connect(self.import_photos)
        detail.addWidget(self.canvas, 1)

        # Fila de info de archivo y partición rápida
        info_row = QHBoxLayout()
        self.filename = QLabel('')
        self.filename.setStyleSheet('color:#64748b; font-size:12px;')
        self.filename.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        info_row.addWidget(self.filename)

        lbl_part = QLabel('Conjunto:')
        lbl_part.setStyleSheet('color:#94a3b8; font-size:11px;')
        info_row.addWidget(lbl_part)
        self.partition_combo = QComboBox()
        self.partition_combo.addItems(['Automático / Otro', '🔵 Train', '🟡 Val', '🟣 Test'])
        self.partition_combo.setFixedWidth(130)
        self.partition_combo.setToolTip(
            'La última elección se aplica a las siguientes fotos sin conjunto asignado. '
            'Las fotos ya asignadas conservan su conjunto.'
        )
        self.partition_combo.currentIndexChanged.connect(self._on_image_partition_changed)
        info_row.addWidget(self.partition_combo)

        lbl_group = QLabel('Grupo:')
        lbl_group.setFixedWidth(46)
        info_row.addWidget(lbl_group)
        self.group = QLineEdit()
        self.group.setFixedWidth(110)
        self.group.editingFinished.connect(self.change_group)
        info_row.addWidget(self.group)
        self.excluded = QCheckBox('Descartar')
        self.excluded.toggled.connect(self.exclude)
        info_row.addWidget(self.excluded)
        detail.addLayout(info_row)

        # Botones de acción
        actions = QHBoxLayout()
        actions.setSpacing(4)
        btn_del = self._make_button('🗑 Borrar rectángulo', self.canvas_delete)
        btn_relabel = self._make_button('Cambiar etiqueta del rectángulo', self.canvas_relabel)
        btn_relabel.setToolTip('Selecciona un rectángulo, elige su nueva etiqueta arriba y pulsa este botón.')
        btn_undo = self._make_button('↩ Deshacer', self.undo)
        btn_empty = self._make_button('☑ Sin objetos', self.mark_empty)
        for b in (btn_relabel, btn_del, btn_undo, btn_empty):
            b.setFixedHeight(30)
            actions.addWidget(b)
        detail.addLayout(actions)

        # Botones de navegación
        nav = QHBoxLayout()
        nav.setSpacing(4)
        btn_prev = self._make_button('← Anterior', lambda: self.move(-1))
        btn_confirm = self._make_button('✓ Confirmar', self.mark_reviewed)
        btn_confirm.setProperty('class', 'primary')
        btn_next = self._make_button('Siguiente →', lambda: self.move(1))
        btn_prev.setFixedHeight(34)
        btn_confirm.setFixedHeight(34)
        btn_next.setFixedHeight(34)
        nav.addWidget(btn_prev)
        nav.addWidget(btn_confirm, 1)
        nav.addWidget(btn_next)
        detail.addLayout(nav)

        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        layout.addWidget(split, 1)
        self.tabs.addTab(self.editor, '1 · Imágenes y etiquetas')

    def _on_class_changed(self, value: str):
        self.canvas.current_label = value
        self.canvas._update_cursor()

    def canvas_delete(self):
        self.canvas.delete_selected()

    def canvas_relabel(self):
        if self.canvas.selected < 0 or not self.canvas.current_label:
            return self.error('Selecciona un rectángulo, elige su nueva etiqueta y pulsa «Cambiar etiqueta del rectángulo».')
        self.canvas.relabel_selected()

    def select_photos(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Seleccionar fotografías', '', 'Imágenes (*.jpg *.jpeg *.png *.webp *.bmp)'
        )
        if paths:
            self.import_photos(paths)

    def import_photos(self, paths):
        """Importar solo los archivos elegidos, sin recorrer sus carpetas."""
        try:
            prepared = []
            for value in paths:
                path = Path(value).resolve()
                if path.suffix.lower() not in EXTENSIONS or not path.is_file():
                    raise ValueError(f'No es una fotografía compatible: {path.name}')
                with Image.open(path) as image:
                    image.verify()
                prepared.append((path, hashlib.sha256(path.read_bytes()).hexdigest()))
            if not prepared:
                return
            if not self.project:
                self.new_project()
                if not self.project:
                    return
            group = f'{self._current_partition}-drop' if self._current_partition in ('train', 'val', 'test') else 'drop'
            known = {row['sha256'] for row in self.project['images']}
            added = 0
            for path, digest in prepared:
                if digest not in known:
                    self.project['images'].append({
                        'path': str(path), 'sha256': digest, 'group': group,
                        'boxes': [], 'box_labels': [], 'reviewed': False, 'excluded': False,
                    })
                    known.add(digest)
                    added += 1
            self.save()
            self.refresh()
            first_digest = prepared[0][1]
            for index, row in enumerate(self.project['images']):
                if row['sha256'] == first_digest:
                    if self._current_partition != 'all' and self._detect_partition(row['group']) != self._current_partition:
                        self.partition_tabs.setCurrentIndex(0)
                    self.images.setCurrentRow(index)
                    self.select(index)
                    break
            self.statusBar().showMessage(f'{added} fotos añadidas; la fotografía seleccionada está lista para anotar.', 4000)
        except Exception as error:
            self.error(f'No se pudieron cargar las fotografías: {error}')

    # ─────────────────────────────────────────────────────────
    # 4b. Tab 2 — Entrenar
    # ─────────────────────────────────────────────────────────
    def build_train(self):
        self._train_page = QWidget()
        layout = QVBoxLayout(self._train_page)
        layout.setSpacing(10)

        # Descripción
        desc = QLabel(
            'Entrenamos las cabezas de clasificación y de rectángulos de SSDLite MobileNetV3. '
            'El extractor y las estadísticas de normalización quedan congelados. CPU, lotes de 4. '
            'La validación elige la mejor época por AP50; la prueba se reserva hasta el final.'
        )
        desc.setWordWrap(True)
        desc.setStyleSheet('color:#94a3b8; font-size:12px;')
        layout.addWidget(desc)

        # Card de parámetros
        params_group = QGroupBox('Parámetros de entrenamiento')
        params_form = QFormLayout(params_group)
        params_form.setSpacing(8)
        self.epochs = QSpinBox()
        self.epochs.setRange(1, 100)
        self.epochs.setValue(15)
        params_form.addRow('Épocas:', self.epochs)
        self.rate = QDoubleSpinBox()
        self.rate.setDecimals(5)
        self.rate.setRange(.00001, 1.)
        self.rate.setValue(.001)
        self.rate.setSingleStep(.001)
        params_form.addRow('Tasa de aprendizaje:', self.rate)
        layout.addWidget(params_group)

        # Botones
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.train_button = self._make_button('▶ Entrenar y exportar', self.start_train, 'primary')
        self.cancel_button = self._make_button('✕ Cancelar', self.cancel, 'danger')
        self.cancel_button.setEnabled(False)
        self.export_button = self._make_button('📋 Copiar para Pi', self.export_package)
        for b in (self.train_button, self.cancel_button, self.export_button):
            b.setFixedHeight(36)
            btn_row.addWidget(b)
        layout.addLayout(btn_row)

        # Barra de progreso
        self.train_progress = QProgressBar()
        self.train_progress.setRange(0, 100)
        self.train_progress.setValue(0)
        self.train_progress.setFormat('En espera')
        layout.addWidget(self.train_progress)

        self.train_status = QLabel('Listo para entrenar.')
        self.train_status.setWordWrap(True)
        self.train_status.setStyleSheet('color:#94a3b8; font-size:13px;')
        layout.addWidget(self.train_status)
        self._activity_timer = QTimer(self)
        self._activity_timer.setInterval(1000)
        self._activity_timer.timeout.connect(self._update_training_activity)

        # Log de entrenamiento
        self.report = QTextEdit()
        self.report.setReadOnly(True)
        layout.addWidget(self.report, 1)

        self.tabs.addTab(self._train_page, '2 · Entrena y evalúa')

    def show_metrics_card(self, metrics: dict):
        """Crea o actualiza la tarjeta de resultado de entrenamiento."""
        result = metrics.get('test_detection', {})
        if not result:
            return
        ap50 = result.get('ap50', 0)
        prec = result.get('precision', 0)
        recall = result.get('recall', 0)

        # Color de fondo según AP50
        if ap50 >= 0.7:
            bg, accent = '#0f2d1c', '#3dd68c'
        elif ap50 >= 0.4:
            bg, accent = '#2d2000', '#f59e0b'
        else:
            bg, accent = '#2d0a0a', '#f87171'

        if self._metrics_card is not None:
            self._metrics_card.setParent(None)
            self._metrics_card.deleteLater()

        card = QFrame()
        card.setStyleSheet(
            f'QFrame {{ background:{bg}; border:1px solid {accent}; border-radius:10px; padding:10px; }}'
        )
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(4)

        ap_lbl = QLabel(f'AP50: {ap50:.1%}')
        ap_lbl.setStyleSheet(f'color:{accent}; font-size:28px; font-weight:700;')
        ap_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(ap_lbl)

        stats_lbl = QLabel(
            f'Precisión: {prec:.1%}  ·  Recuperación: {recall:.1%}  ·  '
            f'TP: {result.get("true_positives", "?")}  '
            f'FP: {result.get("false_positives", "?")}  '
            f'FN: {result.get("false_negatives", "?")}'
        )
        stats_lbl.setStyleSheet(f'color:{accent}; font-size:13px;')
        stats_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(stats_lbl)

        self._metrics_card = card
        # Insertar antes del log (índice 4 en el layout)
        train_layout = self._train_page.layout()
        train_layout.insertWidget(train_layout.count() - 1, card)

    # ─────────────────────────────────────────────────────────
    # 4c. Tab 3 — Prueba
    # ─────────────────────────────────────────────────────────
    def build_test(self):
        page = QWidget()
        page_layout = QHBoxLayout(page)
        page_layout.setSpacing(10)

        # ── Panel izquierdo (controles, ancho fijo) ──
        left = QWidget()
        left.setFixedWidth(260)
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(10)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Grupo — modelo activo
        model_group = QGroupBox('Modelo activo')
        model_glayout = QVBoxLayout(model_group)
        self._model_name_lbl = QLabel('Ninguno')
        self._model_name_lbl.setWordWrap(True)
        self._model_name_lbl.setStyleSheet('color:#94a3b8; font-size:12px;')
        model_glayout.addWidget(self._model_name_lbl)
        self._model_labels_lbl = QLabel('')
        self._model_labels_lbl.setWordWrap(True)
        self._model_labels_lbl.setStyleSheet('color:#3dd68c; font-size:11px;')
        model_glayout.addWidget(self._model_labels_lbl)
        self.model_button = self._make_button('📂 Abrir ZIP', self.open_model)
        model_glayout.addWidget(self.model_button)
        left_layout.addWidget(model_group)

        # Grupo — configuración
        cfg_group = QGroupBox('Configuración')
        cfg_glayout = QVBoxLayout(cfg_group)
        thr_row = QHBoxLayout()
        thr_lbl = QLabel('Umbral:')
        self._thr_val_lbl = QLabel('0.50')
        self._thr_val_lbl.setStyleSheet('color:#3dd68c; font-weight:700;')
        thr_row.addWidget(thr_lbl)
        thr_row.addStretch()
        thr_row.addWidget(self._thr_val_lbl)
        cfg_glayout.addLayout(thr_row)
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(1, 100)
        self.threshold_slider.setValue(50)
        self.threshold_slider.setSingleStep(5)
        self.threshold_slider.valueChanged.connect(self._on_threshold_slider)
        cfg_glayout.addWidget(self.threshold_slider)
        # SpinBox oculto para compatibilidad con código existente
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(.01, 1)
        self.threshold.setSingleStep(.05)
        self.threshold.setValue(.5)
        self.threshold.hide()
        self.test_button = self._make_button('🔍 Detectar en imagen', self.test_image, 'primary')
        cfg_glayout.addWidget(self.test_button)
        left_layout.addWidget(cfg_group)

        # Grupo — resultados
        res_group = QGroupBox('Resultados')
        res_glayout = QVBoxLayout(res_group)
        self.detection_list = QListWidget()
        self.detection_list.setMaximumHeight(180)
        res_glayout.addWidget(self.detection_list)
        self.test_result = QLabel('Sin modelo seleccionado.')
        self.test_result.setWordWrap(True)
        self.test_result.setStyleSheet('color:#94a3b8; font-size:12px;')
        res_glayout.addWidget(self.test_result)
        left_layout.addWidget(res_group)

        # Botón guardar
        btn_save_img = self._make_button('💾 Guardar imagen anotada', self._save_test_image)
        left_layout.addWidget(btn_save_img)
        left_layout.addStretch()

        page_layout.addWidget(left)

        # ── Panel derecho (canvas) ──
        self.test_canvas = BoxCanvas(editable=False)
        self.test_canvas.image_requested.connect(self.test_image)
        self.test_canvas.files_dropped.connect(lambda paths: self.test_image_path(paths[0]))
        page_layout.addWidget(self.test_canvas, 1)

        self.tabs.addTab(page, '3 · Prueba el detector')

    def _on_threshold_slider(self, value: int):
        thr = value / 100.0
        self._thr_val_lbl.setText(f'{thr:.2f}')
        self.threshold.setValue(thr)

    def _save_test_image(self):
        if self.test_canvas.pixmap is None:
            return self.error('No hay imagen en el canvas de prueba.')
        path, _ = QFileDialog.getSaveFileName(
            self, 'Guardar imagen anotada', 'resultado.png', 'Imagen PNG (*.png)'
        )
        if path:
            # Renderizar el canvas a un pixmap
            px = QPixmap(self.test_canvas.size())
            px.fill(Qt.GlobalColor.transparent)
            painter = QPainter(px)
            self.test_canvas.render(painter)
            painter.end()
            px.save(path, 'PNG')

    # ─────────────────────────────────────────────────────────
    # Lógica de datos (sin cambios de comportamiento)
    # ─────────────────────────────────────────────────────────

    def valid(self) -> bool:
        return self.project is not None and 0 <= self.current < len(self.project['images'])

    def save(self):
        if self.project and self.path:
            save_project(self.path, self.project)
            self.statusBar().showMessage(f'Guardado: {self.path}')

    def new_project(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Proyecto de objetos', 'projects/objetos/proyecto.json', 'Proyecto (*.json)'
        )
        if path:
            self.project = {
                'version': 1, 'task': 'object_detection',
                'name': Path(path).stem, 'classes': [], 'images': [],
            }
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
            path, _ = QFileDialog.getSaveFileName(
                self, 'Guardar proyecto convertido', 'projects/caras/proyecto.json', 'Proyecto (*.json)'
            )
            if path:
                save_project(path, project)
                self.project, self.path, self.package = project, Path(path), None
                self.refresh()
        except Exception as error:
            self.error(error)

    def add_images_partition(self, partition: str = 'train'):
        """Añade imágenes asignándolas a un grupo prefijado de entrenamiento, validación o test."""
        if not self.project:
            return self.error('Crea o abre un proyecto primero.')
        folder = QFileDialog.getExistingDirectory(self, f'Carpeta de fotos para {partition.upper()}')
        if not folder:
            return
        # Determinar el nombre de sesión para esta partición
        existing_groups = {row.get('group', '') for row in self.project['images'] if row.get('group', '').startswith(f'{partition}-')}
        next_num = len(existing_groups) + 1
        default_group = f'{partition}-{next_num}'
        group, ok = QInputDialog.getText(
            self, f'Grupo de {partition.upper()}',
            f'Nombre del grupo/sesión ({partition}):',
            text=default_group
        )
        if not ok or not group.strip():
            return
        self._import_folder_into_group(folder, group.strip(), target_partition=partition)

    def add_images(self):
        if not self.project:
            return self.error('Crea o abre un proyecto primero.')
        folder = QFileDialog.getExistingDirectory(self, 'Carpeta de fotografías originales')
        if not folder:
            return
        group, ok = QInputDialog.getText(
            self, 'Grupo', 'Sesión u objeto/persona relacionado:', text='sesion-1'
        )
        if not ok or not group.strip():
            return
        self._import_folder_into_group(folder, group.strip())

    def _import_folder_into_group(self, folder: str, group: str, target_partition: str = None):
        try:
            known = {row['sha256'] for row in self.project['images']}
            added = 0
            for path in sorted(Path(folder).rglob('*')):
                if path.is_file() and path.suffix.lower() in EXTENSIONS:
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    if digest not in known:
                        self.project['images'].append({
                            'path': str(path.resolve()), 'sha256': digest,
                            'group': group, 'boxes': [], 'box_labels': [],
                            'reviewed': False, 'excluded': False,
                        })
                        known.add(digest)
                        added += 1
            self.save()
            self.refresh()
            if target_partition:
                # Cambiar a la pestaña correspondiente
                tab_idx = {'train': 1, 'val': 2, 'test': 3}.get(target_partition, 0)
                self.partition_tabs.setCurrentIndex(tab_idx)
            self.statusBar().showMessage(f'{added} fotos añadidas al grupo «{group}».', 4000)
        except Exception as error:
            self.error(error)

    def _detect_partition(self, group: str) -> str:
        g = group.lower()
        if g.startswith('train') or 'entrenamiento' in g:
            return 'train'
        if g.startswith('val') or 'validaci' in g:
            return 'val'
        if g.startswith('test') or 'prueba' in g:
            return 'test'
        return 'other'

    def _on_partition_tab_changed(self, index: int):
        tab_map = {0: 'all', 1: 'train', 2: 'val', 3: 'test'}
        self._current_partition = tab_map.get(index, 'all')
        self.bulk_panel.setVisible(index == 0)
        self._sync_active_list_selection()

    def _on_list_row_changed(self, part: str, row_idx: int):
        if self._updating_lists or row_idx < 0:
            return
        if part == 'all':
            extending = bool(QApplication.keyboardModifiers() & (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
            self.select(row_idx, inherit_partition=not extending and not self.images.selecting_batch
                        and len(self.images.selectedItems()) <= 1)
        else:
            # Mapear row_idx de la sublista a la lista general
            matches = [i for i, r in enumerate(self.project['images']) if self._detect_partition(r.get('group', '')) == part]
            if 0 <= row_idx < len(matches):
                real_idx = matches[row_idx]
                self.select(real_idx)

    def _on_image_partition_changed(self, combo_idx: int):
        """Asigna prefijo de grupo según el combo de partición."""
        if self._updating_lists or not self.valid():
            return
        self.project['preferred_partition'] = combo_idx
        row = self.project['images'][self.current]
        self._assign_partition(row, combo_idx)
        self.group.setText(row['group'])
        self.update_row()

    @staticmethod
    def _assign_partition(row, combo_idx):
        row['partition_assigned'] = True
        curr_g = row.get('group', '')
        # Quitar prefijos anteriores si los tenía
        clean_g = curr_g
        for prefix in ('train-', 'val-', 'test-', 'train', 'val', 'test'):
            if clean_g.lower().startswith(prefix):
                clean_g = clean_g[len(prefix):].lstrip('-_')
                break
        clean_g = clean_g or '1'

        if combo_idx == 1:   # Train
            row['group'] = f'train-{clean_g}'
        elif combo_idx == 2: # Val
            row['group'] = f'val-{clean_g}'
        elif combo_idx == 3: # Test
            row['group'] = f'test-{clean_g}'
        else:
            row['group'] = clean_g or 'sesion-1'

    def _bulk_indexes(self):
        checked = [index for index in range(self.images.count())
                   if self.images.item(index).checkState() == Qt.CheckState.Checked]
        return checked or sorted(self.images.row(item) for item in self.images.selectedItems())

    def _update_bulk_selection(self, *args):
        if not hasattr(self, 'bulk_count'):
            return
        indexes = self._bulk_indexes()
        checked = any(self.images.item(index).checkState() == Qt.CheckState.Checked for index in indexes)
        self.bulk_count.setText(f'{len(indexes)} fotos ' + ('marcadas con casillas' if checked else 'seleccionadas'))
        self.bulk_move_button.setEnabled(bool(indexes))

    def clear_bulk_selection(self):
        self.images.blockSignals(True)
        for index in range(self.images.count()):
            self.images.item(index).setCheckState(Qt.CheckState.Unchecked)
        self.images.clearSelection()
        self.images.blockSignals(False)
        self._update_bulk_selection()

    def move_selected_partition(self):
        if not self.project or self._current_partition != 'all':
            return
        indexes = self._bulk_indexes()
        if not indexes:
            return
        destination = self.bulk_partition_combo.currentIndex()
        for index in indexes:
            self._assign_partition(self.project['images'][index], destination)
        self.project['preferred_partition'] = destination
        if self.valid():
            self.group.setText(self.project['images'][self.current]['group'])
            saved = self.update_row()
        else:
            try:
                self.save()
                self._refresh_sublists()
                saved = True
            except Exception as error:
                self.error(error)
                saved = False
        if saved:
            self.statusBar().showMessage(
                f'{len(indexes)} fotos movidas a {self.bulk_partition_combo.currentText()}.', 5000)

    def _refresh_sublists(self):
        """Actualiza el contenido de las 4 pestañas de listas y sus contadores."""
        if not self.project:
            return
        self._updating_lists = True
        try:
            counts = {'train': 0, 'val': 0, 'test': 0, 'other': 0}
            self.images_train.clear()
            self.images_val.clear()
            self.images_test.clear()

            for i, row in enumerate(self.project['images']):
                part = self._detect_partition(row.get('group', ''))
                counts[part] = counts.get(part, 0) + 1

                item = QListWidgetItem(self.row_text(row))
                item.setForeground(self._row_color(row))
                item.setData(Qt.ItemDataRole.UserRole, i)

                if part == 'train':
                    self.images_train.addItem(item)
                elif part == 'val':
                    self.images_val.addItem(item)
                elif part == 'test':
                    self.images_test.addItem(item)

            tot = len(self.project['images'])
            self.partition_tabs.setTabText(0, f'Todas ({tot})')
            self.partition_tabs.setTabText(1, f'🔵 Train ({counts["train"]})')
            self.partition_tabs.setTabText(2, f'🟡 Val ({counts["val"]})')
            self.partition_tabs.setTabText(3, f'🟣 Test ({counts["test"]})')
            self._sync_active_list_selection()
        finally:
            self._updating_lists = False

    def _sync_active_list_selection(self):
        if not self.valid():
            return
        self._updating_lists = True
        try:
            self.images.blockSignals(True)
            self.images.setCurrentRow(self.current, QItemSelectionModel.SelectionFlag.NoUpdate)
            self.images.blockSignals(False)

            # Sincronizar sublistas
            curr_row = self.project['images'][self.current]
            curr_part = self._detect_partition(curr_row.get('group', ''))

            # Actualizar selector de combo
            if hasattr(self, 'partition_combo'):
                self.partition_combo.blockSignals(True)
                c_idx = {'train': 1, 'val': 2, 'test': 3}.get(curr_part, 0)
                self.partition_combo.setCurrentIndex(c_idx)
                self.partition_combo.blockSignals(False)

            # Buscar índice en sublista correspondiente
            for part, list_widget in (('train', self.images_train), ('val', self.images_val), ('test', self.images_test)):
                list_widget.blockSignals(True)
                found = -1
                for r_idx in range(list_widget.count()):
                    if list_widget.item(r_idx).data(Qt.ItemDataRole.UserRole) == self.current:
                        found = r_idx
                        break
                list_widget.setCurrentRow(found)
                list_widget.blockSignals(False)
        finally:
            self._updating_lists = False

    def row_text(self, row: dict) -> str:
        state = 'DESCARTADA' if row.get('excluded') else 'Revisada' if row.get('reviewed') else 'PENDIENTE'
        return f'{state} · {Path(row["path"]).name} · {len(row["boxes"])} obj'

    def _row_color(self, row: dict) -> QColor:
        if row.get('excluded'):
            return QColor('#6b7280')
        if row.get('reviewed'):
            return QColor('#3dd68c')
        return QColor('#f59e0b')

    def refresh(self):
        self.undo_boxes.clear()
        self.class_choice.clear()
        self.class_choice.addItems(self.project['classes'])
        if self.project['classes']:
            self.class_choice.setCurrentIndex(0)
        self.images.blockSignals(True)
        self.images.clear()
        for row in self.project['images']:
            item = QListWidgetItem(self.row_text(row))
            item.setForeground(self._row_color(row))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.images.addItem(item)
        self.images.blockSignals(False)
        self.current = -1
        reviewed = sum(1 for r in self.project['images'] if r.get('reviewed') and not r.get('excluded'))
        total = len(self.project['images'])
        rects = sum(len(r['boxes']) for r in self.project['images'])
        self.summary.setText(
            f'<b>{self.project["name"]}</b> · {total} fotos · '
            f'{reviewed} revisadas / {total - reviewed} pendientes · '
            f'{rects} rectángulos  —  '
            + self.project.get('grouping_note', 'Revisa que los grupos sean independientes.')
        )
        self.canvas.pixmap = None
        self.canvas.update()
        self.filename.clear()
        self.group.clear()
        self._refresh_sublists()
        if self.project['images']:
            self.images.blockSignals(True)
            self.images.setCurrentRow(0)
            self.images.blockSignals(False)
            self.select(0, inherit_partition=False)
        self._update_status()
        self._update_bulk_selection()

    def select(self, index: int, inherit_partition: bool = True):
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
        name = Path(row['path']).name
        self.filename.setText(
            f'{index + 1}/{len(self.project["images"])}  ·  {name}  ·  {len(row["boxes"])} obj'
        )
        self.group.setText(row['group'])
        self.excluded.blockSignals(True)
        self.excluded.setChecked(row.get('excluded', False))
        self.excluded.blockSignals(False)
        preferred = self.project.get('preferred_partition')
        if (inherit_partition and preferred in (0, 1, 2, 3)
                and not row.get('partition_assigned')
                and self._detect_partition(row.get('group', '')) == 'other'):
            self._on_image_partition_changed(preferred)
        self._sync_active_list_selection()
        self._update_status()

    def update_row(self) -> bool:
        row = self.project['images'][self.current]
        item = self.images.item(self.current)
        if item:
            item.setText(self.row_text(row))
            item.setForeground(self._row_color(row))
        reviewed = sum(1 for r in self.project['images'] if r.get('reviewed') and not r.get('excluded'))
        total = len(self.project['images'])
        rects = sum(len(r['boxes']) for r in self.project['images'])
        self.summary.setText(
            f'<b>{self.project["name"]}</b> · {total} fotos · '
            f'{reviewed} revisadas / {total - reviewed} pendientes · '
            f'{rects} rectángulos  —  '
            + self.project.get('grouping_note', 'Revisa que los grupos sean independientes.')
        )
        name = Path(row['path']).name
        self.filename.setText(
            f'{self.current + 1}/{total}  ·  {name}  ·  {len(row["boxes"])} obj'
        )
        self._refresh_sublists()
        try:
            self.save()
            return True
        except Exception as error:
            self.error(error)
            return False

    def update_boxes(self, boxes):
        if self.valid():
            row = self.project['images'][self.current]
            self.undo_boxes.setdefault(self.current, []).append(
                (copy.deepcopy(row['boxes']), row['box_labels'].copy(), row.get('reviewed', False))
            )
            if isinstance(boxes, dict):
                row['boxes'], row['box_labels'] = boxes['boxes'], boxes['box_labels']
            else:
                row['boxes'], row['box_labels'] = boxes, [self.canvas.current_label] * len(boxes)
            row['reviewed'] = True
            saved = self.update_row()
            if saved and isinstance(boxes, dict) and boxes.get('added') and self.auto_next.isChecked():
                self.move(1)

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

    def rename_class(self):
        old = self.class_choice.currentText()
        if not self.project or old not in self.project['classes']:
            return self.error('Selecciona la etiqueta que quieres renombrar.')
        name, ok = QInputDialog.getText(self, 'Renombrar etiqueta', 'Nuevo nombre:', text=old)
        name = name.strip()
        if not ok or name == old:
            return
        if not name or len(name) > 80 or name in self.project['classes']:
            return self.error('Usa un nombre distinto, no vacío, de hasta 80 caracteres.')
        index = self.project['classes'].index(old)
        self.project['classes'][index] = name
        for row in self.project['images']:
            row['box_labels'] = [name if label == old else label for label in row['box_labels']]
        self._refresh_after_label_change(name)

    def delete_class(self):
        label = self.class_choice.currentText()
        if not self.project or label not in self.project['classes']:
            return self.error('Selecciona la etiqueta que quieres eliminar.')
        affected = [row for row in self.project['images'] if label in row['box_labels']]
        count = sum(row['box_labels'].count(label) for row in affected)
        if count:
            answer = QMessageBox.question(
                self, 'Eliminar etiqueta',
                f'Eliminar «{label}» borrará {count} rectángulos de {len(affected)} fotos. '
                'Las fotos se conservarán y quedarán pendientes de revisión. '
                'Esta operación no se puede deshacer. ¿Eliminar la etiqueta y sus rectángulos?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.project['classes'].remove(label)
        for row in affected:
            remaining = [(box, value) for box, value in zip(row['boxes'], row['box_labels']) if value != label]
            row['boxes'] = [box for box, _ in remaining]
            row['box_labels'] = [value for _, value in remaining]
            row['reviewed'] = False
        selected = self.project['classes'][0] if self.project['classes'] else ''
        self._refresh_after_label_change(selected)

    def _refresh_after_label_change(self, selected):
        self.package = None
        # Los historiales previos contienen nombres que ya no pertenecen al proyecto.
        self.undo_boxes.clear()
        self.class_choice.blockSignals(True)
        self.class_choice.clear()
        self.class_choice.addItems(self.project['classes'])
        if selected:
            self.class_choice.setCurrentText(selected)
        self.class_choice.blockSignals(False)
        self._on_class_changed(selected)
        self._model_name_lbl.setText('Entrena de nuevo')
        self._model_labels_lbl.setText(' · '.join(self.project['classes']))
        self.test_result.setText('Etiquetas modificadas. Entrena un modelo nuevo para aplicar los cambios.')
        self.images.blockSignals(True)
        for index, row in enumerate(self.project['images']):
            item = self.images.item(index)
            if item:
                item.setText(self.row_text(row))
                item.setForeground(self._row_color(row))
        self.images.blockSignals(False)
        if self.valid():
            self.select(self.current, inherit_partition=False)
            self.update_row()
        else:
            self.save()
        self.statusBar().showMessage('Etiquetas actualizadas. Entrena de nuevo el detector.', 5000)

    def mark_reviewed(self):
        if self.valid():
            self.project['images'][self.current]['reviewed'] = True
            self.update_row()

    def change_group(self):
        if self.valid():
            row = self.project['images'][self.current]
            row['group'] = self.group.text().strip() or row['group']
            self.update_row()

    def exclude(self, value: bool):
        if self.valid():
            self.project['images'][self.current]['excluded'] = value
            self.update_row()

    def move(self, delta: int):
        if self.project and self.project['images']:
            self.images.setCurrentRow(
                max(0, min(self.current + delta, len(self.project['images']) - 1))
            )

    # ─── Worker / entrenamiento ──────────────────────────────

    def run_worker(self, function, ready, training=False):
        if self.worker and self.worker.isRunning():
            return
        self.worker = Worker(function)
        self._work_training = training
        self._work_outcome = None
        self._work_ready = ready
        self.worker.message.connect(self._on_training_message)
        self.worker.failed.connect(self._on_work_failed)
        self.worker.result.connect(self._on_work_result)
        self.worker.finished.connect(self.finished)
        self.editor.setEnabled(False)
        for btn in (self.train_button, self.test_button, self.model_button, self.export_button):
            btn.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._update_status('Entrenando…' if training else 'Procesando…')
        if training:
            self._training_started = time.monotonic()
            self._training_stage = 'Preparando el entrenamiento…'
            self.train_button.setText('⏳ Entrenando…')
            self.train_progress.setRange(0, 0)
            self.epochs.setEnabled(False)
            self.rate.setEnabled(False)
            self._update_training_activity()
            self._activity_timer.start()
        self.worker.start()

    def _update_training_activity(self):
        seconds = int(time.monotonic() - self._training_started)
        self.train_status.setText(f'Entrenando · {seconds // 60:02d}:{seconds % 60:02d} · {self._training_stage}')

    def _on_work_result(self, result):
        try:
            self._work_ready(result)
            self._work_outcome = 'Completado'
        except Exception as error:
            self._on_work_failed(str(error))

    def _on_work_failed(self, text):
        cancelled = self.worker.stop.is_set()
        self._work_outcome = 'Cancelado' if cancelled else 'Error'
        self.report.append(str(text))
        if not cancelled:
            self.error(text)

    def _on_training_message(self, line: str):
        """Procesa líneas del worker; actualiza log y barra de progreso."""
        self.report.append(line)
        if not self._work_training:
            return
        self._training_stage = line
        self._update_training_activity()
        # Detectar "Época X/Y" o "Epoch X/Y" (en inglés) para actualizar la barra
        match = re.search(r'[Éé]poca?\s*(\d+)\s*/\s*(\d+)', line, re.IGNORECASE)
        if not match:
            match = re.search(r'[Ee]poch\s*(\d+)\s*/\s*(\d+)', line)
        if match:
            current_ep = int(match.group(1))
            total_ep = int(match.group(2))
            self.train_progress.setRange(0, total_ep)
            # Los mensajes de lotes describen una época todavía en curso.
            self.train_progress.setValue(current_ep if 'pérdida' in line else current_ep - 1)
            self.train_progress.setFormat(f'Época {current_ep}/{total_ep}')
            self._sb_mode.setText(f'⏳ Entrenando… época {current_ep}/{total_ep}')

    def finished(self):
        self.editor.setEnabled(True)
        for btn in (self.train_button, self.test_button, self.model_button, self.export_button):
            btn.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if self._work_training:
            self._activity_timer.stop()
            outcome = self._work_outcome or 'Interrumpido'
            seconds = int(time.monotonic() - self._training_started)
            self.train_status.setText(f'{outcome} · {seconds // 60:02d}:{seconds % 60:02d}')
            self.train_progress.setRange(0, self.epochs.value())
            if outcome == 'Completado':
                self.train_progress.setValue(self.epochs.value())
            else:
                self.train_progress.setValue(0)
            self.train_progress.setFormat(outcome)
            self.train_button.setText('▶ Entrenar y exportar')
            self.epochs.setEnabled(True)
            self.rate.setEnabled(True)
        self._update_status('Edición')

    def start_train(self):
        if self.worker and self.worker.isRunning():
            return
        if not self.project:
            return self.error('Abre un proyecto de detección.')
        try:
            self.save()
            project = copy.deepcopy(self.project)
            output = self.path.parent / 'resultados'
            epochs, rate = self.epochs.value(), self.rate.value()
            self.report.clear()
            self.train_progress.setValue(0)
            self.train_progress.setRange(0, epochs)
            self.train_progress.setFormat('Iniciando…')

            def work(report, stop):
                report('Comprobando imágenes, etiquetas y grupos…')
                detection_split(project)
                report('Cargando PyTorch y las herramientas de entrenamiento. El primer inicio puede tardar…')
                from aula_ia.object_training import train_objects
                if stop():
                    raise ValueError('Entrenamiento cancelado antes de comenzar.')
                return train_objects(project, output, epochs, rate, report, stop)

            def ready(result):
                path, metrics = result
                self.package = Path(path)
                self.show_metrics(metrics)
                self.show_metrics_card(metrics)

            self.run_worker(
                work, ready, training=True,
            )
        except Exception as error:
            self.error(error)

    def show_metrics(self, metrics: dict):
        """Añade las métricas al log de entrenamiento con colores HTML."""
        result = metrics.get('test_detection')
        if result:
            ap50 = result['ap50']
            if ap50 >= 0.7:
                ap_color = '#3dd68c'
            elif ap50 >= 0.4:
                ap_color = '#f59e0b'
            else:
                ap_color = '#f87171'
            self.report.append(
                f'<br><b>PRUEBA RESERVADA</b>'
                f' · AP50: <span style="color:{ap_color};font-weight:700">{ap50:.1%}</span>'
                f' · Precisión: {result["precision"]:.1%}'
                f' · Recuperación: {result["recall"]:.1%}'
            )
            self.report.append(
                f'Acertados: {result["true_positives"]}  '
                f'Alarmas falsas: {result["false_positives"]}  '
                f'Omitidos: {result["false_negatives"]}  '
                f'Umbral: {result["threshold"]}'
            )
            for label, item in result.get('per_class', {}).items():
                a = item['ap50']
                c = '#3dd68c' if a >= 0.7 else '#f59e0b' if a >= 0.4 else '#f87171'
                self.report.append(
                    f'<span style="color:#94a3b8">{label}</span>: '
                    f'AP50 <span style="color:{c}">{a:.1%}</span>'
                    f' · precisión {item["precision"]:.1%}'
                    f' · recuperación {item["recall"]:.1%}'
                )
            if metrics.get('grouping_note'):
                self.report.append(f'<i style="color:#64748b">{metrics["grouping_note"]}</i>')
        if self.package:
            self.report.append(f'<b>Paquete:</b> {self.package}')
            self.test_result.setText(f'Detector seleccionado: {self.package}')

    def cancel(self):
        if self.worker:
            self.worker.stop.set()
            self.report.append('Cancelación solicitada; espera a completar la operación actual.')
            if self._work_training:
                self._training_stage = 'Cancelación solicitada; terminando la operación actual…'
                self._update_training_activity()
            self.cancel_button.setEnabled(False)

    # ─── Prueba / inferencia ─────────────────────────────────

    def open_model(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Detector de objetos', 'projects', 'Modelo (*.zip)')
        if path:
            self.load_model_path(path)

    def load_model_path(self, path: str):
        def work(report, stop):
            predictor = Predictor(Path(path).read_bytes())
            return predictor.metrics

        def ready(metrics):
            self.package = Path(path)
            self._model_name_lbl.setText(Path(path).name)
            labels = metrics.get('classes', [])
            self._model_labels_lbl.setText('  ·  '.join(labels) if labels else '')
            self.show_metrics(metrics)

        self.run_worker(work, ready)

    def test_image(self):
        if not self.package:
            return self.error('Abre o entrena primero un detector.')
        path, _ = QFileDialog.getOpenFileName(
            self, 'Fotografía de prueba', '', 'Imagen (*.jpg *.jpeg *.png *.webp *.bmp)'
        )
        if not path:
            return
        self.test_image_path(path)

    def test_image_path(self, path):
        if not self.package:
            return self.error('Abre o entrena primero un detector.')
        package, threshold = self.package, self.threshold.value()

        def ready(result):
            detections = result['detections']
            self.test_canvas.set_image(
                path,
                [r['box'] for r in detections],
                [r['label'] for r in detections],
            )
            self.detection_list.clear()
            for det in detections:
                score = det['score']
                color = '#3dd68c' if score >= 0.7 else '#f59e0b' if score >= 0.4 else '#f87171'
                item = QListWidgetItem(f'{det["label"]}: {score:.1%}')
                item.setForeground(QColor(color))
                self.detection_list.addItem(item)
            ms = result.get('inference_ms', '?')
            self.test_result.setText(
                f'{len(detections)} objeto{"s" if len(detections) != 1 else ""} · {ms} ms'
            )

        self.run_worker(
            lambda report, stop: Predictor(package.read_bytes()).predict(path, threshold),
            ready,
        )

    def export_package(self):
        if not self.package:
            return self.error('Abre o entrena primero un detector.')
        path, _ = QFileDialog.getSaveFileName(
            self, 'Paquete para la Raspberry Pi', 'detector-objetos.zip', 'Modelo (*.zip)'
        )
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


# ─────────────────────────────────────────────────────────────
# 5. OBJECT_HELP — HTML de ayuda (sin cambios)
# ─────────────────────────────────────────────────────────────
OBJECT_HELP = '''<h1>Enseñar a localizar y etiquetar objetos</h1>
<p>Elige qué quieres detectar: caras, pelotas, células u otras clases que puedas marcar con rectángulos. Una imagen puede tener cero, uno o varios objetos, incluso de clases distintas.</p>
<h2>El recorrido</h2><ol><li>Crea un proyecto vacío y añade tus propias etiquetas.</li><li>Añade fotografías originales.</li><li>Selecciona una clase y dibuja un rectángulo ajustado alrededor de cada objeto de esa clase.</li><li>Repite con todos los objetos de las clases del proyecto. Confirma la revisión o marca la imagen «sin objetos».</li><li>Revisa los grupos, entrena y evalúa.</li><li>Exporta el ZIP y úsalo con imágenes nuevas o la cámara en la Raspberry Pi.</li></ol>
<h2>Corregir etiquetas</h2><p>«Añadir etiqueta» crea una clase. «Renombrar» cambia el nombre de la etiqueta elegida en todas las fotos. «Eliminar etiqueta» la elimina; si tiene rectángulos, pide confirmar cuántos se borrarán, conserva las fotos y las deja pendientes de revisión. Estos cambios requieren entrenar de nuevo. Para corregir un solo rectángulo, selecciónalo, elige otra clase y pulsa «Cambiar etiqueta del rectángulo». «Borrar rectángulo» o Supr elimina solo el seleccionado. Para cambiar su tamaño, bórralo y dibújalo de nuevo. Puedes deshacer cambios de rectángulos durante la sesión; renombrar o eliminar clases limpia ese historial.</p>
<h2>Qué aprende</h2><p>El modelo aprende las clases y las ubicaciones que le enseñas; no reconoce automáticamente cualquier objeto posible. Reutilizamos un extractor visual SSDLite MobileNetV3 y entrenamos las cabezas de clasificación y coordenadas. El fondo es interno: no debes dibujar rectángulos de fondo.</p>
<h2>Evaluar sin engañarnos</h2><p>Mantén las fotos de una misma sesión, objeto, persona o muestra microscópica en un grupo. No repartas fotos casi iguales entre entrenamiento y prueba. Cada clase necesita ejemplos de varios grupos y todos sus objetos visibles deben estar anotados.</p>
<p>Precisión: de los rectángulos predichos, cuántos tienen clase y posición correctas. Recuperación: de los objetos reales, cuántos encontró. IoU mide el solapamiento. AP50 se calcula por clase con IoU mínimo 0,5; se muestra también su media entre clases.</p>
<h2>Prueba con la cámara</h2><p>Comprueba escenas nuevas, varios objetos y escenas sin objetos de tus clases. Cambia distancia, fondo e iluminación. Baja el umbral y compara objetos recuperados y falsas alarmas. Compara los tiempos en Windows y en la Pi con el mismo ZIP.</p>
<p>Esta versión reduce las imágenes a 320 × 320 para la Pi 4. Objetos muy pequeños o células diminutas en imágenes grandes pueden requerir recortes, más resolución y otro ajuste del modelo. La cámara debe mostrar imágenes comparables a las usadas para entrenar.</p>'''


# ─────────────────────────────────────────────────────────────
# 6. main()
# ─────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    window = ObjectWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
