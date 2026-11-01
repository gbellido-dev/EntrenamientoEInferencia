"""Generar un ZIP ligero con el servidor web y su instalador para ARM64."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent
SERVER_FILES = ['aula_ia/__init__.py', 'aula_ia/web.py', 'aula_ia/inference.py', 'aula_ia/camera.py',
                'scripts/__init__.py', 'scripts/instalar_raspi.py', 'instalar_raspi.sh',
                'requirements-raspi.txt', 'requirements-camera.txt', 'docs/raspberry-pi.md',
                'docs/deteccion-objetos.md', 'docs/guia-alumno.md']


def create_package(destination=None):
    destination = Path(destination) if destination else ROOT/'dist'/'AulaIA-RaspberryPi.zip'
    files = SERVER_FILES+[p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'aula_ia'/'static').iterdir()) if p.is_file()]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for relative in files:
            # Normalizar el script para que funcione aunque se empaquete en Windows.
            data = (ROOT/relative).read_bytes()
            if relative.endswith(('.sh', '.py', '.txt', '.md', '.js', '.css', '.html')):
                data = data.replace(b'\r\n', b'\n')
            archive.writestr(relative, data)
        archive.writestr('LEEME.txt', 'Aula IA - instalador Raspberry Pi 4\n\n'
            '1. Extrae TODO el ZIP en una carpeta permanente dentro de tu usuario.\n'
            '2. Abre una terminal en esa carpeta.\n'
            '3. Ejecuta sin sudo: bash instalar_raspi.sh\n'
            '   Para cámara por cinta CSI: bash instalar_raspi.sh --camera csi\n\n'
            'Requiere Raspberry Pi OS ARM64, Python 3.11+ e Internet.\n'
            'El instalador pedirá sudo para paquetes y servicio.\n'
            'Al terminar muestra la URL y la clave de acceso.\n'
            'No muevas la carpeta después: el servicio utiliza esas rutas.\n'
            'Consulta docs/raspberry-pi.md para opciones y diagnóstico.\n')
    return destination.resolve()


if __name__ == '__main__':
    print(create_package())
