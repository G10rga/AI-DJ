'use strict';
const $=id=>document.getElementById(id),nodes=new Map();
let state=null,polling=false,posting=false,catalogSignature='';
let pipelineInitialized=false;
const improved=()=>$('mixer-pipeline').value==='improved-transitions-1';
const label={plain_crossfade:'Plain crossfade',protected_vocal:'Protected vocal handoff',groove_32:'32-bar groove blend',controlled_16:'16-bar controlled blend',eq_8:'8-bar EQ handoff',phrase_cut:'Phrase cut'};
function text(tag,value,cls){const n=document.createElement(tag);n.textContent=value;if(cls)n.className=cls;return n;}
function message(value='',error=false){$('comparison-message').textContent=value;$('comparison-message').classList.toggle('error',error);}
async function api(url,data){const r=await fetch(url,data===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const value=await r.json();if(!r.ok)throw Error(value.detail||'Request failed. Try again.');return value;}
function buttons(){const active=state?.jobs.some(j=>['queued','running'].includes(j.status));$('generate-comparison').disabled=posting||!state?.library.length||active||$('compare-outgoing').value===$('compare-incoming').value;$('use-preferences').disabled=posting||improved()||!state?.model.ready;if(improved())$('use-preferences').checked=false;}
function seconds(value){return `${Math.floor(value/60)}:${(value%60).toFixed(1).padStart(4,'0')}`;}
function playAt(audio,time){const play=()=>{audio.currentTime=Math.min(Math.max(0,time),Number.isFinite(audio.duration)?audio.duration-.05:time);audio.play().catch(e=>message(e.message,true));};if(audio.readyState>=1)play();else{audio.addEventListener('loadedmetadata',play,{once:true});audio.load();}}
function renderJob(job){
 let row=nodes.get(job.id);
 if(!row){row=text('article','','comparison-job');row.dataset.jobId=job.id;row.append(text('h3',job.payload.song_names.join(' → ')),text('p','','comparison-stage'),text('p','','comparison-error'));const p=document.createElement('progress');p.max=1;p.setAttribute('aria-label','Comparison progress');row.append(p,text('div','','comparison-actions'),text('div','','comparison-result'));nodes.set(job.id,row);}
 row.querySelector('.comparison-stage').textContent=`${job.status} · ${job.stage}`;
 row.querySelector('.comparison-error').textContent=job.error||'';
 const progress=row.querySelector('progress');progress.hidden=!['queued','running'].includes(job.status);progress.value=job.progress;
 const actions=row.querySelector('.comparison-actions');
 if(actions.dataset.status!==job.status){actions.dataset.status=job.status;actions.replaceChildren();
  const action=['queued','running'].includes(job.status)?'cancel':['failed','interrupted','cancelled'].includes(job.status)?'retry':null;
  if(action){const b=text('button',action==='cancel'?'Cancel':'Retry');b.type='button';b.addEventListener('click',()=>submit(()=>api(`/api/v1/learning/jobs/${job.id}/${action}`,{})));actions.append(b);}
  if(job.status==='needs_review'||(job.payload.pipeline==='improved-transitions-1'&&job.status==='succeeded')){const link=text('a','Review transitions');link.href=`/transition-review/${job.id}`;actions.append(link);}
  if(job.status!=='queued'){const link=text('a','View job log');link.href=`/api/v1/learning/jobs/${job.id}/log`;link.target='_blank';link.rel='noopener';actions.append(link);}
 }
 const result=row.querySelector('.comparison-result');
 if(job.status==='succeeded'&&!result.dataset.ready){
  result.dataset.ready='true';const grid=text('div','','comparison-audio'),players=[];
  job.result.alternatives.forEach((alt,index)=>{
   const slot=index?'b':'a',section=text('section','','comparison-alternative');section.append(text('h4',`${slot.toUpperCase()} · ${label[alt.recipe]||alt.recipe}`));
   const audio=document.createElement('audio');audio.controls=true;audio.preload='metadata';audio.src=`/api/v1/comparisons/${job.id}/audio/${slot}`;audio.setAttribute('aria-label',`Alternative ${slot.toUpperCase()}`);players.push(audio);
   audio.addEventListener('play',()=>document.querySelectorAll('audio').forEach(other=>{if(other!==audio)other.pause();}));audio.addEventListener('error',()=>message('Preview audio is unavailable or changed. Generate another comparison.',true));section.append(audio);
   section.append(text('p',`Handoff ${seconds(alt.handoff_seconds)} · overlap ${alt.overlap_seconds.toFixed(1)}s · ${alt.loudness.integrated_lufs.toFixed(1)} LUFS`));
   const play=text('button',`Play ${slot.toUpperCase()} from handoff`);play.type='button';play.addEventListener('click',()=>playAt(audio,alt.handoff_seconds-8));section.append(play);grid.append(section);
  });result.append(grid);
  const switcher=text('button','Switch A/B at same position');switcher.type='button';switcher.addEventListener('click',()=>{const from=players.findIndex(a=>!a.paused);const index=from<0?0:from;const next=players[1-index];const time=players[index].currentTime-job.result.alternatives[index].handoff_seconds+job.result.alternatives[1-index].handoff_seconds;players[index].pause();playAt(next,time);});result.append(switcher);
  const feedback=text('div','','comparison-feedback'),reasonId='reason-'+job.id;
  const reasonLabel=text('label','Reason (optional)');reasonLabel.htmlFor=reasonId;const reason=document.createElement('input');reason.id=reasonId;reason.type='text';reason.maxLength=1000;reason.placeholder='For example: smoother bass change, vocals clash, or energy drops';reason.value=job.review.notes;
  feedback.append(reasonLabel,reason);const choices=text('div','','workflow-actions');
  for(const [choice,title] of [['a','A is better'],['b','B is better'],['tie','Tie'],['neither','Neither works']]){const b=text('button',title);b.type='button';b.dataset.choice=choice;b.addEventListener('click',()=>vote(job.id,choice,row));choices.append(b);}feedback.append(choices,text('p','','feedback-state'));result.append(feedback);
 }
 if(job.status==='succeeded'){
  const feedback=result.querySelector('.comparison-feedback');if(row.dataset.revision===undefined)row.dataset.revision=job.review.revision;
  feedback.querySelectorAll('button').forEach(b=>{b.setAttribute('aria-pressed',String(b.dataset.choice===job.review.choice));b.disabled=posting;});
  feedback.querySelector('.feedback-state').textContent=job.review.choice?`Saved: ${job.review.choice.toUpperCase()} · revision ${job.review.revision}. ${job.review.choice==='neither'?'No winner is used for training. Generate again to try different candidates.':job.review.choice==='tie'?'No winner is used for preference training.':'Preference model updated from your choice.'}`:'Listen to both versions, then choose.';
  if(job.payload.pipeline==='improved-transitions-1')feedback.querySelector('.feedback-state').textContent=job.review.choice?`Saved: ${job.review.choice.toUpperCase()} · revision ${job.review.revision}. Listening review only; training for these controls is not enabled.`:'Listen to both. Choices are saved as listening reviews; these controls are not used for training yet.';
 }
 return row;
}
function render(){
 if(!pipelineInitialized){$('mixer-pipeline').value=state.default_pipeline||'legacy-v1';pipelineInitialized=true;}
 const signature=state.library.map(s=>s.id).join(',');
 if(signature!==catalogSignature){const initial=!catalogSignature;catalogSignature=signature;for(const id of ['compare-outgoing','compare-incoming']){const select=$(id),value=select.value;select.replaceChildren();state.library.forEach(song=>select.add(new Option(song.name,song.id)));if(state.library.some(s=>s.id===value))select.value=value;select.disabled=!state.library.length;}if(initial){const latest=state.jobs.find(j=>j.status==='succeeded');latest?.result.source_hashes?.forEach((hash,index)=>{const song=state.library.find(s=>s.content_hash===hash);if(song)$(index?'compare-incoming':'compare-outgoing').value=song.id;});}if($('compare-outgoing').value===$('compare-incoming').value&&state.library.length>1)$('compare-incoming').selectedIndex=1;}
 $('preference-status').textContent=`${state.model.comparisons} distinct preferences across ${state.model.song_pairs} song pairs. ${state.model.ready?'Learned ranking is available for an explicit comparison.':'Learned ranking needs at least 6 distinct preferences across 3 song pairs.'} ${state.model.held_out_song_pair_accuracy==null?'No held-out song-pair evaluation yet.':`Held-out preference accuracy: ${(state.model.held_out_song_pair_accuracy*100).toFixed(0)}%; listening is still needed.`}`;
 const container=$('comparison-jobs');if(!state.jobs.length){container.replaceChildren(text('p','No comparisons yet. Choose two songs and generate previews.','help'));}else{container.querySelector(':scope > .help')?.remove();state.jobs.forEach((job,index)=>{const row=renderJob(job);if(container.children[index]!==row)container.insertBefore(row,container.children[index]||null);});}buttons();
}
async function refresh(){if(polling)return;polling=true;try{state=await api('/api/v1/comparisons');render();}catch(e){message(`${e.message} Use Refresh to retry.`,true);}finally{polling=false;}}
async function submit(operation){if(posting)return;posting=true;buttons();try{await operation();await refresh();message();}catch(e){message(e.message,true);}finally{posting=false;if(state)render();}}
async function vote(id,choice,row){await submit(async()=>{const value=await api(`/api/v1/comparisons/${id}/feedback`,{choice,expected_revision:Number(row.dataset.revision),notes:row.querySelector('.comparison-feedback input').value});row.dataset.revision=value.review.revision;});}
$('generate-comparison').addEventListener('click',()=>submit(()=>api('/api/v1/comparisons',{track_ids:[$('compare-outgoing').value,$('compare-incoming').value],use_preferences:$('use-preferences').checked,pipeline:$('mixer-pipeline').value})));
$('mixer-pipeline').addEventListener('change',buttons);
$('refresh-comparisons').addEventListener('click',async()=>{await refresh();for(const job of state?.jobs||[]){const row=nodes.get(job.id);if(row)row.dataset.revision=job.review.revision;}message('Saved comparisons reloaded.');});['compare-outgoing','compare-incoming'].forEach(id=>$(id).addEventListener('change',buttons));
refresh();setInterval(refresh,3000);
