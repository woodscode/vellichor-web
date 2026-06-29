// ---------- state ----------
let VOICES = [];
let selected = null;
let filter = 'story';
let chosenFile = null;
const sampleAudio = new Audio();

const $ = (s) => document.querySelector(s);
const fmtTime = (ms) => {
  if (!ms && ms !== 0) return '—';
  const s = Math.round(ms / 1000);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}h ${m}m` : m ? `${m}m ${sec}s` : `${sec}s`;
};
const toast = (msg, kind = '') => {
  const t = $('#toast');
  t.textContent = msg; t.className = `toast show ${kind}`;
  setTimeout(() => (t.className = 'toast'), 3500);
};

// ---------- voices ----------
async function loadVoices() {
  const r = await fetch('/api/voices');
  const data = await r.json();
  VOICES = data.voices;
  $('#device').textContent = data.device === 'cuda' ? '⚡ GPU' : '🐢 CPU';
  selectVoice(data.default);
  renderVoices();
}

function matchesFilter(v) {
  switch (filter) {
    case 'all': return true;
    case 'story': return v.story;
    case 'female': return v.gender === 'female';
    case 'male': return v.gender === 'male';
    case 'American': return v.accent === 'American';
    case 'British': return v.accent === 'British';
    case 'other': return v.accent !== 'American' && v.accent !== 'British';
    default: return true;
  }
}

function renderVoices() {
  const q = $('#voiceSearch').value.toLowerCase();
  const list = $('#voiceList');
  list.innerHTML = '';
  const items = VOICES.filter(matchesFilter).filter(v =>
    !q || v.name.toLowerCase().includes(q) || v.accent.toLowerCase().includes(q));
  if (!items.length) { list.innerHTML = '<div class="muted small">No voices match.</div>'; return; }
  for (const v of items) {
    const el = document.createElement('div');
    el.className = 'voice-card' + (selected === v.id ? ' sel' : '');
    el.innerHTML = `
      <div class="vc-flag">${v.flag}</div>
      <div class="vc-main">
        <div class="vc-name">${v.name} ${v.story ? '<span class="star">★</span>' : ''}
          <span class="vc-grade">${v.grade}</span></div>
        <div class="vc-blurb">${v.blurb}</div>
      </div>
      <button class="vc-play" title="Play sample">▶</button>`;
    el.addEventListener('click', (e) => {
      if (e.target.closest('.vc-play')) return;
      selectVoice(v.id); renderVoices();
    });
    el.querySelector('.vc-play').addEventListener('click', (e) => {
      e.stopPropagation(); playSample(v.id, e.target);
    });
    list.appendChild(el);
  }
}

function selectVoice(id) {
  selected = id;
  const v = VOICES.find(x => x.id === id);
  if (v) $('#selectedVoice').innerHTML = `${v.flag} ${v.name} · <span class="muted">${v.accent} ${v.gender}</span>`;
}

function stopAllAudio() {
  try { sampleAudio.pause(); } catch (e) {}
  ['previewAudio', 'ambAudio'].forEach(id => { const a = $('#' + id); if (a) a.pause(); });
  const amb = $('#ambPlay'); if (amb) amb.textContent = '▶ Preview';
}

function playSample(id, btn) {
  stopAllAudio();
  btn.classList.add('loading'); btn.textContent = '◌';
  sampleAudio.src = `/api/voice-sample/${id}`;
  sampleAudio.play()
    .then(() => { btn.classList.remove('loading'); btn.textContent = '▶'; })
    .catch(() => { btn.classList.remove('loading'); btn.textContent = '▶'; toast('Could not play sample', 'bad'); });
}

// ---------- tabs ----------
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.tabpane').forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  $('#pane-' + t.dataset.tab).classList.add('active');
}));

// ---------- filters / search ----------
$('#voiceFilters').addEventListener('click', (e) => {
  const p = e.target.closest('.pill'); if (!p) return;
  document.querySelectorAll('.pill').forEach(x => x.classList.remove('active'));
  p.classList.add('active'); filter = p.dataset.filter; renderVoices();
});
$('#voiceSearch').addEventListener('input', renderVoices);

// ---------- speed ----------
$('#speed').addEventListener('input', (e) => $('#speedVal').textContent = (+e.target.value).toFixed(2) + '×');

// ---------- upload ----------
const dz = $('#dropzone'), fileInput = $('#fileInput');
dz.addEventListener('click', () => fileInput.click());
dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('drag'); });
dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
dz.addEventListener('drop', (e) => {
  e.preventDefault(); dz.classList.remove('drag');
  if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => fileInput.files[0] && setFile(fileInput.files[0]));
function setFile(f) {
  chosenFile = f;
  const c = $('#fileChosen');
  c.hidden = false;
  c.innerHTML = `📘 <strong>${f.name}</strong> <span class="muted small">(${(f.size / 1024).toFixed(0)} KB)</span>`;
  if (!$('#storyTitle').value) $('#storyTitle').value = f.name.replace(/\.[^.]+$/, '');
}

// ---------- preview ----------
$('#previewBtn').addEventListener('click', async () => {
  const text = ($('#storyText').value || '').trim().slice(0, 400)
    || 'Once upon a time, in a land far away, a little hero set off on a grand adventure.';
  const btn = $('#previewBtn'); btn.disabled = true; btn.textContent = '◌ Synthesizing…';
  try {
    const r = await fetch('/api/preview', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ voice: selected, text, speed: +$('#speed').value }),
    });
    if (!r.ok) throw new Error();
    const blob = await r.blob();
    stopAllAudio();
    const a = $('#previewAudio'); a.src = URL.createObjectURL(blob); a.play();
  } catch { toast('Preview failed', 'bad'); }
  btn.disabled = false; btn.textContent = '▶ Preview voice on this text';
});

// ---------- convert ----------
$('#convertBtn').addEventListener('click', async () => {
  const writing = $('.tab[data-tab="write"]').classList.contains('active');
  const fd = new FormData();
  fd.append('voice', selected);
  fd.append('speed', $('#speed').value);
  fd.append('author', $('#author').value || 'Audiblez');
  fd.append('export_abs', $('#exportAbs').checked);
  const formats = [];
  if ($('#fmtM4b').checked) formats.push('m4b');
  if ($('#fmtMp3').checked) formats.push('mp3');
  if (!formats.length) { toast('Pick at least one output format', 'bad'); return; }
  fd.append('formats', formats.join(','));
  fd.append('title', $('#storyTitle').value || '');
  if ($('#coverInput').files[0]) fd.append('cover', $('#coverInput').files[0]);

  // multi-voice
  const mv = $('#multiVoice').checked;
  fd.append('multivoice', mv);
  if (mv) fd.append('cast', JSON.stringify(gatherCast()));

  // ambience
  fd.append('ambience', $('#ambienceSelect').value || '');
  fd.append('ambience_volume', (+$('#ambVol').value / 100).toFixed(3));
  fd.append('ducking', $('#ducking').checked);
  if (ambUpload) fd.append('ambience_file', ambUpload);

  if (writing) {
    const text = $('#storyText').value.trim();
    if (!text) { toast('Write a story first ✍️', 'bad'); return; }
    fd.append('text', text);
  } else {
    if (!chosenFile) { toast('Choose a file to convert', 'bad'); return; }
    fd.append('file', chosenFile);
  }

  const btn = $('#convertBtn'); btn.disabled = true; btn.textContent = '◌ Queuing…';
  try {
    const r = await fetch('/api/convert', { method: 'POST', body: fd });
    if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'failed'); }
    toast('Added to the queue 🎬', 'good');
    refreshJobs();
  } catch (e) { toast('Could not start: ' + e.message, 'bad'); }
  btn.disabled = false; btn.textContent = '🎬 Create audiobook';
});

// ---------- jobs ----------
async function refreshJobs() {
  const r = await fetch('/api/jobs');
  const { jobs } = await r.json();
  renderJobs(jobs);
}

function renderJobs(jobs) {
  const root = $('#jobs');
  if (!jobs.length) { root.innerHTML = '<div class="muted small">No conversions yet. Write a story and hit “Create audiobook”.</div>'; return; }
  root.innerHTML = '';
  for (const j of jobs) {
    const v = VOICES.find(x => x.id === j.voice);
    const el = document.createElement('div');
    el.className = 'job';
    const dls = (j.result?.downloads || []).map(d =>
      `<a class="dl" href="/api/download/${j.id}/${encodeURIComponent(d.name)}">⬇ ${d.label}</a>`).join('');
    const log = (j.log || []).map(l => `<div>› ${l.msg}</div>`).join('');
    const showProg = j.status === 'running' || j.status === 'queued';
    el.innerHTML = `
      <div class="job-head">
        <div>
          <div class="job-title">${j.title || 'Story'}</div>
          <div class="job-sub">${v ? v.flag + ' ' + v.name : j.voice} · ${(+j.speed).toFixed(2)}×</div>
        </div>
        <div style="display:flex;align-items:center;gap:10px">
          <span class="status ${j.status}">${j.status}</span>
          <button class="job-del" title="Remove">✕</button>
        </div>
      </div>
      ${showProg || j.percent ? `<div class="progress"><div class="bar" style="width:${j.percent || 0}%"></div></div>` : ''}
      <div class="job-meta">
        <span>${j.stage || ''}</span>
        ${j.chunks_total ? `<span>${j.chunks_done || 0}/${j.chunks_total} segments</span>` : ''}
        ${j.eta != null && j.status === 'running' ? `<span>⏱ ~${fmtTime(j.eta * 1000)} left</span>` : ''}
        ${j.result?.duration_ms ? `<span>🎧 ${fmtTime(j.result.duration_ms)} · ${j.result.chapters} ch.</span>` : ''}
      </div>
      ${j.error ? `<div class="exported" style="color:var(--bad)">⚠ ${j.error}</div>` : ''}
      ${j.result?.exported_to ? `<div class="exported">✓ Added to Audiobookshelf</div>` : ''}
      ${dls ? `<div class="downloads">${dls}</div>` : ''}
      ${showProg && log ? `<div class="log">${log}</div>` : ''}`;
    el.querySelector('.job-del').addEventListener('click', async () => {
      await fetch('/api/jobs/' + j.id, { method: 'DELETE' }); refreshJobs();
    });
    root.appendChild(el);
  }
}

// ---------- multi-voice cast ----------
const FEMALE_PALETTE = ['af_bella', 'bf_emma', 'af_nova', 'af_nicole', 'bf_isabella', 'af_sarah'];
const MALE_PALETTE = ['am_michael', 'am_fenrir', 'bm_george', 'am_puck', 'bm_fable', 'am_onyx'];
const ANY_PALETTE = ['af_bella', 'am_michael', 'bf_emma', 'am_fenrir', 'af_nova', 'bm_george'];

function pickVoice(gender, used) {
  const pal = gender === 'female' ? FEMALE_PALETTE
    : gender === 'male' ? MALE_PALETTE : ANY_PALETTE;
  return pal.find(v => !used.has(v)) || pal[0];
}

function voiceSelect(value) {
  const sel = document.createElement('select');
  sel.className = 'field cast-voice';
  const groups = {};
  for (const v of VOICES) (groups[v.accent] ||= []).push(v);
  for (const [accent, vs] of Object.entries(groups)) {
    const og = document.createElement('optgroup'); og.label = accent;
    for (const v of vs) {
      const o = document.createElement('option');
      o.value = v.id; o.textContent = `${v.flag} ${v.name}${v.story ? ' ★' : ''}`;
      if (v.id === value) o.selected = true;
      og.appendChild(o);
    }
    sel.appendChild(og);
  }
  return sel;
}

$('#multiVoice').addEventListener('change', (e) => {
  $('#castArea').hidden = !e.target.checked;
});

async function checkSmartcast() {
  try {
    const r = await fetch('/api/smartcast/status');
    const d = await r.json();
    const btn = $('#smartBtn');
    if (d.available) { btn.disabled = false; btn.title = 'AI model: ' + d.model; }
    else { btn.disabled = false; btn.title = 'AI model still loading/downloading'; }
  } catch (e) {}
}

$('#smartBtn').addEventListener('click', async () => {
  const text = $('#storyText').value.trim();
  if (!text) { toast('Write or paste a story first', 'bad'); return; }
  const btn = $('#smartBtn'); btn.disabled = true; btn.textContent = '🪄 Thinking…';
  try {
    const r = await fetch('/api/smartcast', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (r.status === 503) { toast('AI model still loading — try again in a moment', 'bad'); throw 0; }
    if (!r.ok) throw 0;
    const data = await r.json();
    $('#storyText').value = data.tagged;          // show the AI-inserted [Name] tags
    renderCast({ characters: data.characters, has_markup: true });
    $('#castHint').textContent = '🪄 AI tagged your story with [Name] markup — review/edit it above, then create your audiobook.';
    toast('AI cast ready — story tagged ✨', 'good');
  } catch (e) { if (e !== 0) toast('Smart cast failed', 'bad'); }
  btn.disabled = false; btn.textContent = '🪄 Smart cast (AI)';
});

$('#analyzeBtn').addEventListener('click', async () => {
  const text = $('#storyText').value.trim();
  if (!text) { toast('Write or paste a story first', 'bad'); return; }
  const btn = $('#analyzeBtn'); btn.disabled = true; btn.textContent = '◌ Analyzing…';
  try {
    const r = await fetch('/api/analyze', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const data = await r.json();
    renderCast(data);
  } catch { toast('Analysis failed', 'bad'); }
  btn.disabled = false; btn.textContent = '🔎 Analyze story for characters';
});

function renderCast(data) {
  const list = $('#castList');
  list.innerHTML = '';
  $('#castHint').textContent = data.has_markup
    ? '✓ Using your [Name] tags.'
    : 'Auto-detected from quotes & dialogue tags. Tip: add [Name] tags for perfect accuracy.';
  if (!data.characters || !data.characters.length) {
    list.innerHTML = '<div class="muted small">No characters detected.</div>'; return;
  }
  const used = new Set([selected]);
  for (const c of data.characters) {
    const isNarr = c.name.toLowerCase() === 'narrator';
    let dflt;
    if (isNarr) { dflt = selected; }
    else { dflt = pickVoice(c.gender, used); used.add(dflt); }
    const gicon = c.gender === 'female' ? ' <span class="gender f">♀</span>'
      : c.gender === 'male' ? ' <span class="gender m">♂</span>' : '';
    const row = document.createElement('div');
    row.className = 'cast-row'; row.dataset.name = c.name;
    row.innerHTML = `<div class="cast-name">${isNarr ? '📖' : '🗣️'} ${c.name}${gicon}
        <span class="muted small">${c.lines} line${c.lines === 1 ? '' : 's'}</span></div>`;
    const sel = voiceSelect(dflt);
    const play = document.createElement('button');
    play.className = 'vc-play'; play.textContent = '▶';
    play.addEventListener('click', () => playSample(sel.value, play));
    row.appendChild(sel); row.appendChild(play);
    list.appendChild(row);
  }
}

function gatherCast() {
  const map = {};
  document.querySelectorAll('.cast-row').forEach(r => {
    map[r.dataset.name] = r.querySelector('.cast-voice').value;
  });
  return map;
}

// ---------- ambience ----------
let ambUpload = null;
async function loadAmbience() {
  const r = await fetch('/api/ambience');
  const { beds } = await r.json();
  const sel = $('#ambienceSelect');
  for (const b of beds) {
    const o = document.createElement('option');
    o.value = b.id; o.textContent = b.label; sel.appendChild(o);
  }
}
$('#ambVol').addEventListener('input', (e) => $('#ambVolVal').textContent = e.target.value + '%');
$('#ambienceFile').addEventListener('change', (e) => {
  ambUpload = e.target.files[0] || null;
  $('#ambUploadName').textContent = ambUpload ? '📁 ' + ambUpload.name + ' (will be used)' : '';
});
const ambAudioEl = $('#ambAudio');
ambAudioEl.addEventListener('ended', () => $('#ambPlay').textContent = '▶ Preview');
$('#ambPlay').addEventListener('click', () => {
  const btn = $('#ambPlay');
  if (!ambAudioEl.paused) { stopAllAudio(); return; }  // toggle off
  let src;
  if (ambUpload) { src = URL.createObjectURL(ambUpload); }
  else {
    const id = $('#ambienceSelect').value;
    if (!id) { toast('Pick an ambience bed first', 'bad'); return; }
    src = `/api/ambience-sample/${encodeURIComponent(id)}`;
  }
  stopAllAudio();
  ambAudioEl.src = src;
  ambAudioEl.play().then(() => btn.textContent = '⏸ Stop')
    .catch(() => toast('Could not play preview', 'bad'));
});
// stop ambience preview if the user switches beds
$('#ambienceSelect').addEventListener('change', stopAllAudio);

$('#logoutBtn').addEventListener('click', async () => {
  await fetch('/api/logout', { method: 'POST' }); location.href = '/login';
});

// ---------- boot ----------
loadVoices();
loadAmbience();
checkSmartcast();
refreshJobs();
setInterval(refreshJobs, 1500);
