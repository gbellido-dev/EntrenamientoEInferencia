"""Descargar el conjunto indicado e inventariarlo sin reinterpretar sus etiquetas.

Uso: python -m scripts.descargar_kaggle --handle propietario/conjunto
     python -m scripts.descargar_kaggle --inspect-only CARPETA
"""
import argparse
from collections import Counter
import csv
import json
import os
from pathlib import Path
from aula_ia.kaggle import dataset_destination, normalize_handle

ROOT = Path(__file__).resolve().parent.parent
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}


def inspect_dataset(folder):
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise ValueError(f'No existe la carpeta: {folder}')
    counts = Counter()
    directories = Counter()
    examples = {}
    size = 0
    for path in sorted(folder.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(folder)
        if relative.parts[0] == '.complete':
            continue  # Marcadores de caché de kagglehub, no archivos del dataset.
        extension = path.suffix.lower() or '(sin extensión)'
        counts[extension] += 1
        size += path.stat().st_size
        directories[str(relative.parent)] += 1
        examples.setdefault(extension, [])
        if len(examples[extension]) < 5:
            examples[extension].append(relative.as_posix())
    annotation_info = []
    for extension in ('.csv', '.json', '.yaml', '.yml', '.txt', '.xml'):
        for relative in examples.get(extension, [])[:2]:
            path = folder/relative
            item = {'file': relative}
            try:
                # Limitar las lecturas: no cargar grandes tablas completas.
                with path.open(encoding='utf-8-sig', errors='replace') as stream:
                    prefix = stream.read(32768)
                if extension == '.csv':
                    item['columns'] = next(csv.reader(prefix.splitlines()), [])
                elif extension == '.json' and path.stat().st_size <= 32768:
                    value = json.loads(prefix)
                    item['structure'] = type(value).__name__
                    if isinstance(value, dict):
                        item['keys'] = list(value)[:30]
                    elif isinstance(value, list) and value and isinstance(value[0], dict):
                        item['item_keys'] = list(value[0])[:30]
                elif extension == '.xml':
                    item['pascal_voc_boxes'] = '<bndbox>' in prefix
                elif extension == '.txt':
                    lines = [line.split() for line in prefix.splitlines()[:10] if line.strip()]
                    def yolo_row(row):
                        try:
                            return (len(row) == 5 and int(row[0]) >= 0
                                    and all(0 <= float(x) <= 1 for x in row[1:]))
                        except ValueError:
                            return False
                    item['looks_like_yolo_boxes'] = bool(lines) and all(yolo_row(row) for row in lines)
                    item['note'] = 'Indicio por formato; verificar semántica en la documentación del proveedor.'
            except (OSError, UnicodeError, ValueError) as error:
                item['inspection_error'] = str(error)
            annotation_info.append(item)
    return {'folder': str(folder), 'file_count': sum(counts.values()), 'bytes_unpacked': size,
            'image_count': sum(counts[extension] for extension in IMAGE_EXTENSIONS),
            'extensions': dict(counts), 'directories': dict(directories.most_common(30)),
            'examples': examples, 'annotation_samples': annotation_info,
            'note': 'Inventario; no importa etiquetas ni genera un proyecto automáticamente.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--handle',
                        help='owner/dataset o owner/dataset/versions/N para fijar una versión')
    parser.add_argument('--inspect-only', type=Path, help='Inspeccionar una descarga ya existente sin usar red')
    parser.add_argument('--destination', type=Path, default=ROOT/'datasets',
                        help='Carpeta base de descarga; se añaden propietario/dataset/versión')
    args = parser.parse_args()
    if args.handle:
        try:
            args.handle = normalize_handle(args.handle)
        except ValueError as error:
            parser.error(str(error))
    if args.inspect_only:
        folder = args.inspect_only
    else:
        if not args.handle:
            parser.error('Indica --handle propietario/conjunto o utiliza --inspect-only CARPETA.')
        # No se imprimen credenciales ni se configura autenticación de forma automática.
        os.environ.setdefault('KAGGLEHUB_CACHE', str(ROOT/'.cache'/'kagglehub'))
        try:
            import kagglehub
        except ImportError as error:
            raise SystemExit('Instala primero: python -m pip install -r requirements-datasets.txt') from error
        destination = dataset_destination(args.destination, args.handle)
        print(f'Descargando {args.handle} en {destination}', flush=True)
        folder = Path(kagglehub.dataset_download(args.handle, output_dir=str(destination)))
    report = inspect_dataset(folder)
    report['requested_handle'] = args.handle
    output = folder.parent/f'{folder.name}-inventario.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('folder', 'file_count', 'image_count', 'bytes_unpacked', 'extensions', 'annotation_samples')},
                     ensure_ascii=True, indent=2))
    print(f'Inventario completo: {output}')
    print('No se ha entrenado ningún modelo ni convertido etiquetas.')
    print('AULA_KAGGLE_RESULT:'+json.dumps({
        'folder': str(folder.resolve()), 'inventory': str(output),
        'file_count': report['file_count'], 'image_count': report['image_count'],
        'bytes_unpacked': report['bytes_unpacked'], 'extensions': report['extensions'],
    }, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
