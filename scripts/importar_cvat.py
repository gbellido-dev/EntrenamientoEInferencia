"""Convertir anotaciones CVAT XML a un proyecto de detección de objetos."""
import argparse
from pathlib import Path

from aula_ia.project import import_cvat, save_project


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('xml', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('El destino ya existe; usa otro nombre para conservar el proyecto guardado.')
    project = import_cvat(args.xml)
    save_project(args.output, project)
    print(f'{len(project["images"])} imágenes · {sum(len(row["boxes"]) for row in project["images"])} rectángulos')
    print(f'Etiquetas importadas: {", ".join(project["classes"])}')
    print(f'Proyecto: {args.output.resolve()}')
