# Verificación de la versión de objetos

Entorno: Windows, Python 3.12.14. Las versiones instaladas están registradas en `requirements-windows.lock.txt`.

La batería de **18 pruebas ha pasado**, incluida la creación de proyectos vacíos sin etiquetas y el instalador de Raspberry Pi. Se han retirado las versiones anteriores y sus dependencias internas.

## Comprobaciones

Las pruebas automáticas cubren:

- Crear, guardar y abrir un proyecto sin etiquetas; añadir después una sola etiqueta propia.
- Importación CVAT, cajas giradas y reparto por grupos.
- Qt: dibujar, etiquetar, corregir la etiqueta de una caja, guardar, deshacer y confirmar imágenes sin objetos.
- Entrenamiento y exportación ONNX con una y varias etiquetas, sin descargar pesos durante las pruebas.
- Comparación numérica de cajas y puntuaciones ONNX/PyTorch.
- Supresión de duplicados por etiqueta y reescalado de coordenadas.
- Métricas que penalizan una etiqueta incorrecta aunque su caja coincida.
- Gradientes de fondo en imágenes negativas revisadas.
- Carga web, autenticación, rechazo de archivos inválidos, persistencia y cámara simulada.
- Conversión de color y liberación del backend USB con dispositivo simulado.
- Instalador: simulación sin cambios, conservación de clave/modelo, fallo de dependencias sin sustituir el servicio, restauración tras fallo de arranque y limpieza de una primera instalación fallida.
- CSI: acceso a paquetes del sistema y restricción de NumPy compatible.
- ZIP de despliegue sin entrenamiento, Qt, datasets, modelos ni entornos de Windows; script Bash con finales de línea Linux.
- Cámara web: cabeceras con recuentos por etiqueta, tiempos, resolución e identificador de modelo; panel de vídeo y estadísticas comprobado desde el navegador con una cámara simulada, sin abrir dispositivos físicos.

También se comprueban sintaxis JavaScript, compilación de módulos Python y dependencias con `pip check`. Las capturas Qt se renderizan sin pantalla, registrando Segoe UI explícitamente porque ese entorno de pruebas no descubre fuentes automáticamente.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
node --check aula_ia/static/app.js
.\.venv\Scripts\python.exe -m compileall -q aula_ia scripts tests
.\.venv\Scripts\python.exe -m pip check
```

Los ejemplos artificiales verifican el recorrido técnico, no precisión con objetos reales. El dataset descargado previamente se conserva como material local opcional, separado del proyecto vacío y excluido de Git.

## Pendiente de hardware

No se ha conectado una Raspberry Pi ni una cámara física. Falta comprobar instalación ARM64, captura USB/CSI, color, velocidad, memoria, temperatura, red del aula y arranque automático en la placa.

## Avisos de bibliotecas

PyTorch avisa de la futura retirada del exportador ONNX clásico. Esta versión utiliza explícitamente `dynamo=False`, opset 17, y comprueba la equivalencia numérica antes de publicar cada modelo.

Starlette avisa de una futura migración del backend de TestClient. Es un aviso de las pruebas y no del servidor Uvicorn. Las actualizaciones de dependencias necesitan volver a verificar el recorrido.
