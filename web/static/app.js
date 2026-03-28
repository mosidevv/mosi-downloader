// ── Helpers ───────────────────────────────────────────────────────────────────

function api(path) {
  // Resolve relative to the base href (/viddown/) so subpath works correctly.
  return `api/${path}`;
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function statusPillHtml(status) {
  const map = {
    downloading: 'pill-downloading',
    queued:      'pill-queued',
    completed:   'pill-completed',
    failed:      'pill-failed',
  };
  const cls = map[status] || '';
  return `<span class="status-pill ${cls}">${status}</span>`;
}

function formatAge(ts) {
  if (!ts) return '';
  const secs = Math.round(Date.now() / 1000 - ts);
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

function urlDomain(url) {
  try { return new URL(url).hostname.replace('www.', ''); }
  catch { return url; }
}

// ── Thumbnail via oEmbed ──────────────────────────────────────────────────────

const OEMBED_PROVIDERS = [
  { pattern: /youtube\.com|youtu\.be/, endpoint: 'https://www.youtube.com/oembed' },
  { pattern: /twitter\.com|x\.com/,    endpoint: 'https://publish.twitter.com/oembed' },
];

const thumbCache = {};

async function getThumbnail(url) {
  if (thumbCache[url] !== undefined) return thumbCache[url];
  for (const p of OEMBED_PROVIDERS) {
    if (p.pattern.test(url)) {
      try {
        const r = await fetch(`${p.endpoint}?url=${encodeURIComponent(url)}&format=json`);
        if (r.ok) {
          const data = await r.json();
          thumbCache[url] = data.thumbnail_url || null;
          return thumbCache[url];
        }
      } catch { /* ignore */ }
    }
  }
  thumbCache[url] = null;
  return null;
}

// ── Job card renderer ─────────────────────────────────────────────────────────

async function deleteJob(jobId) {
  try {
    await fetchJson(api(`jobs/${encodeURIComponent(jobId)}`), { method: 'DELETE' });
    document.querySelector(`.job-card[data-id="${jobId}"]`)?.remove();
  } catch (e) {
    console.warn('Delete failed:', e);
  }
}

function jobCardHtml(job, thumb) {
  const title = job.title || urlDomain(job.url);
  const age   = formatAge(job.created_at);
  const pct   = job.progress || 0;
  const canDismiss = job.status === 'completed' || job.status === 'failed';

  const thumbHtml = thumb
    ? `<img class="job-card-thumb" src="${thumb}" alt="" loading="lazy">`
    : `<div class="job-card-thumb-placeholder">▶</div>`;

  let bottomHtml = '';
  if (job.status === 'downloading') {
    const speed = job.speed ? ` · ${job.speed}` : '';
    const eta   = job.eta   ? ` · ETA ${job.eta}` : '';
    bottomHtml = `<span class="job-card-stats">${pct.toFixed(1)}%${speed}${eta}</span>`;
  } else if (job.status === 'failed') {
    const errSnip = (job.error || 'Unknown error').slice(0, 60);
    bottomHtml = `<span class="job-card-error" title="${job.error || ''}">${errSnip}</span>`;
  } else if (job.status === 'completed') {
    bottomHtml = `<span class="job-card-stats">${formatAge(job.completed_at)}</span>`;
  } else {
    bottomHtml = `<span class="job-card-stats">${age}</span>`;
  }

  const actionsHtml = job.status === 'completed'
    ? `<a href="${api('file/' + encodeURIComponent(job.job_id))}" class="btn btn-sm btn-primary">⬇ Download</a>`
    : '';

  const dismissHtml = canDismiss
    ? `<button class="btn-dismiss" onclick="deleteJob('${job.job_id}')" title="Dismiss">✕</button>`
    : '';

  const progressHtml = (job.status === 'downloading' || job.status === 'queued')
    ? `<div class="job-card-progress">
         <div class="job-card-progress-fill" style="width:${pct}%"></div>
       </div>`
    : '';

  return `
    <div class="job-card" data-id="${job.job_id}">
      <div class="job-card-top">
        ${thumbHtml}
        <div class="job-card-info">
          <div class="job-card-title" title="${title}">${title}</div>
          <div class="job-card-url"><a href="job/${encodeURIComponent(job.job_id)}">${urlDomain(job.url)}</a></div>
        </div>
        ${dismissHtml}
      </div>
      ${progressHtml}
      <div class="job-card-bottom">
        ${bottomHtml}
        <div class="job-card-actions">
          ${actionsHtml}
          <a href="job/${encodeURIComponent(job.job_id)}" class="btn btn-sm btn-secondary">Details</a>
        </div>
      </div>
    </div>`;
}

// ── Index page ────────────────────────────────────────────────────────────────

async function initIndex() {
  // yt-dlp version badge
  try {
    const v = await fetchJson(api('ytdlp-version'));
    const el = document.getElementById('ytdlp-badge');
    if (el) el.textContent = `yt-dlp ${v.version}`;
  } catch { /* ignore */ }

  await loadJobs();
  setInterval(loadJobs, 4000);

  document.getElementById('download-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    const url      = document.getElementById('url').value.trim();
    const quality  = document.getElementById('quality').value;
    const playlist = document.getElementById('playlist').checked;
    const btn = e.target.querySelector('button[type=submit]');
    btn.disabled = true;
    btn.textContent = 'Queuing…';
    try {
      const res = await fetchJson(api('download'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, quality, playlist }),
      });
      window.location.href = `job/${encodeURIComponent(res.job_id)}`;
    } catch (err) {
      alert('Error: ' + err.message);
      btn.disabled = false;
      btn.textContent = 'Queue';
    }
  });
}

async function loadJobs() {
  let jobs;
  try {
    jobs = await fetchJson(api('jobs'));
  } catch { return; }

  const buckets = { downloading: [], queued: [], completed: [], failed: [] };
  for (const j of jobs) {
    (buckets[j.status] || buckets.failed).push(j);
  }

  const map = {
    downloading: 'list-active',
    queued:      'list-queued',
    completed:   'list-done',
    failed:      'list-failed',
  };
  const badgeMap = {
    downloading: 'badge-active',
    queued:      'badge-queued',
    completed:   'badge-done',
    failed:      'badge-failed',
  };

  for (const [status, listId] of Object.entries(map)) {
    const el = document.getElementById(listId);
    const badge = document.getElementById(badgeMap[status]);
    if (!el) continue;
    const list = buckets[status];
    badge.textContent = list.length;

    // Fetch thumbnails concurrently
    const thumbs = await Promise.all(list.map(j => getThumbnail(j.url)));
    el.innerHTML = list.map((j, i) => jobCardHtml(j, thumbs[i])).join('');
  }

  // Show/hide "Clear all failed" button
  const clearBtn = document.getElementById('btn-clear-failed');
  if (clearBtn) {
    clearBtn.style.display = buckets.failed.length > 0 ? 'inline-flex' : 'none';
    clearBtn.onclick = async () => {
      await Promise.all(buckets.failed.map(j => deleteJob(j.job_id)));
      await loadJobs();
    };
  }
}

// ── Job detail page ───────────────────────────────────────────────────────────

function initJobPage() {
  const match = window.location.pathname.match(/job\/([^/]+)$/);
  if (!match) return;
  const jobId = decodeURIComponent(match[1]);

  let lastStatus = null;

  async function refreshJob() {
    let job;
    try {
      job = await fetchJson(api(`status/${encodeURIComponent(jobId)}`));
    } catch (err) {
      document.getElementById('job-title').textContent = 'Job not found';
      return;
    }

    document.getElementById('job-title').textContent = job.title || 'Download job';
    document.getElementById('job-status-pill').outerHTML =
      `<span class="status-pill" id="job-status-pill">${job.status}</span>`;
    // Re-apply pill class
    const pill = document.getElementById('job-status-pill');
    const pillClasses = { downloading: 'pill-downloading', queued: 'pill-queued', completed: 'pill-completed', failed: 'pill-failed' };
    Object.values(pillClasses).forEach(c => pill.classList.remove(c));
    if (pillClasses[job.status]) pill.classList.add(pillClasses[job.status]);

    const urlEl = document.getElementById('job-url-display');
    if (urlEl) { urlEl.textContent = job.url; urlEl.title = job.url; }

    const pct = job.progress || 0;
    const bar = document.getElementById('job-progress-bar');
    const label = document.getElementById('progress-label');
    if (bar) bar.style.width = `${pct}%`;
    if (label) label.textContent = `${pct.toFixed(1)}%`;

    const speedEl = document.getElementById('job-speed');
    const etaEl   = document.getElementById('job-eta');
    if (speedEl) speedEl.textContent = job.speed ? `${job.speed}` : '';
    if (etaEl)   etaEl.textContent   = job.eta   ? `ETA ${job.eta}` : '';

    const logEl = document.getElementById('job-log');
    if (logEl) {
      logEl.textContent = (job.log_tail || []).join('\n');
      logEl.scrollTop = logEl.scrollHeight;
    }

    const errEl = document.getElementById('job-error');
    if (errEl) {
      if (job.status === 'failed' && job.error) {
        errEl.textContent = job.error;
        errEl.style.display = 'block';
      } else {
        errEl.style.display = 'none';
      }
    }

    const area = document.getElementById('download-area');
    if (area) {
      if (job.status === 'completed') {
        area.innerHTML = `<a href="${api('file/' + encodeURIComponent(jobId))}" class="btn btn-primary">⬇ Download</a>`;
      } else if (job.status !== 'failed') {
        area.textContent = '';
      }
    }

    // Fetch and show thumbnail
    if (job.status !== lastStatus || lastStatus === null) {
      const thumb = await getThumbnail(job.url);
      const wrap = document.getElementById('job-thumb-wrap');
      const img  = document.getElementById('job-thumb');
      if (thumb && wrap && img) {
        img.src = thumb;
        wrap.style.display = 'block';
      }
    }

    lastStatus = job.status;
  }

  refreshJob();
  setInterval(refreshJob, 3000);
}

// ── Admin page ────────────────────────────────────────────────────────────────

async function initAdmin() {
  // yt-dlp version
  async function loadVersion() {
    try {
      const v = await fetchJson(api('ytdlp-version'));
      document.getElementById('ytdlp-version').textContent = v.version;
    } catch (e) {
      document.getElementById('ytdlp-version').textContent = 'Error: ' + e.message;
    }
  }
  await loadVersion();

  document.getElementById('btn-update-ytdlp')?.addEventListener('click', async function () {
    this.disabled = true;
    this.textContent = 'Updating…';
    const out = document.getElementById('update-output');
    out.style.display = 'block';
    out.textContent = 'Running pip install -U yt-dlp…';
    try {
      const res = await fetchJson(api('admin/update-ytdlp'), { method: 'POST' });
      out.textContent = res.output || 'Done.';
      document.getElementById('ytdlp-version').textContent = res.version || '?';
    } catch (e) {
      out.textContent = 'Error: ' + e.message;
    } finally {
      this.disabled = false;
      this.textContent = 'Update now';
    }
  });

  // Cookies
  async function loadCookies() {
    try {
      const list = await fetchJson(api('admin/cookies'));
      const grid = document.getElementById('cookie-list');
      grid.innerHTML = list.map(c => {
        const loaded = c.size !== null;
        const age    = loaded ? `Updated ${formatAge(c.updated_at)} · ${(c.size / 1024).toFixed(1)} KB` : 'Not uploaded';
        const delBtn = loaded
          ? `<button class="btn btn-sm btn-danger" onclick="deleteCookie('${c.site}')">Remove</button>`
          : '';
        return `<div class="cookie-card ${loaded ? 'loaded' : 'missing'}">
          <div class="cookie-card-site">${c.site}</div>
          <div class="cookie-card-status">${loaded ? '✓ Loaded' : '✕ Missing'}</div>
          <div class="muted" style="font-size:11px;margin-bottom:8px;">${age}</div>
          ${delBtn}
        </div>`;
      }).join('');
    } catch { }
  }
  await loadCookies();

  window.deleteCookie = async function (site) {
    if (!confirm(`Remove ${site} cookies?`)) return;
    try {
      await fetchJson(api(`admin/cookies/${site}`), { method: 'DELETE' });
      await loadCookies();
    } catch (e) {
      alert('Error: ' + e.message);
    }
  };

  // File picker display
  document.getElementById('cookie-file')?.addEventListener('change', function () {
    const nameEl = document.getElementById('file-name-display');
    nameEl.textContent = this.files[0]?.name || 'Choose cookies.txt…';
  });

  // Cookie upload
  document.getElementById('btn-upload-cookie')?.addEventListener('click', async function () {
    const site = document.getElementById('cookie-site').value;
    const file = document.getElementById('cookie-file').files[0];
    const result = document.getElementById('upload-result');
    if (!file) { result.innerHTML = '<span class="error-msg">Select a file first.</span>'; return; }

    this.disabled = true;
    this.textContent = 'Uploading…';
    result.innerHTML = '';

    const form = new FormData();
    form.append('site', site);
    form.append('file', file);

    try {
      const res = await fetch(api('admin/cookies'), { method: 'POST', body: form });
      if (!res.ok) throw new Error(await res.text());
      result.innerHTML = `<span class="success-msg">✓ Uploaded ${site} cookies (${(file.size / 1024).toFixed(1)} KB)</span>`;
      await loadCookies();
      document.getElementById('cookie-file').value = '';
      document.getElementById('file-name-display').textContent = 'Choose cookies.txt…';
    } catch (e) {
      result.innerHTML = `<span class="error-msg">Error: ${e.message}</span>`;
    } finally {
      this.disabled = false;
      this.textContent = 'Upload';
    }
  });
}

// ── Router ────────────────────────────────────────────────────────────────────

const path = window.location.pathname;

if (path.includes('/job/')) {
  initJobPage();
} else if (path.endsWith('/admin')) {
  initAdmin();
} else {
  initIndex();
}
