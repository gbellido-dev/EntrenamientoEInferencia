# Arquitectura de detección de objetos

```text
Windows · Qt → proyecto JSON → entrenamiento SSDLite → detector-objetos.zip
                                                               ↓ carga web
Navegador → FastAPI en la Pi → ONNX Runtime → cajas, etiquetas y puntuaciones
                              ↑
                        cámara USB / CSI
```

## Módulos

| Archivo | Responsabilidad |
|---|---|
| `object_desktop.py` | Editor de cajas, etiquetas propias, entrenamiento y prueba local. |
| `project.py` | Guardado, lectura, CVAT y reparto por grupos. |
| `object_training.py` | Ajuste de SSDLite, evaluación por etiqueta y exportación. |
| `inference.py` | Contrato del ZIP, preprocesamiento y decodificación. |
| `workers.py`, `errors.py` | Segundo plano en Qt y cancelación cooperativa. |
| `camera.py` | Captura USB/CSI y dibujo de cajas. |
| `web.py`, `static/` | API e interfaz web local. |

## Proyecto

JSON versión 1, tarea `object_detection`, nombre, lista `classes` y lista `images`. **Se permite una lista de etiquetas vacía para crear y guardar un proyecto nuevo.** Antes de entrenar debe existir al menos una etiqueta con ejemplos.

Cada imagen guarda ruta, SHA256, `boxes` (coordenadas originales), `box_labels` (una etiqueta por caja), grupo, revisión y descarte. Las etiquetas de las cajas deben pertenecer al proyecto. Las imágenes pendientes o descartadas se omiten.

El reparto busca aproximadamente 60/20/20 mediante grupos completos, con semilla 42. Cada etiqueta debe estar representada en los tres conjuntos. Los grupos relacionados los define el alumno; un hash solo detecta duplicados exactos. Los proyectos guardan rutas absolutas, pero también admiten rutas relativas al JSON al abrirlos.

## Entrenamiento

SSDLite320 MobileNetV3 con pesos oficiales. Se congelan el extractor y BatchNorm, se ajustan las cabezas para C etiquetas más fondo, con AdamW, lotes de cuatro y CPU. Las imágenes negativas revisadas aportan una pérdida de fondo sobre los 32 candidatos más difíciles. No hay aumentos de datos ni reanudación de entrenamientos interrumpidos.

Se selecciona la época con mayor media AP50 de validación y después se evalúa la prueba. AP50 se calcula por etiqueta con IoU 0,5 y candidatos desde 0,01; precisión y recuperación se muestran a umbral 0,5. No es el mAP COCO de varios IoU.

## Contrato de despliegue

ZIP con tres archivos en la raíz: `model.onnx`, `manifest.json`, `metrics.json`. Solo se acepta tarea `object_detection`.

- Entrada float32 `[1,3,320,320]`, RGB, 0–1, estirado bilineal y orientación de píxeles original. Normalización dentro del grafo.
- Salidas float32 `boxes [1,N,4]` y `scores [1,N,C]`.
- Filtrado por puntuación, hasta 200 candidatos por etiqueta, NMS IoU 0,4 por etiqueta y hasta 100 resultados globales.
- Cajas reescaladas a la imagen original, con nombre y puntuación de su etiqueta.

Antes de publicar el paquete se comparan cajas y puntuaciones ONNX/PyTorch en hasta cinco imágenes reservadas. Un fallo o cancelación conserva el paquete anterior.

## API y cámara

| Ruta | Uso |
|---|---|
| `GET /api/status` | Estado y manifiesto. |
| `POST /api/model` | Multipart `file`: detector ZIP. |
| `POST /api/predict?threshold=0.5` | Multipart `file`: foto; devuelve cajas y JPEG anotado. |
| `POST /api/camera/start` | Abre la cámara configurada del servidor. |
| `POST /api/camera/frame?threshold=0.5` | Captura, detecta y devuelve JPEG anotado. |
| `POST /api/camera/stop` | Libera la cámara. |

Las operaciones POST exigen cabecera `X-Aula-Token`. Hay una operación de carga/inferencia a la vez; se responde 409 si está ocupado. La cámara y el modelo son compartidos. Tras 30 segundos sin pedir imagen se libera la cámara.

Se limita el paquete y su contenido a 64 MiB, el manifiesto a 64 KiB, las métricas a 2 MiB, las fotos web a 10 MiB y 20 millones de píxeles. Los datos de entrenamiento locales admiten hasta 64 millones de píxeles. Los modelos deben proceder de una fuente de confianza; validar el contrato no es un sandbox.

La versión no incluye segmentación, aceleradores ni cuantización. La captura y el rendimiento físicos siguen pendientes de probar en la Pi 4.
