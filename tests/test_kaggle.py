import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

from aula_ia.kaggle import dataset_destination, normalize_handle


class KaggleTests(unittest.TestCase):
    def test_generic_handles_urls_versions_and_invalid_input(self):
        self.assertEqual(normalize_handle(' vivek468/superstore-dataset-final '),
                         'vivek468/superstore-dataset-final')
        self.assertEqual(normalize_handle('https://www.kaggle.com/datasets/owner/data/versions/12?x=1#data'),
                         'owner/data/versions/12')
        self.assertEqual(normalize_handle('https://kaggle.com/datasets/other/cells/'), 'other/cells')
        for value in ('', 'owner', '../data', 'owner/../../data', 'owner/data/versions/0',
                      'https://example.com/datasets/owner/data', 'https://kaggle.com.evil.test/datasets/a/b',
                      'https://www.kaggle.com/competitions/a', 'import kagglehub', 'owner/data; echo hello'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_handle(value)
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(dataset_destination(folder, 'owner/data/versions/2'),
                             Path(folder).resolve()/'owner'/'data'/'version-2')
            self.assertNotEqual(dataset_destination(folder, 'owner/data'), dataset_destination(folder, 'other/data'))

    def test_cli_downloads_selected_dataset_and_inventories_without_importing_labels(self):
        from scripts.descargar_kaggle import main
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)/'descargas'
            def download(handle, *, output_dir):
                self.assertEqual(handle, 'arbitrary/data/versions/4')
                target = Path(output_dir)
                self.assertEqual(target, base/'arbitrary'/'data'/'version-4')
                target.mkdir(parents=True)
                Image.new('RGB', (20, 20), 'red').save(target/'foto.png')
                (target/'tabla.csv').write_text('nombre,valor\ncélula,1\n', encoding='cp1252')
                (target/'.complete').mkdir()
                (target/'.complete'/'4.complete').write_text('')
                return str(target)
            with patch.dict(sys.modules, {'kagglehub': SimpleNamespace(dataset_download=download)}), \
                    patch.object(sys, 'argv', ['descargar_kaggle', '--handle',
                                             'https://www.kaggle.com/datasets/arbitrary/data/versions/4',
                                             '--destination', str(base)]), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                main()
            line = next(line for line in output.getvalue().splitlines() if line.startswith('AULA_KAGGLE_RESULT:'))
            result = json.loads(line.split(':', 1)[1])
            self.assertEqual(result['file_count'], 2)
            self.assertEqual(result['image_count'], 1)
            inventory = json.loads(Path(result['inventory']).read_text(encoding='utf-8'))
            self.assertEqual(inventory['annotation_samples'][0]['columns'], ['nombre', 'valor'])
            self.assertNotIn('classes', inventory)
            self.assertFalse(list(base.rglob('proyecto.json')))

    def test_download_dialog_runs_responsively_and_handles_images_tables_failure_and_cancel(self):
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        from PySide6.QtCore import QProcess, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from aula_ia.kaggle_desktop import KaggleDownloadDialog
        app = QApplication.instance() or QApplication([])

        def wait_until(predicate):
            deadline = time.monotonic() + 7
            while not predicate() and time.monotonic() < deadline:
                QTest.qWait(10)
            self.assertTrue(predicate())

        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            script = folder/'simulador.py'
            script.write_text('''import json, os, sys, time
from pathlib import Path
mode, destination = sys.argv[1:]
print('Preparación de descarga', flush=True)
print('token=' + os.environ.get('KAGGLE_API_TOKEN', ''), flush=True)
if mode == 'cancel':
    time.sleep(30)
if mode == 'failure':
    print('403: acceso requerido', flush=True)
    sys.exit(1)
Path(destination).mkdir(parents=True, exist_ok=True)
print('AULA_KAGGLE_RESULT:' + json.dumps({'folder': destination, 'inventory': destination + '-inventario.json',
      'file_count': 2, 'image_count': int(mode == 'images'), 'bytes_unpacked': 1200, 'extensions': {}}), flush=True)
''', encoding='utf-8')
            for mode in ('images', 'tables', 'failure', 'cancel'):
                with self.subTest(mode=mode):
                    dialog = KaggleDownloadDialog()
                    dialog.show()
                    dialog.handle.setText('https://www.kaggle.com/datasets/owner/any-data')
                    dialog.destination.setText(str(folder/'datasets'))
                    secret = 'token-simulado-no-real'
                    dialog.token.setText(secret)
                    try:
                        with patch('aula_ia.kaggle_desktop.download_command',
                                   return_value=(sys.executable, ['-u', str(script), mode, str(folder/mode)])), \
                                patch('aula_ia.kaggle_desktop.importlib.util.find_spec', return_value=object()):
                            dialog.start_download()
                        self.assertFalse(dialog.download_button.isEnabled())
                        self.assertEqual(dialog.progress.maximum(), 0)
                        wait_until(lambda: 'Preparación' in dialog.log.toPlainText())
                        if mode == 'cancel':
                            QTest.qWait(1100)
                            self.assertIn('00:01', dialog.status.text())
                            QTest.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)
                        wait_until(lambda: dialog.process.state() == QProcess.ProcessState.NotRunning and not dialog.timer.isActive())
                        self.assertTrue(dialog.download_button.isEnabled())
                        self.assertFalse(dialog.cancel_button.isEnabled())
                        self.assertEqual(dialog.token.text(), '')
                        self.assertNotIn(secret, dialog.log.toPlainText())
                        self.assertIn('[token oculto]', dialog.log.toPlainText())
                        self.assertEqual(dialog.process.processEnvironment().value('KAGGLE_API_TOKEN'), '')
                        if mode in ('images', 'tables'):
                            self.assertIn('Descarga completada', dialog.status.text())
                            self.assertTrue(dialog.open_button.isEnabled())
                            self.assertEqual(dialog.import_button.isEnabled(), mode == 'images')
                            if mode == 'tables':
                                self.assertIn('no contiene imágenes', dialog.status.text())
                            else:
                                requested = []
                                dialog.images_requested.connect(requested.append)
                                dialog.use_images()
                                self.assertEqual(requested, [str(folder/mode)])
                        else:
                            self.assertIsNone(dialog.result_info)
                            self.assertFalse(dialog.import_button.isEnabled())
                            self.assertIn('cancelada' if mode == 'cancel' else 'No se completó', dialog.status.text())
                    finally:
                        if dialog.process.state() != QProcess.ProcessState.NotRunning:
                            dialog.process.kill()
                            dialog.process.waitForFinished(3000)
                        app.processEvents()
                        dialog.close()


if __name__ == '__main__':
    unittest.main()
