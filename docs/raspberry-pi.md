# Instalación en Raspberry Pi 4

## Preparación

Consulta [el recorrido de anotación y entrenamiento](deteccion-objetos.md). Esta página recoge la instalación del servidor y las dos opciones de cámara.

Necesitas Raspberry Pi OS de **64 bits**, Python 3.11 o 3.12, conexión a la red del aula y acceso inicial por terminal/SSH. Comprueba:

```bash
uname -m
python3 --version
```

La arquitectura debe ser `aarch64`. La disponibilidad de wheels de ONNX Runtime depende también de Python y del sistema: si pip indica que no existe una distribución compatible, comprueba estos tres datos antes de cambiar versiones. Esta entrega no ha sido ejecutada físicamente en una Pi.

Copia la carpeta del proyecto a `/home/TU_USUARIO/EntrenamientoEInferencia`, **excluyendo** `.venv`, `.git`, `.cache`, `demo-data` y los proyectos/fotografías que no necesites. No hace falta copiar los datos de entrenamiento a la Pi.

## Instalar y arrancar

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip libgomp1
cd ~/EntrenamientoEInferencia
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-raspi.txt

# Genera una clave y anótala para introducirla en la web.
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(24))"
export AULA_TOKEN='PEGA_AQUI_LA_CLAVE_GENERADA'
export AULA_DATA="$HOME/EntrenamientoEInferencia/raspi-data"
.venv/bin/python -m aula_ia.web --host 0.0.0.0 --port 8000
```

El servidor exige una clave de al menos 12 caracteres. Si el puerto 8000 está ocupado, elige otro con `--port`.

En otra terminal, `hostname -I` muestra las direcciones de la Pi. Desde un dispositivo de la misma red abre `http://IP_DE_LA_PI:8000`. También puede funcionar `http://raspberrypi.local:8000`, dependiendo del nombre y la resolución mDNS de la red.

Introduce la clave, carga `detector-objetos.zip` y prueba una fotografía. Cierra el servidor con Ctrl+C.

Se conserva `raspi-data/active.zip` y se carga al reiniciar. Una carga incompatible conserva el modelo anterior. Las fotografías recibidas se procesan en memoria y no se guardan por la aplicación. Protege esta carpeta: los modelos deben proceder del aula y el formato ONNX no constituye un aislamiento de ejecución.

## Cámara USB

Instala la captura en el mismo entorno del servidor y selecciona la cámara antes de arrancarlo:

```bash
.venv/bin/python -m pip install -r requirements-camera.txt
export AULA_CAMERA=usb
export AULA_CAMERA_INDEX=0
.venv/bin/python -m aula_ia.web --host 0.0.0.0 --port 8000
```

Mantén también `AULA_TOKEN` configurada. En la web carga `detector-objetos.zip` y pulsa «Iniciar cámara». La cámara utilizada es la del servidor, no la del navegador. Se solicita 640 × 480; la resolución final depende del dispositivo.

«Detener cámara» la libera. Si se deja de pedir imagen, se cierra tras 30 segundos de inactividad. No se guardan fotos ni vídeo. La web pide un fotograma cada vez y limita el ritmo a unas cinco solicitudes por segundo como máximo; la Pi puede ser más lenta. Comprueba conexión, índice y permisos de vídeo si no se abre.

## Cámara CSI por cinta

Utiliza el Python de Raspberry Pi OS y un entorno con acceso a Picamera2/libcamera del sistema:

```bash
sudo apt install python3-picamera2 python3-opencv python3-numpy python3-venv
cd ~/EntrenamientoEInferencia
python3 -m venv --system-site-packages .venv-csi
.venv-csi/bin/python -m pip install -r requirements-raspi.txt
export AULA_CAMERA=csi
export AULA_CAMERA_INDEX=0
export AULA_TOKEN='TU_CLAVE_DE_AL_MENOS_12_CARACTERES'
.venv-csi/bin/python -m aula_ia.web --host 0.0.0.0 --port 8000
```

Con CSI utiliza el OpenCV de apt y conserva su combinación de NumPy/Picamera2; no instales además `requirements-camera.txt` en ese entorno. El adaptador solicita `RGB888` (array BGR en Picamera2) y lo convierte a RGB para el detector. [Manual oficial](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf).

**La captura física USB/CSI todavía no se ha probado en una Pi.** Hay que verificar cámara, color, paquetes ARM64 y rendimiento en tu placa.

## Arranque automático con systemd

1. Edita `deploy/aula-ia.service`: sustituye `alumno` por tu usuario real y ajusta las rutas.
2. Guarda la configuración local con permisos restringidos:

```bash
mkdir -p ~/.config
nano ~/.config/aula-ia.env
```

Contenido (usa tu clave y rutas reales):

```ini
AULA_TOKEN=PEGA_AQUI_LA_CLAVE_GENERADA
AULA_DATA=/home/alumno/EntrenamientoEInferencia/raspi-data
AULA_CAMERA=usb
AULA_CAMERA_INDEX=0
```

3. Activa el servicio:

Si usas CSI cambia también el ejecutable de `ExecStart` a `.venv-csi/bin/python` y el tipo de cámara a `csi`.

```bash
chmod 600 ~/.config/aula-ia.env
sudo cp deploy/aula-ia.service /etc/systemd/system/aula-ia.service
sudo systemctl daemon-reload
sudo systemctl enable --now aula-ia
sudo systemctl status aula-ia
```

Diagnóstico y parada:

```bash
journalctl -u aula-ia -n 60 --no-pager
sudo systemctl stop aula-ia
```

## Red del aula y uso

Se incluye clave para cargar modelos y analizar imágenes, y límites de tamaño. El estado y el nombre del modelo son visibles a quien acceda a la web. La conexión HTTP transmite la clave sin cifrar: utiliza una red de laboratorio confiable. Para acceso desde fuera, utiliza una VPN o un proxy HTTPS administrado por el centro; no abras directamente el puerto del router a Internet.

La Pi acepta una operación de modelo/inferencia cada vez; si está ocupada responde que esperes. Es una Pi compartida: cargar un modelo cambia el modelo activo para todos. Para prácticas simultáneas usa una Pi por grupo o turnos explícitos.

Después de verificar la instalación, guarda las versiones propias de la Pi:

```bash
.venv/bin/python -m pip freeze > requirements-raspi.validado.txt
```

Comprueba con el mismo paquete y fotografía: clase, puntuaciones próximas, tiempos, reinicio del servicio y rechazo de un ZIP inválido que conserve el modelo anterior. No se promete igualdad exacta de decimales entre arquitecturas ni rendimiento de vídeo.

## Ensayar la web en Windows

En PowerShell, desde la carpeta del proyecto:

```powershell
$env:AULA_TOKEN = 'una-clave-local-de-al-menos-12-caracteres'
.\.venv\Scripts\python.exe -m aula_ia.web
```

Abre `http://127.0.0.1:8000`. Por defecto solo escucha en el propio equipo. Para la Pi utilizamos `--host 0.0.0.0` porque debe aceptar conexiones de la red.

