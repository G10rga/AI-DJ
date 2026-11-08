'use strict';
const $ = id => document.getElementById(id);
const timeFields = ['mix_start','mix_end','outgoing_source_in','outgoing_source_out','incoming_source_in','incoming_source_out'];
const valueFields = [...timeFields,'outgoing_hash','incoming_hash','recipe','overlap_bars','vocal_behavior','energy_behavior'];
const media = [$('reference-audio'),$('outgoing-audio'),$('incoming-audio')];
let references = [], batch = null, selected = 0, dirty = false, saving = false, loading = false, conflict = false, playEnd = null;
$('queue-panel').open = !window.matchMedia('(max-width:760px)').matches;
function message(text = '', error = false) { $('message').textContent = text; $('message').classList.toggle('error', error); }
function formatTime(seconds) {
  if (seconds === null || seconds === undefined) return '';
  const millis = Math.round(seconds*1000), minutes = Math.floor(millis/60000);
  return `${minutes}:${((millis%60000)/1000).toFixed(3).padStart(6,'0')}`.replace(/\.?0+$/,'').replace(/:$/ ,':00');
}
function parseTime(value) {
  value = value.trim();
  if (!value) return null;
  if (!/^\d+(?::\d{1,2}){0,2}(?:\.\d+)?$/.test(value)) throw Error('Enter times as m:ss or seconds.');
  const parts = value.split(':').map(Number);
  if (parts.length > 1 && parts.slice(1).some(x => x >= 60)) throw Error('Seconds and minutes after a colon must be below 60.');
  const result = parts.reduce((a,b) => a*60+b, 0);
  if (!Number.isFinite(result)) throw Error('Enter a finite time.');
  return result;
}
async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) { const error = Error(data.detail || 'The request failed. Try again.'); error.status = response.status; throw error; }
  return data;
}
function pauseAll() { media.forEach(audio => audio.pause()); playEnd = null; }
media.forEach(audio => {
  audio.addEventListener('play', () => { if(audio!==$('reference-audio')) playEnd=null; media.forEach(other => { if (other !== audio) other.pause(); }); });
  audio.addEventListener('error', () => message('Audio is unavailable or changed. Check the source file and reload.', true));
});
$('reference-audio').addEventListener('timeupdate', () => {
  if (playEnd !== null && $('reference-audio').currentTime >= playEnd) { $('reference-audio').pause(); playEnd = null; }
});
async function listen() {
  try {
    let start = parseTime($('mix_start').value), end = parseTime($('mix_end').value);
    const focus = batch.transitions[selected].focus_seconds;
    start = Math.max(0, (start ?? focus-20)-8);
    end = Math.min(batch.duration_seconds, (end ?? focus+20)+8);
    if (end < start) throw Error('Recording exit must follow entry. Correct the times before playing this range.');
    const audio = $('reference-audio');
    pauseAll();
    audio.currentTime = start;
    playEnd = end;
    await audio.play();
  } catch (error) { message(error.message, true); }
}
function editState() {
  $('save-review').disabled = !dirty || saving || loading || conflict;
  $('discard-review').disabled = !dirty || saving || loading;
  const review=batch?.transitions[selected]?.review;
  $('save-review').textContent = $('listened').checked && $('learn').value ? 'Save review' : 'Save timing';
  $('edit-state').textContent = saving ? 'Saving changes…' : loading ? 'Loading saved reviews…' : conflict ? 'Reload required before saving' : dirty ? 'Unsaved edits — timing can be saved now' : review?.reviewed ? 'Review saved' : review ? 'Timing saved · listening review pending' : 'No listening review saved';
  $('edit-state').classList.toggle('dirty-state', dirty);
}
function changed(event) {
  if (saving || loading || !batch) return;
  dirty = true;
  if (event?.target?.id !== 'listened') $('listened').checked = false;
  editState();
}
function setLocked(value) {
  saving = value;
  const locked=saving||loading;
  document.querySelectorAll('button,input,select').forEach(control => { control.disabled = locked; });
  if (!locked && batch) {
    $('next-transition').disabled = selected === batch.transitions.length-1;
    updateSource('outgoing'); updateSource('incoming');
  }
  editState();
}
function canLeave() { return !dirty || window.confirm('Discard unsaved changes to this transition?'); }
function stateOf(transition) { return transition.review?.reviewed ? transition.review.learn ? 'included' : 'excluded' : 'pending'; }
function renderQueue() {
  const list = $('transition-list'); list.replaceChildren();
  const filter = $('queue-filter').value;
  let visible = 0;
  batch.transitions.forEach((transition, index) => {
    const state = stateOf(transition);
    if (filter !== 'all' && state !== filter) return;
    const button = document.createElement('button'); button.type = 'button';
    button.setAttribute('aria-current', String(index === selected));
    button.textContent = `${index+1}. ${transition.title}`;
    const small = document.createElement('small'); small.dataset.state = state;
    small.textContent = state === 'included' ? 'Included for learning' : state === 'excluded' ? 'Excluded from learning' : transition.review ? 'Timing saved · needs listening review' : 'Needs listening review';
    button.append(small); button.addEventListener('click', () => selectJoin(index)); list.append(button); visible++;
  });
  if (!visible) { const empty = document.createElement('p'); empty.className = 'hint'; empty.textContent = 'No transitions match this filter.'; list.append(empty); }
  $('review-count').textContent = `${batch.counts.reviewed} of ${batch.counts.total} reviewed · ${batch.counts.included} included for learning`;
  if(batch.counts.draft_saved) $('review-count').textContent+=` · ${batch.counts.draft_saved} timing drafts saved`;
  $('export-reviews').hidden = !batch.counts.included;
  $('export-reviews').href = `/api/v1/reference-drafts/${batch.id}/training-examples`;
}
function updateSource(prefix) {
  if (!batch) return;
  const track = batch.tracks[selected+(prefix === 'incoming' ? 1 : 0)];
  const source = track.sources.find(s => s.content_hash === $(prefix+'_hash').value);
  const audio = $(prefix+'-audio');
  if (source) {
    if (audio.getAttribute('src') !== source.audio_url) { audio.pause(); audio.src = source.audio_url; }
  } else { audio.pause(); audio.removeAttribute('src'); audio.load(); }
  audio.hidden = !source;
  document.querySelectorAll(`[data-mark^="${prefix}"]`).forEach(button => { button.disabled = saving || loading || !source; });
}
function cueSource(prefix) {
  const audio=$(prefix+'-audio'), url=audio.getAttribute('src');
  const time=parseTime($(prefix+'_source_in').value);
  if(!url || time===null) return;
  const seek=()=>{ if(audio.getAttribute('src')===url) audio.currentTime=Math.min(time,Number.isFinite(audio.duration)?audio.duration:time); };
  if(audio.readyState>=1) seek(); else audio.addEventListener('loadedmetadata',seek,{once:true});
}
function drawEvidence() {
  const svg = $('match-chart'); svg.replaceChildren();
  const transition = batch.transitions[selected];
  const focus = transition.focus_seconds, draft = transition.draft;
  const from = Math.max(0, (draft.mix_start ?? focus-20)-16), to = Math.min(batch.duration_seconds, (draft.mix_end ?? focus+20)+16);
  const ns = 'http://www.w3.org/2000/svg';
  function add(name, attrs, text) { const node = document.createElementNS(ns,name); Object.entries(attrs).forEach(([k,v])=>node.setAttribute(k,v)); if(text!==undefined) node.textContent=text; svg.append(node); }
  [0,.5,1].forEach(value => { const y = 126-value*106; add('line',{x1:36,x2:780,y1:y,y2:y,stroke:'#343434'}); add('text',{x:4,y:y+4}, String(value)); });
  [from,(from+to)/2,to].forEach((time,i)=>add('text',{x:36+i*372,y:151,'text-anchor':i===0?'start':i===2?'end':'middle'},formatTime(time)));
  ['#b4b4b4','#c6f24e'].forEach((stroke,index) => {
    const curve = batch.tracks[selected+index].presence?.curve || [];
    const points = curve.filter(row=>row.seconds>=from && row.seconds<=to);
    if (!points.length) return;
    const path = points.map((row,i)=>`${i?'L':'M'}${36+(row.seconds-from)/(to-from)*744},${126-Math.max(0,row.similarity)*106}`).join(' ');
    add('path',{d:path,stroke,fill:'none','stroke-width':2});
  });
  $('evidence-caption').textContent = 'Similarity is uncalibrated. Draft brackets stay separate from saved listening reviews.';
}
function populate() {
  const transition = batch.transitions[selected], values = transition.review || transition.draft;
  pauseAll(); conflict = false; dirty = false;
  $('pair-title').textContent = transition.title;
  $('join-position').textContent = `${selected+1} of ${batch.transitions.length}`;
  $('draft-description').textContent = transition.review?.reviewed ? 'Your saved listening review. Edit and save another revision to correct it.' : transition.review ? 'Your timing corrections are saved. Complete the listening review when ready.' : transition.reason;
  $('review-revision').textContent = transition.revision ? `Saved revision ${transition.revision}` : 'Unreviewed draft';
  for (const prefix of ['outgoing','incoming']) {
    const track = batch.tracks[selected+(prefix==='incoming'?1:0)], select = $(prefix+'_hash');
    $(prefix+'-title').textContent = track.title; select.replaceChildren();
    select.add(new Option('Choose original file', ''));
    track.sources.forEach(source=>select.add(new Option(source.name, source.content_hash)));
  }
  valueFields.forEach(id=>{ $(id).value = timeFields.includes(id) ? formatTime(values[id]) : values[id] ?? ''; });
  $('learn').value = transition.review?.learn === true ? 'include' : transition.review?.learn === false ? 'exclude' : '';
  $('review-note').value = values.note || '';
  $('listened').checked = transition.review?.reviewed === true;
  updateSource('outgoing'); updateSource('incoming');
  cueSource('outgoing'); cueSource('incoming');
  $('next-transition').disabled = selected === batch.transitions.length-1;
  drawEvidence(); renderQueue(); editState();
}
function selectJoin(index) {
  if (saving || loading || !canLeave()) return;
  selected = index; message(); populate();
  if(window.matchMedia('(max-width:760px)').matches) $('queue-panel').open=false;
}
async function loadReference(id, preservePosition=false) {
  if (saving || loading || !canLeave()) { if(batch) $('reference-select').value=batch.reference_id; return; }
  const reference = references.find(r=>r.id===id);
  loading=true; setLocked(false);
  try {
    pauseAll(); message('Loading reference transitions…');
    $('review-workspace').hidden = true;
    if (!reference?.draft_id) { batch=null; dirty=false; $('reference-empty').hidden=false; message('Transitions have not been prepared for this recording yet.'); return; }
    const loaded = await request(`/api/v1/reference-drafts/${reference.draft_id}`);
    batch = loaded; selected = preservePosition ? Math.min(selected,batch.transitions.length-1) : 0;
    $('reference-empty').hidden=true; $('review-workspace').hidden=false;
    $('reference-select').value=id;
    if($('reference-audio').getAttribute('src')!==batch.audio_url) $('reference-audio').src=batch.audio_url;
    $('reference-summary').textContent=`${batch.title} · ${formatTime(batch.duration_seconds)} recording · ${batch.transitions.length} handoffs`;
    populate(); message();
  } catch(error) { $('review-workspace').hidden=!batch; if(batch) $('reference-select').value=batch.reference_id; message(`${error.message} Your unsaved edits have been kept.`,true); }
  finally { loading=false; setLocked(false); }
}
$('reference-select').addEventListener('change',()=>loadReference($('reference-select').value));
$('queue-filter').addEventListener('change',()=>{ if(batch) renderQueue(); });
$('reload-reference').addEventListener('click',()=>{ if(batch) loadReference(batch.reference_id,true); else initialize(); });
$('next-transition').addEventListener('click',()=>selectJoin(Math.min(selected+1,batch.transitions.length-1)));
$('discard-review').addEventListener('click',()=>{ if(!saving && canLeave()) { message(); populate(); } });
$('listen-handoff').addEventListener('click',listen);
$('mark-entry').addEventListener('click',()=>{ $('mix_start').value=formatTime($('reference-audio').currentTime); changed(); });
$('mark-exit').addEventListener('click',()=>{ $('mix_end').value=formatTime($('reference-audio').currentTime); changed(); });
document.querySelectorAll('[data-mark]').forEach(button=>button.addEventListener('click',()=>{
  const prefix=button.dataset.mark.startsWith('outgoing')?'outgoing':'incoming';
  $(button.dataset.mark).value=formatTime($(prefix+'-audio').currentTime); changed();
}));
['outgoing','incoming'].forEach(prefix=>$(prefix+'_hash').addEventListener('change',()=>{
  $(prefix+'_source_in').value=''; $(prefix+'_source_out').value=''; updateSource(prefix); changed();
}));
$('estimate-cues').addEventListener('click',()=>{
  try {
    const start=parseTime($('mix_start').value), end=parseTime($('mix_end').value);
    if(start===null || end===null || end<start) throw Error('Set recording entry and exit first.');
    let missing=false;
    ['outgoing','incoming'].forEach((prefix,index)=>{
      const track=batch.tracks[selected+index], source=track.sources.find(s=>s.content_hash===$(prefix+'_hash').value);
      const mapping=source?.content_hash===track.source_hash?track.mapping:null;
      ['in','out'].forEach((suffix,i)=>{
        const value=mapping?([start,end][i]-mapping.offset_seconds)/mapping.scale:null;
        const valid=value!==null && value>=0 && value<=source.duration_seconds;
        $(prefix+'_source_'+suffix).value=valid?formatTime(value):''; if(!valid) missing=true;
      });
    }); changed(); message(missing?'Some source cues are unknown. Locate them in the original players.':'Source estimates updated. Check them against the original songs.');
  } catch(error) { message(error.message,true); }
});
$('review-form').addEventListener('input',changed);
$('review-form').addEventListener('change',changed);
$('review-form').addEventListener('submit',async event=>{
  event.preventDefault(); if(saving || loading || !dirty || conflict) return;
  try {
    const review={reviewed:$('listened').checked && Boolean($('learn').value),
      learn:$('learn').value ? $('learn').value==='include' : null,note:$('review-note').value};
    valueFields.forEach(id=>{ review[id]=timeFields.includes(id)?parseTime($(id).value):id==='overlap_bars'?($(id).value===''?null:Number($(id).value)):$(id).value||null; });
    const incomplete=review.learn === true && ([...timeFields,'outgoing_hash','incoming_hash'].some(id=>review[id]===null));
    if(incomplete) review.reviewed=false;
    const revision=batch.transitions[selected].revision;
    setLocked(true); message('Saving changes…');
    batch=await request(`/api/v1/reference-drafts/${batch.id}/transitions/${selected}/reviews`,{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:revision,review})});
    populate(); message(review.reviewed ? 'Review saved. Only included, reviewed transitions are exported for training.' :
      incomplete ? 'Timing saved. Complete the original-song cues and confirm listening before including this transition in training.' :
      'Timing saved. You can finish the listening review later; this timing draft is not used for training.');
  } catch(error) { if(error.status===409) conflict=true; message(error.message,true); }
  finally { setLocked(false); }
});
window.addEventListener('beforeunload',event=>{ if(dirty){ event.preventDefault(); event.returnValue=''; } });
async function initialize() {
  try {
    message('Loading reference recordings…');
    references=(await request('/api/v1/references')).references;
    const select=$('reference-select'); select.replaceChildren();
    references.forEach(reference=>select.add(new Option(reference.title,reference.id)));
    select.disabled=!references.length;
    if(!references.length){ $('reference-empty').hidden=false; $('review-count').textContent='No references imported'; message(); return; }
    await loadReference(references[0].id);
  } catch(error) { message(`${error.message} Use Reload saved reviews to try again.`,true); }
}
initialize();
