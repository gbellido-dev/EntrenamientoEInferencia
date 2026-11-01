"""Identificadores genéricos de datasets de Kaggle; no ejecuta código pegado."""
from pathlib import Path
import re
from urllib.parse import urlsplit


def normalize_handle(value):
    value = value.strip()
    if '://' in value:
        url = urlsplit(value)
        if url.scheme != 'https' or url.netloc.lower() not in ('kaggle.com', 'www.kaggle.com'):
            raise ValueError('Usa un enlace https://www.kaggle.com/datasets/propietario/dataset.')
        if not url.path.startswith('/datasets/'):
            raise ValueError('El enlace debe corresponder a un dataset de Kaggle.')
        value = url.path[len('/datasets/'):].rstrip('/')
    value = value.rstrip('/')
    if not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+(?:/versions/[1-9][0-9]*)?', value):
        raise ValueError('Pega un enlace de dataset o propietario/dataset (opcional: /versions/N).')
    return value


def dataset_destination(base, handle):
    parts = normalize_handle(handle).split('/')
    version = f'version-{parts[3]}' if len(parts) == 4 else 'latest'
    return Path(base).resolve()/parts[0]/parts[1]/version
