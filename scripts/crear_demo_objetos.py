"""Escenas dibujadas con dos clases: solo para practicar el recorrido técnico."""
import hashlib
from pathlib import Path
import random

from PIL import Image, ImageDraw
from aula_ia.project import save_project


def create_demo(folder='demo-data/objetos'):
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    rng = random.Random(43)
    project = {'version': 1, 'task': 'object_detection', 'name': 'Demo dibujada: pelota y caja',
               'classes': ['Pelota', 'Caja'], 'images': [],
               'grouping_note': 'Escenas artificiales para aprender la herramienta; no representan objetos reales.'}
    for index in range(20):
        image = Image.new('RGB', (640, 400), '#eee8db')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 310, 640, 400), fill='#d2c6ac')
        x, y = rng.randint(30, 100), rng.randint(60, 140)
        ball = [x, y, x+150, y+150]
        draw.ellipse(ball, fill='#2780ab', outline='#154d70', width=4)
        draw.arc((x+20, y, x+130, y+150), start=80, end=270, fill='#b5e0ee', width=5)
        x, y = rng.randint(340, 400), rng.randint(80, 140)
        box = [x, y, x+170, y+160]
        draw.rectangle(box, fill='#c98543', outline='#76502b', width=4)
        draw.rectangle((x+65, y, x+90, y+160), fill='#e4b771')
        path = folder/f'escena-{index:02d}.png'
        image.save(path)
        project['images'].append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'boxes': [ball, box], 'box_labels': ['Pelota', 'Caja'], 'reviewed': True, 'excluded': False,
            'group': f'grupo-demo-{index//4}'})
    output = folder/'proyecto.json'
    save_project(output, project)
    return output


if __name__ == '__main__':
    print(create_demo())
