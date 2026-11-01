"""Captura explícita de la cámara del servidor, con cierre por inactividad."""
import os
import threading

from PIL import Image, ImageDraw


class Camera:
    def __init__(self):
        self.kind = os.environ.get('AULA_CAMERA', 'usb').lower()
        self.index = int(os.environ.get('AULA_CAMERA_INDEX', '0'))
        self.device = None
        self.lock = threading.RLock()
        self.timer = None

    def _touch(self):
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(30, self.close)
        self.timer.daemon = True
        self.timer.start()

    def start(self):
        with self.lock:
            if self.device is None:
                if self.kind == 'csi':
                    try:
                        from picamera2 import Picamera2
                    except ImportError as error:
                        raise ValueError('CSI necesita Picamera2 del sistema y un entorno con --system-site-packages.') from error
                    device = Picamera2(self.index)
                    try:
                        device.configure(device.create_video_configuration(main={'size': (640, 480), 'format': 'RGB888'}))
                        device.start()
                    except Exception:
                        device.close()
                        raise
                elif self.kind == 'usb':
                    import cv2
                    device = cv2.VideoCapture(self.index)
                    if not device.isOpened():
                        device.release()
                        raise ValueError('No se puede abrir la cámara USB. Comprueba conexión, índice y permisos de vídeo.')
                    device.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    device.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    device.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                else:
                    raise ValueError('AULA_CAMERA debe ser usb o csi.')
                self.device = device
            self._touch()
            return {'active': True, 'kind': self.kind, 'index': self.index}

    def frame(self):
        with self.lock:
            if self.device is None:
                raise ValueError('La cámara está detenida. Pulsa Iniciar cámara.')
            if self.kind == 'csi':
                frame = self.device.capture_array('main')
            else:
                ok, frame = self.device.read()
                if not ok:
                    self.close()
                    raise ValueError('No se ha recibido un fotograma de la cámara USB.')
            self._touch()
            # Picamera2 RGB888 y OpenCV entregan aquí canales B,G,R.
            return Image.fromarray(frame[:, :, :3][:, :, ::-1].copy())

    def close(self):
        with self.lock:
            if self.timer:
                self.timer.cancel()
                self.timer = None
            if self.device is not None:
                device, self.device = self.device, None
                if self.kind == 'csi':
                    try:
                        device.stop()
                    finally:
                        device.close()
                else:
                    device.release()


def annotated_image(image, detections):
    image = image.convert('RGB').copy()
    draw = ImageDraw.Draw(image)
    for item in detections:
        box = item['box']
        draw.rectangle(box, outline='#00df86', width=max(2, image.width//250))
        text = f'{item["label"]} {item["score"]:.0%}'
        x, y = box[:2]
        y = max(0, y-17)
        draw.rectangle((x, y, x+max(90, len(text)*7), y+16), fill='#123d2b')
        draw.text((x+3, y+1), text, fill='white')
    return image
