// ---------- icons (inline SVG, stroke=currentColor) ----------
const S = (p) => `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const ICONS = {
  home: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M18 6l-2.5 2.5M8.5 15.5L6 18"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  tag: '<path d="M20 12l-8 8-9-9V3h8z"/><circle cx="7.5" cy="7.5" r="1.3"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/>',
  moon: '<path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"/>',
};
document.querySelectorAll('i[data-i]').forEach(el => el.innerHTML = ICONS[el.dataset.i] || '');

// ---------- agents ----------
const AGENTS = {
  director:    { name: 'Director',    color: '#0FB8A6' },
  strategist:  { name: 'Strategist',  color: '#6366F1' },
  copywriter:  { name: 'Copywriter',  color: '#F59E0B' },
  art_director:{ name: 'Art Director',color: '#EC4899' },
  critic:      { name: 'Critic',      color: '#EF4444' },
};

// ---------- helpers ----------
const $ = (s) => document.querySelector(s);
const api = (p, opts) => fetch(p, opts).then(r => r.json());
const assetUrl = (path) => path && path.includes('/output/') ? '/assets/' + path.split('/output/')[1] : path;
const scoreColor = (v) => v >= 78 ? 'var(--green)' : v >= 60 ? 'var(--amber)' : 'var(--red)';

let CHANNEL = 'instagram';
let LAST = [];

// ---------- view routing ----------
function show(view) {
  document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
  $('#view-' + view)?.classList.remove('hidden');
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.view === view));
  if (view === 'brands') loadBrands();
  if (view === 'gallery') renderGallery(LAST);
  if (view === 'home') loadStats();
}
document.querySelectorAll('.nav-item[data-view]').forEach(n => n.onclick = () => show(n.dataset.view));
document.querySelectorAll('[data-go]').forEach(b => b.onclick = () => show(b.dataset.go));

// ---------- theme ----------
$('#theme-toggle').onclick = () => {
  const r = document.documentElement;
  r.dataset.theme = r.dataset.theme === 'dark' ? 'light' : 'dark';
};

// ---------- home ----------
function legend() {
  $('#agent-legend').innerHTML = Object.values(AGENTS).map(a =>
    `<span class="agent-chip"><span class="dot" style="background:${a.color}"></span>${a.name}</span>`).join('');
}
async function loadStats() {
  const { brands = [] } = await api('/brands');
  const scored = LAST.filter(c => c.scorecard);
  const avg = scored.length ? Math.round(scored.reduce((s, c) => s + c.scorecard.overall, 0) / scored.length) : '—';
  const pass = scored.length ? Math.round(100 * scored.filter(c => c.status === 'pass').length / scored.length) + '%' : '—';
  const stat = (ic, num, lbl) => `<div class="card stat"><div class="ic">${S(ICONS[ic])}</div><div class="num">${num}</div><div class="lbl">${lbl}</div></div>`;
  $('#home-stats').innerHTML =
    stat('tag', brands.length, 'Brands in memory') +
    stat('grid', LAST.length || '—', 'Creatives this session') +
    stat('chart', avg, 'Avg critic score') +
    stat('spark', pass, 'Passed the bar');
}

// ---------- brands ----------
async function loadBrandSelect() {
  const { brands = [] } = await api('/brands');
  $('#brand-select').innerHTML = brands.map(b => `<option value="${b.id}">${b.name}</option>`).join('')
    || '<option value="">No brands yet — add one</option>';
}
async function loadBrands() {
  const { brands = [] } = await api('/brands');
  $('#brands-list').innerHTML = brands.length ? brands.map(b => `
    <div class="card brand-card">
      <div class="nm">${b.name || 'Untitled'}</div>
      <div class="pal">${(b.palette || []).slice(0, 5).map(c => `<span class="sw" style="background:${c}"></span>`).join('')}</div>
      <div class="meta"><b>${(b.tone || '')}</b><br>${b.audience || ''}</div>
    </div>`).join('') : '<p class="empty">No brands yet. Add one in New Campaign.</p>';
}

// ---------- new campaign ----------
document.querySelectorAll('#channel-chips .chip').forEach(c => c.onclick = () => {
  document.querySelectorAll('#channel-chips .chip').forEach(x => x.classList.remove('active'));
  c.classList.add('active'); CHANNEL = c.dataset.v;
});
$('#add-brand-btn').onclick = () => $('#add-brand-row').classList.toggle('hidden');
$('#extract-btn').onclick = async () => {
  const url = $('#brand-url').value.trim(); if (!url) return;
  $('#extract-btn').textContent = 'Extracting…'; $('#extract-btn').disabled = true;
  try {
    const { brand_kit } = await api('/brand', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }) });
    await loadBrandSelect();
    if (brand_kit?.id) $('#brand-select').value = brand_kit.id;
    $('#add-brand-row').classList.add('hidden'); $('#brand-url').value = '';
  } finally { $('#extract-btn').textContent = 'Extract brand'; $('#extract-btn').disabled = false; }
};
$('#generate-btn').onclick = async () => {
  const brand_kit_id = $('#brand-select').value;
  const objective = $('#objective').value.trim() || 'Drive new customers';
  if (!brand_kit_id) { alert('Add a brand first.'); return; }
  const body = { brand_kit_id, objective, channel: CHANNEL, n: +$('#n').value, max_rounds: +$('#rounds').value };
  const { job_id } = await api('/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  startRun(job_id, objective);
};

// ---------- working / live stream ----------
function entryEl(e) {
  const a = AGENTS[e.agent] || { name: e.agent, color: '#888' };
  const div = document.createElement('div');
  let cls = 'entry';
  if (e.kind === 'verdict') cls += /PASS/.test(e.message) ? ' verdict-pass' : ' verdict-reject';
  div.className = cls;
  const thumb = e.data && e.data.image_path ? `<img class="thumb" src="${assetUrl(e.data.image_path)}?t=${Date.now()}">` : '';
  div.innerHTML = `<div class="who"><span class="dot" style="background:${a.color}"></span>${a.name}</div>
    <div class="msg"><span class="k">${e.kind}</span>${e.message}</div>${thumb}`;
  return div;
}
function startRun(jobId, objective) {
  show('working');
  $('#run-objective').textContent = '“' + objective + '”';
  const status = $('#run-status'); status.className = 'status-pill'; status.textContent = 'running';
  const tl = $('#timeline'); tl.innerHTML = '';
  const es = new EventSource(`/job/${jobId}/stream`);
  es.onmessage = (ev) => {
    const e = JSON.parse(ev.data);
    tl.appendChild(entryEl(e));
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
  };
  es.addEventListener('end', (ev) => {
    const { status: st, creatives = [] } = JSON.parse(ev.data);
    LAST = creatives;
    status.textContent = st; status.className = 'status-pill ' + st;
    es.close();
    setTimeout(() => { show('gallery'); }, 900);
  });
  es.onerror = () => { status.textContent = 'connection lost'; status.className = 'status-pill error'; es.close(); };
}

// ---------- gallery ----------
const DIMS = [['thumbstop', 'thumbstop'], ['hierarchy', 'hierarchy'], ['legibility', 'legibility'], ['brand_fit', 'brand fit'], ['hook_clarity', 'hook'], ['cta_visibility', 'CTA']];
function renderGallery(creatives) {
  const g = $('#gallery');
  if (!creatives || !creatives.length) { g.innerHTML = '<p class="empty">No creatives yet. Run a campaign to fill the gallery.</p>'; return; }
  g.innerHTML = creatives.map(c => {
    const sc = c.scorecard || {}; const ov = sc.overall ?? 0;
    const bars = DIMS.map(([k, lbl]) => `<div class="bar"><span>${lbl}</span><div class="track"><div class="fill" style="width:${(sc[k] || 0) * 10}%"></div></div><span>${sc[k] ?? 0}</span></div>`).join('');
    const pass = c.status === 'pass';
    return `<div class="creative">
      <div class="img"><img src="${assetUrl(c.image_path)}" alt="">
        <span class="score-pill" style="background:${scoreColor(ov)}">${ov}</span></div>
      <div class="body">
        <div class="hl">${(c.brief && c.brief.headline) || ''}</div>
        <span class="status ${pass ? 'st-pass' : 'st-best'}">${pass ? 'Passed the bar' : 'Best effort'}</span>
        <div class="bars">${bars}</div>
        <div class="rationale">${c.rationale || ''}</div>
      </div></div>`;
  }).join('');
}

// ---------- boot ----------
legend(); loadStats(); loadBrandSelect();
