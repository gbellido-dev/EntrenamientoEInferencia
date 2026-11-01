"""Proyectos de detección de objetos: JSON, CVAT y reparto por grupos."""
import hashlib
import json
import math
import os
from pathlib import Path
import random
import xml.etree.ElementTree as ET

from PIL import Image

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}

def save_project(path, project):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def rotated_bounds(box, width, height):
    x1, y1, x2, y2 = (float(box[key]) for key in ('xtl', 'ytl', 'xbr', 'ybr'))
    angle = math.radians(float(box.get('rotation', 0)))
    if not all(math.isfinite(x) for x in (x1, y1, x2, y2, angle)) or x2 <= x1 or y2 <= y1:
        raise ValueError('Rectángulo CVAT no válido.')
    cx, cy = (x1+x2)/2, (y1+y2)/2
    dx = abs(math.cos(angle))*(x2-x1)/2 + abs(math.sin(angle))*(y2-y1)/2
    dy = abs(math.sin(angle))*(x2-x1)/2 + abs(math.cos(angle))*(y2-y1)/2
    return [max(0., cx-dx), max(0., cy-dy), min(float(width), cx+dx), min(float(height), cy+dy)]


def import_cvat(xml_path):
    xml_path = Path(xml_path).resolve()
    if xml_path.stat().st_size > 20*1024*1024:
        raise ValueError('El XML supera el límite de 20 MiB.')
    root = ET.fromstring(xml_path.read_bytes())
    if root.tag != 'annotations' or not root.findall('image'):
        raise ValueError('Se requiere CVAT XML de imágenes con elementos image/box.')
    classes = list(dict.fromkeys(box.get('label', '').strip() for image in root.findall('image') for box in image.findall('box')))
    if not classes or any(not label for label in classes):
        raise ValueError('El XML debe contener al menos una clase de rectángulos con nombre.')
    project = {'version': 1, 'task': 'object_detection', 'name': 'Detector de objetos', 'classes': classes,
               'grouping_note': 'Grupos iniciales por imagen. Revisa sesiones y objetos relacionados antes de evaluar.',
               'source': str(xml_path), 'images': []}
    known = set()
    for element in root.findall('image'):
        path = (xml_path.parent/element.attrib['name']).resolve()
        if not path.is_relative_to(xml_path.parent):
            raise ValueError('La ruta de una imagen sale de la carpeta del dataset.')
        with Image.open(path) as image:
            width, height = image.size
        if width != int(element.attrib['width']) or height != int(element.attrib['height']):
            raise ValueError(f'Las dimensiones de {path.name} no coinciden con las anotaciones.')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in known:
            continue
        known.add(digest)
        boxes, box_labels = [], []
        for box in element.findall('box'):
            bounds = rotated_bounds(box.attrib, width, height)
            if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
                raise ValueError('Rectángulo fuera de la imagen.')
            boxes.append(bounds)
            box_labels.append(box.attrib['label'].strip())
        project['images'].append({'path': str(path), 'sha256': digest, 'boxes': boxes, 'box_labels': box_labels,
                                  'reviewed': True, 'excluded': False, 'group': f'imagen-{digest[:12]}'})
    return validate_project(project)


def validate_project(project, path=None):
    if project.get('task') != 'object_detection' or project.get('version') != 1:
        raise ValueError('No es un proyecto de detección de objetos compatible.')
    classes = project.get('classes')
    if (not isinstance(classes, list) or not 0 <= len(classes) <= 100
            or any(not isinstance(c, str) or not c.strip() or len(c) > 80 for c in classes)
            or len(set(classes)) != len(classes)):
        raise ValueError('Las etiquetas deben ser distintas, de hasta 80 caracteres; máximo 100.')
    if not isinstance(project.get('name'), str) or not 1 <= len(project['name']) <= 100:
        raise ValueError('El proyecto necesita un nombre de 1 a 100 caracteres.')
    if not isinstance(project.get('images'), list):
        raise ValueError('El proyecto necesita una lista de imágenes.')
    for row in project['images']:
        if path:
            row['path'] = str((Path(path).resolve().parent/row['path']).resolve())
        if not isinstance(row.get('group'), str) or not row['group'].strip():
            raise ValueError('Cada imagen necesita un grupo.')
        if not isinstance(row.get('boxes'), list):
            raise ValueError('Cada imagen necesita una lista de rectángulos.')
        if 'box_labels' not in row and len(classes) == 1:
            row['box_labels'] = [classes[0]]*len(row['boxes'])
        if (not isinstance(row.get('box_labels'), list) or len(row['box_labels']) != len(row['boxes'])
                or any(label not in classes for label in row['box_labels'])):
            raise ValueError('Cada rectángulo necesita una etiqueta de las clases del proyecto.')
        for box in row['boxes']:
            if (len(box) != 4 or any(type(v) not in (float, int) or not math.isfinite(v) for v in box)
                    or min(box) < 0 or box[2] <= box[0] or box[3] <= box[1]):
                raise ValueError('Hay un rectángulo inválido.')
    return project


def detection_split(project):
    validate_project(project)
    if not project['classes']:
        raise ValueError('Añade al menos una etiqueta y anota sus objetos antes de entrenar.')
    rows = [r for r in project['images'] if r.get('reviewed') and not r.get('excluded')]
    groups = sorted({r['group'] for r in rows})
    if len(groups) < 3 or len(rows) < 6:
        raise ValueError('Necesitas al menos seis imágenes revisadas en tres grupos.')
    for label in project['classes']:
        if len({r['group'] for r in rows if label in r['box_labels']}) < 3:
            raise ValueError(f'La clase «{label}» necesita objetos anotados en al menos tres grupos.')
    # Evitar duplicados exactos incluso si el JSON fue editado externamente.
    hashes = {}
    for row in rows:
        group = hashes.setdefault(row['sha256'], row['group'])
        if group != row['group']:
            raise ValueError('Una imagen duplicada aparece en grupos distintos.')
    rng = random.Random(42)
    best, score = None, float('inf')
    for _ in range(300):
        shuffled = groups.copy()
        rng.shuffle(shuffled)
        n = max(1, round(len(groups)*.2))
        assignment = {g: ('val' if i < n else 'test' if i < 2*n else 'train') for i, g in enumerate(shuffled)}
        parts = {key: [r for r in rows if assignment[r['group']] == key] for key in ('train', 'val', 'test')}
        if len(parts['train']) < 2 or any({label for row in part for label in row['box_labels']} != set(project['classes'])
                                        for part in parts.values()):
            continue
        error = sum(abs(len(parts[key])/len(rows)-target) for key, target in [('train', .6), ('val', .2), ('test', .2)])
        if error < score:
            best, score = parts, error
    if best is None:
        raise ValueError('No hay ejemplos suficientes de todas las clases en grupos distintos para repartir los datos.')
    return best


def load_project(path):
    path = Path(path).resolve()
    return validate_project(json.loads(path.read_text(encoding='utf-8-sig')), path)
