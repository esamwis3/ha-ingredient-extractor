/* Ingredient Extractor card: photo of a recipe -> items on the shopping list.
 * Single vanilla JS file, no build step, no imports. */
const IE_VERSION = '0.4.2';
const IE_ENDPOINT = '/api/ingredient_extractor/extract';
const IE_TIMEOUT_MS = 60000;
const IE_MAX_BYTES = 4 * 1024 * 1024; // keep under the backend's 5 MB limit

// Friendly fallbacks, used only when the server sends no `message`.
const IE_MESSAGES = {
  no_image: 'No image was received.',
  too_large: 'That image is too large. Try a smaller photo.',
  unsupported_type: "That image format isn't supported. Try a JPEG or PNG.",
  not_a_recipe: "That doesn't look like a recipe or shopping list. Try a photo of the ingredients or the list.",
  no_ingredients: 'No ingredients were found in that photo.',
  provider_auth: 'The AI provider rejected the API key. Check the integration settings.',
  provider_error: 'The AI service had a problem. Please try again.',
  timeout: 'The AI took too long to respond. Please try again.',
  todo_error: "Some items couldn't be added to the list.",
  not_configured: "Ingredient Extractor isn't set up yet. Add the integration first.",
  invalid_url: "That doesn't look like a web link.",
  blocked_url: "Links to local network addresses aren't allowed.",
  fetch_failed: "Couldn't open that page. The site may block automated access — try a photo instead.",
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
  /* Recipe-link row: input + add. */
  .linkrow { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
  .linkrow input {
    flex: 1; min-width: 0; box-sizing: border-box; min-height: 44px; padding: 0 12px;
    font: inherit; color: var(--primary-text-color); background: var(--secondary-background-color);
    border: 1px solid var(--divider-color); border-radius: 22px;
  }
  .linkrow input::placeholder { color: var(--secondary-text-color); }
  .linkrow input:focus { outline: 2px solid var(--primary-color); outline-offset: 1px; border-color: var(--primary-color); }
  .linkrow button {
    flex: none; display: inline-flex; align-items: center; justify-content: center;
    width: 44px; height: 44px; padding: 0; cursor: pointer; border: 0; border-radius: 50%;
    color: var(--primary-text-color); background: var(--secondary-background-color);
  }
  .linkrow button.go { color: var(--text-primary-color, #fff); background: var(--primary-color); }
  .linkrow button:disabled { opacity: .45; cursor: default; }
  .linkrow button:focus-visible { outline: 2px solid var(--primary-text-color); outline-offset: 2px; }
  .linkrow ha-icon { --mdc-icon-size: 22px; }
  .status .sub { font-size: .875rem; color: var(--secondary-text-color); overflow-wrap: anywhere; }
`;

/* Styles for the in-card spacer shown in `fab` layout (the card itself is invisible). */
const IE_SPACER_STYLE = `
  :host { display: block; }
  .spacer { height: 80px; }
`;

/* Styles for the portalled floating button + bottom sheet (`fab` layout). They are added
 * to IE_STYLE inside the portal's own shadow root, so the card's tiles, link row,
 * viewfinder, status and error styles are reused as they are. */
const IE_FAB_STYLE = `
  :host { font-family: var(--ha-font-family-body, var(--primary-font-family, Roboto, sans-serif)); }
  [hidden] { display: none !important; }
  .fab {
    position: fixed; z-index: 50; box-sizing: border-box; height: 56px; padding: 0 22px 0 16px;
    /* HA's --safe-area-inset-* (what navbar-card uses) first, so the button moves with the bar. */
    right: calc(var(--ie-fab-right, 16px) + var(--safe-area-inset-right, env(safe-area-inset-right, 0px)));
    bottom: calc(var(--ie-fab-bottom, 108px) + var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px)));
    display: inline-flex; align-items: center; gap: 8px; border: 0; border-radius: 28px;
    font: inherit; font-size: 1rem; font-weight: 500; cursor: pointer;
    color: var(--text-primary-color, #fff); background: var(--primary-color, #03a9f4);
    box-shadow: 0 6px 18px rgba(0, 0, 0, .55);
  }
  .fab ha-icon { --mdc-icon-size: 24px; }
  .fab:focus-visible { outline: 2px solid var(--primary-text-color); outline-offset: 3px; }
  .layer {
    position: fixed; inset: 0; z-index: 1000; display: flex;
    align-items: flex-end; justify-content: center;
  }
  .backdrop {
    position: absolute; inset: 0; background: rgba(0, 0, 0, .6); touch-action: none;
    animation: ie-fade .2s ease-out;
  }
  .sheet {
    position: relative; box-sizing: border-box; width: 100%; max-width: 560px;
    max-height: 90vh; max-height: 90dvh; overflow-y: auto; overscroll-behavior: contain;
    padding-bottom: var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px)); outline: none;
    color: var(--primary-text-color); background: var(--card-background-color, #1d1d1d);
    border-radius: 24px 24px 0 0; box-shadow: 0 -8px 32px rgba(0, 0, 0, .4);
    animation: ie-up .24s cubic-bezier(.2, .8, .2, 1);
  }
  @keyframes ie-up { from { transform: translateY(100%); } }
  @keyframes ie-fade { from { opacity: 0; } }
  @media (prefers-reduced-motion: reduce) { .sheet, .backdrop { animation: none; } }
  .head { display: flex; align-items: center; gap: 8px; padding: 12px 8px 8px 16px; }
  .sheet h2 { flex: 1; margin: 0; font-size: 1.25rem; font-weight: 500; }
  .close {
    flex: none; display: inline-flex; align-items: center; justify-content: center;
    width: 44px; height: 44px; padding: 0; border: 0; border-radius: 50%; cursor: pointer;
    color: var(--secondary-text-color, #9b9b9b); background: none;
  }
  .close:hover { background: rgba(127, 127, 127, .15); }
  .close:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -2px; }
  .close:disabled { opacity: .35; cursor: default; }
  .close ha-icon { --mdc-icon-size: 24px; }
  .sheet .tiles.one { grid-template-columns: 1fr; }
  .sheet .tiles .dropzone,
  .sheet .tiles .dropzone:hover,
  .sheet .tiles .dropzone:focus-within {
    min-height: 96px; padding: 12px 8px; border: 0; border-radius: 16px;
    color: var(--primary-text-color);
    background: rgba(138, 180, 248, .15);
    background: color-mix(in srgb, var(--primary-color, #8ab4f8) 16%, transparent);
  }
  .sheet .tiles .dropzone:hover, .sheet .tiles .dropzone.drag {
    background: rgba(138, 180, 248, .25);
    background: color-mix(in srgb, var(--primary-color, #8ab4f8) 26%, transparent);
  }
  .sheet .tiles .dropzone ha-icon { --mdc-icon-size: 32px; }
  .sheet .linkrow { margin-top: 16px; }
  .sheet .linkrow input { min-height: 48px; padding: 0 18px; border-radius: 24px; }
  .sheet .linkrow button { width: 48px; height: 48px; }
  .sheet .viewfinder video { max-height: 50vh; }
  .tip { margin: 12px 4px 0; font-size: .8125rem; line-height: 1.4; color: var(--secondary-text-color); }
`;

/* First http(s) URL in free text (share text often reads "Recipe name https://..."),
 * or null if it is not a valid web link. */
function ieExtractUrl(text) {
  const m = /https?:\/\/[^\s<>"']+/i.exec(String(text || ''));
  if (!m) return null;
  const raw = m[0].replace(/[.,;:!?)\]]+$/, '');
  try {
    const u = new URL(raw);
    return (u.protocol === 'http:' || u.protocol === 'https:') && u.hostname ? u : null;
  } catch (e) {
    return null;
  }
}

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
    this._linkValue = ''; // survives re-renders (e.g. a detour via a photo tile)
    this._workingHost = null;
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
    if (config && config.android_camera != null && !['viewfinder', 'native'].includes(config.android_camera)) {
      throw new Error('"android_camera" must be viewfinder or native');
    }
    if (config && config.layout != null && !['inline', 'fab'].includes(config.layout)) {
      throw new Error('"layout" must be inline or fab');
    }
    if (config && config.fab_label != null && (typeof config.fab_label !== 'string' || !config.fab_label.trim())) {
      throw new Error('"fab_label" must be a non-empty string');
    }
    if (config && config.fab_bottom != null && (typeof config.fab_bottom !== 'string'
        || (window.CSS && CSS.supports && !CSS.supports('bottom', config.fab_bottom)))) {
      throw new Error('"fab_bottom" must be a CSS length, e.g. 108px');
    }
    if (config && config.fab_right != null && (typeof config.fab_right !== 'string'
        || (window.CSS && CSS.supports && !CSS.supports('right', config.fab_right)))) {
      throw new Error('"fab_right" must be a CSS length, e.g. 16px');
    }
    this._teardownPortal();
    this._config = {
      title: 'Recipe to shopping list', camera: 'auto', android_camera: 'viewfinder', ...(config || {}),
    };
    this._config.layout = (config && config.layout) || 'inline';
    this._config.fab_label = (config && config.fab_label) || 'Recipe';
    this._config.fab_bottom = (config && config.fab_bottom) || '108px';
    this._config.fab_right = (config && config.fab_right) || '16px';
    this._setState('idle');
    if (this.isConnected) this._buildPortal();
  }

  _fab() { return !!this._config && this._config.layout === 'fab'; }

  /* Where state views render: the portal in fab layout, the card's own shadow root otherwise. */
  _stage() { return this._fab() && this._portalRoot ? this._portalRoot : this.shadowRoot; }

  /* Camera tile: forced by config, otherwise only on touch-first devices, where
   * `capture` opens the camera. Desktop browsers ignore `capture`. */
  _showCamera() {
    const { camera } = this._config;
    if (this._fab()) return camera !== false; // phones are the target: both tiles unless disabled
    if (camera !== 'auto') return camera;
    return !!(window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
  }

  /* The Android Companion app (and Android WebView generally) ignores `capture` and
   * always opens the media picker, so there the card runs its own viewfinder. iOS
   * honours `capture` and opens the native camera, which is the better experience. */
  _useLiveCamera() {
    // `android_camera: native` is for Companion app releases that honour `capture`
    // (support was merged in October 2026, after the 2026.10.1 release).
    if (this._config.android_camera === 'native') return false;
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)
      && /Android/i.test(navigator.userAgent);
  }

  // Store only; re-rendering on every hass update would wipe the current state.
  set hass(hass) { this._hass = hass; }

  getCardSize() { return this._fab() ? 1 : 3; }
  getGridOptions() { return this._fab() ? { columns: 12, min_rows: 1 } : { columns: 12, min_rows: 2 }; }
  static getStubConfig() { return {}; }

  connectedCallback() {
    if (this._config && this._fab()) this._buildPortal();
  }

  disconnectedCallback() {
    this._revokeThumb();
    this._stopCamera();
    this._teardownPortal(); // HA disconnects cards on view change, so the FAB only shows here
  }

  /* ---------- floating button + bottom sheet (fab layout) ----------
   * Both live in a host element on document.body with its own shadow root, not inside
   * the card: an ancestor with transform/filter/contain (card-mod, view layouts) would
   * turn position:fixed into position:relative-to-that-ancestor. */

  _buildPortal() {
    if (this._portal || !this._fab()) return;
    // Drop orphans left by cards that were replaced without a disconnect.
    document.querySelectorAll('[data-ie-portal]').forEach((h) => {
      if (h._ieOwner !== this && !(h._ieOwner && h._ieOwner.isConnected)) h.remove();
    });
    const host = document.createElement('div');
    host.setAttribute('data-ie-portal', '');
    host._ieOwner = this;
    const root = host.attachShadow({ mode: 'open' });

    const fab = el('button', { class: 'fab', type: 'button', 'aria-haspopup': 'dialog' }, [
      el('ha-icon', { icon: 'mdi:plus' }), el('span', { text: this._config.fab_label }),
    ]);
    fab.style.setProperty('--ie-fab-bottom', this._config.fab_bottom);
    fab.style.setProperty('--ie-fab-right', this._config.fab_right);
    fab.addEventListener('click', () => this._openSheet());

    // A plain close button rather than a drag handle: the sheet can't be swiped, and a bar
    // at the bottom of a phone screen reads as the system's own navigation bar.
    const close = el('button', { class: 'close', type: 'button', 'aria-label': 'Close' },
      [el('ha-icon', { icon: 'mdi:close' })]);
    close.addEventListener('click', () => this._closeSheet());
    const body = el('div', { class: 'body' });
    const sheet = el('div', {
      class: 'sheet', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'ie-title', tabindex: '-1',
    }, [el('div', { class: 'head' }, [el('h2', { id: 'ie-title', text: 'Add a recipe' }), close]), body]);
    const backdrop = el('div', { class: 'backdrop' });
    backdrop.addEventListener('click', () => this._closeSheet());
    const layer = el('div', { class: 'layer' }, [backdrop, sheet]);
    layer.hidden = true;

    root.append(el('style', { text: IE_STYLE + IE_FAB_STYLE }), fab, layer);
    document.body.appendChild(host);
    this._portal = host;
    this._portalRoot = root;
    this._fabBtn = fab;
    this._layer = layer;
    this._sheet = sheet;
    this._sheetBody = body;
    this._closeBtn = close;
    this._open = false;
    this._render();
  }

  _teardownPortal() {
    if (this._open) this._unlockOpen();
    this._stopCamera();
    if (this._portal) this._portal.remove();
    this._portal = this._portalRoot = this._fabBtn = this._layer = this._sheet = this._sheetBody = this._closeBtn = null;
    this._open = false;
    if (this._state !== 'working') this._state = 'idle'; // don't resurrect a stale sheet view
  }

  _openSheet() {
    if (this._open || !this._portal) return;
    this._open = true;
    if (this._state !== 'idle') this._setState('idle');
    this._layer.hidden = false;
    this._prevOverflow = [document.body.style.overflow, document.documentElement.style.overflow];
    document.body.style.overflow = 'hidden';
    document.documentElement.style.overflow = 'hidden';
    this._onKey = (e) => this._handleKey(e);
    document.addEventListener('keydown', this._onKey, true);
    this._sheet.focus({ preventScroll: true });
  }

  /* Dismiss. Ignored while the request is in flight unless `force`. */
  _closeSheet(force = false) {
    if (!this._open || (this._busy && !force)) return;
    this._unlockOpen();
    this._open = false;
    if (this._layer) this._layer.hidden = true;
    this._stopCamera();
    if (this._state !== 'idle') this._setState('idle');
    if (this._fabBtn) this._fabBtn.focus({ preventScroll: true });
  }

  _unlockOpen() {
    document.removeEventListener('keydown', this._onKey, true);
    const [b, h] = this._prevOverflow || ['', ''];
    document.body.style.overflow = b;
    document.documentElement.style.overflow = h;
  }

  _handleKey(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      this._closeSheet();
    } else if (e.key === 'Tab' && this._sheet) { // keep focus inside the modal sheet
      const nodes = [...this._sheet.querySelectorAll('button, input, [tabindex="0"]')]
        .filter((n) => !n.disabled);
      if (!nodes.length) return;
      const active = this._portalRoot.activeElement;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (e.shiftKey && (active === first || active === this._sheet || !active)) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && (active === last || !active)) {
        e.preventDefault(); first.focus();
      }
    }
  }

  /* Success in fab layout: HA's toast instead of an in-sheet view. */
  _notifyAdded() {
    this.dispatchEvent(new CustomEvent('hass-notification', {
      detail: { message: this._successText() }, bubbles: true, composed: true,
    }));
  }

  _successText() {
    const { added, title } = this._result;
    const n = `${added} item${added === 1 ? '' : 's'}`;
    return title ? `Added ${n} from ${title}` : `Added ${n} to your shopping list`;
  }

  /* ---------- live camera ---------- */

  async _startCamera() {
    if (this._busy) return;
    this._setState('camera');
    if (!this._fab()) this.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
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
    const videoEl = this._stage().querySelector('video');
    if (videoEl) videoEl.srcObject = stream;
  }

  /* Full-resolution still where ImageCapture exists (Chrome on Android), otherwise
   * the current video frame. prepareImage() then shrinks it like any other photo. */
  async _capture() {
    const video = this._stage().querySelector('video');
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
    this._workingHost = null;
    this._thumbUrl = !file.type || file.type.startsWith('image/') ? URL.createObjectURL(file) : null;
    this._submit(async () => {
      const blob = await prepareImage(file);
      const fd = new FormData();
      fd.append('image', blob, 'recipe.jpg');
      return fd;
    });
  }

  /* Recipe link: validate client-side, then POST {"url": ...} as JSON. */
  _submitLink(text) {
    if (this._busy) return;
    const url = ieExtractUrl(String(text || '').trim());
    if (!url) {
      this._error = { code: 'invalid_url', message: IE_MESSAGES.invalid_url };
      this._setState('error');
      return;
    }
    this._revokeThumb();
    this._workingHost = url.hostname;
    this._submit(async () => JSON.stringify({ url: url.href }), true);
  }

  /* Generic pathway: payloadBuilder() resolves to a request body. */
  async _submit(payloadBuilder, isLink = false) {
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
        const init = { method: 'POST', body, signal: ctrl.signal };
        // A string body is JSON; FormData must keep the browser-set multipart boundary.
        if (typeof body === 'string') init.headers = { 'Content-Type': 'application/json' };
        resp = await this._hass.fetchWithAuth(IE_ENDPOINT, init);
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
      this._result = {
        items,
        added: Number.isFinite(data.added) ? data.added : items.length,
        title: typeof data.title === 'string' && data.title.trim() ? data.title.trim() : null,
      };
      if (isLink) this._linkValue = '';
      this._revokeThumb();
      if (this._fab()) {
        this._notifyAdded();
        this._closeSheet(true);
        if (this._state !== 'idle') this._setState('idle');
      } else {
        this._setState('success');
      }
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
    if (this._fab()) {
      // The card is just an invisible spacer; the state views render in the sheet.
      this.shadowRoot.replaceChildren(
        el('style', { text: IE_SPACER_STYLE }), el('div', { class: 'spacer', 'aria-hidden': 'true' }),
      );
      if (!this._sheetBody) return;
      this._closeBtn.disabled = this._state === 'working'; // closing is ignored mid-request anyway
      this._sheetBody.replaceChildren(this._renderState());
      // The view that had focus was just replaced; keep focus inside the open sheet.
      if (this._open && !this._portalRoot.activeElement) this._sheet.focus({ preventScroll: true });
      return;
    }
    const body = el('div', { class: 'body' }, [this._renderState()]);
    const card = el('ha-card', { header: this._config.title }, [body]);
    this.shadowRoot.replaceChildren(el('style', { text: IE_STYLE }), card);
  }

  _renderState() {
    const s = this._state;
    if (s === 'idle') return this._renderPicker();
    if (s === 'camera') return this._renderViewfinder();
    if (s === 'working') return this._renderWorking();
    if (s === 'success') return this._renderSuccess();
    return this._renderError();
  }

  _renderPicker() {
    const kids = [this._renderPhotoPicker(), this._renderLinkRow()];
    if (this._fab()) {
      kids.push(el('p', {
        class: 'tip',
        text: 'Tip: share a recipe page to Home Assistant from your browser to add it without opening the app.',
      }));
    }
    return el('div', {}, kids);
  }

  _renderPhotoPicker() {
    if (!this._showCamera()) {
      if (this._fab()) {
        return el('div', { class: 'tiles one' }, [
          this._renderDropzone('mdi:image-multiple', 'Choose photo', 'Choose a recipe photo'),
        ]);
      }
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

  _renderLinkRow() {
    const input = el('input', {
      type: 'url', inputmode: 'url', autocomplete: 'off', 'aria-label': 'Recipe link',
      placeholder: this._fab() ? 'Paste a recipe link' : 'Or paste a recipe link',
    });
    input.value = this._linkValue;
    const addBtn = el('button', { class: 'go', type: 'button', 'aria-label': 'Add', title: 'Add' },
      [el('ha-icon', { icon: 'mdi:plus' })]);
    addBtn.disabled = !input.value.trim();

    const submit = (text) => this._submitLink(text);
    input.addEventListener('input', (e) => {
      const prev = this._linkValue;
      this._linkValue = input.value;
      addBtn.disabled = !input.value.trim();
      const pasted = e.inputType === 'insertFromPaste';
      // Gboard's clipboard chip can arrive as insertText/insertReplacementText with the
      // whole URL: an empty field that becomes a complete link counts as a paste.
      const chip = !prev.trim() && /^https?:\/\/\S+$/i.test(input.value.trim());
      if ((pasted || chip) && ieExtractUrl(input.value)) submit(input.value);
    });
    input.addEventListener('paste', (e) => {
      const text = e.clipboardData && e.clipboardData.getData('text');
      if (!text || !ieExtractUrl(text)) return; // no link: let the browser paste normally
      e.preventDefault();
      input.value = text.trim();
      this._linkValue = input.value;
      submit(text);
    });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); if (input.value.trim()) submit(input.value); }
    });
    addBtn.addEventListener('click', () => { if (input.value.trim()) submit(input.value); });
    return el('div', { class: 'linkrow' }, [input, addBtn]);
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
    const textKids = [el('div', { text: 'Reading recipe…' })];
    if (this._workingHost) textKids.push(el('div', { class: 'sub', text: this._workingHost }));
    const kids = [spinner, el('div', { class: 'text' }, textKids)];
    if (this._thumbUrl && !this._workingHost) kids.push(el('img', { class: 'thumb', src: this._thumbUrl, alt: 'Selected recipe photo' }));
    return el('div', { class: 'status', role: 'status', 'aria-live': 'polite' }, kids);
  }

  _itemList(items) {
    return el('ul', { class: 'items' }, items.map((t) => el('li', { text: t })));
  }

  _renderSuccess() {
    const text = this._successText();
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
