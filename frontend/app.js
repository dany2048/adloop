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
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V7a4 4 0 018 0v4"/>',
  bolt: '<path d="M13 2L4.5 13.5H11L9.5 22 19 10h-6.5z"/>',
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
  if (view === 'history') loadRuns();
  if (view === 'gallery') renderGallery(LAST);
  if (view !== 'working') { $('#jump-new')?.classList.add('hidden'); }
}
// ---------- sidebar drawer ----------
const sidebarEl = document.querySelector('.sidebar');
const backdropEl = document.getElementById('sidebar-backdrop');
function toggleMenu(open) {
  const next = open ?? !sidebarEl.classList.contains('open');
  sidebarEl.classList.toggle('open', next);
  backdropEl.classList.toggle('open', next);
}
document.getElementById('menu-btn')?.addEventListener('click', () => toggleMenu());
backdropEl?.addEventListener('click', () => toggleMenu(false));
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') toggleMenu(false); });

document.querySelectorAll('.nav-item[data-view]').forEach(n => n.onclick = () => { show(n.dataset.view); toggleMenu(false); });
document.querySelectorAll('[data-go]').forEach(b => b.onclick = () => show(b.dataset.go));


// ---------- the agent society (home intro) ----------
const SOCIETY = [
  { key: 'strategist', name: 'Strategist', color: '#6366F1', role: 'Reads the product URL → structured brand DNA (tone, palette, value props, rules).', model: 'qwen-plus' },
  { key: 'copywriter', name: 'Copywriter', color: '#F59E0B', role: 'Writes N framework-diverse ad angles, each anchored to a concrete product fact.', model: 'qwen-max' },
  { key: 'design_researcher', name: 'Design Researcher', color: '#06B6D4', role: 'Pulls real Pinterest references, reads them, distills a design brief.', model: 'qwen-vl-max + Pinterest' },
  { key: 'art_director', name: 'Art Director', color: '#EC4899', role: 'Generates the background scene and composites the type layer into a finished ad.', model: 'wan2.2-t2i + qwen-plus' },
  { key: 'critic', name: 'Critic', color: '#EF4444', role: 'Scores every creative 0–100 on 6 dimensions and sends weak work back for revision.', model: 'qwen-vl-max' },
  { key: 'director', name: 'Director', color: '#0FB8A6', role: 'Orchestrates the loop, keeps the best result, writes lessons back to memory.', model: 'orchestrator' },
];
const spriteUrl = (k) => '/sprites/' + k + '.png?v=5';   // bump v when sprites are regenerated
const FLOW = ['strategist', 'director', 'copywriter', 'design_researcher', 'art_director', 'critic'];
// tools/model chips per agent. Filmmaker + Motion Artist are future agents (locked, "coming soon").
const FC_TOOLS = {
  strategist: ['qwen-plus', 'scrape', 'search'],
  director: ['memory', 'orchestrate'],
  critic: ['qwen-vl-max', 'vision'],
  copywriter: ['qwen-max'],
  design_researcher: ['qwen-vl', 'pinterest'],
  art_director: ['wan2.2'],
  filmmaker: ['soon'],
  motion_artist: ['soon'],
};
const LOCKED_META = {
  filmmaker: { name: 'Filmmaker', color: '#8B5CF6' },
  motion_artist: { name: 'Motion Artist', color: '#F97316' },
};
const nodeMeta = (k) => SOCIETY.find(s => s.key === k) || LOCKED_META[k] || { name: k, color: '#888' };
// Top-down org chart: Strategist (top) → Director (orchestrator) ⇄ Critic; Director fans out to the worker row (+ locked future agents). Matches the code: Director orchestrates, Critic reports back.
// Grid: 5 worker columns w=196 step=208 starting at x=12 → centers 110/318/526/734/942. Director + Strategist centre on the middle column (526).
const FC_NODES = {
  strategist: { x: 416, y: 74, w: 220, h: 104, desc: 'scrapes + researches' },
  director: { x: 396, y: 222, w: 260, h: 104, desc: 'orchestrates everything', core: true },
  critic: { x: 716, y: 232, w: 210, h: 84, desc: 'scores + reports back' },
  copywriter: { x: 12, y: 414, w: 196, h: 118, vertical: true },
  design_researcher: { x: 220, y: 414, w: 196, h: 118, vertical: true },
  art_director: { x: 428, y: 414, w: 196, h: 118, vertical: true },
  filmmaker: { x: 636, y: 414, w: 196, h: 118, vertical: true, locked: true },
  motion_artist: { x: 844, y: 414, w: 196, h: 118, vertical: true, locked: true },
};
const FC_EDGES = [
  { id: 'strategist', d: 'M526,40 V74' },
  { id: 'director', d: 'M526,178 V222' },
  { id: 'critic', d: 'M656,274 H716', two: true },
  { id: '_trunk', d: 'M526,326 V374', trunk: true },
  { id: '_bus', d: 'M110,374 H942', trunk: true },
  { id: 'copywriter', d: 'M110,374 V414' },
  { id: 'design_researcher', d: 'M318,374 V414' },
  { id: 'art_director', d: 'M526,374 V414' },
  { id: 'filmmaker', d: 'M734,374 V414', locked: true },
  { id: 'motion_artist', d: 'M942,374 V414', locked: true },
];
function renderFlowchart(elId, live) {
  const el = document.getElementById(elId); if (!el) return;
  el.className = 'flowchart';
  const pre = live ? 'live-' : '';
  const edgeSvg = FC_EDGES.map(e => {
    const flow = e.id.startsWith('_') ? '' : ` style="--flow:${nodeMeta(e.id).color}"`;
    const me = e.trunk ? '' : ` marker-end="url(#fcah-${pre})"`;   // trunk/bus are plain rails, no arrowheads
    const ms = e.two ? ` marker-start="url(#fcah-${pre})"` : '';
    return `<path class="fc-edge${e.trunk ? ' trunk' : ''}${e.locked ? ' locked' : ''}" id="edge-${pre}${e.id}" d="${e.d}"${me}${ms}${flow}></path>`;
  }).join('');
  const nodeSvg = Object.entries(FC_NODES).map(([k, n]) => {
    const a = nodeMeta(k);
    const chips = (FC_TOOLS[k] || []).map(t => `<span class="fc-tool">${t}</span>`).join('');
    const icon = SPRITE_KEYS.has(k) ? `<img class="fc-sprite" src="${spriteUrl(k)}" alt=""/>` : `<span class="fc-lockicon">${S(ICONS.lock)}</span>`;
    const cls = `fc-node${n.core ? ' core' : ''}${n.locked ? ' locked' : ''}${n.vertical ? ' col' : ''}`;
    const body = n.vertical
      ? `<div class="fc-name">${a.name}<span class="fc-dot"></span></div><div class="fc-tools">${chips}</div>`
      : `<div class="fc-name">${a.name}<span class="fc-dot"></span></div><div class="fc-desc">${n.desc || ''}</div><div class="fc-tools">${chips}</div>`;
    return `<foreignObject x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}">
      <div class="${cls}" id="fc-${pre}${k}" style="--c:${a.color}" xmlns="http://www.w3.org/1999/xhtml">
        ${icon}<div class="fc-body">${body}</div><span class="fc-check">✓</span>
      </div></foreignObject>`;
  }).join('');
  el.innerHTML = `<svg viewBox="0 0 1060 560" class="fc-svg" preserveAspectRatio="xMidYMid meet">
    <defs><marker id="fcah-${pre}" markerWidth="7" markerHeight="7" refX="5" refY="3" orient="auto-start-reverse"><path d="M0,0 L6,3 L0,6 Z" fill="context-stroke"/></marker></defs>
    ${edgeSvg}
    <foreignObject x="446" y="6" width="160" height="34"><div class="fc-pill trigger" xmlns="http://www.w3.org/1999/xhtml">${S(ICONS.bolt)}<span>Product URL</span></div></foreignObject>
    ${nodeSvg}
  </svg>`;
}
let demoTimer;
function fcActivate(pre, key) {
  const scope = pre ? '#work-flowchart' : '#society-diagram';
  document.querySelectorAll(scope + ' .fc-node.active').forEach(n => { n.classList.remove('active'); n.classList.add('done'); });
  document.querySelectorAll(scope + ' .fc-edge.flowing').forEach(e => e.classList.remove('flowing'));
  const node = document.getElementById('fc-' + pre + key);
  if (node) { node.classList.add('active'); node.classList.remove('done'); }
  document.getElementById('edge-' + pre + key)?.classList.add('flowing');
}
function startDemo() {   // home page: auto-play a demo run on a loop
  clearInterval(demoTimer);
  let i = 0;
  demoTimer = setInterval(() => {
    if (i >= FLOW.length) {
      document.querySelectorAll('#society-diagram .fc-node').forEach(n => n.classList.remove('active', 'done'));
      document.querySelectorAll('#society-diagram .fc-edge').forEach(e => e.classList.remove('flowing'));
      i = 0; return;
    }
    fcActivate('', FLOW[i]); i++;
  }, 850);
}
function renderSociety() {
  renderFlowchart('society-diagram', false);
  renderTune();
  startDemo();
}
const EDITABLE = new Set(['strategist', 'copywriter', 'art_director', 'critic']);  // agents with an editable prompt
const LOCKED_AGENTS = [
  { name: 'Filmmaker', role: 'Turns the campaign into short-form video ads.', color: '#8B5CF6' },
  { name: 'Motion Artist', role: 'Adds motion graphics and animated variants.', color: '#F97316' },
  { name: 'Video Editor', role: 'Cuts long footage into ad-ready clips.', color: '#0EA5E9' },
  { name: 'Media Buyer', role: 'Plans budget and targeting across ad channels.', color: '#22C55E' },
  { name: 'Performance Analyst', role: 'Reads results and feeds winners back into memory.', color: '#EAB308' },
  { name: 'Localizer', role: 'Adapts copy and design for new markets and languages.', color: '#EC4899' },
];
function renderTune() {
  const el = $('#tune-list'); if (!el) return;
  const real = SOCIETY.map(a => {
    const editable = EDITABLE.has(a.key);
    return `<div class="tune-card">
      <div class="tc-head"><img src="${spriteUrl(a.key)}" alt=""><div><div class="tc-name">${a.name}</div><div class="tc-model">${a.model}</div></div></div>
      <div class="tc-role">${a.role}</div>
      <div class="tune-btns">
        ${editable ? `<button class="edit" onclick="openPromptModal('${a.key}')">Edit prompt</button>` : `<button class="locked" title="No editable prompt">Edit prompt</button>`}
        <button class="locked" title="Coming soon">Reference docs</button>
        <button class="locked" title="Coming soon">Tool access</button>
      </div>
    </div>`;
  }).join('');
  const locked = LOCKED_AGENTS.map(a => `
    <div class="tune-card locked-card">
      <div class="tc-head"><span class="tc-lock" style="background:${a.color}22;color:${a.color}">${S(ICONS.lock)}</span><div><div class="tc-name">${a.name}</div><div class="tc-model">Coming soon</div></div></div>
      <div class="tc-role">${a.role}</div>
      <div class="tune-btns"><button class="locked">Coming soon</button></div>
    </div>`).join('');
  el.innerHTML = real + locked;
}

// ---------- home ----------
function legend() {
  $('#agent-legend').innerHTML = Object.values(AGENTS).map(a =>
    `<span class="agent-chip"><span class="dot" style="background:${a.color}"></span>${a.name}</span>`).join('');
}
async function loadStats() {
  const { brands = [] } = await api('/brands');
  const scored = LAST.filter(c => c.scorecard);
  const avg = scored.length ? Math.round(scored.reduce((s, c) => s + c.scorecard.overall, 0) / scored.length) : '-';
  const pass = scored.length ? Math.round(100 * scored.filter(c => c.status === 'pass').length / scored.length) + '%' : '-';
  const stat = (ic, num, lbl) => `<div class="card stat"><div class="ic">${S(ICONS[ic])}</div><div class="num">${num}</div><div class="lbl">${lbl}</div></div>`;
  $('#home-stats').innerHTML =
    stat('tag', brands.length, 'Brands in memory') +
    stat('grid', LAST.length || '-', 'Creatives generated') +
    stat('chart', avg, 'Avg critic score') +
    stat('spark', pass, 'Passed the bar');
}

// ---------- brands ----------
async function loadBrandSelect() {
  const { brands = [] } = await api('/brands');
  $('#brand-select').innerHTML = brands.map(b => `<option value="${b.id}">${b.name}</option>`).join('')
    || '<option value="">No brands yet. Add one</option>';
}
async function loadBrands() {
  const { brands = [] } = await api('/brands');
  const grid = $('#brands-list');
  grid.className = 'brands-grid';
  grid.innerHTML = brands.length ? brands.map(b => {
    const img = b.logo_url ? `<img class="brand-img" src="${b.logo_url}" referrerpolicy="no-referrer" onerror="this.remove()" alt="">` : '';
    const props = (b.value_props || []).slice(0, 3).map(v => `<li>${v}</li>`).join('');
    const pal = (b.palette || []).slice(0, 6).map(c => `<span class="sw" style="background:${c}"></span>`).join('');
    const tone = Array.isArray(b.tone) ? b.tone.join(', ') : (b.tone || '');
    return `<div class="brand-rich">
      ${img}
      <div class="brand-body">
        <div class="brand-top"><div class="brand-nm">${b.name || 'Untitled'}</div>${b.offering_type ? `<span class="brand-type">${b.offering_type}</span>` : ''}</div>
        <div class="brand-sum">${b.product_summary || ''}</div>
        ${b.audience ? `<div class="brand-row"><b>Audience:</b> ${b.audience}</div>` : ''}
        ${tone ? `<div class="brand-row"><b>Tone:</b> ${tone}</div>` : ''}
        ${props ? `<ul class="brand-props">${props}</ul>` : ''}
        <div class="brand-pal">${pal}</div>
      </div>
    </div>`;
  }).join('') : '<p class="empty">No brands yet. Add one in New Campaign.</p>';
}

// ---------- tune agents (editable prompts) ----------
const esc = (s) => (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
async function loadPrompts(filterKey) {
  const { prompts = [] } = await api('/prompts');
  const list = filterKey ? prompts.filter(p => p.key === filterKey) : prompts;
  $('#prompts-list').innerHTML = list.map(p => `
    <div class="panel" style="margin-bottom:var(--sp-4)">
      <div class="prompt-row-head">
        <b>${p.label}</b>
        ${p.overridden ? '<span class="prompt-flag edited">EDITED</span>' : '<span class="prompt-flag default">default</span>'}
      </div>
      ${p.vars.length ? `<div class="prompt-vars">must keep: ${p.vars.map(v => `<code>${esc(v)}</code>`).join(' ')}</div>` : ''}
      <textarea id="pt-${p.key}" rows="11" class="prompt-ta">${esc(p.prompt)}</textarea>
      <div class="prompt-actions">
        <button class="btn primary sm" onclick="savePrompt('${p.key}')">Save</button>
        <button class="btn ghost sm" onclick="resetPrompt('${p.key}')">Reset to default</button>
      </div>
    </div>`).join('');
}
let currentPromptKey = null;
window.savePrompt = async (key) => {
  const prompt = document.getElementById('pt-' + key).value;
  await api('/prompts/' + key, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt }) });
  loadPrompts(currentPromptKey);
};
window.resetPrompt = async (key) => {
  await api('/prompts/' + key + '/reset', { method: 'POST' });
  loadPrompts(currentPromptKey);
};
window.openPromptModal = (key) => { currentPromptKey = key || null; loadPrompts(currentPromptKey); $('#prompt-modal').classList.remove('hidden'); };
window.closePromptModal = () => { $('#prompt-modal').classList.add('hidden'); };

// ---------- new campaign ----------
document.querySelectorAll('#channel-chips .chip').forEach(c => c.onclick = () => {
  document.querySelectorAll('#channel-chips .chip').forEach(x => x.classList.remove('active'));
  c.classList.add('active'); CHANNEL = c.dataset.v;
});
// intake mode: URL-first (default) vs a saved brand
let MODE = 'url';
document.querySelectorAll('#mode-chips .chip').forEach(c => c.onclick = () => {
  document.querySelectorAll('#mode-chips .chip').forEach(x => x.classList.remove('active'));
  c.classList.add('active'); MODE = c.dataset.mode;
  $('#mode-url').classList.toggle('hidden', MODE !== 'url');
  $('#mode-saved').classList.toggle('hidden', MODE !== 'saved');
});
$('#generate-btn').onclick = async () => {
  const objective = $('#objective').value.trim() || 'Drive new customers';
  const body = { objective, channel: CHANNEL, n: +$('#n').value, max_rounds: +$('#rounds').value };
  if (MODE === 'url') {
    const url = $('#brand-url').value.trim();
    if (!url) { alert('Paste a product URL (or switch to “Saved brand”).'); return; }
    body.url = url;
    const desc = $('#brand-desc').value.trim();
    if (desc) body.description = desc;
  } else {
    const id = $('#brand-select').value;
    if (!id) { alert('Pick a saved brand (or switch to “From product URL”).'); return; }
    body.brand_kit_id = id;
  }
  const res = await api('/campaign', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!res || !res.job_id) { alert('Could not start: ' + ((res && res.error) || 'unknown error')); return; }
  startRun(res.job_id, objective);
};

// ---------- working / live stream ----------
let newCount = 0;
const nearBottom = () => (window.innerHeight + window.scrollY) >= document.body.scrollHeight - 140;
function updateJump() {
  const b = $('#jump-new'); if (!b) return;
  if (newCount > 0) { $('#jump-count').textContent = newCount; b.classList.remove('hidden'); }
  else b.classList.add('hidden');
}
window.jumpToBottom = () => { window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }); newCount = 0; updateJump(); };
window.addEventListener('scroll', () => { if (nearBottom()) { newCount = 0; updateJump(); } });

const SPRITE_KEYS = new Set(SOCIETY.map(a => a.key));
function setActiveAgent(key) { fcActivate('live-', key); }
function setStatus(agent, message) {
  const bar = $('#fc-status'); if (!bar) return;
  bar.classList.remove('hidden');
  const a = SOCIETY.find(s => s.key === agent);
  $('#fc-status-text').textContent = (a ? a.name + ' · ' : '') + (message || '').slice(0, 90);
}
function clearActiveAgents() {
  document.querySelectorAll('#work-flowchart .fc-node.active').forEach(n => { n.classList.remove('active'); n.classList.add('done'); });
  document.querySelectorAll('#work-flowchart .fc-edge.flowing').forEach(e => e.classList.remove('flowing'));
  $('#fc-status')?.classList.add('hidden');
}
function entryEl(e) {
  const a = SOCIETY.find(s => s.key === e.agent) || AGENTS[e.agent] || { name: e.agent, color: '#888' };
  const div = document.createElement('div');
  let cls = 'entry';
  if (e.kind === 'verdict') cls += /PASS/.test(e.message) ? ' verdict-pass' : ' verdict-reject';
  div.className = cls;
  const thumb = e.data && e.data.image_path ? `<img class="thumb" src="${assetUrl(e.data.image_path)}?t=${Date.now()}">` : '';
  const refs = (e.data && e.data.references && e.data.references.length)
    ? `<div class="entry-refs">`
      + e.data.references.slice(0, 6).map(u =>
          `<a href="${u}" target="_blank" rel="noopener" title="open real Pinterest reference"><img class="ref-thumb" src="${u}" loading="lazy" referrerpolicy="no-referrer"></a>`
        ).join('')
      + `</div>`
    : '';
  const who = SPRITE_KEYS.has(e.agent)
    ? `<img class="tl-sprite" src="${spriteUrl(e.agent)}" alt=""> ${a.name}`
    : `<span class="dot" style="background:${a.color}"></span>${a.name}`;
  div.innerHTML = `<div class="who">${who}</div>
    <div class="msg"><span class="k">${e.kind}</span>${e.message}</div>${thumb}${refs}`;
  return div;
}
function showRunError() {
  const tl = $('#timeline');
  const last = tl && tl.lastElementChild ? tl.lastElementChild.textContent.trim() : '';
  const msg = /fail|quota|error|snag|could not/i.test(last)
    ? last.replace(/^INFO/i, '').trim()
    : 'The run ended with an error before any creative was produced. See the timeline for details.';
  const el = $('#run-error');
  if (el) { el.textContent = msg; el.classList.remove('hidden'); }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function startRun(jobId, objective) {
  show('working');
  $('#run-objective').textContent = '“' + objective + '”';
  const status = $('#run-status'); status.className = 'status-pill'; status.textContent = 'running';
  $('#run-error')?.classList.add('hidden');   // clear any prior failure banner
  const rr = $('#run-results'); if (rr) { rr.classList.add('hidden'); rr.innerHTML = ''; }
  const th = document.querySelector('#view-working .page-title'); if (th) th.textContent = 'The team is working';
  const tl = $('#timeline'); tl.innerHTML = '';
  renderFlowchart('work-flowchart', true);
  newCount = 0; updateJump();
  const es = new EventSource(`/job/${jobId}/stream`);
  es.onmessage = (ev) => {
    const stick = nearBottom();               // only auto-scroll if you're already at the bottom
    const e = JSON.parse(ev.data);
    tl.appendChild(entryEl(e));
    setActiveAgent(e.agent);                   // the posting agent's node glows + connector flows
    setStatus(e.agent, e.message);             // bottom status bar (spinner + latest action)
    if (stick) window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
    else { newCount++; updateJump(); }         // scrolled up to read → count new, don't yank
  };
  es.addEventListener('end', async (ev) => {
    const data = JSON.parse(ev.data);
    const st = data.status;
    status.textContent = st; status.className = 'status-pill ' + st;
    clearActiveAgents();
    es.close();
    await loadCreatives();   // pull the full persisted history (this run + everything before)
    if (st === 'error') { showRunError(); return; }   // stay put and surface the failure
    // Show THIS run's results in context instead of yanking to the global gallery.
    const k = (data.creatives || []).length || (+$('#n').value || 3);
    renderRunResults(LAST.slice(0, k), objective);
  });
  es.onerror = () => { status.textContent = 'connection lost'; status.className = 'status-pill error'; es.close(); };
}

// ---------- completed-run results (shown inline on the working view) ----------
function renderRunResults(creatives, objective) {
  const el = $('#run-results'); if (!el) return;
  const th = document.querySelector('#view-working .page-title');
  if (!creatives || !creatives.length) {
    if (th) th.textContent = 'Run finished';
    el.innerHTML = `<div class="rr-head"><div><div class="rr-title">Run finished</div>
      <div class="rr-sub">No creatives came through this run — check the timeline below for what happened.</div></div></div>`;
    el.classList.remove('hidden'); el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }
  const scored = creatives.filter(c => c.scorecard && c.scorecard.overall != null);
  const avg = scored.length ? Math.round(scored.reduce((s, c) => s + (c.scorecard.overall || 0), 0) / scored.length) : '-';
  const passed = creatives.filter(c => c.status === 'pass').length;
  const cards = creatives.map((c) => {
    const i = LAST.indexOf(c);
    const ov = (c.scorecard || {}).overall ?? 0;
    return `<div class="g-item" onclick="openCreative(${i})">
      <img src="${c.image_url || assetUrl(c.image_path)}" loading="lazy" alt="">
      <span class="g-score" style="background:${scoreColor(ov)}">${ov}</span></div>`;
  }).join('');
  if (th) th.textContent = 'Campaign complete';
  el.innerHTML = `
    <div class="rr-head">
      <div>
        <div class="rr-title">✓ Your campaign is ready</div>
        <div class="rr-sub">${creatives.length} creative${creatives.length !== 1 ? 's' : ''} · avg <b>${avg}/100</b> · ${passed} passed the critic · tap any to see its scorecard</div>
      </div>
      <div class="rr-btns">
        <button class="btn primary" data-rr="gallery">Open full gallery</button>
        <button class="btn ghost" data-rr="new">New campaign</button>
      </div>
    </div>
    <div class="gallery masonry rr-grid">${cards}</div>`;
  el.querySelectorAll('[data-rr]').forEach(b => b.onclick = () => show(b.dataset.rr));
  el.classList.remove('hidden');
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ---------- gallery ----------
const DIMS = [['thumbstop', 'thumbstop'], ['hierarchy', 'hierarchy'], ['legibility', 'legibility'], ['brand_fit', 'brand fit'], ['hook_clarity', 'hook'], ['cta_visibility', 'CTA']];

// Critic trail: every round the critic saw: rejected images, scores, and the exact fixes it demanded.
function renderTrail(trail) {
  if (!trail || !trail.length) return '';
  const badge = (r) => {
    if (r.kept) return `<span class="tbadge kept">KEPT</span>`;
    return r.pass ? `<span class="tbadge pass">PASS</span>`
                  : `<span class="tbadge reject">REJECTED</span>`;
  };
  const rounds = trail.map(r => {
    const changes = (r.required_changes || []).map(ch =>
      `<li><b>${ch.target || ''}</b>: ${ch.issue || ''} → <i>${ch.fix || ''}</i></li>`).join('');
    return `<div class="trail-round">
      <img class="trail-img" src="${r.image_url || assetUrl(r.image_path)}" alt="">
      <div class="trail-body">
        <div class="trail-meta">Round ${(r.round ?? 0) + 1} · <b>${r.overall}/100</b> ${badge(r)}</div>
        <div>${r.rationale || ''}</div>
        ${changes ? `<ul>${changes}</ul>` : ''}
      </div></div>`;
  }).join('');
  return `<details class="trail"><summary>Critic trail: ${trail.length} round${trail.length > 1 ? 's' : ''}</summary>${rounds}</details>`;
}

// The real Pinterest references the Design Researcher used to ground this creative.
function renderRefs(refs) {
  if (!refs || !refs.length) return '';
  const thumbs = refs.slice(0, 6).map(u =>
    `<a href="${u}" target="_blank" rel="noopener"><img class="ref-thumb" src="${u}" loading="lazy" referrerpolicy="no-referrer"></a>`).join('');
  return `<div class="refs">
    <div class="refs-label">Grounded in ${refs.length} real Pinterest references</div>
    <div class="refs-row">${thumbs}</div></div>`;
}
function creativeCard(c) {
  const sc = c.scorecard || {}; const ov = sc.overall ?? 0;
  const bars = DIMS.map(([k, lbl]) => `<div class="bar"><span>${lbl}</span><div class="track"><div class="fill" style="width:${(sc[k] || 0) * 10}%"></div></div><span>${sc[k] ?? 0}</span></div>`).join('');
  const pass = c.status === 'pass';
  return `<div class="creative">
    <div class="img"><img src="${c.image_url || assetUrl(c.image_path)}" alt="">
      <span class="score-pill" style="background:${scoreColor(ov)}">${ov}</span></div>
    <div class="body">
      <div class="hl">${(c.brief && c.brief.headline) || ''}</div>
      <span class="status ${pass ? 'st-pass' : 'st-best'}">${pass ? 'Passed the bar' : 'Best effort'}</span>
      <div class="bars">${bars}</div>
      <div class="rationale">${c.rationale || ''}</div>
      ${renderRefs(c.design_refs)}
      ${renderTrail(c.trail)}
    </div></div>`;
}
function renderGallery(creatives) {
  const g = $('#gallery');
  if (!creatives || !creatives.length) { g.className = 'gallery'; g.innerHTML = '<p class="empty">No creatives yet. Run a campaign to fill the gallery.</p>'; return; }
  g.className = 'gallery masonry';
  g.innerHTML = creatives.map((c, i) => {
    const ov = (c.scorecard || {}).overall ?? 0;
    return `<div class="g-item" onclick="openCreative(${i})">
      <img src="${c.image_url || assetUrl(c.image_path)}" loading="lazy" alt="">
      <span class="g-score" style="background:${scoreColor(ov)}">${ov}</span>
    </div>`;
  }).join('');
}
window.openCreative = (i) => {
  const c = LAST[i]; if (!c) return;
  $('#creative-body').innerHTML = creativeCard(c);
  $('#creative-modal').classList.remove('hidden');
};
window.closeCreative = () => { $('#creative-modal')?.classList.add('hidden'); };

// ---------- run history ----------
async function loadRuns() {
  const { runs = [] } = await api('/runs');
  $('#runs-list').innerHTML = runs.length ? runs.map(r => `
    <div class="run-item" id="run-${r.id}" onclick="openRun('${r.id}')">
      <div class="run-nm">${r.brand_name || 'Untitled'}</div>
      <div class="run-obj">${(r.objective || '').slice(0, 52)}</div>
      <div class="run-meta">${r.status} · avg ${r.avg_score ?? '-'}/100</div>
    </div>`).join('') : '<p class="empty">No runs yet. Run a campaign.</p>';
  if (runs.length) openRun(runs[0].id);
}
window.openRun = async (id) => {
  document.querySelectorAll('.run-item').forEach(n => n.classList.remove('active'));
  document.getElementById('run-' + id)?.classList.add('active');
  const run = await api('/runs/' + id);
  const log = run.log || [];
  const creatives = run.creatives || [];
  const timeline = log.map(e => entryEl(e).outerHTML).join('');
  const gallery = creatives.length ? creatives.map(creativeCard).join('') : '<p class="empty">No creatives.</p>';
  $('#run-detail').innerHTML =
    `<h3 class="detail-h">Society timeline</h3>
     <div class="timeline">${timeline}</div>
     <h3 class="detail-h" style="margin-top:var(--sp-6)">Creatives</h3>
     <div class="gallery">${gallery}</div>`;
};

// ---------- persisted creatives (survive reload) ----------
async function loadCreatives() {
  try {
    const { creatives = [] } = await api('/creatives');
    LAST = creatives;
  } catch (e) { /* keep whatever we have */ }
  return LAST;
}

// ---------- boot ----------
renderSociety(); loadBrandSelect();
loadCreatives().then(() => { renderGallery(LAST); });
// deep-link support: /#new, /#history, /#gallery, ...
window.addEventListener('hashchange', () => { const v = location.hash.slice(1); if (v) show(v); });
if (location.hash.slice(1)) show(location.hash.slice(1));
