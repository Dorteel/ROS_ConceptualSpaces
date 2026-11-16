'use strict';
const $ = selector => document.querySelector(selector);
const clone = value => JSON.parse(JSON.stringify(value));
let axes = [], editing = null, busy = false;

function message(text, error = false) {
  $('#message').textContent = text;
  $('#message').classList.toggle('error', error);
}
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed.');
  return result;
}
async function operation(action) {
  if (busy) return;
  busy = true;
  $('#workspace').inert = true;
  try { await action(); } catch (error) { message(error.message, true); }
  finally { busy = false; $('#workspace').inert = false; }
}
function wrap(doc) { return {doc, dirty: !doc.modified_at, candidates: [], selected: null, suggested: false}; }
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function button(text, action, className) {
  const node = element('button', className, text);
  node.type = 'button'; node.addEventListener('click', action); return node;
}
function changed(axis) { axis.dirty = true; render(); }
function positionAt(event, track) {
  const rect = track.getBoundingClientRect();
  return Math.max(0.001, Math.min(0.999, (event.clientX - rect.left) / rect.width));
}
function addCandidate(axis, candidate, position) {
  axis.doc.gradient.push({concept: candidate.concept, position, source: 'wordnet', provenance: clone(candidate.provenance)});
  axis.selected = null; changed(axis);
}
function openConcept(axis, index, position) {
  editing = {axis, index};
  const item = index === null ? null : axis.doc.gradient[index];
  $('#dialog-title').textContent = item ? 'Edit concept' : 'Add concept';
  $('#concept-word').value = item?.concept || '';
  $('#concept-position').value = item?.position ?? position;
  $('#concept-origin').textContent = item?.source === 'wordnet' ? 'Accepted from WordNet. Renaming makes this a manual concept; the original candidate is retained as origin metadata.' : 'Manually positioned by you.';
  $('#delete-concept').hidden = !item;
  $('#concept-dialog').showModal(); $('#concept-word').focus();
}
$('#concept-form').addEventListener('submit', event => {
  event.preventDefault();
  const {axis, index} = editing;
  const word = $('#concept-word').value.trim(), position = Number($('#concept-position').value);
  if (!word || !(position > 0 && position < 1)) return;
  const old = index === null ? null : axis.doc.gradient[index];
  const item = old ? {...old, concept: word, position} : {concept: word, position, source: 'manual'};
  if (old?.source === 'wordnet' && word !== old.concept) {
    item.origin = {concept: old.concept, provenance: clone(old.provenance)};
    item.source = 'manual'; delete item.provenance;
  }
  if (index === null) axis.doc.gradient.push(item); else axis.doc.gradient[index] = item;
  $('#concept-dialog').close(); changed(axis);
});
$('#cancel-concept').onclick = () => $('#concept-dialog').close();
$('#delete-concept').onclick = () => {
  editing.axis.doc.gradient.splice(editing.index, 1);
  $('#concept-dialog').close(); changed(editing.axis);
};

// Pack labels into measured lanes, with connectors preserving the exact position.
function layoutLabels(track) {
  const width = track.clientWidth, lanes = [];
  const endpointHeight = Math.max(...[...track.querySelectorAll('.endpoint')].map(n => n.offsetHeight));
  track.style.marginTop = `${Math.max(44, endpointHeight + 20)}px`;
  const nodes = [...track.querySelectorAll('.concept')].sort((a, b) => +a.dataset.position - +b.dataset.position);
  for (const node of nodes) {
    const x = Number(node.dataset.position) * width;
    const left = Math.max(-30, Math.min(width + 30 - node.offsetWidth, x - node.offsetWidth / 2));
    let lane = lanes.findIndex(right => right + 10 <= left);
    if (lane < 0) lane = lanes.length;
    lanes[lane] = left + node.offsetWidth;
    node.style.left = `${left}px`; node.dataset.lane = lane;
  }
  const heights = lanes.map((_, lane) => Math.max(...nodes.filter(n => +n.dataset.lane === lane).map(n => n.offsetHeight)));
  const tops = []; let height = 22;
  heights.forEach(h => { tops.push(height); height += h + 9; });
  track.querySelectorAll('.connector').forEach(n => n.remove());
  for (const node of nodes) {
    const top = tops[Number(node.dataset.lane)]; node.style.top = `${top}px`;
    const connector = element('span', 'connector');
    connector.style.left = `${Number(node.dataset.position) * 100}%`;
    connector.style.height = `${top}px`; track.append(connector);
  }
  track.style.height = `${Math.max(height + 5, 65)}px`;
}
function render() {
  const root = $('#editor'); root.replaceChildren();
  if (!axes.length) root.append(element('p', '', 'Choose a pair count and select Resample to begin.'));
  for (const axis of axes) {
    const doc = axis.doc, card = element('article', 'card'); card.dataset.id = doc.id;
    const heading = element('div', 'card-heading');
    heading.append(element('h2', '', `${doc.antonyms.left} — ${doc.antonyms.right}`));
    heading.append(element('span', `state${axis.dirty ? ' dirty' : ''}`, axis.dirty ? 'Unsaved changes' : 'Saved'));
    heading.append(button('Save', () => operation(async () => { await save(axis); message('Gradient saved.'); }), 'save'));
    heading.append(button('Suggest Concepts', () => operation(async () => {
      message('Looking up lexical candidates…');
      axis.candidates = await api('/api/suggest', {endpoints: doc.endpoints});
      axis.suggested = true; render(); message('Candidates are unplaced. Select one, then click its position on the axis.');
    }), 'suggest'));
    card.append(heading, element('p', 'sense', `${doc.endpoints.left.synset} ↔ ${doc.endpoints.right.synset}`));
    card.append(element('p', 'axis-help', 'Click the axis to add a concept. Drag a label to move it; click it to edit, set a precise position, or delete.'));
    const track = element('div', 'axis'); track.tabIndex = 0;
    track.setAttribute('role', 'group'); track.setAttribute('aria-label', `${doc.antonyms.left} to ${doc.antonyms.right} axis; press Enter to add a concept`);
    track.append(element('div', 'track'), element('span', 'endpoint left', doc.antonyms.left), element('span', 'endpoint right', doc.antonyms.right));
    track.addEventListener('click', event => {
      if (event.target.closest('.concept')) return;
      const pos = positionAt(event, track);
      if (axis.selected) addCandidate(axis, axis.selected, pos); else openConcept(axis, null, pos);
    });
    track.addEventListener('keydown', event => {
      if (event.target === track && event.key === 'Enter') {
        event.preventDefault();
        if (axis.selected) addCandidate(axis, axis.selected, 0.5); else openConcept(axis, null, 0.5);
      }
    });
    track.addEventListener('dragover', event => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; });
    track.addEventListener('drop', event => {
      event.preventDefault();
      try {
        const data = JSON.parse(event.dataTransfer.getData('application/json'));
        if (data.axis === doc.id && axis.candidates[data.index]) addCandidate(axis, axis.candidates[data.index], positionAt(event, track));
      } catch (_) { /* Ignore non-candidate drops. */ }
    });
    doc.gradient.forEach((item, index) => {
      const node = button(item.concept, () => openConcept(axis, index), `concept ${item.source}`);
      node.dataset.position = item.position;
      node.title = `${item.concept} · ${item.position.toFixed(3)} · ${item.source}`;
      let start = null, moved = false;
      node.addEventListener('pointerdown', event => {
        if (event.button !== 0) return;
        start = event.clientX; moved = false; node.setPointerCapture(event.pointerId);
      });
      node.addEventListener('pointermove', event => {
        if (start === null) return;
        if (Math.abs(event.clientX - start) > 3) moved = true;
        if (moved) { node.dataset.position = positionAt(event, track); layoutLabels(track); }
      });
      node.addEventListener('pointerup', event => {
        if (start === null) return;
        start = null;
        if (moved) { item.position = positionAt(event, track); axis.dirty = true; setTimeout(render, 0); }
      });
      node.addEventListener('click', event => { if (moved) { event.stopImmediatePropagation(); event.preventDefault(); } }, true);
      node.addEventListener('pointercancel', () => { start = null; render(); });
      track.append(node);
    });
    card.append(track);
    const panel = element('section', 'suggestions');
    panel.append(element('p', 'suggestion-note', 'WordNet candidates are lexical neighbors, not verified intermediate meanings. All positions are your judgment.'));
    if (axis.suggested && !axis.candidates.length) panel.append(element('p', '', 'No suitable candidates found for these senses.'));
    const candidates = element('div', 'candidates');
    axis.candidates.forEach((candidate, index) => {
      const accepted = doc.gradient.some(item => item.source === 'wordnet' && item.concept === candidate.concept);
      const node = button(candidate.concept, () => { axis.selected = axis.selected === candidate ? null : candidate; render(); },
        `candidate${axis.selected === candidate ? ' selected' : ''}${accepted ? ' accepted' : ''}`);
      node.setAttribute('aria-pressed', String(axis.selected === candidate));
      node.append(element('small', '', [...new Set(candidate.provenance.map(p => `${p.endpoint}: ${p.relation}`))].join(', ') + (accepted ? ' · accepted' : ' · unplaced')));
      node.title = candidate.provenance.map(p => `${p.from_synset} → ${p.synset} (${p.lemma_key})`).join('\n');
      node.draggable = true;
      node.addEventListener('dragstart', event => {
        event.dataTransfer.setData('application/json', JSON.stringify({axis: doc.id, index})); event.dataTransfer.effectAllowed = 'copy';
      });
      candidates.append(node);
    });
    panel.append(candidates); card.append(panel); root.append(card);
    layoutLabels(track);
  }
}
window.addEventListener('resize', () => document.querySelectorAll('.axis').forEach(layoutLabels));
async function save(axis) { axis.doc = await api('/api/save', axis.doc); axis.dirty = false; render(); }
async function resample() {
  const count = Number($('#count').value);
  if (!Number.isInteger(count) || count < 1 || count > 50) throw new Error('Choose between 1 and 50 pairs.');
  if (axes.some(axis => axis.dirty) && !confirm('Discard unsaved changes and resample?')) return;
  message('Sampling WordNet antonyms… The first load may take a few seconds.');
  const docs = await api('/api/sample', {count, exclude: axes.map(axis => axis.doc.id)});
  axes = docs.map(wrap); showView('editor'); render();
  message(`Sampled ${docs.length} pairs.${docs.length < count ? ' Fewer distinct pairs were available than requested.' : ''}`);
}
function showView(view) {
  $('#editor').hidden = view !== 'editor'; $('#saved').hidden = view !== 'saved';
  $('#editor-tab').setAttribute('aria-pressed', String(view === 'editor'));
  $('#saved-tab').setAttribute('aria-pressed', String(view === 'saved'));
  if (view === 'editor') requestAnimationFrame(() => document.querySelectorAll('.axis').forEach(layoutLabels));
}
async function listSaved() {
  const docs = await api(`/api/saved?q=${encodeURIComponent($('#search').value)}`);
  const root = $('#saved-list'); root.replaceChildren();
  if (!docs.length) root.append(element('p', '', 'No saved gradients match.'));
  for (const doc of docs) {
    const row = element('div', 'saved-row');
    row.append(element('p', '', `${doc.antonyms.left} — ${doc.antonyms.right} · ${doc.gradient.length} concepts · ${doc.modified_at}`));
    row.append(button('Load', () => operation(async () => {
      const existing = axes.findIndex(axis => axis.doc.id === doc.id);
      if (existing >= 0 && axes[existing].dirty && !confirm('Discard unsaved edits to this gradient and reload the saved version?')) return;
      const loaded = wrap(await api(`/api/saved/${doc.id}`));
      if (existing >= 0) axes[existing] = loaded; else axes.push(loaded);
      showView('editor'); render(); message('Loaded saved gradient. Other axes are preserved.');
    })));
    root.append(row);
  }
}
$('#resample').onclick = () => operation(resample);
$('#save-all').onclick = () => operation(async () => {
  let saved = 0;
  for (const axis of axes) if (axis.dirty) { await save(axis); saved++; message(`Saved ${saved} gradients…`); }
  message(`Saved ${saved} gradients.`);
});
$('#editor-tab').onclick = () => showView('editor');
$('#saved-tab').onclick = () => operation(async () => { showView('saved'); await listSaved(); });
$('#search-button').onclick = () => operation(listSaved);
$('#search').addEventListener('keydown', event => { if (event.key === 'Enter') operation(listSaved); });
window.addEventListener('beforeunload', event => {
  if (axes.some(axis => axis.dirty)) { event.preventDefault(); event.returnValue = ''; }
});
render(); operation(resample);
