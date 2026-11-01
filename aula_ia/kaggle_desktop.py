"""Descarga de datasets en un proceso separado, con registro y cancelación."""
import codecs
import importlib.util
import json
from pathlib import Path
import sys
import time

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout,
)

from aula_ia.kaggle import dataset_destination, normalize_handle

ROOT = Path(__file__).resolve().parent.parent


def download_command(handle, base):
    return sys.executable, ['-u', '-m', 'scripts.descargar_kaggle', '--handle', handle,
                            '--destination', str(base)]


class KaggleDownloadDialog(QDialog):
    images_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Descargar un dataset de Kaggle')
        self.resize(760, 600)
        self.result_info = None
        self._cancelled = False
        self._secret = ''
        self._pending = ''
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(ROOT))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.kill_timer = QTimer(self)
        self.kill_timer.setSingleShot(True)
        self.kill_timer.setInterval(1500)
        self.kill_timer.timeout.connect(self.process.kill)

        layout = QVBoxLayout(self)
        intro = QLabel('Pega el enlace de un dataset o su identificador propietario/dataset. '
                       'Se descargan sus archivos, sean imágenes, tablas u otros tipos de datos.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.handle = QLineEdit()
        self.handle.setPlaceholderText('https://www.kaggle.com/datasets/propietario/dataset')
        form.addRow('Dataset:', self.handle)
        destination_row = QHBoxLayout()
        self.destination = QLineEdit(str(ROOT/'datasets'))
        self.browse_button = QPushButton('Elegir carpeta…')
        self.browse_button.clicked.connect(self._choose_destination)
        destination_row.addWidget(self.destination, 1)
        destination_row.addWidget(self.browse_button)
        form.addRow('Guardar en:', destination_row)
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText('Opcional; solo se usa para esta descarga')
        form.addRow('Token Kaggle:', self.token)
        layout.addLayout(form)
        note = QLabel('Los archivos se guardan en subcarpetas por propietario, dataset y versión. '
                      'Puedes dejar el token vacío para datasets públicos que no requieran acceso. '
                      'Si Kaggle pide permisos o aceptar condiciones, visita primero su página.')
        note.setWordWrap(True)
        layout.addWidget(note)
        links = QHBoxLayout()
        browse_kaggle = QPushButton('Buscar datasets en Kaggle')
        browse_kaggle.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://www.kaggle.com/datasets')))
        auth = QPushButton('Obtener token en Kaggle')
        auth.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://www.kaggle.com/settings/api')))
        links.addWidget(browse_kaggle)
        links.addWidget(auth)
        layout.addLayout(links)
        actions = QHBoxLayout()
        self.download_button = QPushButton('Descargar dataset')
        self.download_button.clicked.connect(self.start_download)
        self.cancel_button = QPushButton('Cancelar descarga')
        self.cancel_button.clicked.connect(self.cancel_download)
        self.cancel_button.setEnabled(False)
        actions.addWidget(self.download_button)
        actions.addWidget(self.cancel_button)
        layout.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.status = QLabel('En espera.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(500)
        layout.addWidget(self.log, 1)
        results = QHBoxLayout()
        self.open_button = QPushButton('Abrir carpeta descargada')
        self.open_button.clicked.connect(self.open_folder)
        self.open_button.setEnabled(False)
        self.import_button = QPushButton('Añadir imágenes al proyecto…')
        self.import_button.clicked.connect(self.use_images)
        self.import_button.setEnabled(False)
        close = QPushButton('Cerrar')
        close.clicked.connect(self.reject)
        results.addWidget(self.open_button)
        results.addWidget(self.import_button)
        results.addWidget(close)
        layout.addLayout(results)

    def _choose_destination(self):
        folder = QFileDialog.getExistingDirectory(self, 'Carpeta base para datasets', self.destination.text())
        if folder:
            self.destination.setText(folder)

    def _busy(self, value):
        for widget in (self.handle, self.destination, self.browse_button, self.token, self.download_button):
            widget.setEnabled(not value)
        self.cancel_button.setEnabled(value)
        self.progress.setRange(0, 0 if value else 1)

    def start_download(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        try:
            handle = normalize_handle(self.handle.text())
            if not self.destination.text().strip():
                raise ValueError('Elige dónde guardar los datasets.')
            base = Path(self.destination.text()).expanduser().resolve()
            if base.exists() and not base.is_dir():
                raise ValueError('El destino debe ser una carpeta.')
            if importlib.util.find_spec('kagglehub') is None:
                raise ValueError('Falta kagglehub. Cierra la aplicación, ejecuta instalar_windows.cmd y vuelve a abrirla.')
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.handle.setText(handle)
        self.result_info = None
        self._cancelled = False
        self._pending = ''
        self._decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.log.clear()
        self.log.appendPlainText(f'Dataset: {handle}\nDestino: {dataset_destination(base, handle)}')
        self.open_button.setEnabled(False)
        self.import_button.setEnabled(False)
        environment = QProcessEnvironment.systemEnvironment()
        self._secret = self.token.text().strip() or environment.value('KAGGLE_API_TOKEN')
        if self.token.text().strip():
            environment.insert('KAGGLE_API_TOKEN', self._secret)
        environment.insert('PYTHONIOENCODING', 'utf-8')
        self.process.setProcessEnvironment(environment)
        self.token.clear()
        self._busy(True)
        self._started = time.monotonic()
        self._tick()
        self.timer.start()
        program, arguments = download_command(handle, base)
        self.process.start(program, arguments)
        self.process.closeWriteChannel()

    def _tick(self):
        seconds = int(time.monotonic() - self._started)
        phase = 'Cancelando' if self._cancelled else 'Descargando y preparando archivos'
        self.status.setText(f'{phase} · {seconds // 60:02d}:{seconds % 60:02d} · Consulta el registro para ver los detalles.')

    def _read_output(self):
        text = self._decoder.decode(bytes(self.process.readAllStandardOutput()))
        self._pending += text.replace('\r', '\n')
        while '\n' in self._pending:
            line, self._pending = self._pending.split('\n', 1)
            self._line(line)

    def _line(self, line):
        if line.startswith('AULA_KAGGLE_RESULT:'):
            try:
                self.result_info = json.loads(line.split(':', 1)[1])
            except ValueError:
                self.log.appendPlainText('No se pudo interpretar el resultado de la descarga.')
        elif line.strip():
            self.log.appendPlainText(line.replace(self._secret, '[token oculto]') if self._secret else line)

    def _finished(self, exit_code, exit_status):
        self.kill_timer.stop()
        self._read_output()
        if self._pending:
            self._line(self._pending)
            self._pending = ''
        self.timer.stop()
        self._busy(False)
        self.process.setProcessEnvironment(QProcessEnvironment())
        self._secret = ''
        if self._cancelled:
            self.result_info = None
            self.status.setText('Descarga cancelada. Puede haber archivos parciales en la carpeta de destino; puedes reintentar.')
        elif exit_code != 0 or exit_status != QProcess.ExitStatus.NormalExit or not self.result_info:
            self.result_info = None
            self.status.setText('No se completó la descarga. Revisa el registro, el enlace y los permisos de Kaggle. '
                                'Si pide acceso, genera un token o acepta las condiciones en la página del dataset.')
        else:
            info = self.result_info
            size = info['bytes_unpacked'] / (1024 * 1024)
            message = f"Descarga completada: {info['file_count']} archivos · {info['image_count']} imágenes · {size:.1f} MiB."
            if not info['image_count']:
                message += ' Este dataset no contiene imágenes compatibles con el editor de objetos.'
            self.status.setText(message)
            self.progress.setValue(1)
            self.open_button.setEnabled(True)
            self.import_button.setEnabled(info['image_count'] > 0)

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.timer.stop()
            self._busy(False)
            self._secret = ''
            self.process.setProcessEnvironment(QProcessEnvironment())
            self.status.setText('No se pudo iniciar Python para descargar. Revisa la instalación de Windows.')

    def cancel_download(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self._cancelled = True
            self.cancel_button.setEnabled(False)
            self._tick()
            self.process.terminate()
            self.kill_timer.start()

    def open_folder(self):
        if self.result_info:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.result_info['folder']))

    def use_images(self):
        if self.result_info and self.result_info['image_count']:
            folder = self.result_info['folder']
            self.accept()
            self.images_requested.emit(folder)

    def reject(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.cancel_download()
            return
        super().reject()

    def closeEvent(self, event):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.cancel_download()
            event.ignore()
        else:
            event.accept()
