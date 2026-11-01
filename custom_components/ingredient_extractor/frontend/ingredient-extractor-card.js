/* Ingredient Extractor card: photo of a recipe -> items on the shopping list.
 * Single vanilla JS file, no build step, no imports. */
const IE_VERSION = '0.1.8';
const IE_ENDPOINT = '/api/ingredient_extractor/extract';
const IE_TIMEOUT_MS = 60000;
const IE_MAX_BYTES = 4 * 1024 * 1024; // keep under the backend's 5 MB limit

// Friendly fallbacks, used only when the server sends no `message`.
const IE_MESSAGES = {
  no_image: 'No image was received.',
  too_large: 'That image is too large. Try a smaller photo.',
  unsupported_type: "That image format isn't supported. Try a JPEG or PNG.",
  not_a_recipe: "That doesn't look like a recipe. Try a photo of the ingredients list.",
  no_ingredients: 'No ingredients were found in that photo.',
  provider_auth: 'The AI provider rejected the API key. Check the integration settings.',
  provider_error: 'The AI service had a problem. Please try again.',
  timeout: 'The AI took too long to respond. Please try again.',
  todo_error: "Some items couldn't be added to the list.",
  not_configured: "Ingredient Extractor isn't set up yet. Add the integration first.",
  unknown: 'Something went wrong. Please try again.',
};

const IE_STYLE = `
  :host { display: block; }
  .body { padding: 0 16px 16px; }
  .dropzone {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 8px; box-sizing: border-box; min-height: 140px; padding: 20px 12px;
    border: 2px dashed var(--divider-color); border-radius: var(--ha-card-border-radius, 12px);
    color: var(--secondary-text-color); text-align: center; cursor: pointer;
    transition: border-color .15s, background-color .15s;
  }
  .dropzone:hover, .dropzone.drag, .dropzone:focus-within {
    border-color: var(--primary-color); background: var(--secondary-background-color);
  }
  .dropzone:focus-within { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .dropzone ha-icon { --mdc-icon-size: 40px; color: var(--primary-color); }
  .dropzone .label { font-size: 1rem; color: var(--primary-text-color); }
  /* Camera + library side by side on touch devices. */
  .tiles { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .tiles .dropzone { min-height: 120px; padding: 16px 8px; }
  /* Visually hidden but still focusable, so keyboard and screen readers work. */
  .sr-input {
    position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0;
    overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
  }
  .status { display: flex; align-items: center; gap: 12px; padding: 8px 0; }
  .status .text { flex: 1; min-width: 0; color: var(--primary-text-color); }
  .thumb {
    width: 56px; height: 56px; flex: none; object-fit: cover;
    border-radius: 8px; border: 1px solid var(--divider-color);
  }
  .spinner {
    width: 32px; height: 32px; flex: none; box-sizing: border-box; border-radius: 50%;
    border: 3px solid var(--divider-color); border-top-color: var(--primary-color);
    animation: spin .8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) { .spinner { animation-duration: 3s; } }
  .headline { display: flex; align-items: center; gap: 8px; font-weight: 500; color: var(--primary-text-color); }
  .headline ha-icon { flex: none; }
  .ok ha-icon { color: var(--success-color, var(--primary-color)); }
  .err ha-icon { color: var(--error-color); }
  .err .headline { color: var(--error-color); }
  ul.items { margin: 12px 0; padding: 0; list-style: none; max-height: 40vh; overflow-y: auto; }
  ul.items li { padding: 6px 0; border-bottom: 1px solid var(--divider-color); overflow-wrap: anywhere; }
  ul.items li:last-child { border-bottom: 0; }
  .err .detail { margin: 8px 0 0; color: var(--secondary-text-color); overflow-wrap: anywhere; }
  button.action {
    margin-top: 12px; padding: 10px 16px; min-height: 40px; font: inherit; font-weight: 500;
    color: var(--text-primary-color, #fff); background: var(--primary-color);
    border: 0; border-radius: 8px; cursor: pointer;
  }
  button.action:focus-visible { outline: 2px solid var(--primary-text-color); outline-offset: 2px; }
  button.action.secondary {
    color: var(--primary-text-color); background: var(--secondary-background-color);
  }
  /* Live viewfinder (Android, where the app ignores the file input's capture hint). */
  .viewfinder video {
    display: block; width: 100%; max-height: 45vh; object-fit: contain;
    background: #000; border-radius: var(--ha-card-border-radius, 12px);
  }
  /* Buttons sit over the bottom of the video so they stay visible on short screens. */
  .viewfinder { position: relative; }
  .viewfinder .actions {
    position: absolute; left: 12px; right: 12px; bottom: 12px; display: flex; gap: 8px;
  }
  .viewfinder .actions button { flex: 1; margin-top: 0; box-shadow: 0 2px 6px rgba(0, 0, 0, .4); }
`;

/* Tiny DOM helper: all text goes through textContent, never innerHTML. */
function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (v === true) node.setAttribute(k, '');
    else if (v !== false && v != null) node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) if (c) node.appendChild(c);
  return node;
}

/* Error carrying one of the contract's error codes. */
class ExtractError extends Error {
  constructor(code, message, items) {
    super(message || IE_MESSAGES[code] || IE_MESSAGES.unknown);
    this.code = code;
    this.items = items;
  }
}

/* Decode, orient, downscale and re-encode as JPEG. Falls back to the original
 * file if the browser cannot decode it (e.g. HEIC); the backend then answers
 * 415 with a clear message. */
async function prepareImage(file) {
  // Some Android pickers report an empty type; let decoding decide in that case.
  if (!file || (file.type && !file.type.startsWith('image/'))) {
    throw new ExtractError('unsupported_type');
  }
  let bitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
  } catch (e) {
    return file;
  }
  try {
    const encode = async (longEdge, quality) => {
      const scale = Math.min(1, longEdge / Math.max(bitmap.width, bitmap.height)); // never upscale
      const w = Math.max(1, Math.round(bitmap.width * scale));
      const h = Math.max(1, Math.round(bitmap.height * scale));
      const canvas = typeof OffscreenCanvas !== 'undefined'
        ? new OffscreenCanvas(w, h)
        : Object.assign(document.createElement('canvas'), { width: w, height: h });
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#fff'; // flatten transparent PNGs onto white
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(bitmap, 0, 0, w, h);
      const blob = canvas.convertToBlob
        ? await canvas.convertToBlob({ type: 'image/jpeg', quality })
        : await new Promise((res) => canvas.toBlob(res, 'image/jpeg', quality));
      if (!blob) throw new Error('encode failed');
      return blob;
    };
    let blob;
    try {
      blob = await encode(1568, 0.85);
      if (blob.size > IE_MAX_BYTES) blob = await encode(1280, 0.7);
    } catch (e) {
      return file; // canvas trouble: let the backend judge the original
    }
    if (blob.size > IE_MAX_BYTES) throw new ExtractError('too_large');
    return blob;
  } finally {
    bitmap.close();
  }
}

class IngredientExtractorCard extends HTMLElement {
  constructor() {
    super();
    this._state = 'idle'; // idle | working | success | error
    this._thumbUrl = null;
    this._busy = false;
    this.attachShadow({ mode: 'open' });
  }

  // Future modes (link, manual add) would be read from config here and just supply
  // a different payload builder to _submit.
  setConfig(config) {
    if (config != null && typeof config !== 'object') throw new Error('Invalid configuration');
    if (config && config.title != null && typeof config.title !== 'string') {
      throw new Error('"title" must be a string');
    }
    if (config && config.camera != null && ![true, false, 'auto'].includes(config.camera)) {
      throw new Error('"camera" must be true, false or auto');
    }
    this._config = { title: 'Recipe to shopping list', camera: 'auto', ...(config || {}) };
    this._setState('idle');
  }

  /* Camera tile: forced by config, otherwise only on touch-first devices, where
   * `capture` opens the camera. Desktop browsers ignore `capture`. */
  _showCamera() {
    const { camera } = this._config;
    if (camera !== 'auto') return camera;
    return !!(window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
  }

  /* The Android Companion app (and Android WebView generally) ignores `capture` and
   * always opens the media picker, so there the card runs its own viewfinder. iOS
   * honours `capture` and opens the native camera, which is the better experience. */
  _useLiveCamera() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)
      && /Android/i.test(navigator.userAgent);
  }

  // Store only; re-rendering on every hass update would wipe the current state.
  set hass(hass) { this._hass = hass; }

  getCardSize() { return 3; }
  getGridOptions() { return { columns: 12, min_rows: 2 }; }
  static getStubConfig() { return {}; }

  disconnectedCallback() {
    this._revokeThumb();
    this._stopCamera();
  }

  /* ---------- live camera ---------- */

  async _startCamera() {
    if (this._busy) return;
    this._setState('camera');
    this.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    // Most demanding first; some devices reject resolution hints outright.
    const attempts = [
      { facingMode: { ideal: 'environment' }, width: { ideal: 3840 }, height: { ideal: 2160 } },
      { facingMode: { ideal: 'environment' } },
      true,
    ];
    let stream = null;
    let lastError = null;
    for (const video of attempts) {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: false, video });
        break;
      } catch (e) {
        lastError = e;
        if (e && (e.name === 'NotAllowedError' || e.name === 'SecurityError')) break; // retrying won't help
      }
    }
    if (!stream) {
      this._stopCamera();
      const reason = lastError && lastError.name ? lastError.name : 'unknown';
      const denied = reason === 'NotAllowedError' || reason === 'SecurityError';
      this._error = {
        code: 'camera',
        message: denied
          ? "Camera access was blocked. Allow camera access for the app, or use Choose photo."
          : "The camera couldn't be opened. Use Choose photo instead.",
        detail: `Camera error: ${reason}${lastError && lastError.message ? ` – ${lastError.message}` : ''}`,
      };
      this._setState('error');
      return;
    }
    if (this._state !== 'camera') { // cancelled while the permission prompt was up
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    this._stream = stream;
    const videoEl = this.shadowRoot.querySelector('video');
    if (videoEl) videoEl.srcObject = stream;
  }

  /* Full-resolution still where ImageCapture exists (Chrome on Android), otherwise
   * the current video frame. prepareImage() then shrinks it like any other photo. */
  async _capture() {
    const video = this.shadowRoot.querySelector('video');
    const track = this._stream && this._stream.getVideoTracks()[0];
    if (!video || !track) return;
    let blob = null;
    if (typeof ImageCapture !== 'undefined') {
      try { blob = await new ImageCapture(track).takePhoto(); } catch (e) { /* fall back to a frame */ }
    }
    if (!blob && video.videoWidth) {
      const canvas = Object.assign(document.createElement('canvas'), {
        width: video.videoWidth, height: video.videoHeight,
      });
      canvas.getContext('2d').drawImage(video, 0, 0);
      blob = await new Promise((res) => canvas.toBlob(res, 'image/jpeg', 0.92));
    }
    this._stopCamera();
    if (!blob) {
      this._error = { code: 'camera', message: "The photo couldn't be taken. Please try again." };
      this._setState('error');
      return;
    }
    this._handleFile(new File([blob], 'camera.jpg', { type: blob.type || 'image/jpeg' }));
  }

  _stopCamera() {
    if (this._stream) this._stream.getTracks().forEach((t) => t.stop());
    this._stream = null;
  }

  /* ---------- flow ---------- */

  _handleFile(file) {
    if (this._busy || !file) return;
    this._revokeThumb();
    this._thumbUrl = !file.type || file.type.startsWith('image/') ? URL.createObjectURL(file) : null;
    this._submit(async () => {
      const blob = await prepareImage(file);
      const fd = new FormData();
      fd.append('image', blob, 'recipe.jpg');
      return fd;
    });
  }

  /* Generic pathway: payloadBuilder() resolves to a request body. */
  async _submit(payloadBuilder) {
    if (this._busy) return;
    this._busy = true;
    this._setState('working');
    const ctrl = new AbortController();
    let timedOut = false;
    let timer;
    try {
      const body = await payloadBuilder();
      if (!this._hass || !this._hass.fetchWithAuth) throw new ExtractError('unknown');
      timer = setTimeout(() => { timedOut = true; ctrl.abort(); }, IE_TIMEOUT_MS);
      let resp;
      try {
        resp = await this._hass.fetchWithAuth(IE_ENDPOINT, { method: 'POST', body, signal: ctrl.signal });
      } catch (e) {
        throw new ExtractError(timedOut ? 'timeout' : 'unknown');
      }
      let data = null;
      try { data = await resp.json(); } catch (e) { /* non-JSON body */ }
      if (!data || typeof data !== 'object') throw new ExtractError('unknown');
      if (!resp.ok || data.ok === false) {
        throw new ExtractError(data.error || 'unknown', data.message, data.items);
      }
      const items = Array.isArray(data.items) ? data.items.map(String) : [];
      this._result = { items, added: Number.isFinite(data.added) ? data.added : items.length };
      this._revokeThumb();
      this._setState('success');
    } catch (e) {
      const err = e instanceof ExtractError ? e : new ExtractError('unknown');
      this._error = { code: err.code, message: err.message, items: err.items };
      this._revokeThumb();
      this._setState('error');
    } finally {
      clearTimeout(timer);
      this._busy = false;
    }
  }

  _revokeThumb() {
    if (this._thumbUrl) URL.revokeObjectURL(this._thumbUrl);
    this._thumbUrl = null;
  }

  /* ---------- rendering ---------- */

  _setState(state) {
    this._state = state;
    this._render();
  }

  _render() {
    const root = this.shadowRoot;
    const body = el('div', { class: 'body' });
    const s = this._state;
    if (s === 'idle') body.appendChild(this._renderPicker());
    else if (s === 'camera') body.appendChild(this._renderViewfinder());
    else if (s === 'working') body.appendChild(this._renderWorking());
    else if (s === 'success') body.appendChild(this._renderSuccess());
    else body.appendChild(this._renderError());
    const card = el('ha-card', { header: this._config.title }, [body]);
    root.replaceChildren(el('style', { text: IE_STYLE }), card);
  }

  _renderPicker() {
    if (!this._showCamera()) {
      return this._renderDropzone('mdi:image-plus', 'Tap to choose a recipe photo', 'Attach recipe photo');
    }
    const take = this._useLiveCamera()
      ? this._renderCameraTile()
      : this._renderDropzone('mdi:camera', 'Take photo', 'Take a photo of a recipe', 'environment');
    return el('div', { class: 'tiles' }, [
      take,
      this._renderDropzone('mdi:image-multiple', 'Choose photo', 'Choose a recipe photo'),
    ]);
  }

  /* Same look as a dropzone, but opens the in-card viewfinder. */
  _renderCameraTile() {
    const tile = el('div', {
      class: 'dropzone', role: 'button', tabindex: '0', 'aria-label': 'Take a photo of a recipe',
    }, [el('ha-icon', { icon: 'mdi:camera' }), el('span', { class: 'label', text: 'Take photo' })]);
    tile.addEventListener('click', () => this._startCamera());
    tile.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this._startCamera(); }
    });
    return tile;
  }

  _renderViewfinder() {
    const video = el('video', { autoplay: true, playsinline: true, muted: true });
    video.muted = true; // attribute alone doesn't mute in every WebView
    if (this._stream) video.srcObject = this._stream;
    const capture = el('button', { class: 'action', type: 'button', text: 'Capture' });
    capture.addEventListener('click', () => this._capture());
    const cancel = el('button', { class: 'action secondary', type: 'button', text: 'Cancel' });
    cancel.addEventListener('click', () => { this._stopCamera(); this._setState('idle'); });
    return el('div', { class: 'viewfinder' }, [video, el('div', { class: 'actions' }, [cancel, capture])]);
  }

  /* A tappable label wrapping a hidden file input. With `capture`, phones open the
   * camera directly instead of the picker. */
  _renderDropzone(icon, text, ariaLabel, capture) {
    const input = el('input', {
      class: 'sr-input', type: 'file', accept: 'image/*', capture,
      'aria-label': ariaLabel,
    });
    input.addEventListener('change', () => {
      const file = input.files && input.files[0];
      input.value = ''; // allow choosing the same file again
      this._handleFile(file);
    });
    const zone = el('label', { class: 'dropzone' }, [
      el('ha-icon', { icon }),
      el('span', { class: 'label', text }),
      input,
    ]);
    zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag'));
    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      zone.classList.remove('drag');
      this._handleFile(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]);
    });
    return zone;
  }

  _renderWorking() {
    const spinner = customElements.get('ha-circular-progress')
      ? el('ha-circular-progress', { indeterminate: true, size: 'small' })
      : el('div', { class: 'spinner' });
    const kids = [spinner, el('div', { class: 'text', text: 'Reading recipe…' })];
    if (this._thumbUrl) kids.push(el('img', { class: 'thumb', src: this._thumbUrl, alt: 'Selected recipe photo' }));
    return el('div', { class: 'status', role: 'status', 'aria-live': 'polite' }, kids);
  }

  _itemList(items) {
    return el('ul', { class: 'items' }, items.map((t) => el('li', { text: t })));
  }

  _renderSuccess() {
    const { added } = this._result;
    const text = `Added ${added} item${added === 1 ? '' : 's'} to your shopping list`;
    return el('div', { class: 'ok', role: 'status' }, [
      el('div', { class: 'headline' }, [el('ha-icon', { icon: 'mdi:check-circle' }), el('span', { text })]),
      this._button('Add another recipe'),
    ]);
  }

  _renderError() {
    const { message, items, detail } = this._error;
    const kids = [
      el('div', { class: 'headline' }, [el('ha-icon', { icon: 'mdi:alert-circle' }), el('span', { text: message })]),
    ];
    if (detail) kids.push(el('p', { class: 'detail', text: detail }));
    if (Array.isArray(items) && items.length) {
      kids.push(el('p', { class: 'detail', text: 'Added before the problem:' }), this._itemList(items.map(String)));
    }
    kids.push(this._button('Try again'));
    return el('div', { class: 'err', role: 'alert' }, kids);
  }

  _button(label) {
    const b = el('button', { class: 'action', type: 'button', text: label });
    b.addEventListener('click', () => this._setState('idle'));
    return b;
  }
}

const IE_TAG = 'ingredient-extractor-card';

/* Register with whatever registry window.customElements currently is. Returns true once
 * that registry knows the card. */
function ieRegister() {
  const registry = window.customElements;
  if (registry.get(IE_TAG)) return true;
  try {
    registry.define(IE_TAG, IngredientExtractorCard);
  } catch (e) {
    /* already defined natively; nothing more this registry can do */
  }
  return !!registry.get(IE_TAG);
}

ieRegister();
// Some dashboard cards load a scoped-custom-element-registry polyfill that replaces
// window.customElements with a fresh, empty registry. If that happens after this script
// ran, Lovelace can no longer find the card and shows "Configuration error". Re-register
// with the replacement for the first minute; Lovelace rebuilds the card once it appears.
let ieChecks = 0;
const ieWatch = setInterval(() => {
  if (++ieChecks >= 60) clearInterval(ieWatch);
  else ieRegister();
}, 1000);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === 'ingredient-extractor-card')) {
  window.customCards.push({
    type: 'ingredient-extractor-card',
    name: 'Ingredient Extractor',
    description: 'Photograph a recipe and add its ingredients to your shopping list.',
    preview: true,
  });
}
console.info(
  `%c INGREDIENT-EXTRACTOR-CARD %c v${IE_VERSION} `,
  'color: #fff; background: #03a9f4; font-weight: 700;',
  'color: #03a9f4; background: #fff; font-weight: 700;'
);
