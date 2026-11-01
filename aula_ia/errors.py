"""Errores compartidos sin dependencias de interfaz."""


class Cancelled(Exception):
    """El usuario ha solicitado detener el proceso sin publicar un modelo nuevo."""
