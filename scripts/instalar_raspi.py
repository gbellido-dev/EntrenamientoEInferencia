"""Instalador de servidor para Raspberry Pi OS ARM64; ejecutar sin sudo."""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import getpass
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

MARKER = '# Gestionado por Aula IA installer v1'
SERVICE = 'aula-ia.service'
ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    root: Path
    home: Path
    username: str
    camera: str = 'usb'
    camera_index: int = 0
    port: int = 8000
    unit_path: Path = Path('/etc/systemd/system/aula-ia.service')
    video_group: bool = True
    env_id: str = ''

    @property
    def config(self):
        return self.home/'.config'/'aula-ia'/'server.env'

    @property
    def data(self):
        return self.root/'raspi-data'

    @property
    def venv(self):
        return self.root/'.raspi-envs'/(self.env_id or f'{self.camera}-nuevo')


class Runner:
    def run(self, command, *, check=True, capture=False):
        print('+ '+shlex.join([str(part) for part in command]), flush=True)
        return subprocess.run([str(part) for part in command], check=check,
                              capture_output=capture, text=True)


def quote(value, command=False):
    value = str(value)
    if any(char in value for char in '\n\r\0'):
        raise ValueError('Las rutas y valores no pueden contener saltos de línea.')
    value = value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    if command:
        value = value.replace('$', '$$')
    return '"'+value+'"'


def render_service(settings):
    if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_.-]*\$?', settings.username):
        raise ValueError('El nombre de usuario no es compatible con el servicio.')
    video = 'SupplementaryGroups=video\n' if settings.video_group else ''
    return f'''{MARKER}
[Unit]
Description=Aula IA - deteccion de objetos
After=network.target

[Service]
Type=simple
User={settings.username}
{video}WorkingDirectory={quote(settings.root)}
EnvironmentFile={quote(settings.config)}
ExecStart={quote(settings.venv/'bin'/'python', command=True)} -m aula_ia.web --host 0.0.0.0 --port {settings.port}
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
UMask=0077

[Install]
WantedBy=multi-user.target
'''


def read_config(path):
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator or not re.fullmatch(r'AULA_[A-Z_]+', key):
            raise ValueError(f'Configuración no reconocida en {path}; revísala antes de reinstalar.')
        values[key] = json.loads(value) if value.startswith('"') else value
        if not isinstance(values[key], str) or any(char in values[key] for char in '\r\n\0'):
            raise ValueError('Valor inválido en el archivo de configuración.')
    return values


def write_config(settings, token):
    values = {'AULA_TOKEN': token, 'AULA_DATA': str(settings.data),
              'AULA_CAMERA': settings.camera, 'AULA_CAMERA_INDEX': str(settings.camera_index),
              'AULA_PORT': str(settings.port)}
    content = MARKER+'\n'+''.join(f'{key}={json.dumps(value, ensure_ascii=False)}\n' for key, value in values.items())
    settings.config.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=settings.config.parent, prefix='.server-')
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, settings.config)
    finally:
        Path(temporary).unlink(missing_ok=True)


def preflight(root):
    if platform.system() != 'Linux' or platform.machine().lower() not in ('aarch64', 'arm64') or struct.calcsize('P') != 8:
        raise ValueError('Este instalador requiere Raspberry Pi OS de 64 bits (ARM64). Usa --dry-run para ver el plan.')
    if sys.version_info < (3, 11):
        raise ValueError('Se necesita Python 3.11 o superior. Utiliza una versión reciente de Raspberry Pi OS de 64 bits.')
    if os.geteuid() == 0:
        raise ValueError('Ejecuta sin sudo: bash instalar_raspi.sh. Se pedirá sudo solo para paquetes y servicio.')
    if not shutil.which('apt-get') or not shutil.which('systemctl') or not Path('/run/systemd/system').exists():
        raise ValueError('Se necesita un sistema Debian/Raspberry Pi OS con APT y systemd en funcionamiento.')
    if not shutil.which('sudo'):
        raise ValueError('El usuario necesita sudo para instalar los paquetes y el servicio.')
    for path in ('aula_ia/web.py', 'aula_ia/static/index.html', 'requirements-raspi.txt', 'requirements-camera.txt'):
        if not (root/path).is_file():
            raise ValueError(f'Falta {path}. Extrae el paquete completo antes de ejecutar el instalador.')


def wait_for_web(port):
    deadline = time.monotonic()+20
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/status', timeout=2) as response:
                result = json.load(response)
                if type(result.get('ready')) is bool:
                    return
        except (OSError, ValueError):
            pass
        time.sleep(.5)
    raise RuntimeError('El servidor no respondió a la comprobación local de arranque.')


def install(settings, runner):
    """Preparar un entorno nuevo antes de sustituir la configuración del servicio."""
    if settings.venv.exists():
        raise ValueError('El directorio del nuevo entorno ya existe; vuelve a ejecutar el instalador.')
    previous_unit = settings.unit_path.read_text(encoding='utf-8') if settings.unit_path.exists() else None
    if previous_unit is not None and not previous_unit.startswith(MARKER):
        raise ValueError('Ya existe aula-ia.service creado manualmente. Conserva su configuración y retíralo o renómbralo antes de usar este instalador.')
    fragment = runner.run(['systemctl', 'show', '-p', 'FragmentPath', '--value', SERVICE], check=False, capture=True)
    if fragment.stdout.strip() and previous_unit is None:
        raise ValueError('Hay otro servicio aula-ia instalado fuera de la ruta gestionada; no se sustituirá.')
    old_values = read_config(settings.config)
    token = old_values.get('AULA_TOKEN') or secrets.token_urlsafe(24)
    if len(token) < 12:
        raise ValueError('La clave existente tiene menos de 12 caracteres; revisa server.env.')
    old_config = settings.config.read_bytes() if settings.config.exists() else None
    apt = ['python3-venv', 'python3-pip', 'libgomp1']
    if settings.camera == 'csi':
        apt.extend(['python3-picamera2', 'python3-opencv', 'python3-numpy'])
    runner.run(['sudo', 'apt-get', 'update'])
    runner.run(['sudo', 'apt-get', 'install', '-y', *apt])
    settings.venv.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'venv']
    if settings.camera == 'csi':
        command.append('--system-site-packages')
    runner.run([*command, str(settings.venv)])
    python = settings.venv/'bin'/'python'
    pip = [str(python), '-m', 'pip', 'install', '--only-binary=:all:']
    if settings.camera == 'csi':
        # Conservar la versión de NumPy del sistema que usa OpenCV/Picamera2.
        version = runner.run([sys.executable, '-c', 'import numpy; print(numpy.__version__)'], capture=True).stdout.strip()
        if not re.fullmatch(r'[0-9][A-Za-z0-9.+_-]*', version):
            raise ValueError('No se pudo comprobar NumPy del sistema para CSI.')
        settings.venv.mkdir(parents=True, exist_ok=True)
        constraint = settings.venv/'aula-constraints.txt'
        constraint.write_text(f'numpy=={version}\n', encoding='utf-8')
        pip.extend(['-c', str(constraint)])
    requirements = 'requirements-camera.txt' if settings.camera == 'usb' else 'requirements-raspi.txt'
    runner.run([*pip, '-r', str(settings.root/requirements)])
    modules = 'import numpy, PIL, onnxruntime, fastapi, uvicorn, cv2'
    if settings.camera == 'csi':
        modules += '; import picamera2'
    runner.run([str(python), '-c', modules])
    runner.run([str(python), '-m', 'pip', 'check'])
    was_active = runner.run(['systemctl', 'is-active', '--quiet', SERVICE], check=False, capture=True).returncode == 0
    was_enabled = runner.run(['systemctl', 'is-enabled', '--quiet', SERVICE], check=False, capture=True).returncode == 0
    settings.data.mkdir(parents=True, exist_ok=True)
    unit = render_service(settings)
    # No se toca la cámara ni se carga ningún modelo durante la instalación.
    with tempfile.TemporaryDirectory(prefix='aula-ia-') as temporary:
        unit_file = Path(temporary)/SERVICE
        unit_file.write_text(unit, encoding='utf-8', newline='\n')
        restart_requested = False
        try:
            write_config(settings, token)
            runner.run(['sudo', 'install', '-m', '644', str(unit_file), str(settings.unit_path)])
            runner.run(['sudo', 'systemctl', 'daemon-reload'])
            runner.run(['sudo', 'systemctl', 'enable', SERVICE])
            restart_requested = True
            runner.run(['sudo', 'systemctl', 'restart', SERVICE])
            if runner.run(['systemctl', 'is-active', '--quiet', SERVICE], check=False, capture=True).returncode != 0:
                raise RuntimeError('El servicio no permanece activo.')
            wait_for_web(settings.port)
        except Exception as original:
            print('No se completó el arranque. Restaurando la configuración anterior…', file=sys.stderr)
            try:
                if restart_requested:
                    runner.run(['sudo', 'systemctl', 'stop', SERVICE], check=False)
                if not was_enabled:
                    runner.run(['sudo', 'systemctl', 'disable', SERVICE], check=False)
                if previous_unit is not None:
                    unit_file.write_text(previous_unit, encoding='utf-8', newline='\n')
                    runner.run(['sudo', 'install', '-m', '644', str(unit_file), str(settings.unit_path)])
                else:
                    runner.run(['sudo', 'rm', '-f', '--', str(settings.unit_path)])
                if old_config is not None:
                    settings.config.write_bytes(old_config)
                    os.chmod(settings.config, 0o600)
                else:
                    settings.config.unlink(missing_ok=True)
                runner.run(['sudo', 'systemctl', 'daemon-reload'])
                if was_active and restart_requested:
                    runner.run(['sudo', 'systemctl', 'start', SERVICE])
            except Exception as rollback:
                raise RuntimeError(f'Instalación fallida: {original}. La restauración también falló: {rollback}') from original
            raise RuntimeError(f'Instalación fallida: {original}. Configuración anterior restaurada.') from original
    return token


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera', choices=['usb', 'csi'], help='USB por defecto; se conserva el tipo anterior al reinstalar')
    parser.add_argument('--camera-index', type=int, help='Índice del dispositivo (0 por defecto)')
    parser.add_argument('--port', type=int, help='Puerto web (8000 por defecto)')
    parser.add_argument('--dry-run', action='store_true', help='Mostrar el plan sin instalar ni modificar nada')
    args = parser.parse_args(argv)
    home = Path.home()
    try:
        if not args.dry_run:
            preflight(ROOT)
        previous = read_config(home/'.config'/'aula-ia'/'server.env') if not args.dry_run else {}
        camera = args.camera or previous.get('AULA_CAMERA', 'usb')
        port = args.port if args.port is not None else int(previous.get('AULA_PORT', '8000'))
        index = args.camera_index if args.camera_index is not None else int(previous.get('AULA_CAMERA_INDEX', '0'))
        if camera not in ('usb', 'csi') or not 1024 <= port <= 65535 or not 0 <= index <= 20:
            raise ValueError('Usa cámara usb/csi, puerto 1024–65535 e índice 0–20.')
        username = getpass.getuser()
        video_group = True
        if not args.dry_run:
            import pwd
            import grp
            username = pwd.getpwuid(os.getuid()).pw_name
            try:
                grp.getgrnam('video')
            except KeyError:
                video_group = False
        env_id = camera+'-'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')+'-'+secrets.token_hex(3)
        settings = Settings(ROOT, home, username, camera, index, port, video_group=video_group, env_id=env_id)
        if args.dry_run:
            print('SIMULACIÓN: no se modifica el equipo.')
            print(f'Cámara: {camera} · índice {index} · puerto {port}')
            print('Pasos: APT -> entorno Python nuevo -> dependencias -> comprobar imports -> clave/configuracion -> servicio -> comprobar web.')
            print(render_service(settings))
            return 0
        print(f'Instalando Aula IA · cámara {camera} · puerto {port}', flush=True)
        token = install(settings, Runner())
        print('\nINSTALACIÓN COMPLETADA · servicio aula-ia activo y habilitado al arrancar.')
        try:
            addresses = subprocess.check_output(['hostname', '-I'], text=True).split()
            addresses = [str(ipaddress.IPv4Address(item)) for item in addresses if ':' not in item]
        except (OSError, ValueError, subprocess.CalledProcessError):
            addresses = []
        for address in addresses or ['raspberrypi.local']:
            print(f'Web: http://{address}:{port}')
        print(f'Clave del aula: {token}')
        print(f'Configuración privada: {settings.config}')
        print('Carga detector-objetos.zip desde la web. La cámara se abre solo al pulsar Iniciar.')
        print('Diagnóstico: journalctl -u aula-ia -n 60 --no-pager')
        print('Para detener: sudo systemctl stop aula-ia')
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        print('No se borran los modelos ni las imágenes. Revisa los mensajes antes de repetir.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
