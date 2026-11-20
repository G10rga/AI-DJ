const $ = id => document.getElementById(id);
const base = '/api/v1/mix-projects';
let library = [], project = null, tracks = [], open = null, draft, drag;
let context, player, loaded, pendingAudio, playing = false;
let undo = [], redo = [], initialized = false;
let waveCenters = {};
const limits = {gain:[0,1.5,.01], low:[-24,12,.1], mid:[-24,12,.1], high:[-24,12,.1], hp:[20,18000,1], lp:[40,20000,1]};
const blank = side => ({gain:[[0,side==='a'?1:0],[1,side==='a'?0:1]],low:[[0,0],[1,0]],mid:[[0,0],[1,0]],high:[[0,0],[1,0]],hp:[[0,20],[1,20]],lp:[[0,20000],[1,20000]]});
function node(tag, content, className) {
  const el = document.createElement(tag);
  if (content !== undefined) el.textContent = content;
  if (className) el.className = className;
  return el;
}
function button(label, fn, accessible = label) {
  const el = node('button', label);
  el.type = 'button'; el.setAttribute('aria-label', accessible);
  el.onclick = () => run(fn); return el;
}
async function api(url, payload, method = 'POST', headers = {}) {
  const response = await fetch(url, payload === undefined ? {} : {
    method, headers: {'Content-Type':'application/json', ...headers},
    body: payload instanceof File ? payload : JSON.stringify(payload)
  });
  if (!response.ok) throw Error((await response.json().catch(() => ({}))).detail || 'Request failed');
  return response;
}
const read = async (url, payload, method) => (await api(url,payload,method)).json();
function status(message, error = false) {
  $('status').textContent = message;
  $('status').classList.toggle('error',error);
}
async function run(fn) {
  try { await fn(); } catch(error) { status(error.message,true); }
}
const path = () => base + '/' + project.id;
const command = (action, payload = {}) => read(path()+'/'+action,{expected_revision:project.revision,...payload});
const current = () => project?.jobs.find(j => j.result?.project_revision === project.revision && j.result?.status !== 'reorder_proposal')?.result;
const proposal = () => project?.jobs.find(j => j.result?.project_revision === project.revision && j.result?.status === 'reorder_proposal')?.result;
const active = () => project?.jobs.find(j => ['queued','running'].includes(j.status));
const preview = () => project && [...project.jobs.map(j=>j.result), project.playable].find(r=>
  r?.previews?.[open] && r.evidence[open]?.reference.source_hash===tracks[open]?.content_hash &&
  r.evidence[open+1]?.reference.source_hash===tracks[open+1]?.content_hash);
async function index() {
  const data = await read(base); library = data.library;
  $('projects').replaceChildren(new Option('New playlist',''), ...data.projects.map(p=>new Option(p.name,p.id,p.id===project?.id,p.id===project?.id)));
  showLibrary();
}
async function load(id) {
  pause(); loaded = null; open = null; draft = null; undo = []; redo = [];
  project = id ? await read(base+'/'+id) : null;
  $('projects').value=id || '';
  tracks = project?.sources.slice() || [];
  $('name').value = project?.name || 'Untitled playlist';
  history.replaceState(null,'',id ? '/playlist?project='+encodeURIComponent(id):'/playlist');
  show();
}
function showLibrary() {
  const filter = $('search').value.toLowerCase();
  const matches = library.filter(t=>t.name.toLowerCase().includes(filter));
  $('library').replaceChildren(...matches.map(t=>{
    const item = node('li');
    item.append(button('+  '+t.name,()=>changeTracks([...tracks,t]),'Add '+t.name)); return item;
  }));
  if (!matches.length) $('library').append(node('li',filter ? 'No matching songs' : 'Upload audio to start', 'meta'));
}
async function changeTracks(next) {
  if (next.length > 50) throw Error('Playlist limit is 50 songs');
  if (!next.length && project) throw Error('A saved playlist needs at least one song');
  if (project) {
    project = await read(path(),{expected_revision:project.revision,track_ids:next.map(t=>t.id)},'PATCH');
  }
  tracks = next;
  open = null; draft = null; undo = []; redo = []; pause(); show();
}
async function ensureProject() {
  const name = $('name').value.trim();
  if (!project) {
    project = await read(base,{name,track_ids:tracks.map(t=>t.id)});
    history.replaceState(null,'','/playlist?project='+project.id);
    await index();
  } else if (name !== project.name) {
    project = await read(path(),{expected_revision:project.revision,name},'PATCH');
    await index();
  }
}
async function queue(action) {
  await ensureProject();
  await command(action);
  await refresh();
}
function move(from,to) {
  if (from===to || to<0 || to>=tracks.length) return;
  const next=tracks.slice(); next.splice(to,0,next.splice(from,1)[0]); return changeTracks(next);
}
function show() {
  const report = current(), job = active(), result = project?.playable, suggestion = proposal();
  $('count').textContent = tracks.length+' '+(tracks.length===1?'song':'songs');
  $('mix').disabled = !tracks.length || !!job;
  $('reorder').disabled = tracks.length<2 || !!job;
  $('render').disabled = !!job || report?.status!=='validated' && report?.status!=='preview_ready';
  $('progress').hidden = $('cancel').hidden = !job;
  $('progress').value = job?.progress || 0;
  if (job) status(job.stage);
  else if (report?.reason) status(report.reason);
  else if (project?.jobs[0]?.error) status(project.jobs[0].error,true);
  else if (report) status('Revision '+project.revision+' prepared');
  else status('');
  $('suggestion').hidden = !suggestion;
  if (suggestion) $('suggestion').replaceChildren(node('p','Suggested order: '+suggestion.order.map(i=>tracks[i]?.name).join(' → ')),
    button('Apply order',()=>changeTracks(suggestion.order.map(i=>tracks[i]))));
  const trackList = [];
  tracks.forEach((t,i)=>{
    const e = report?.evidence?.[i] || suggestion?.evidence?.[i];
    const item = node('li',undefined,'track'); item.draggable=true;
    item.ondragstart=e=>{drag=i;e.dataTransfer.setData('text/plain',String(i));};
    item.ondragover=e=>e.preventDefault();
    item.ondrop=e=>{e.preventDefault(); if(Number.isInteger(drag)) run(()=>move(drag,i));drag=null;};
    item.ondragend=()=>{drag=null;};
    const title=node('div'); title.append(node('strong',t.name),node('span',e?.bpm?e.bpm.toFixed(1)+' BPM · '+e.key:'Analysis pending','meta'));
    const actions=node('div',undefined,'row');
    const up=button('↑',()=>move(i,i-1),'Move '+t.name+' up'); up.disabled=i===0;
    const down=button('↓',()=>move(i,i+1),'Move '+t.name+' down'); down.disabled=i===tracks.length-1;
    const remove=button('×',()=>changeTracks(tracks.filter((_,j)=>i!==j)),'Remove '+t.name); remove.disabled=!!project&&tracks.length===1;
    actions.append(up,down,remove); item.append(node('span',String(i+1),'number'),title,actions); trackList.push(item);
    if(i===tracks.length-1)return;
    const join=report?.plan?.joins?.[i], audit=report?.plan?.validation?.joins?.[i];
    const state = audit?.status==='aligned'?'Ready':report?.status==='needs_review'?'Needs correction':job?'Preparing':'Awaiting Mix';
    const handoff=node('li',undefined,'handoff');
    const edit=button('Transition '+(i+1)+' · '+state+(join?' · '+join.bars+' bars':''),()=>selectJoin(i));
    edit.disabled=!project; edit.setAttribute('aria-expanded',String(open===i));
    handoff.append(edit);trackList.push(handoff);
  });
  $('tracks').replaceChildren(...trackList);
  if(!tracks.length) $('tracks').append(node('li','Choose songs from your library or upload local audio.', 'meta'));
  $('export-note').textContent = result ? (result.project_revision===project.revision?'Ready to play and download.':'Playing a previous export. Mix and render the current revision to replace it.') :
    'The full set can be rendered once all transition timing checks pass.';
  const audio=$('full-audio'); audio.hidden=!result?.audio_url;
  if (result?.audio_url && audio.getAttribute('src')!==result.audio_url) audio.src=result.audio_url;
  if (!result?.audio_url && audio.hasAttribute('src')) { audio.removeAttribute('src');audio.load(); }
  $('downloads').replaceChildren(...(result?.audio_url?[['MP3',result.audio_url],['WAV',result.wav_url]].map(([name,url])=>{
    const a=node('a','Download '+name);a.href=url+'?download=true';return a;
  }):[]));
  showEditor();
}
function selectJoin(i) {
  if(open!==i){pause();loaded=null;open=i;draft=null;waveCenters={};$('seek').value=0;}
  show();$('transition').scrollIntoView({block:'nearest'});
}
function showEditor() {
  $('transition').hidden=open===null || !tracks[open+1];
  if($('transition').hidden)return;
  const report=current(), old=preview(), join=report?.plan?.joins?.[open] || old?.plan?.joins[open];
  if(!draft) {
    const edit=project.transitions[String(open)] || {};
    draft={...edit,automationEdited:!!edit.automation};
    $('a-cue').value=edit.a_cue ?? join?.a_cue?.toFixed(3) ?? '';
    $('b-cue').value=edit.b_cue ?? join?.b_cue?.toFixed(3) ?? '';
    $('bars').value=edit.bars ?? join?.bars ?? 8;
    $('preset').value=edit.preset ?? join?.preset ?? 'blend';
    $('vocal').value=edit.vocal_ending ?? '';
    draft.automation=structuredClone(edit.automation || join?.automation || {a:blank('a'),b:blank('b')});
    showPoints(); gridFields();
  }
  $('join-title').textContent='Transition '+(open+1);
  $('a-name').textContent=tracks[open].name; $('b-name').textContent=tracks[open+1].name;
  $('join-note').textContent=[old && old.project_revision!==project.revision?'Previous preview available while this revision prepares.':'',...(join?.warnings || [])].filter(Boolean).join(' ');
  editStatus();
  $('audition').disabled=!old; $('pause').disabled=!playing;
  $('seek').disabled=!old; $('seek').max=old?.previews[open].duration || 0;
  $('undo').disabled=!undo.length; $('redo').disabled=!redo.length;
  $('diagnostics').textContent=JSON.stringify({scores:join?.scores,attempts:report?.attempts?.filter(a=>a.join===open)},null,2);
  for(const [i,side] of ['a','b'].entries())drawWave(side,(report || old)?.evidence?.[open+i]);
  drawCurve();
}
function surface(canvas) {
  const ratio=devicePixelRatio || 1;
  canvas.width=Math.round(canvas.clientWidth*ratio);canvas.height=Math.round(canvas.clientHeight*ratio);
  const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);
  return [ctx,canvas.clientWidth,canvas.clientHeight];
}
function waveBounds(side,e) {
  const zoom=Number($('wave-zoom').value), duration=Math.min(zoom || e.duration,e.duration);
  const cueTime=Number($(side+'-cue').value);
  const center=waveCenters[side] ?? cueTime;
  const start=Math.max(0,Math.min(e.duration-duration,center-duration/2));
  return [start,start+duration];
}
function drawWave(side,e) {
  const [ctx,w,h]=surface($(side+'-wave'));
  if(!e?.duration)return;
  const [start,end]=waveBounds(side,e);
  const x=t=>w*(t-start)/(end-start);
  ctx.fillStyle='#454545';
  const level=Math.max(.05,...e.waveform.map(r=>r.rms));
  for(const r of e.waveform){
    if(r.end<start||r.start>end)continue;
    const y=Math.min(h*.41,r.rms/level*h*.41);
    ctx.fillRect(x(r.start),h*.44-y,Math.max(1,x(r.end)-x(r.start)-1),2*y);
  }
  for(const [list,height,color] of [[e.beats,7,'#555'],[e.downbeats,15,'#b4b4b4']]){
    ctx.fillStyle=color;for(const t of list)if(t>=start&&t<=end)ctx.fillRect(x(t),h-height,1,height);
  }
  const field=$(side+'-cue');
  if(field.value!==''){ctx.fillStyle='#c6f24e';ctx.fillRect(x(Number(field.value)),0,2,h);}
}
function drawCurve() {
  if(!draft)return;
  const [ctx,w,h]=surface($('curve'));
  const k=$('curve-control').value, points=draft.automation[$('curve-side').value][k];
  const [min,max]=limits[k];
  ctx.strokeStyle='#c6f24e';ctx.lineWidth=2;ctx.beginPath();
  points.forEach(([x,y],i)=>ctx[i?'lineTo':'moveTo'](4+x*(w-8),4+(max-y)/(max-min)*(h-8)));ctx.stroke();
  ctx.fillStyle='#c6f24e';
  points.forEach(([x,y])=>{ctx.beginPath();ctx.arc(4+x*(w-8),4+(max-y)/(max-min)*(h-8),3,0,2*Math.PI);ctx.fill();});
}
function showPoints() {
  const side=$('curve-side').value,k=$('curve-control').value;
  const points=draft.automation[side][k], [min,max,step]=limits[k];
  $('points').replaceChildren(...points.map(([x,y],i)=>{
    const group=node('div',undefined,'row');
    for(const [j,initial,low,high,increment,title] of [[0,x,0,1,.001,'Position'],[1,y,min,max,step,'Value']]){
      const label=node('label',title+' '+(i+1)), input=node('input');
      Object.assign(input,{type:'number',value:initial,min:low,max:high,step:increment});
      input.disabled=j===0&&(i===0||i===points.length-1);
      input.oninput=()=>{
        const n=input.valueAsNumber;
        if(!Number.isFinite(n)||n<low||n>high||j===0&&(n<=points[i-1][0]||n>=points[i+1][0]))return;
        points[i][j]=n;draft.automationEdited=draft.dirty=true;drawCurve();liveCurves();
      };
      input.onchange=()=>input.value=points[i][j]; label.append(input);group.append(label);
    }
    if(i>0&&i<points.length-1)group.append(button('Remove',()=>{points.splice(i,1);draft.automationEdited=draft.dirty=true;showPoints();liveCurves();}));
    return group;
  }));
  drawCurve();
}
function gridFields() {
  const i=open+Number($('grid-side').value), track=tracks[i];
  if(!track)return;
  const e=(current() || preview())?.evidence?.[i];
  const g=project.grids[track.content_hash];
  $('bpm').value=g?.bpm ?? e?.bpm?.toFixed(3) ?? '';
  $('downbeat').value=g?.first_downbeat ?? e?.downbeats?.[0]?.toFixed(3) ?? '';
  $('phase').value=g?.bar_phase ?? 0;
  $('local-tempo').checked=g?.use_detected_intervals ?? false;
  $('anchors').value=(g?.anchors || []).map(p=>p.join(':')).join(', ');
  const audio=$('original-audio'), source=path()+'/source/'+i+'?revision='+project.revision;
  if(audio.getAttribute('src')!==source)audio.setAttribute('src',source);
}
function editStatus() {
  $('edit-note').textContent=draft?.dirty?'Unsaved changes. Save and prepare to use them in the set.':'';
}
async function edit(action,payload) {
  const revision=project.revision;
  project=await command(action,payload);undo.push(revision);redo=[];
  draft=null;await queue('preview');
}
async function restore(from,to) {
  const revision=from.at(-1), before=project.revision;
  project=await command('restore',{revision});
  from.pop();to.push(before);draft=null;await queue('preview');
}
function liveCurves() {
  editStatus();
  const r=preview(), p=r?.previews[open];
  if(!draft?.automationEdited||!p||loaded!==p.tracks[0].url)return;
  player.port.postMessage({type:'automation',segments:p.tracks.map((t,i)=>t.segments.map(s=>
    Math.abs(s.start-p.overlap_start)<.0001?{...s,curves:draft.automation[i?'b':'a']}:s))});
}
async function audition() {
  const p=preview()?.previews[open];
  if(!p)return;
  $('full-audio').pause();
  $('original-audio').pause();
  context ||= new AudioContext({sampleRate:44100});
  await context.resume();
  if(!player) {
    await context.audioWorklet.addModule('/assets/playlist-worklet.mjs');
    player=new AudioWorkletNode(context,'playlist-player',{numberOfInputs:0,numberOfOutputs:1,outputChannelCount:[2]});
    player.onprocessorerror=()=>{pause();loaded=null;player.disconnect();player=null;status('Preview audio stopped. Press Play around transition to retry.',true);};
    player.connect(context.destination);
    player.port.onmessage=({data})=>{
      if(data.ended){playing=false;$('pause').disabled=true;}
      if(data.seconds!==undefined)$('seek').value=data.seconds;
    };
  }
  const key=p.tracks[0].url;
  if(loaded!==key) {
    pendingAudio=key;
    const module=await WebAssembly.compile(await (await api('/assets/playlist-dsp.wasm')).arrayBuffer());
    const prepared=await Promise.all(p.tracks.map(async t=>{
      const buffer=await context.decodeAudioData(await (await api(t.url)).arrayBuffer());
      const samples=new Float32Array(buffer.length*2), l=buffer.getChannelData(0),r=buffer.getChannelData(1);
      for(let i=0;i<buffer.length;i++){samples[i*2]=l[i];samples[i*2+1]=r[i];}
      return {samples,segments:t.segments};
    }));
    if(pendingAudio!==key||preview()?.previews[open]?.tracks[0].url!==key)return;
    player.port.postMessage({type:'load',tracks:prepared,module},prepared.map(t=>t.samples.buffer));
    loaded=key;$('seek').value=0;liveCurves();
  }
  for(const [type,value] of [['loop',$('loop').checked],['solo',$('solo').value]])player.port.postMessage({type,value});
  player.port.postMessage({type:'play'});playing=true;$('pause').disabled=false;
}
function pause() {
  pendingAudio=null; playing=false;player?.port.postMessage({type:'pause'});$('pause').disabled=true;
}
async function refresh() {
  if(!project)return;
  const id=project.id, previous=project;
  const next=await read(path());
  if(project?.id!==id||next.revision<project.revision)return;
  const changed=JSON.stringify(previous.jobs.map(j=>[j.id,j.status,j.progress,j.stage]))!==JSON.stringify(next.jobs.map(j=>[j.id,j.status,j.progress,j.stage]));
  project=next;
  if(changed) {
    if(!draft?.dirty && current()?.plan)draft=null;
    show();
  }
}
$('search').oninput=showLibrary;
$('projects').onchange=()=>run(()=>load($('projects').value));
$('mix').onclick=()=>run(()=>queue('auto'));
$('render').onclick=()=>run(()=>queue('export'));
$('reorder').onclick=()=>run(()=>queue('reorder'));
$('cancel').onclick=()=>run(async()=>{const job=active();if(job)await command('cancel',{job_id:job.id});await refresh();});
$('upload').onchange=()=>run(async()=>{
  const files=[...$('upload').files], added=[]; $('upload').value='';
  try{
    for(const file of files){
      status('Uploading '+file.name);
      const response=await api('/api/v1/learning/library',file,'POST',{'X-File-Name':encodeURIComponent(file.name)});
      const t=await response.json();added.push({id:t.id,name:t.imported});
    }
  } finally {
    await index();
    if(added.length)await changeTracks([...tracks,...added]);
  }
});
$('save').onclick=()=>run(()=>{
  const settings={bars:Number($('bars').value),preset:$('preset').value};
  for(const [id,key] of [['a-cue','a_cue'],['b-cue','b_cue'],['vocal','vocal_ending']])
    if($(id).value!=='')settings[key]=$(id).valueAsNumber;
  if(draft.automationEdited)settings.automation=draft.automation;
  return edit('transition',{index:open,settings});
});
$('reset').onclick=()=>run(()=>edit('reset',{index:open}));
$('undo').onclick=()=>run(()=>restore(undo,redo));$('redo').onclick=()=>run(()=>restore(redo,undo));
$('grid-side').onchange=gridFields;
$('original-audio').onplay=()=>{pause();$('full-audio').pause();};
$('mark-downbeat').onclick=()=>{$('downbeat').value=$('original-audio').currentTime.toFixed(3);};
$('grid').onsubmit=e=>{
  e.preventDefault();run(()=>edit('grid',{index:open+Number($('grid-side').value),grid:{
    bpm:$('bpm').valueAsNumber,first_downbeat:$('downbeat').valueAsNumber,bar_phase:$('phase').valueAsNumber,
    use_detected_intervals:$('local-tempo').checked,
    anchors:$('anchors').value.trim()?$('anchors').value.split(',').map(s=>s.split(':').map(Number)):[]
  }}));
};
$('audition').onclick=()=>run(audition);$('pause').onclick=pause;
$('full-audio').onplay=()=>{pause();$('original-audio').pause();};
$('loop').onchange=()=>player?.port.postMessage({type:'loop',value:$('loop').checked});
$('solo').onchange=()=>player?.port.postMessage({type:'solo',value:$('solo').value});
$('seek').oninput=()=>player?.port.postMessage({type:'seek',seconds:$('seek').valueAsNumber});
$('curve-side').onchange=$('curve-control').onchange=showPoints;
$('wave-zoom').onchange=()=>{
  waveCenters=Object.fromEntries(['a','b'].map(side=>[side,Number($(side+'-cue').value)]));
  showEditor();
};
$('add-point').onclick=()=>{
  const points=draft.automation[$('curve-side').value][$('curve-control').value];
  if(points.length>=64)return;
  let widest=1;
  for(let i=2;i<points.length;i++)if(points[i][0]-points[i-1][0]>points[widest][0]-points[widest-1][0])widest=i;
  points.splice(widest,0,points[widest].map((n,j)=>(n+points[widest-1][j])/2));
  draft.automationEdited=draft.dirty=true;showPoints();liveCurves();
};
const curveCanvas=$('curve');
let draggedPoint=null;
function curveTarget(event) {
  const box=curveCanvas.getBoundingClientRect(), control=$('curve-control').value;
  const [min,max,step]=limits[control];
  return {
    points:draft.automation[$('curve-side').value][control],
    x:(event.clientX-box.left-4)/(box.width-8),
    y:max-(event.clientY-box.top-4)/(box.height-8)*(max-min),
    min,max,step,width:box.width,height:box.height
  };
}
curveCanvas.onpointerdown=event=>{
  if(!draft)return;
  const target=curveTarget(event);
  const index=target.points.findIndex(([x,y])=>Math.hypot((x-target.x)*target.width,
    (y-target.y)/(target.max-target.min)*target.height)<=14);
  if(index<0)return;
  draggedPoint=index;
  curveCanvas.setPointerCapture(event.pointerId);
};
curveCanvas.onpointermove=event=>{
  if(draggedPoint===null || !curveCanvas.hasPointerCapture(event.pointerId))return;
  const {points,x,y,min,max,step}=curveTarget(event), index=draggedPoint;
  if(index>0 && index<points.length-1){
    const left=points[index-1][0], right=points[index+1][0];
    const spacing=Math.min(.001,(right-left)/4);
    points[index][0]=Math.max(left+spacing,Math.min(right-spacing,x));
  }
  points[index][1]=Number(Math.max(min,Math.min(max,Math.round(y/step)*step)).toFixed(4));
  draft.automationEdited=draft.dirty=true;
  drawCurve();liveCurves();
};
curveCanvas.onlostpointercapture=()=>{if(draggedPoint!==null){draggedPoint=null;if(draft)showPoints();}};
for(const [i,side] of ['a','b'].entries()){
  const canvas=$(side+'-wave'), field=$(side+'-cue');
  const evidence=()=> (current() || preview())?.evidence?.[open+i];
  field.oninput=()=>{if(draft)draft.dirty=true;editStatus();drawWave(side,evidence());};
  const position=e=>{
    const record=evidence();if(!record?.duration)return;
    const box=canvas.getBoundingClientRect();
    const [start,end]=waveBounds(side,record);
    field.value=(start+Math.max(0,Math.min(1,(e.clientX-box.left)/box.width))*(end-start)).toFixed(3);
    field.dispatchEvent(new Event('input'));
  };
  canvas.onpointerdown=e=>{
    waveCenters[side] ??= Number(field.value);
    canvas.setPointerCapture(e.pointerId);position(e);
  };
  canvas.onpointermove=e=>{if(canvas.hasPointerCapture(e.pointerId))position(e);};
}
for(const id of ['bars','vocal'])$(id).oninput=()=>{if(draft)draft.dirty=true;editStatus();};
$('preset').oninput=()=>{
  if(!draft)return;
  const a=blank('a'), b=blank('b'), preset=$('preset').value;
  if(preset==='bass-swap') {
    a.low=[[0,0],[.45,0],[.55,-24],[1,-24]];
    b.low=[[0,-24],[.45,-24],[.55,0],[1,0]];
  }
  if(preset==='filter') {
    a.hp=[[0,20],[1,1500]];
    b.lp=[[0,800],[1,20000]];
  }
  draft.automation={a,b};draft.dirty=draft.automationEdited=true;showPoints();liveCurves();
};
window.addEventListener('resize',()=>{if(open!==null)showEditor();});
await run(async()=>{await index();await load(new URLSearchParams(location.search).get('project'));initialized=true;});
setInterval(()=>{if(initialized&&active())run(refresh);},1200);
