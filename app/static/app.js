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

// ---------- theme ----------
// The saved theme is already applied to <html> by the inline <head> script
// (no-flash). Here we just sync the picker and persist changes.
(function initTheme() {
  const sel = $('#themeSelect');
  if (!sel) return;
  let saved = 'dark';
  try { saved = localStorage.getItem('vellichor-theme') || 'dark'; } catch (e) {}
  sel.value = saved;
  sel.addEventListener('change', () => {
    document.documentElement.setAttribute('data-theme', sel.value);
    try { localStorage.setItem('vellichor-theme', sel.value); } catch (e) {}
  });
})();

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

// ---------- loudness ----------
// slider index -> label / LUFS target (0 = off, i.e. leave the audio untouched)
const LOUD_LABELS = ['Off', 'Standard', 'Loud', 'Extra loud'];
const LOUD_LUFS = [0, -18, -16, -14];
$('#loud').addEventListener('input', (e) => $('#loudVal').textContent = LOUD_LABELS[+e.target.value]);

// ---------- TTS engine ----------
let ENGINES = [];
async function loadEngines() {
  try {
    const r = await fetch('/api/engines');
    const d = await r.json();
    ENGINES = d.engines || [];
    const sel = $('#engineSelect');
    sel.innerHTML = '';
    for (const e of ENGINES) {
      const o = document.createElement('option');
      o.value = e.id;
      o.textContent = e.available ? e.label : `${e.label} — unavailable`;
      o.disabled = !e.available;
      if (e.id === d.default) o.selected = true;
      sel.appendChild(o);
    }
    sel.addEventListener('change', updateEngineUI);
    updateEngineUI();
  } catch (e) {}
}
function currentEngine() {
  return ENGINES.find(e => e.id === $('#engineSelect').value) || ENGINES[0] || null;
}
function updateEngineUI() {
  const e = currentEngine();
  $('#engineBlurb').textContent = e ? (e.blurb || '') : '';
  const expressive = !!e && (e.controls || []).includes('exaggeration');
  $('#expressiveControls').hidden = !expressive;
}
$('#exag').addEventListener('input', (e) => $('#exagVal').textContent = (+e.target.value).toFixed(2));

// ---------- reference voices ("My Voices") + in-app recorder ----------
let MY_VOICES = [];
// how to source the clone reference: {type:'preset'} | {type:'myvoice',id} | {type:'oneoff',file,label}
let selectedRef = { type: 'preset' };
let recordedBlob = null, pendingClip = null, mediaRec = null, recChunks = [], recTimerId = null, recSeconds = 0;

const REC_SCRIPT = "Once upon a time, in a cosy little house at the edge of a quiet wood, " +
  "there lived a curious child who loved stories more than anything. Every night, as the " +
  "stars blinked awake, a warm and gentle voice would read aloud, carrying them off to " +
  "lands of dragons, kind giants, and sleepy, moonlit seas.";

async function loadMyVoices() {
  try { MY_VOICES = (await (await fetch('/api/myvoices')).json()).voices || []; }
  catch (e) { MY_VOICES = []; }
  renderMyVoices();
}

function renderMyVoices() {
  const list = $('#myVoicesList'); if (!list) return;
  list.innerHTML = '';
  const row = (checked, label) => {
    const el = document.createElement('label');
    el.className = 'ref-row' + (checked ? ' sel' : '');
    el.innerHTML = `<input type="radio" name="refsrc" ${checked ? 'checked' : ''}/><span class="ref-name">${label}</span>`;
    return el;
  };
  const preset = row(selectedRef.type === 'preset', '🎛️ Preset voice (from the list on the left)');
  preset.querySelector('input').addEventListener('change', () => {
    selectedRef = { type: 'preset' }; $('#refChosen').textContent = ''; renderMyVoices();
  });
  list.appendChild(preset);
  for (const v of MY_VOICES) {
    const r = row(selectedRef.type === 'myvoice' && selectedRef.id === v.id, '🗣️ ' + v.name);
    const play = document.createElement('button');
    play.type = 'button'; play.className = 'vc-play'; play.textContent = '▶'; play.title = 'Preview';
    play.addEventListener('click', (e) => { e.preventDefault(); stopAllAudio(); sampleAudio.src = `/api/myvoices/${v.id}/sample`; sampleAudio.play().catch(() => toast('Could not play preview', 'bad')); });
    const del = document.createElement('button');
    del.type = 'button'; del.className = 'ref-del'; del.textContent = '✕'; del.title = 'Delete';
    del.addEventListener('click', async (e) => {
      e.preventDefault();
      if (!confirm(`Delete voice "${v.name}"?`)) return;
      await fetch('/api/myvoices/' + v.id, { method: 'DELETE' });
      if (selectedRef.type === 'myvoice' && selectedRef.id === v.id) selectedRef = { type: 'preset' };
      loadMyVoices();
    });
    r.querySelector('input').addEventListener('change', () => {
      selectedRef = { type: 'myvoice', id: v.id }; $('#refChosen').textContent = ''; renderMyVoices();
    });
    r.appendChild(play); r.appendChild(del);
    list.appendChild(r);
  }
}

function setOneOff(file, label) {
  selectedRef = { type: 'oneoff', file, label };
  $('#refChosen').textContent = '✓ ' + label;
  renderMyVoices();
}
function blobExt(b) { return (b.type || '').includes('ogg') ? 'ogg' : 'webm'; }
function clipToFile(clip) {
  if (clip instanceof File) return clip;
  return new File([clip], 'recording.' + blobExt(clip), { type: clip.type || 'audio/webm' });
}

// Uploading a clip behaves like a recording: you can Use it once OR Save it to My Voices.
$('#referenceInput').addEventListener('change', (e) => {
  const f = e.target.files[0]; if (!f) return;
  pendingClip = f;
  const pb = $('#recPlayback'); pb.src = URL.createObjectURL(f); pb.hidden = false;
  $('#recPanel').hidden = false;
  $('#recUse').disabled = false; $('#recSave').disabled = false;
  $('#recName').value = (f.name || '').replace(/\.[^.]+$/, '');
  $('#recMsg').textContent = `Selected "${f.name}" — Use for this book, or name it and Save.`;
  setOneOff(f, f.name + ' (this book only)');
});

// ---- recorder ----
$('#recScript').textContent = REC_SCRIPT;
$('#recToggle').addEventListener('click', () => { const p = $('#recPanel'); p.hidden = !p.hidden; });
$('#recStart').addEventListener('click', startRecording);
$('#recStop').addEventListener('click', stopRecording);
$('#recUse').addEventListener('click', () => {
  if (!pendingClip) return;
  const f = clipToFile(pendingClip);
  setOneOff(f, (pendingClip instanceof File ? f.name : '🎙️ recording') + ' (this book only)');
  toast('Set for this book', 'good');
});
$('#recSave').addEventListener('click', saveRecording);

async function startRecording() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.isSecureContext) {
    $('#recMsg').textContent = '🔒 Recording needs a secure connection — open Vellichor via your https:// address.';
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recChunks = [];
    mediaRec = new MediaRecorder(stream);
    mediaRec.ondataavailable = (e) => { if (e.data.size) recChunks.push(e.data); };
    mediaRec.onstop = () => {
      stream.getTracks().forEach(t => t.stop());
      recordedBlob = new Blob(recChunks, { type: mediaRec.mimeType || 'audio/webm' });
      pendingClip = recordedBlob;
      const pb = $('#recPlayback'); pb.src = URL.createObjectURL(recordedBlob); pb.hidden = false;
      $('#recUse').disabled = false; $('#recSave').disabled = false;
    };
    mediaRec.start();
    recSeconds = 0; $('#recTimer').textContent = '0:00';
    recTimerId = setInterval(() => {
      recSeconds++;
      $('#recTimer').textContent = Math.floor(recSeconds / 60) + ':' + String(recSeconds % 60).padStart(2, '0');
      if (recSeconds >= 60) stopRecording();   // safety cap
    }, 1000);
    $('#recStart').disabled = true; $('#recStop').disabled = false; $('#recMsg').textContent = 'Recording…';
  } catch (err) {
    $('#recMsg').textContent = 'Mic blocked or unavailable: ' + (err.message || err.name || '');
  }
}
function stopRecording() {
  if (mediaRec && mediaRec.state !== 'inactive') mediaRec.stop();
  if (recTimerId) { clearInterval(recTimerId); recTimerId = null; }
  $('#recStart').disabled = false; $('#recStop').disabled = true;
  $('#recMsg').textContent = 'Recorded ' + $('#recTimer').textContent + ' — review, then Use or Save.';
}
async function saveRecording() {
  if (!pendingClip) return;
  const name = ($('#recName').value || '').trim();
  if (!name) { toast('Give the voice a name first', 'bad'); return; }
  const f = clipToFile(pendingClip);
  const fd = new FormData();
  fd.append('name', name);
  fd.append('audio', f, f.name);
  const btn = $('#recSave'); btn.disabled = true; btn.textContent = '◌ Saving…';
  try {
    const r = await fetch('/api/myvoices', { method: 'POST', body: fd });
    if (!r.ok) throw new Error(((await r.json().catch(() => ({}))).detail) || 'save failed');
    const v = await r.json();
    await loadMyVoices();
    selectedRef = { type: 'myvoice', id: v.id }; $('#refChosen').textContent = ''; renderMyVoices();
    $('#recPanel').hidden = true; $('#recName').value = '';
    toast('Voice saved ✨', 'good');
  } catch (e) { toast('Could not save voice: ' + e.message, 'bad'); }
  finally { btn.disabled = false; btn.textContent = 'Save voice'; }
}

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
  const text = ($('#storyText').value || '').trim().slice(0, 500)
    || 'Once upon a time, in a land far away, a little hero set off on a grand adventure.';
  const eng = $('#engineSelect').value || 'kokoro';
  const btn = $('#previewBtn'); btn.disabled = true;
  btn.textContent = eng === 'kokoro' ? '◌ Synthesizing…' : '◌ Synthesizing (Chatterbox is slower)…';
  try {
    const fd = new FormData();
    fd.append('voice', selected);
    fd.append('engine', eng);
    fd.append('speed', $('#speed').value);
    fd.append('exaggeration', $('#exag').value);
    fd.append('loudness', LOUD_LUFS[+$('#loud').value]);
    fd.append('text', text);
    if (eng !== 'kokoro') {
      if (selectedRef.type === 'oneoff' && selectedRef.file) {
        fd.append('reference_file', selectedRef.file, selectedRef.file.name || 'reference.webm');
      } else if (selectedRef.type === 'myvoice') {
        fd.append('reference_voice', selectedRef.id);
      }
    }
    const r = await fetch('/api/preview', { method: 'POST', body: fd });
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
  const eng = $('#engineSelect').value || 'kokoro';
  fd.append('engine', eng);
  fd.append('speed', $('#speed').value);
  fd.append('exaggeration', $('#exag').value);
  if (eng !== 'kokoro') {
    if (selectedRef.type === 'oneoff' && selectedRef.file) {
      fd.append('reference_file', selectedRef.file, selectedRef.file.name || 'reference.webm');
    } else if (selectedRef.type === 'myvoice') {
      fd.append('reference_voice', selectedRef.id);
    }
    // 'preset' → send nothing; backend clones a Kokoro render of the picked voice
  }
  fd.append('loudness', LOUD_LUFS[+$('#loud').value]);
  fd.append('author', $('#author').value || 'Vellichor');
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
          <div class="job-sub">${j.voice_label || (v ? v.flag + ' ' + v.name : j.voice)}${(j.engine && j.engine !== 'kokoro') ? '' : ' · ' + (+j.speed).toFixed(2) + '×'}</div>
        </div>
        <div style="display:flex;align-items:center;gap:10px">
          <span class="status ${j.status}">${j.status}</span>
          ${showProg
            ? '<button class="job-stop" title="Stop conversion">■ Stop</button>'
            : '<button class="job-del" title="Remove">✕</button>'}
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
    const stopBtn = el.querySelector('.job-stop');
    if (stopBtn) stopBtn.addEventListener('click', async () => {
      stopBtn.disabled = true; stopBtn.textContent = '◌ Stopping…';
      await fetch('/api/jobs/' + j.id + '/cancel', { method: 'POST' }); refreshJobs();
    });
    const delBtn = el.querySelector('.job-del');
    if (delBtn) delBtn.addEventListener('click', async () => {
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

function onUploadTab() {
  return $('.tab[data-tab="upload"]').classList.contains('active');
}
function switchToWrite() { $('.tab[data-tab="write"]').click(); }

async function extractFileText() {
  const fd = new FormData(); fd.append('file', chosenFile);
  const r = await fetch('/api/extract', { method: 'POST', body: fd });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'extract failed'); }
  return (await r.json()).text;
}

// Source text for cast analysis: the editor, or an uploaded file's contents.
async function castSourceText() {
  if (onUploadTab() && chosenFile) return await extractFileText();
  return $('#storyText').value.trim();
}

$('#smartBtn').addEventListener('click', async () => {
  const btn = $('#smartBtn'); btn.disabled = true; btn.textContent = '🪄 Thinking…';
  try {
    const fromFile = onUploadTab() && chosenFile;
    const text = fromFile ? await extractFileText() : $('#storyText').value.trim();
    if (!text) { toast('Write a story or choose a file first', 'bad'); return; }
    if (text.length > 15000 &&
        !confirm('This is a long text — AI Smart cast may take several minutes. ' +
                 'Continue? (Quick detect is instant.)')) return;
    const r = await fetch('/api/smartcast', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (r.status === 503) { toast('AI model still loading — try again in a moment', 'bad'); return; }
    if (!r.ok) throw new Error();
    const data = await r.json();
    // AI rewrites the text with [Name] tags, so it becomes the source we convert
    $('#storyText').value = data.tagged;
    if (fromFile) {
      switchToWrite(); chosenFile = null;
      $('#fileChosen').hidden = true; $('#fileInput').value = '';
      toast('Imported & tagged from file ✨', 'good');
    } else {
      toast('AI cast ready — story tagged ✨', 'good');
    }
    renderCast({ characters: data.characters, has_markup: true });
    $('#castHint').textContent = '🪄 AI tagged your story with [Name] markup — review/edit it above, then create your audiobook.';
  } catch (e) { toast('Smart cast failed', 'bad'); }
  finally { btn.disabled = false; btn.textContent = '🪄 Smart cast (AI)'; }
});

$('#analyzeBtn').addEventListener('click', async () => {
  const btn = $('#analyzeBtn'); btn.disabled = true; btn.textContent = '◌ Analyzing…';
  try {
    const text = await castSourceText();
    if (!text) { toast('Write a story or choose a file first', 'bad'); return; }
    const r = await fetch('/api/analyze', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    renderCast(await r.json());
  } catch (e) { toast('Analysis failed: ' + (e.message || ''), 'bad'); }
  finally { btn.disabled = false; btn.textContent = '🔎 Quick detect'; }
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

// ---------- pronunciations ----------
async function loadPron() {
  try { renderPron(((await (await fetch('/api/pronunciations')).json()).rules) || []); }
  catch (e) {}
}
function renderPron(rules) {
  const list = $('#pronList'); if (!list) return;
  list.innerHTML = '';
  if (!rules.length) { list.innerHTML = '<div class="muted small">No rules yet.</div>'; return; }
  for (const it of rules) {
    const row = document.createElement('div');
    row.className = 'pron-row';
    row.innerHTML = `<span class="pron-from">${it.from}</span><span class="pron-arrow">→</span><span class="pron-to">${it.to || '—'}</span>`;
    const del = document.createElement('button');
    del.className = 'ref-del'; del.textContent = '✕'; del.title = 'Delete';
    del.addEventListener('click', async () => {
      await fetch('/api/pronunciations/' + encodeURIComponent(it.from), { method: 'DELETE' });
      loadPron();
    });
    row.appendChild(del);
    list.appendChild(row);
  }
}
$('#pronAdd').addEventListener('click', async () => {
  const from = $('#pronFrom').value.trim(), to = $('#pronTo').value.trim();
  if (!from) { toast('Enter a word', 'bad'); return; }
  const r = await fetch('/api/pronunciations', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from, to }),
  });
  if (r.ok) { $('#pronFrom').value = ''; $('#pronTo').value = ''; renderPron((await r.json()).rules || []); toast('Added', 'good'); }
  else toast('Could not add', 'bad');
});

// ---------- boot ----------
loadVoices();
loadEngines();
loadMyVoices();
loadAmbience();
loadPron();
checkSmartcast();
refreshJobs();
setInterval(refreshJobs, 1500);
