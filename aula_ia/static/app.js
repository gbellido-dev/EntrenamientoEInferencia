const $ = id => document.getElementById(id);
let previewURL;
let busy = false;
let cameraRunning = false;
let cameraURL;
async function request(url, options = {}) {
  const response = await fetch(url, options);
  let result;
  try { result = await response.json(); } catch { throw new Error('El servidor no devolvió una respuesta válida.'); }
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Revisa los datos enviados.');
  return result;
}
async function refresh() {
  const data = await request('/api/status');
  $('status').textContent = data.ready ? '● Modelo preparado' : '○ Esperando un modelo';
  $('model-info').textContent = data.ready ? `${data.model.name} · Etiquetas: ${data.model.classes.join(', ')}` : 'Todavía no hay un modelo activo.';
  const detector = data.ready;
  $('camera-start').disabled = !detector || cameraRunning;
  if (!cameraRunning) $('camera-status').textContent = detector ? 'Detector preparado. La cámara se abre solo al pulsar Iniciar.' : 'Carga un paquete de detección para utilizar esta función.';
}
async function action(work) {
  if (busy) return;
  busy = true;
  $('message').textContent = 'Procesando…';
  for (const id of ['load', 'predict']) $(id).disabled = true;
  try { await work(); $('message').textContent = ''; }
  catch (error) { $('message').textContent = error.message; }
  finally { busy = false; for (const id of ['load', 'predict']) $(id).disabled = false; }
}
function upload(id, max) {
  if (!$('token').value) throw new Error('Introduce la clave del aula.');
  const file = $(id).files[0];
  if (!file) throw new Error('Selecciona primero un archivo.');
  if (file.size > max * 1024 * 1024) throw new Error(`El archivo supera ${max} MiB.`);
  const body = new FormData(); body.append('file', file);
  return {method: 'POST', body, headers: {'X-Aula-Token': $('token').value}};
}
$('load').addEventListener('click', () => action(async () => {
  if (cameraRunning) await stopCamera();
  await request('/api/model', upload('model', 64));
  $('results').hidden = true;
  await refresh();
}));
$('image').addEventListener('change', () => {
  if (previewURL) URL.revokeObjectURL(previewURL);
  const file = $('image').files[0];
  $('results').hidden = true;
  $('preview').hidden = !file;
  if (file) { previewURL = URL.createObjectURL(file); $('preview').src = previewURL; }
});
$('predict').addEventListener('click', () => action(async () => {
  $('results').hidden = true;
  const threshold = Number($('threshold').value);
  if (!Number.isFinite(threshold) || threshold < 0.01 || threshold > 1) throw new Error('El umbral debe estar entre 0,01 y 1.');
  const result = await request(`/api/predict?threshold=${threshold}`, upload('image', 10));
  $('scores').replaceChildren();
  $('prediction').textContent = `Objetos detectados: ${result.detections.length}`;
  $('preview').src = `data:image/jpeg;base64,${result.annotated_image}`;
  for (const [index, item] of result.detections.entries()) {
    const text = document.createElement('p');
    text.textContent = `${item.label} ${index + 1}: ${(item.score * 100).toFixed(1)} %`;
    $('scores').append(text);
  }
  $('timing').textContent = `Modelo y salida: ${result.inference_ms} ms · Preparación e inferencia: ${result.processing_ms} ms (excluye red y dibujo).`;
  $('results').hidden = false;
}));
function cameraOptions() {
  if (!$('token').value) throw new Error('Introduce la clave del aula.');
  return {method: 'POST', headers: {'X-Aula-Token': $('token').value}};
}
async function stopCamera() {
  cameraRunning = false;
  $('camera-stop').disabled = true;
  try { await request('/api/camera/stop', cameraOptions()); }
  catch (error) { $('message').textContent = error.message; }
  $('camera-start').disabled = false;
  $('camera-status').textContent = 'Cámara detenida.';
  $('camera-preview').hidden = true;
  if (cameraURL) { URL.revokeObjectURL(cameraURL); cameraURL = undefined; }
}
async function cameraFrame() {
  if (!cameraRunning) return;
  const start = performance.now();
  try {
    const threshold = Number($('threshold').value);
    if (!Number.isFinite(threshold) || threshold < 0.01 || threshold > 1) throw new Error('El umbral debe estar entre 0,01 y 1.');
    const response = await fetch(`/api/camera/frame?threshold=${threshold}`, cameraOptions());
    if (!response.ok) {
      const error = await response.json();
      if (response.status === 409 && String(error.detail).includes('ocupado') && cameraRunning) { setTimeout(cameraFrame, 500); return; }
      throw new Error(error.detail || 'No se puede leer la cámara.');
    }
    const blob = await response.blob();
    if (!cameraRunning) return;
    if (cameraURL) URL.revokeObjectURL(cameraURL);
    cameraURL = URL.createObjectURL(blob);
    $('camera-preview').src = cameraURL;
    $('camera-preview').hidden = false;
    const elapsed = performance.now() - start;
    $('camera-status').textContent = `${response.headers.get('X-Object-Count')} objetos · Modelo y salida: ${response.headers.get('X-Inference-Ms')} ms · Ciclo con red: ${elapsed.toFixed(0)} ms`;
    setTimeout(cameraFrame, Math.max(0, 200-elapsed));
  } catch (error) {
    await stopCamera();
    $('message').textContent = error.message;
  }
}
$('camera-start').addEventListener('click', () => action(async () => {
  await request('/api/camera/start', cameraOptions());
  cameraRunning = true;
  $('camera-start').disabled = true;
  $('camera-stop').disabled = false;
  cameraFrame();
}));
$('camera-stop').addEventListener('click', stopCamera);
window.addEventListener('pagehide', () => {
  if (cameraRunning) {
    cameraRunning = false;
    fetch('/api/camera/stop', {...cameraOptions(), keepalive: true}).catch(() => {});
  }
});
refresh().catch(error => { $('message').textContent = error.message; $('status').textContent = 'Sin conexión'; });

