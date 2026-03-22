/* ============================================================
   LRN_PXE — Frontend JavaScript
   ============================================================ */

'use strict';

// ── Toast notifications ───────────────────────────────────────────────────
function showToast(message, type = 'success') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const icons = { success: 'check-circle-fill', error: 'exclamation-triangle-fill', info: 'info-circle-fill', warning: 'exclamation-circle-fill' };
  const colors = { success: 'var(--success-color)', error: 'var(--danger-color)', info: 'var(--brand-color)', warning: 'var(--warning-color)' };

  const id = 'toast-' + Date.now();
  container.insertAdjacentHTML('beforeend', `
    <div id="${id}" class="toast align-items-center border-0" role="alert" style="background:var(--card-bg);border-color:var(--card-border)!important;">
      <div class="d-flex">
        <div class="toast-body d-flex align-items-center gap-2">
          <i class="bi bi-${icons[type] || icons.info}" style="color:${colors[type] || colors.info};font-size:16px;"></i>
          <span style="color:var(--text-primary);font-size:14px;">${message}</span>
        </div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
      </div>
    </div>
  `);

  const el = document.getElementById(id);
  const toast = new bootstrap.Toast(el, { delay: 4000 });
  toast.show();
  el.addEventListener('hidden.bs.toast', () => el.remove());
}

// ── API helper ────────────────────────────────────────────────────────────
async function api(method, url, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

// ── Upload with progress ──────────────────────────────────────────────────
function uploadFile(url, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append('file', file);

    xhr.upload.addEventListener('progress', e => {
      if (e.lengthComputable && onProgress) onProgress(Math.round(e.loaded / e.total * 100));
    });

    xhr.addEventListener('load', () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else reject(new Error(data.error || `HTTP ${xhr.status}`));
      } catch { reject(new Error('Invalid server response')); }
    });

    xhr.addEventListener('error', () => reject(new Error('Network error')));
    xhr.open('POST', url);
    xhr.send(formData);
  });
}

// ── Drag & drop upload zone ───────────────────────────────────────────────
function initUploadZone(zoneEl, inputEl, options = {}) {
  const { accept = '.iso', onFile } = options;

  zoneEl.addEventListener('click', () => inputEl.click());

  zoneEl.addEventListener('dragover', e => {
    e.preventDefault();
    zoneEl.classList.add('drag-over');
  });

  zoneEl.addEventListener('dragleave', () => zoneEl.classList.remove('drag-over'));

  zoneEl.addEventListener('drop', e => {
    e.preventDefault();
    zoneEl.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file && onFile) onFile(file);
  });

  inputEl.addEventListener('change', () => {
    if (inputEl.files[0] && onFile) onFile(inputEl.files[0]);
  });
}

// ── Menu drag-and-drop reorder ────────────────────────────────────────────
function initDragReorder(listEl, onReorder) {
  let dragged = null;

  listEl.addEventListener('dragstart', e => {
    dragged = e.target.closest('[data-id]');
    if (dragged) {
      dragged.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    }
  });

  listEl.addEventListener('dragend', () => {
    if (dragged) dragged.classList.remove('dragging');
    dragged = null;
  });

  listEl.addEventListener('dragover', e => {
    e.preventDefault();
    const over = e.target.closest('[data-id]');
    if (over && dragged && over !== dragged) {
      const rect = over.getBoundingClientRect();
      const after = e.clientY > rect.top + rect.height / 2;
      if (after) over.after(dragged);
      else over.before(dragged);
    }
  });

  listEl.addEventListener('drop', e => {
    e.preventDefault();
    if (onReorder) {
      const order = [...listEl.querySelectorAll('[data-id]')].map(el => el.dataset.id);
      onReorder(order);
    }
  });
}

// ── Status polling ────────────────────────────────────────────────────────
function pollStatus(svcEls) {
  setInterval(async () => {
    try {
      const data = await api('GET', '/api/status');
      Object.entries(data.services || {}).forEach(([name, status]) => {
        const el = svcEls[name];
        if (!el) return;
        el.className = `svc-badge ${status === 'active' ? 'active' : status === 'inactive' ? 'inactive' : 'unknown'}`;
        el.querySelector('.svc-name').textContent = name;
        el.querySelector('.svc-status').textContent = status;
      });
    } catch {}
  }, 10000);
}

// ── Confirm dialog ────────────────────────────────────────────────────────
function confirmAction(message) {
  return new Promise(resolve => {
    const id = 'confirm-' + Date.now();
    document.body.insertAdjacentHTML('beforeend', `
      <div class="modal fade" id="${id}" tabindex="-1">
        <div class="modal-dialog modal-dialog-centered modal-sm">
          <div class="modal-content">
            <div class="modal-body p-4">
              <p class="mb-0" style="color:var(--text-primary);font-size:15px;">${message}</p>
            </div>
            <div class="modal-footer border-0 pt-0">
              <button class="btn-lrn ghost btn-cancel" style="padding:7px 14px;">Cancel</button>
              <button class="btn-lrn danger btn-confirm" style="padding:7px 14px;">Confirm</button>
            </div>
          </div>
        </div>
      </div>
    `);
    const el = document.getElementById(id);
    const modal = new bootstrap.Modal(el);
    modal.show();
    el.querySelector('.btn-confirm').onclick = () => { modal.hide(); resolve(true); };
    el.querySelector('.btn-cancel').onclick = () => { modal.hide(); resolve(false); };
    el.addEventListener('hidden.bs.modal', () => { el.remove(); resolve(false); });
  });
}

// ── Init ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Auto-dismiss alerts
  document.querySelectorAll('.alert.auto-dismiss').forEach(el => {
    setTimeout(() => el.classList.remove('show'), 4000);
  });
});
