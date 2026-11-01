from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from scripts.instalar_raspi import MARKER, Settings, install, main, read_config, render_service, write_config
from scripts.crear_paquete_raspi import create_package


class FakeRunner:
    def __init__(self, unit, existing=False, fail_pip=False, fail_restart=False):
        self.unit = unit
        self.existing = existing
        self.fail_pip = fail_pip
        self.fail_restart = fail_restart
        self.commands = []

    def run(self, command, *, check=True, capture=False):
        command = [str(part) for part in command]
        self.commands.append(command)
        if command[:2] == ['systemctl', 'show']:
            return SimpleNamespace(returncode=0, stdout=str(self.unit) if self.existing else '')
        if command[:2] in (['systemctl', 'is-active'], ['systemctl', 'is-enabled']):
            return SimpleNamespace(returncode=0 if self.existing or self.unit.exists() else 1, stdout='')
        if command[:2] == ['sudo', 'install']:
            self.unit.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(command[-2], command[-1])
        elif command[:3] == ['sudo', 'rm', '-f']:
            self.unit.unlink(missing_ok=True)
        if self.fail_pip and command[1:5] == ['-m', 'pip', 'install', '--only-binary=:all:']:
            raise subprocess.CalledProcessError(1, ['pip', 'install'])
        if self.fail_restart and command[:3] == ['sudo', 'systemctl', 'restart']:
            self.fail_restart = False
            raise subprocess.CalledProcessError(1, command)
        if len(command) > 2 and command[-2:] == ['-c', 'import numpy; print(numpy.__version__)']:
            return SimpleNamespace(returncode=0, stdout='1.24.2\n')
        return SimpleNamespace(returncode=0, stdout='')


def settings(folder, camera='usb'):
    folder = Path(folder)
    return Settings(folder/'app', folder/'home', 'alumno', camera=camera,
                    unit_path=folder/'systemd'/'aula-ia.service', env_id=camera+'-test')


class InstallerTests(unittest.TestCase):
    def test_service_paths_and_dry_run_no_mutations(self):
        with tempfile.TemporaryDirectory(prefix='aula con espacios ') as folder:
            config = settings(folder)
            unit = render_service(config)
            self.assertIn('User=alumno', unit)
            self.assertIn('SupplementaryGroups=video', unit)
            self.assertIn('WorkingDirectory="'+str(config.root).replace('\\', '\\\\')+'"', unit)
            self.assertIn('--port 8000', unit)
            with patch('scripts.instalar_raspi.ROOT', config.root), patch('scripts.instalar_raspi.Path.home', return_value=config.home), \
                    patch('scripts.instalar_raspi.Runner.run') as run, redirect_stdout(StringIO()) as output:
                self.assertEqual(main(['--dry-run', '--camera', 'csi']), 0)
                run.assert_not_called()
                self.assertIn('SIMULACIÓN', output.getvalue())
                self.assertFalse(config.root.exists())
                self.assertFalse(config.home.exists())

    def test_install_keeps_existing_key_and_model(self):
        with tempfile.TemporaryDirectory() as folder:
            config = settings(folder)
            config.data.mkdir(parents=True)
            model = config.data/'active.zip'
            model.write_bytes(b'modelo del alumno')
            write_config(config, 'clave-del-aula-conservada')
            runner = FakeRunner(config.unit_path)
            with patch('scripts.instalar_raspi.wait_for_web') as health:
                token = install(config, runner)
                health.assert_called_once_with(8000)
            self.assertEqual(token, 'clave-del-aula-conservada')
            self.assertEqual(read_config(config.config)['AULA_TOKEN'], token)
            self.assertEqual(model.read_bytes(), b'modelo del alumno')
            self.assertIn(['sudo', 'systemctl', 'enable', 'aula-ia.service'], runner.commands)
            self.assertTrue(config.unit_path.read_text(encoding='utf-8').startswith(MARKER))

    def test_pip_failure_does_not_replace_previous_service(self):
        with tempfile.TemporaryDirectory() as folder:
            config = settings(folder)
            config.unit_path.parent.mkdir(parents=True)
            previous = MARKER+'\nservicio anterior\n'
            config.unit_path.write_text(previous, encoding='utf-8')
            write_config(config, 'clave-conservada-123456')
            previous_config = config.config.read_bytes()
            runner = FakeRunner(config.unit_path, existing=True, fail_pip=True)
            with self.assertRaises(subprocess.CalledProcessError):
                install(config, runner)
            self.assertEqual(config.unit_path.read_text(encoding='utf-8'), previous)
            self.assertEqual(config.config.read_bytes(), previous_config)
            self.assertFalse(any(command[:3] == ['sudo', 'systemctl', 'stop'] for command in runner.commands))

    def test_failed_restart_restores_previous_service_and_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            config = settings(folder)
            config.unit_path.parent.mkdir(parents=True)
            previous = MARKER+'\nservicio anterior\n'
            config.unit_path.write_text(previous, encoding='utf-8')
            write_config(config, 'clave-anterior-123456')
            previous_config = config.config.read_bytes()
            runner = FakeRunner(config.unit_path, existing=True, fail_restart=True)
            with self.assertRaisesRegex(RuntimeError, 'Configuración anterior restaurada'):
                install(config, runner)
            self.assertEqual(config.unit_path.read_text(encoding='utf-8'), previous)
            self.assertEqual(config.config.read_bytes(), previous_config)
            self.assertIn(['sudo', 'systemctl', 'start', 'aula-ia.service'], runner.commands)

    def test_csi_preserves_system_numpy_and_uses_system_site_packages(self):
        with tempfile.TemporaryDirectory() as folder:
            config = settings(folder, 'csi')
            runner = FakeRunner(config.unit_path)
            with patch('scripts.instalar_raspi.wait_for_web'):
                install(config, runner)
            self.assertTrue(any('--system-site-packages' in command for command in runner.commands))
            self.assertEqual((config.venv/'aula-constraints.txt').read_text(encoding='utf-8'), 'numpy==1.24.2\n')
            pip = next(command for command in runner.commands if '--only-binary=:all:' in command)
            self.assertIn('-c', pip)
            self.assertTrue(pip[-1].endswith('requirements-raspi.txt'))

    def test_failed_health_on_first_install_removes_new_unit_and_key(self):
        with tempfile.TemporaryDirectory() as folder:
            config = settings(folder)
            runner = FakeRunner(config.unit_path)
            with patch('scripts.instalar_raspi.wait_for_web', side_effect=RuntimeError('Sin respuesta')):
                with self.assertRaisesRegex(RuntimeError, 'Configuración anterior restaurada'):
                    install(config, runner)
            self.assertFalse(config.unit_path.exists())
            self.assertFalse(config.config.exists())
            self.assertTrue(config.data.exists())

    def test_runtime_package_excludes_training_data_and_desktop(self):
        with tempfile.TemporaryDirectory() as folder:
            package = create_package(Path(folder)/'raspi.zip')
            with zipfile.ZipFile(package) as archive:
                names = set(archive.namelist())
                self.assertIn('instalar_raspi.sh', names)
                self.assertIn('scripts/instalar_raspi.py', names)
                self.assertIn('aula_ia/static/app.js', names)
                self.assertIn('LEEME.txt', names)
                self.assertNotIn('aula_ia/object_training.py', names)
                self.assertNotIn('aula_ia/object_desktop.py', names)
                self.assertFalse(any(name.startswith(('datasets/', 'projects/', '.venv/', '.git/')) for name in names))
                self.assertNotIn(b'\r\n', archive.read('instalar_raspi.sh'))


if __name__ == '__main__':
    unittest.main()
