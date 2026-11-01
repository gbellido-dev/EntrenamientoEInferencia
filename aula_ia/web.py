"""Servidor local de inferencia. Arrancar con python -m aula_ia.web."""
import argparse
import base64
import io
import os
import secrets
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from PIL import Image

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from aula_ia.inference import MAX_IMAGE, MAX_PACKAGE, Predictor
from aula_ia.camera import Camera, annotated_image


def create_app(data_dir=None, token=None, camera=None):
    root = Path(data_dir or os.environ.get('AULA_DATA', 'raspi-data')).resolve()
    root.mkdir(parents=True, exist_ok=True)
    token = token if token is not None else os.environ.get('AULA_TOKEN', '')
    if len(token) < 12:
        raise ValueError('Configura AULA_TOKEN con al menos 12 caracteres antes de arrancar.')
    camera = camera if camera is not None else Camera()
    @asynccontextmanager
    async def lifespan(app):
        yield
        camera.close()
    app = FastAPI(title='Aula IA · Raspberry Pi', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.predictor = None
    lock = threading.Lock()
    if (root/'active.zip').exists():
        app.state.predictor = Predictor((root/'active.zip').read_bytes())

    def authorize(value):
        if not secrets.compare_digest(value or '', token):
            raise HTTPException(401, 'Clave incorrecta. Introduce la clave del aula.')

    async def read_limited(upload, limit):
        try:
            data = await upload.read(limit+1)
            if not data:
                raise HTTPException(400, 'El archivo está vacío.')
            if len(data) > limit:
                raise HTTPException(413, f'El archivo supera {limit//1024//1024} MiB.')
            return data
        finally:
            await upload.close()

    @app.middleware('http')
    async def limit_body(request, call_next):
        # Límite real de flujo también para cuerpos sin Content-Length.
        limit = MAX_PACKAGE + 1024*1024 if request.url.path == '/api/model' else MAX_IMAGE + 1024*1024
        try:
            length = int(request.headers.get('content-length', '0'))
        except ValueError:
            return JSONResponse({'detail': 'Content-Length inválido.'}, status_code=400)
        if length > limit:
            return JSONResponse({'detail': 'La petición supera el tamaño permitido.'}, status_code=413)
        received = 0
        original = request._receive
        async def receive():
            nonlocal received
            message = await original()
            received += len(message.get('body', b''))
            if received > limit:
                raise HTTPException(413, 'La petición supera el tamaño permitido.')
            return message
        request._receive = receive
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob: data:; script-src 'self'; style-src 'self'"
        return response

    @app.get('/')
    def index():
        return FileResponse(Path(__file__).parent/'static'/'index.html')

    @app.get('/app.js')
    def javascript():
        return FileResponse(Path(__file__).parent/'static'/'app.js', media_type='application/javascript')

    @app.get('/style.css')
    def css():
        return FileResponse(Path(__file__).parent/'static'/'style.css', media_type='text/css')

    @app.get('/api/status')
    def status():
        predictor = app.state.predictor
        return {'ready': predictor is not None,
                'model': predictor.manifest if predictor else None}

    @app.post('/api/model')
    async def upload_model(file: UploadFile = File(...), x_aula_token: str = Header(default='')):
        authorize(x_aula_token)
        data = await read_limited(file, MAX_PACKAGE)
        def activate():
            if not lock.acquire(blocking=False):
                raise HTTPException(409, 'La Raspberry Pi está ocupada. Espera y vuelve a intentarlo.')
            try:
                try:
                    candidate = Predictor(data)
                except Exception as error:
                    raise HTTPException(400, f'Modelo incompatible: {str(error)[:350]}') from error
                temporary = root/'incoming.tmp'
                temporary.write_bytes(data)
                os.replace(temporary, root/'active.zip')
                app.state.predictor = candidate
                return {'name': candidate.manifest['name'], 'classes': candidate.manifest['classes']}
            finally:
                lock.release()
        return await run_in_threadpool(activate)

    @app.post('/api/predict')
    async def predict(file: UploadFile = File(...), threshold: float = .5,
                      x_aula_token: str = Header(default='')):
        authorize(x_aula_token)
        data = await read_limited(file, MAX_IMAGE)
        def execute():
            if not lock.acquire(blocking=False):
                raise HTTPException(409, 'La Raspberry Pi está ocupada. Espera y vuelve a intentarlo.')
            try:
                predictor = app.state.predictor
                if predictor is None:
                    raise HTTPException(409, 'Primero carga un modelo.')
                try:
                    result = predictor.predict(io.BytesIO(data), threshold)
                    with Image.open(io.BytesIO(data)) as original:
                        image = annotated_image(original, result['detections'])
                    image.thumbnail((1280, 960))
                    buffer = io.BytesIO()
                    image.save(buffer, format='JPEG', quality=85)
                    result['annotated_image'] = base64.b64encode(buffer.getvalue()).decode('ascii')
                    return result
                except Exception as error:
                    raise HTTPException(400, f'No se puede analizar la imagen: {str(error)[:350]}') from error
            finally:
                lock.release()
        return await run_in_threadpool(execute)

    @app.post('/api/camera/start')
    def camera_start(x_aula_token: str = Header(default='')):
        authorize(x_aula_token)
        if app.state.predictor is None:
            raise HTTPException(409, 'Carga primero un paquete de detección de objetos.')
        try:
            return camera.start()
        except Exception as error:
            raise HTTPException(400, str(error)[:350]) from error

    @app.post('/api/camera/stop')
    def camera_stop(x_aula_token: str = Header(default='')):
        authorize(x_aula_token)
        camera.close()
        return {'active': False}

    @app.post('/api/camera/frame')
    def camera_frame(threshold: float = .5, x_aula_token: str = Header(default='')):
        authorize(x_aula_token)
        if not lock.acquire(blocking=False):
            raise HTTPException(409, 'El servidor está ocupado; vuelve a intentarlo.')
        try:
            predictor = app.state.predictor
            if predictor is None:
                raise HTTPException(409, 'Carga un detector de objetos.')
            try:
                image = camera.frame()
                result = predictor.predict(image, threshold)
                buffer = io.BytesIO()
                annotated_image(image, result['detections']).save(buffer, format='JPEG', quality=80)
                return Response(buffer.getvalue(), media_type='image/jpeg', headers={
                    'X-Object-Count': str(len(result['detections'])), 'X-Inference-Ms': str(result['inference_ms'])})
            except Exception as error:
                raise HTTPException(400, str(error)[:350]) from error
        finally:
            lock.release()

    return app


def main():
    import uvicorn
    parser = argparse.ArgumentParser(description='Servidor Aula IA para red local')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port, workers=1)


if __name__ == '__main__':
    main()

