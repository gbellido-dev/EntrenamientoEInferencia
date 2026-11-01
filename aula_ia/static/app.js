/**
 * AULA IA · app.js
 * Interfaz de inferencia para Raspberry Pi — Vanilla JS, sin dependencias.
 *
 * Organización:
 *  1. Utilidades DOM y helpers
 *  2. Estado global de la aplicación
 *  3. Tema (oscuro/claro) con persistencia en localStorage
 *  4. Navegación entre paneles (sidebar + mobile nav)
 *  5. Sistema de toasts
 *  6. Paleta de colores por clase
 *  7. API — comunicación con el servidor
 *  8. Panel Conexión (estado del servidor y modelo)
 *  9. Panel Modelo (carga de ZIP con drag & drop)
 * 10. Panel Análisis (predict + canvas + zoom/pan + historial)
 * 11. Panel Cámara (stream de fotogramas + overlay + captura)
 * 12. Historial de sesión (IndexedDB-like via localStorage + base64)
 * 13. Inicialización
 */

'use strict';

/* ══════════════════════════════════════════════════════════════════════════
   1. UTILIDADES DOM Y HELPERS
   ══════════════════════════════════════════════════════════════════════════ */

/** Atajo para getElementById. */
const $ = id => document.getElementById(id);

/** Atajo para querySelector desde un elemento (o document). */
const qs = (sel, root = document) => root.querySelector(sel);

/** Atajo para querySelectorAll desde un elemento (o document). */
const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/** Formatea milisegundos con sufijo. */
const fmtMs = ms => ms != null ? `${Number(ms).toFixed(0)} ms` : '—';

/** Formatea porcentaje con un decimal. */
const fmtPct = v => `${(v * 100).toFixed(1)} %`;

/** Limita un valor entre min y max. */
const clamp = (v, min, max) => Math.min(Math.max(v, min), max);

/* ══════════════════════════════════════════════════════════════════════════
   2. ESTADO GLOBAL
   ══════════════════════════════════════════════════════════════════════════ */

const STATE = {
  busy: false,             // operación bloqueante en curso
  modelId: null,           // ID del modelo activo en el servidor
  modelLabels: [],         // etiquetas del modelo activo
  modelReady: false,       // ¿hay modelo cargado?

  // Análisis de imagen
  lastImageFile: null,     // File de la última imagen subida (para re-analizar)
  lastDetections: null,    // Detecciones del último análisis (para exportar)
  lastImageMeta: null,     // Metadatos del último resultado

  // Canvas
  canvasImg: null,         // HTMLImageElement original cargada en el canvas
  canvasDetections: [],    // detecciones pintadas en el canvas
  canvasScale: 1,          // zoom actual
  canvasOffsetX: 0,        // pan X
  canvasOffsetY: 0,        // pan Y
  canvasDragging: false,
  canvasDragStart: {x: 0, y: 0},

  // Cámara
  cameraRunning: false,
  cameraSession: 0,        // versión de sesión para cancelar loops antiguos
  cameraFrames: 0,
  frameTimes: [],          // timestamps de los últimos N frames para calcular FPS
  cameraURL: null,         // Object URL del último frame
};

/* ══════════════════════════════════════════════════════════════════════════
   3. TEMA OSCURO / CLARO
   ══════════════════════════════════════════════════════════════════════════ */

/** Aplica un tema ('dark' | 'light') al <html> y lo persiste. */
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('aula-theme', theme);
}

/** Alterna entre oscuro y claro. */
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  applyTheme(current === 'dark' ? 'light' : 'dark');
}

// Inicializar tema desde preferencia guardada o sistema.
(function initTheme() {
  const saved = localStorage.getItem('aula-theme');
  if (saved === 'dark' || saved === 'light') {
    applyTheme(saved);
  } else {
    applyTheme(window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  }
})();

$('theme-toggle').addEventListener('click', toggleTheme);

/* ══════════════════════════════════════════════════════════════════════════
   4. NAVEGACIÓN ENTRE PANELES
   ══════════════════════════════════════════════════════════════════════════ */

/**
 * Activa el panel indicado y marca el botón de nav correspondiente.
 * @param {string} panelId - ID del panel a mostrar.
 */
function showPanel(panelId) {
  // Paneles
  qsa('.panel').forEach(p => {
    p.hidden = (p.id !== panelId);
  });
  // Sidebar nav
  qsa('.nav-item').forEach(btn => {
    const active = btn.dataset.panel === panelId;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-selected', String(active));
  });
  // Mobile nav
  qsa('.mobile-nav-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.panel === panelId);
  });
}

// Bind botones de sidebar
qsa('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => showPanel(btn.dataset.panel));
});

// Bind botones de mobile nav
qsa('.mobile-nav-item').forEach(btn => {
  btn.addEventListener('click', () => showPanel(btn.dataset.panel));
});

// Menú hamburguesa en móvil
$('menu-toggle').addEventListener('click', () => {
  const sidebar = $('sidebar');
  const open = sidebar.classList.toggle('open');
  $('menu-toggle').setAttribute('aria-expanded', String(open));
});

// Cerrar sidebar al hacer clic fuera en móvil
document.addEventListener('click', e => {
  const sidebar = $('sidebar');
  if (sidebar.classList.contains('open') &&
      !sidebar.contains(e.target) &&
      e.target !== $('menu-toggle')) {
    sidebar.classList.remove('open');
    $('menu-toggle').setAttribute('aria-expanded', 'false');
  }
});

/* ══════════════════════════════════════════════════════════════════════════
   5. SISTEMA DE TOASTS
   ══════════════════════════════════════════════════════════════════════════ */

/**
 * Muestra un toast no bloqueante en la esquina inferior derecha.
 * @param {string} msg - Mensaje a mostrar.
 * @param {'success'|'error'|'info'|'warn'} type - Tipo de toast.
 * @param {number} [duration=4000] - Ms hasta el auto-dismiss.
 */
function toast(msg, type = 'info', duration = 4000) {
  const container = $('toast-container');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  el.setAttribute('role', 'alert');

  // Cerrar al hacer clic
  el.addEventListener('click', () => dismissToast(el));

  container.prepend(el);

  // Auto-dismiss
  setTimeout(() => dismissToast(el), duration);
}

function dismissToast(el) {
  if (!el.isConnected) return;
  el.classList.add('toast-out');
  el.addEventListener('animationend', () => el.remove(), {once: true});
}

/* ══════════════════════════════════════════════════════════════════════════
   6. PALETA DE COLORES POR CLASE
   ══════════════════════════════════════════════════════════════════════════ */

// Colores visualmente distinguibles para bounding boxes y badges
const CLASS_COLORS = [
  '#e63946', '#457b9d', '#f4a261', '#2a9d8f', '#e9c46a',
  '#6a4c93', '#f72585', '#4cc9f0', '#80b918', '#ff6b6b',
  '#48cae4', '#f77f00', '#7209b7', '#06d6a0', '#ef233c',
  '#3a86ff', '#fb8500', '#8338ec', '#219ebc', '#d62828',
];

/** Devuelve el color asignado a una clase por su ID. */
function classColor(classId) {
  return CLASS_COLORS[Number(classId) % CLASS_COLORS.length];
}

/* ══════════════════════════════════════════════════════════════════════════
   7. API — COMUNICACIÓN CON EL SERVIDOR
   ══════════════════════════════════════════════════════════════════════════ */

/** Devuelve el token introducido en el campo de clave. */
function getToken() {
  return $('token').value;
}

/** Cabeceras de autenticación. */
function authHeaders() {
  return {'X-Aula-Token': getToken()};
}

/**
 * Realiza una petición fetch y devuelve el JSON.
 * Lanza Error con mensaje legible en caso de fallo.
 */
async function apiRequest(url, options = {}) {
  const response = await fetch(url, options);
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error('El servidor no devolvió una respuesta válida.');
  }
  if (!response.ok) {
    const detail = typeof result.detail === 'string' ? result.detail : 'Revisa los datos enviados.';
    throw new Error(detail);
  }
  return result;
}

/**
 * Construye FormData + opciones para subir un archivo.
 * Lanza Error si falta token o archivo.
 */
function buildUpload(inputId, maxMiB) {
  if (!getToken()) throw new Error('Introduce la clave del aula.');
  const file = $(inputId).files[0];
  if (!file) throw new Error('Selecciona primero un archivo.');
  if (file.size > maxMiB * 1024 * 1024) throw new Error(`El archivo supera ${maxMiB} MiB.`);
  const body = new FormData();
  body.append('file', file);
  return {method: 'POST', body, headers: authHeaders()};
}

/**
 * Ejecuta una función asíncrona con el flag de busy activo,
 * deshabilitando los botones de carga y análisis.
 */
async function withBusy(work) {
  if (STATE.busy) return;
  STATE.busy = true;
  for (const id of ['load', 'predict', 'reanalyze']) {
    const el = $(id);
    if (el) el.disabled = true;
  }
  try {
    await work();
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    STATE.busy = false;
    for (const id of ['load', 'predict', 'reanalyze']) {
      const el = $(id);
      if (el) el.disabled = false;
    }
  }
}

/* ══════════════════════════════════════════════════════════════════════════
   8. ESTADO DEL SERVIDOR Y MODELO
   ══════════════════════════════════════════════════════════════════════════ */

/**
 * Consulta /api/status y actualiza toda la UI de conexión.
 */
async function refreshStatus() {
  const data = await apiRequest('/api/status');

  STATE.modelId = data.model_id;
  STATE.modelReady = data.ready;
  STATE.modelLabels = data.ready ? (data.model.classes || []) : [];

  // Indicador de conexión (punto pulsante)
  const dot = $('status-dot');
  const label = $('status-label');
  if (data.ready) {
    dot.classList.add('connected');
    label.textContent = 'Modelo preparado';
  } else {
    dot.classList.remove('connected');
    label.textContent = 'Sin modelo activo';
  }

  // Info del modelo en panel Conexión
  const icon = $('model-status-icon');
  const title = $('model-info-title');
  const infoEl = $('model-info');
  if (data.ready) {
    icon.classList.add('ready');
    title.textContent = data.model.name;
    infoEl.textContent = `Etiquetas: ${data.model.classes.join(', ')}`;
  } else {
    icon.classList.remove('ready');
    title.textContent = 'Sin modelo activo';
    infoEl.textContent = 'Todavía no hay un modelo cargado.';
  }

  // Botones de cámara
  $('camera-start').disabled = !data.ready || STATE.cameraRunning;
  if (!STATE.cameraRunning) {
    $('camera-status').textContent = data.ready
      ? 'Detector preparado. Pulsa Iniciar cámara para comenzar.'
      : 'Carga un paquete de detección para utilizar esta función.';
  }
}

/* ══════════════════════════════════════════════════════════════════════════
   9. PANEL MODELO — CARGA DE ZIP CON DRAG & DROP
   ══════════════════════════════════════════════════════════════════════════ */

/** Configura una drop zone para ficheros. */
function setupDropZone(dropZoneId, inputId, onFileSelected) {
  const zone = $(dropZoneId);
  const input = $(inputId);

  // Clic en la zona → abrir selector de fichero
  zone.addEventListener('click', e => {
    if (e.target !== input) input.click();
  });

  // Teclado (accesibilidad)
  zone.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); }
  });

  // Drag events
  zone.addEventListener('dragover', e => {
    e.preventDefault();
    zone.classList.add('drag-over');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) {
      setFileOnInput(input, file);
      onFileSelected(file);
    }
  });

  // Input change
  input.addEventListener('change', () => {
    if (input.files[0]) onFileSelected(input.files[0]);
  });
}

/** Asigna programáticamente un File a un input[type=file]. */
function setFileOnInput(input, file) {
  try {
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
  } catch { /* No todos los navegadores soportan DataTransfer asignable */ }
}

// Drop zone del modelo
setupDropZone('model-drop-zone', 'model', file => {
  $('model-file-name').hidden = false;
  $('model-file-label').textContent = file.name;
});

// Botón "Cargar modelo"
$('load').addEventListener('click', () => withBusy(async () => {
  if (STATE.cameraRunning) await stopCamera();
  $('model-skeleton').hidden = false;
  try {
    await apiRequest('/api/model', buildUpload('model', 64));
    $('results').hidden = true;
    await refreshStatus();
    toast('Modelo cargado correctamente.', 'success');
  } finally {
    $('model-skeleton').hidden = true;
  }
}));

/* ══════════════════════════════════════════════════════════════════════════
   10. PANEL ANÁLISIS — PREDICT + CANVAS + ZOOM/PAN
   ══════════════════════════════════════════════════════════════════════════ */

/* ── 10a. Slider de umbral ─────────────────────────────────────────────── */

const thresholdSlider = $('threshold');
const thresholdDisplay = $('threshold-display');

/** Actualiza el display del slider y el gradiente de fondo. */
function updateSliderUI() {
  const val = Number(thresholdSlider.value);
  thresholdDisplay.textContent = val.toFixed(2);
  const pct = ((val - 0.01) / (1 - 0.01) * 100).toFixed(1);
  thresholdSlider.style.setProperty('--slider-pct', `${pct}%`);
}

thresholdSlider.addEventListener('input', updateSliderUI);
updateSliderUI();

/* ── 10b. Drop zone de imagen ──────────────────────────────────────────── */

setupDropZone('image-drop-zone', 'image', file => {
  STATE.lastImageFile = file;
  $('results').hidden = true;
  $('results-placeholder').style.display = '';
  resetCanvas();

  const reader = new FileReader();
  reader.onload = e => {
    loadImageOnCanvas(e.target.result);
  };
  reader.readAsDataURL(file);

  $('reanalyze').hidden = false;
  $('export-json-btn').hidden = true;
  $('export-canvas-btn').hidden = true;
});

/* ── 10c. Canvas — dibujar imagen y bounding boxes ─────────────────────── */

const canvas = $('preview-canvas');
const ctx = canvas.getContext('2d');

/** Carga una imagen (URL/dataURL) en el canvas sin detecciones. */
function loadImageOnCanvas(src) {
  const img = new Image();
  img.onload = () => {
    STATE.canvasImg = img;
    STATE.canvasDetections = [];
    STATE.canvasScale = 1;
    STATE.canvasOffsetX = 0;
    STATE.canvasOffsetY = 0;
    fitCanvasToContainer();
    renderCanvas();
    $('canvas-wrapper').hidden = false;
  };
  img.src = src;
}

/** Ajusta el tamaño del canvas al contenedor y calcula escala inicial. */
function fitCanvasToContainer() {
  if (!STATE.canvasImg) return;
  const wrapper = $('canvas-wrapper');
  const maxW = wrapper.clientWidth || 600;
  const maxH = 360;
  const scale = Math.min(maxW / STATE.canvasImg.width, maxH / STATE.canvasImg.height, 1);
  canvas.width = STATE.canvasImg.width;
  canvas.height = STATE.canvasImg.height;
  canvas.style.width = `${Math.round(STATE.canvasImg.width * scale)}px`;
  canvas.style.height = `${Math.round(STATE.canvasImg.height * scale)}px`;
}

/** Limpia el canvas y resetea estado de zoom/pan. */
function resetCanvas() {
  STATE.canvasImg = null;
  STATE.canvasDetections = [];
  STATE.canvasScale = 1;
  STATE.canvasOffsetX = 0;
  STATE.canvasOffsetY = 0;
  $('canvas-wrapper').hidden = true;
}

/**
 * Renderiza la imagen + bounding boxes en el canvas aplicando zoom y pan.
 * Las bounding boxes vienen en coordenadas de la imagen original.
 */
function renderCanvas() {
  if (!STATE.canvasImg) return;
  const img = STATE.canvasImg;
  const s = STATE.canvasScale;
  const ox = STATE.canvasOffsetX;
  const oy = STATE.canvasOffsetY;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  ctx.translate(ox, oy);
  ctx.scale(s, s);
  ctx.drawImage(img, 0, 0);

  // Dibujar bounding boxes
  for (const det of STATE.canvasDetections) {
    const [x1, y1, x2, y2] = det.box;
    const color = classColor(det.class_id);
    const lw = Math.max(2, Math.round(2 / s));

    ctx.strokeStyle = color;
    ctx.lineWidth = lw;
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

    // Label con fondo sólido
    const label = `${det.label} ${fmtPct(det.score)}`;
    const fontSize = Math.max(11, Math.round(14 / s));
    ctx.font = `600 ${fontSize}px system-ui, sans-serif`;
    const tw = ctx.measureText(label).width;
    const padX = 5, padY = 3;
    const lh = fontSize + padY * 2;
    const ly = Math.max(0, y1 - lh);

    ctx.fillStyle = color;
    ctx.fillRect(x1 - lw / 2, ly, tw + padX * 2, lh);

    ctx.fillStyle = '#ffffff';
    ctx.fillText(label, x1 + padX - lw / 2, ly + lh - padY - 1);
  }
  ctx.restore();
}

/* ── 10d. Zoom y pan en el canvas ──────────────────────────────────────── */

canvas.addEventListener('wheel', e => {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
  const newScale = clamp(STATE.canvasScale * factor, 0.2, 10);

  // Zoom hacia el punto del cursor
  const rect = canvas.getBoundingClientRect();
  const mx = (e.clientX - rect.left) * (canvas.width / rect.width);
  const my = (e.clientY - rect.top) * (canvas.height / rect.height);

  STATE.canvasOffsetX = mx - (mx - STATE.canvasOffsetX) * (newScale / STATE.canvasScale);
  STATE.canvasOffsetY = my - (my - STATE.canvasOffsetY) * (newScale / STATE.canvasScale);
  STATE.canvasScale = newScale;
  renderCanvas();
}, {passive: false});

canvas.addEventListener('mousedown', e => {
  STATE.canvasDragging = true;
  STATE.canvasDragStart = {x: e.clientX - STATE.canvasOffsetX, y: e.clientY - STATE.canvasOffsetY};
});

window.addEventListener('mousemove', e => {
  if (!STATE.canvasDragging) return;
  STATE.canvasOffsetX = e.clientX - STATE.canvasDragStart.x;
  STATE.canvasOffsetY = e.clientY - STATE.canvasDragStart.y;
  renderCanvas();
});

window.addEventListener('mouseup', () => { STATE.canvasDragging = false; });

// Botones de zoom
$('zoom-in-btn').addEventListener('click', () => {
  STATE.canvasScale = clamp(STATE.canvasScale * 1.25, 0.2, 10);
  renderCanvas();
});
$('zoom-out-btn').addEventListener('click', () => {
  STATE.canvasScale = clamp(STATE.canvasScale / 1.25, 0.2, 10);
  renderCanvas();
});
$('zoom-reset-btn').addEventListener('click', () => {
  STATE.canvasScale = 1;
  STATE.canvasOffsetX = 0;
  STATE.canvasOffsetY = 0;
  renderCanvas();
});

/* ── 10e. Análisis y re-análisis ───────────────────────────────────────── */

/** Sube una imagen y ejecuta el análisis en el servidor. */
async function runPredict(file) {
  if (!getToken()) throw new Error('Introduce la clave del aula.');
  if (!file) throw new Error('Selecciona primero una imagen.');
  if (file.size > 10 * 1024 * 1024) throw new Error('El archivo supera 10 MiB.');

  const threshold = Number(thresholdSlider.value);

  // Mostrar skeleton mientras procesa
  $('predict-skeleton').hidden = false;
  $('results').hidden = true;
  $('results-placeholder').style.display = 'none';

  try {
    const body = new FormData();
    body.append('file', file);
    const result = await apiRequest(
      `/api/predict?threshold=${threshold}`,
      {method: 'POST', body, headers: authHeaders()}
    );

    STATE.lastDetections = result.detections;
    STATE.lastImageMeta = {
      inference_ms: result.inference_ms,
      processing_ms: result.processing_ms,
      threshold,
    };

    // Actualizar canvas con la imagen anotada del servidor y detecciones
    const imgSrc = `data:image/jpeg;base64,${result.annotated_image}`;
    // Cargar imagen original para el canvas (con nuestro propio dibujo)
    const origReader = new FileReader();
    origReader.onload = e => {
      loadImageOnCanvas(e.target.result);
      // Esperar a que la imagen cargue antes de añadir detecciones
      setTimeout(() => {
        STATE.canvasDetections = result.detections;
        renderCanvas();
      }, 50);
    };
    origReader.readAsDataURL(file);

    // Renderizar panel de resultados
    renderResults(result);

    // Añadir al historial
    historyAdd(file.name, imgSrc, result.detections.length);

    // Mostrar botones adicionales
    $('reanalyze').hidden = false;
    $('export-json-btn').hidden = false;
    $('export-canvas-btn').hidden = false;

    toast(`Se detectaron ${result.detections.length} objeto(s).`, 'success');
  } finally {
    $('predict-skeleton').hidden = true;
  }
}

$('predict').addEventListener('click', () => withBusy(async () => {
  const file = $('image').files[0];
  STATE.lastImageFile = file;
  await runPredict(file);
}));

$('reanalyze').addEventListener('click', () => withBusy(async () => {
  if (!STATE.lastImageFile) {
    toast('No hay ninguna imagen para re-analizar.', 'warn');
    return;
  }
  await runPredict(STATE.lastImageFile);
}));

/* ── 10f. Renderizar panel de resultados ────────────────────────────────── */

/** Renderiza las detecciones en el panel de resultados lateral. */
function renderResults(result) {
  const dets = result.detections;

  // Resumen
  $('stat-total').textContent = dets.length;

  if (dets.length > 0) {
    // Clase más frecuente
    const freq = {};
    for (const d of dets) freq[d.label] = (freq[d.label] || 0) + 1;
    const topClass = Object.entries(freq).sort((a, b) => b[1] - a[1])[0][0];
    $('stat-top-class').textContent = topClass;

    // Confianza media
    const avgConf = dets.reduce((acc, d) => acc + d.score, 0) / dets.length;
    $('stat-avg-conf').textContent = fmtPct(avgConf);
  } else {
    $('stat-top-class').textContent = '—';
    $('stat-avg-conf').textContent = '—';
  }

  // Timing
  $('timing').textContent =
    `Inferencia: ${fmtMs(result.inference_ms)} · Procesamiento: ${fmtMs(result.processing_ms)}`;

  // Cards de detección
  const scoresEl = $('scores');
  scoresEl.replaceChildren();

  for (const [idx, det] of dets.entries()) {
    const color = classColor(det.class_id);
    const pct = det.score * 100;
    const confClass = pct >= 70 ? 'conf-high' : pct >= 50 ? 'conf-mid' : 'conf-low';

    const card = document.createElement('div');
    card.className = 'detection-card';
    card.style.setProperty('--card-color', color);

    card.innerHTML = `
      <div class="detection-card-header">
        <span class="detection-label">${escapeHtml(det.label)} <small style="color:var(--text-muted)">#${idx + 1}</small></span>
        <span class="detection-badge">${fmtPct(det.score)}</span>
      </div>
      <div class="confidence-bar-wrap">
        <div class="confidence-bar ${confClass}" style="width:${pct.toFixed(1)}%"></div>
      </div>`;

    scoresEl.append(card);
  }

  $('results').hidden = false;
  $('results-placeholder').style.display = 'none';
}

/* ── 10g. Exportar resultados ───────────────────────────────────────────── */

/** Escapa caracteres especiales HTML. */
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Exporta el resultado como archivo JSON. */
$('export-json-btn').addEventListener('click', () => {
  if (!STATE.lastDetections) return;
  const payload = {
    timestamp: new Date().toISOString(),
    threshold: STATE.lastImageMeta?.threshold,
    inference_ms: STATE.lastImageMeta?.inference_ms,
    processing_ms: STATE.lastImageMeta?.processing_ms,
    total_objects: STATE.lastDetections.length,
    detections: STATE.lastDetections,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {type: 'application/json'});
  downloadBlob(blob, `aula-ia-detecciones-${Date.now()}.json`);
  toast('JSON exportado.', 'success');
});

/** Exporta la imagen anotada del canvas como JPEG. */
$('export-canvas-btn').addEventListener('click', () => {
  if (!STATE.canvasImg) return;
  canvas.toBlob(blob => {
    downloadBlob(blob, `aula-ia-anotada-${Date.now()}.jpg`);
    toast('Imagen exportada.', 'success');
  }, 'image/jpeg', 0.92);
});

/** Descarga un Blob como fichero. */
function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

/* ══════════════════════════════════════════════════════════════════════════
   11. PANEL CÁMARA
   ══════════════════════════════════════════════════════════════════════════ */

/** Opciones de fetch para las llamadas de cámara. */
function cameraFetchOptions() {
  if (!getToken()) throw new Error('Introduce la clave del aula.');
  return {method: 'POST', headers: authHeaders()};
}

/** Detiene la cámara limpiando estado y UI. */
async function stopCamera() {
  STATE.cameraRunning = false;
  STATE.cameraSession++;
  $('camera-stop').disabled = true;
  $('camera-screenshot').disabled = true;
  $('camera-screenshot').hidden = true;
  try {
    await apiRequest('/api/camera/stop', cameraFetchOptions());
  } catch (error) {
    toast(error.message, 'warn');
  }
  $('camera-start').disabled = !STATE.modelReady;
  $('camera-status').textContent = 'Cámara detenida.';
  $('camera-preview').hidden = true;
  $('camera-live').hidden = true;
  $('camera-overlay').hidden = true;
  if (STATE.cameraURL) {
    URL.revokeObjectURL(STATE.cameraURL);
    STATE.cameraURL = null;
  }
}

/**
 * Actualiza estadísticas de la cámara a partir de los headers de respuesta.
 */
function updateCameraStats(response, elapsed) {
  STATE.cameraFrames++;
  STATE.frameTimes.push(performance.now());
  if (STATE.frameTimes.length > 25) STATE.frameTimes.shift();

  const span = STATE.frameTimes.at(-1) - STATE.frameTimes[0];
  const fps = STATE.frameTimes.length > 1 && span > 0
    ? ((STATE.frameTimes.length - 1) * 1000 / span).toFixed(1)
    : '—';

  const objCount = response.headers.get('X-Object-Count') || '0';
  const inferencMs = response.headers.get('X-Inference-Ms');
  const frameMs = response.headers.get('X-Frame-Ms');
  const w = response.headers.get('X-Frame-Width');
  const h = response.headers.get('X-Frame-Height');

  // Panel lateral
  $('stat-objects').textContent = objCount;
  $('stat-fps').textContent = fps;
  $('stat-inference').textContent = fmtMs(inferencMs);
  $('stat-frame').textContent = fmtMs(frameMs);
  $('stat-network').textContent = fmtMs(elapsed);
  $('stat-frames').textContent = String(STATE.cameraFrames);
  $('stat-resolution').textContent = w && h ? `${w} × ${h}` : '—';

  // Overlay sobre la imagen
  $('overlay-fps').textContent = fps;
  $('overlay-objects').textContent = objCount;
  $('overlay-inference').textContent = fmtMs(inferencMs);

  // Lista de etiquetas
  const countsEl = $('camera-counts');
  countsEl.replaceChildren();
  let counts = {};
  try { counts = JSON.parse(response.headers.get('X-Object-Counts') || '{}'); } catch {}

  const entries = Object.entries(counts);
  if (entries.length === 0) {
    const li = document.createElement('li');
    li.textContent = 'Sin objetos detectados';
    li.style.color = 'var(--text-muted)';
    countsEl.append(li);
  } else {
    for (const [id, count] of entries) {
      const label = response.headers.get('X-Model-Id') === STATE.modelId
        ? (STATE.modelLabels[Number(id)] || `Clase ${id}`)
        : `Clase ${Number(id) + 1}`;
      const color = classColor(id);
      const li = document.createElement('li');
      li.className = 'camera-count-item';
      li.innerHTML = `
        <span class="camera-count-dot" style="background:${color}"></span>
        <span>${escapeHtml(label)}: <strong>${count}</strong></span>`;
      countsEl.append(li);
    }
  }
}

/**
 * Solicita un fotograma al servidor, actualiza la imagen y vuelve a programarse.
 * @param {number} session - ID de sesión; el loop se cancela si difiere del actual.
 */
async function cameraFrame(session) {
  if (!STATE.cameraRunning || session !== STATE.cameraSession) return;
  const start = performance.now();
  try {
    const threshold = Number(thresholdSlider.value);
    const resolution = $('camera-resolution').value;
    const response = await fetch(
      `/api/camera/frame?threshold=${threshold}&resolution=${resolution}`,
      cameraFetchOptions()
    );

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      // 409 "ocupado" → reintentar tras 500 ms
      if (response.status === 409 && String(err.detail).includes('ocupado') && STATE.cameraRunning) {
        setTimeout(() => cameraFrame(session), 500);
        return;
      }
      throw new Error(err.detail || 'No se puede leer la cámara.');
    }

    const blob = await response.blob();
    if (!STATE.cameraRunning || session !== STATE.cameraSession) return;

    const elapsed = performance.now() - start;

    // Actualizar modelo si cambió
    if (response.headers.get('X-Model-Id') !== STATE.modelId) await refreshStatus();
    if (!STATE.cameraRunning || session !== STATE.cameraSession) return;

    // Actualizar imagen
    if (STATE.cameraURL) URL.revokeObjectURL(STATE.cameraURL);
    STATE.cameraURL = URL.createObjectURL(blob);
    $('camera-preview').src = STATE.cameraURL;
    $('camera-preview').hidden = false;
    $('camera-live').hidden = false;
    $('camera-overlay').hidden = false;

    updateCameraStats(response, elapsed);

    const active = 'Cámara activa · detección en directo.';
    if ($('camera-status').textContent !== active) {
      $('camera-status').textContent = active;
    }

    // Programar siguiente frame (~200 ms mínimo entre peticiones)
    setTimeout(() => cameraFrame(session), Math.max(0, 200 - elapsed));

  } catch (error) {
    if (session !== STATE.cameraSession) return;
    await stopCamera();
    toast(error.message, 'error');
  }
}

// Iniciar cámara
$('camera-start').addEventListener('click', () => withBusy(async () => {
  await apiRequest('/api/camera/start', cameraFetchOptions());
  STATE.cameraRunning = true;
  STATE.cameraSession++;
  STATE.cameraFrames = 0;
  STATE.frameTimes = [];
  $('camera-start').disabled = true;
  $('camera-stop').disabled = false;
  $('camera-screenshot').disabled = false;
  $('camera-screenshot').hidden = false;
  cameraFrame(STATE.cameraSession);
}));

// Detener cámara
$('camera-stop').addEventListener('click', stopCamera);

// Captura de pantalla de la cámara
$('camera-screenshot').addEventListener('click', () => {
  const img = $('camera-preview');
  if (!img.src) return;
  const a = document.createElement('a');
  a.href = img.src;
  a.download = `aula-ia-captura-${Date.now()}.jpg`;
  a.click();
  toast('Captura descargada.', 'success');
});

// Limpiar session al cerrar la pestaña
window.addEventListener('pagehide', () => {
  if (STATE.cameraRunning) {
    STATE.cameraRunning = false;
    const opts = {method: 'POST', headers: {'X-Aula-Token': getToken()}, keepalive: true};
    fetch('/api/camera/stop', opts).catch(() => {});
  }
});

/* ══════════════════════════════════════════════════════════════════════════
   12. HISTORIAL DE SESIÓN (localStorage + base64)
   ══════════════════════════════════════════════════════════════════════════ */

const HISTORY_KEY = 'aula-ia-history';
const HISTORY_MAX = 5;

/** Carga el historial desde localStorage. */
function historyLoad() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
  } catch { return []; }
}

/** Guarda el historial en localStorage. */
function historySave(items) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(items));
  } catch { /* cuota excedida */ }
}

/**
 * Añade una entrada al historial y renderiza el panel.
 * @param {string} name  - Nombre del archivo.
 * @param {string} src   - Data URL de la imagen anotada.
 * @param {number} count - Número de objetos detectados.
 */
function historyAdd(name, src, count) {
  let items = historyLoad();
  items.unshift({name, src, count, ts: Date.now()});
  if (items.length > HISTORY_MAX) items = items.slice(0, HISTORY_MAX);
  historySave(items);
  renderHistory();
}

/** Renderiza el panel de historial. */
function renderHistory() {
  const items = historyLoad();
  const grid = $('history-grid');
  const empty = $('history-empty');

  // Limpiar ítems previos (conservar el placeholder)
  qsa('.history-item', grid).forEach(el => el.remove());

  if (items.length === 0) {
    empty.style.display = '';
    return;
  }
  empty.style.display = 'none';

  for (const item of items) {
    const el = document.createElement('div');
    el.className = 'history-item';
    el.setAttribute('tabindex', '0');
    el.setAttribute('role', 'button');
    el.setAttribute('aria-label', `${item.name} — ${item.count} objetos`);
    el.innerHTML = `
      <img class="history-thumb" src="${item.src}" alt="${escapeHtml(item.name)}" loading="lazy">
      <div class="history-meta">
        <div class="history-name">${escapeHtml(item.name)}</div>
        <div class="history-count">${item.count} objeto(s)</div>
      </div>`;
    el.addEventListener('click', () => {
      // Al hacer clic en un ítem del historial, cargar la imagen en el canvas del panel de análisis
      loadImageOnCanvas(item.src);
      showPanel('panel-predict');
      toast(`Imagen "${item.name}" cargada desde el historial.`, 'info');
    });
    el.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') el.click();
    });
    grid.append(el);
  }
}

// Limpiar historial
$('clear-history-btn').addEventListener('click', () => {
  localStorage.removeItem(HISTORY_KEY);
  renderHistory();
  toast('Historial eliminado.', 'info');
});

/* ══════════════════════════════════════════════════════════════════════════
   13. INICIALIZACIÓN
   ══════════════════════════════════════════════════════════════════════════ */

/** Arranca la aplicación: comprueba estado del servidor y renderiza historial. */
async function init() {
  try {
    await refreshStatus();
  } catch (error) {
    toast(`Sin conexión con el servidor: ${error.message}`, 'error', 7000);
    $('status-dot').classList.remove('connected');
    $('status-label').textContent = 'Sin conexión';
  }
  renderHistory();
}

init();
