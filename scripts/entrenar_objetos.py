"""Entrenar cualquier proyecto de detección por rectángulos desde la terminal."""
import argparse
import json
from pathlib import Path

from aula_ia.project import validate_project
from aula_ia.object_training import train_objects


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', help='Archivo JSON del proyecto de detección')
    parser.add_argument('--epochs', type=int, default=15)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    path = Path(args.project)
    project = validate_project(json.loads(path.read_text(encoding='utf-8')), path)
    output = args.output or path.parent/'resultados'
    package, _ = train_objects(project, output, args.epochs, report=lambda s: print(s, flush=True))
    print(package)
