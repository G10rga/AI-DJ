'use strict';
const el=id=>document.getElementById(id);
let state=null,selected=[],referenceId=null,modelId=null,polling=false,posting=false,initialized=false,requestedModelJob=null;
let librarySignature=null,modelSignature=null,referenceSignature=null,refreshFailed=false;
const jobNodes=new Map();
function note(text='',error=false){el('workflow-message').textContent=text;el('workflow-message').classList.toggle('error',error);}
async function api(url,options){const response=await fetch(url,options);const data=await response.json();if(!response.ok)throw Error(data.detail||'Request failed. Try again.');return data;}
async function post(url,data){return api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});}
function text(tag,value,cls){const node=document.createElement(tag);node.textContent=value;if(cls)node.className=cls;return node;}
function option(select,label,value){select.add(new Option(label,value));}
function active(job){return job.status==='queued'||job.status==='running';}
function chosenModel(){return state?.models.find(model=>model.id===modelId);}
function isStale(model){return model&&state.readiness&&model.draft_id===state.readiness.draft_id&&model.review_fingerprint!==state.readiness.review_fingerprint;}
function refreshButtons(){
  const ready=state?.readiness,model=chosenModel();
  const training=state?.jobs.some(job=>job.kind==='train'&&active(job)&&job.payload.draft_id===referenceId);
  el('train-model').disabled=posting||!ready?.can_train||training;
  el('train-model').textContent=training?'Training job in progress…':'Train from included reviews';
  el('generate-test').disabled=posting||selected.length<2||!model||isStale(model);
  el('generate-baseline').disabled=posting||selected.length<2;
  el('add-song').disabled=posting||!state?.library.length||selected.length>=50;
  const needsTraining=!model||isStale(model);
  el('train-model').classList.toggle('primary',needsTraining);
  el('generate-test').classList.toggle('primary',!needsTraining);
}
function renderSelection(){
  const list=el('selected-songs');list.replaceChildren();
  const catalog=new Map(state.library.map(song=>[song.id,song]));
  selected.forEach((id,index)=>{
    const song=catalog.get(id);if(!song)return;
    const row=document.createElement('li');row.append(text('span',`${index+1}. ${song.name}`,'song-name'));
    const controls=document.createElement('div');controls.className='song-controls';
    [['Up',index>0,()=>{[selected[index-1],selected[index]]=[selected[index],selected[index-1]];}],
     ['Down',index<selected.length-1,()=>{[selected[index+1],selected[index]]=[selected[index],selected[index+1]];}],
     ['Remove',true,()=>selected.splice(index,1)]].forEach(([label,enabled,action])=>{
       const button=text('button',label);button.type='button';button.disabled=!enabled;button.setAttribute('aria-label',`${label} ${song.name}`);
       button.addEventListener('click',()=>{action();renderSelection();refreshButtons();});controls.append(button);
     });row.append(controls);list.append(row);
  });
  if(!selected.length)list.append(text('li','Add at least two songs to make a test mix.','help'));
  el('test-context').textContent=`${selected.length} song${selected.length===1?'':'s'} selected. The model is applied only to this test; the default mixer is unchanged.`;
}
function renderModel(){
  const model=chosenModel();el('model-metrics').replaceChildren();el('model-details').hidden=!model;
  if(!model){el('model-summary').textContent='Train a version to try its cue and overlap choices.';el('model-evaluation').textContent='';return;}
  const report=model.report;
  el('model-summary').textContent=isStale(model)?'Reviews changed since this version was trained. Train a new version to use your latest decisions.':
    `Experimental · ${report.examples} included transitions · ${report.trained_style_examples} style-labeled training examples. ${report.trained_style_examples?'':'Cue and overlap learning is available; styles remain unlabeled.'}`;
  const evaluation=report.evaluation;
  el('model-evaluation').textContent=evaluation?
    `Held-out error ${evaluation.normalized_mse<evaluation.mean_baseline_mse?'beat':'did not beat'} the average-choice baseline on ${evaluation.examples} transition${evaluation.examples===1?'':'s'}. Listening is still needed.`:
    'Training finished. There are not enough source-disjoint examples for evaluation yet.';
  const metrics=[['Training transitions',report.train.examples],['Held-out transitions',evaluation?.examples??'Unavailable'],
    ['Human style labels',report.human_style_examples??report.style_examples],
    ['Automatic style estimates',report.automatic_style_examples??0],
    ['Held-out cue error',evaluation?`${evaluation.cue_mae_seconds.toFixed(1)} seconds`:'Unavailable'],
    ['Held-out overlap error',evaluation?`${evaluation.overlap_mae_seconds.toFixed(1)} seconds`:'Unavailable'],
    ['Independent reference-set test','Unavailable'],['Model use','Experimental tests only']];
  metrics.forEach(([label,value])=>{el('model-metrics').append(text('dt',label),text('dd',String(value)));});
}
function renderJobs(){
  const container=el('workflow-jobs');
  if(!state.jobs.length){container.replaceChildren(text('p','No training or test jobs yet.','empty-jobs'));jobNodes.clear();el('worker-summary').textContent='Worker ready';return;}
  container.querySelector('.empty-jobs')?.remove();
  state.jobs.forEach((job,index)=>{
    let row=jobNodes.get(job.id);
    if(!row){
      row=document.createElement('article');row.className='workflow-job';row.dataset.jobId=job.id;
      const heading=document.createElement('div');heading.className='job-heading';heading.append(text('h3',''),text('span','','job-state'));
      row.append(heading,text('p','','job-model help'),text('p','','job-stage'));
      const progress=document.createElement('progress');progress.max=1;progress.setAttribute('aria-label','Job stage progress');row.append(progress);
      row.append(text('p','','job-error'));const actions=document.createElement('div');actions.className='job-actions';row.append(actions);
      const result=document.createElement('div');result.className='job-result';row.append(result);jobNodes.set(job.id,row);
    }
    if(container.children[index]!==row)container.insertBefore(row,container.children[index]||null);
    row.querySelector('h3').textContent=job.kind==='pair_audition'?`Compare transitions · ${job.payload.song_names.length} songs`:job.kind==='transition_analysis'?`Analyze ${job.payload.examples} transitions`:job.kind==='train'?`Train on ${job.payload.examples} included transitions`:
      `${job.payload.baseline?'Baseline':'Model test mix'} · ${job.payload.song_names.length} songs`;
    const pinnedModelId=job.payload.model_id||job.result?.model_id;
    const modelIndex=state.models.findIndex(model=>model.id===pinnedModelId);
    const provenance=row.querySelector('.job-model');
    provenance.hidden=job.kind!=='test_mix'||job.payload.baseline;
    provenance.textContent=pinnedModelId?
      `${modelIndex>=0?`Model version ${state.models.length-modelIndex}`:'Saved model'} · ${pinnedModelId.slice(0,12)}${modelIndex<0?' (unavailable)':''}`:
      'Model identity unavailable';
    provenance.title=pinnedModelId||'';
    row.querySelector('.job-state').textContent=job.cancel_requested&&job.status==='running'?'Cancelling…':job.status[0].toUpperCase()+job.status.slice(1);
    row.querySelector('.job-stage').textContent=job.stage;
    row.querySelector('progress').hidden=!active(job);row.querySelector('progress').value=job.progress;
    row.querySelector('.job-error').textContent=job.error||'';
    const actions=row.querySelector('.job-actions');
    if(actions.dataset.status!==`${job.status}-${job.cancel_requested}`){
      actions.replaceChildren();actions.dataset.status=`${job.status}-${job.cancel_requested}`;
      if(active(job)){
        const cancel=text('button',job.cancel_requested?'Cancelling…':'Cancel');cancel.type='button';cancel.disabled=Boolean(job.cancel_requested);
        cancel.addEventListener('click',()=>jobAction(job.id,'cancel'));actions.append(cancel);
      }else if(['failed','cancelled','interrupted'].includes(job.status)){
        const retry=text('button','Retry');retry.type='button';retry.addEventListener('click',()=>jobAction(job.id,'retry'));actions.append(retry);
      }
      if(job.status!=='queued'){const log=text('a','View job log');log.href=`/api/v1/learning/jobs/${job.id}/log`;log.target='_blank';log.rel='noopener';actions.append(log);}
    }
    const result=row.querySelector('.job-result');
    if(job.status==='succeeded'&&!result.dataset.ready){
      result.dataset.ready='true';
      if(job.kind==='pair_audition'){
        const compare=text('a','Listen to A/B and save your preference');compare.href='/compare';result.append(compare);
      }else if(job.result?.summary&&job.kind==='transition_analysis'){
        const summary=job.result.summary;
        result.append(text('p',`${summary.processed} analyzed · ${summary.recognized} techniques described · ${summary.training_labels} training labels · ${summary.uncertain} uncertain`,'help'));
        const review=text('a','Read transition descriptions');review.href='/references';result.append(review);
      }else if(job.result?.audio_url){
        const audio=document.createElement('audio');audio.controls=true;audio.preload='metadata';audio.src=job.result.audio_url;
        audio.setAttribute('aria-label',`${job.payload.baseline?'Baseline':'Model'} test mix playback`);
        audio.addEventListener('play',()=>document.querySelectorAll('audio').forEach(other=>{if(other!==audio)other.pause();}));
        audio.addEventListener('error',()=>{row.querySelector('.job-error').textContent='Rendered audio is unavailable. Generate another test or check Mixes.';});
        result.append(audio);
        if(job.result.applied_transitions)result.append(text('p','Applied handoffs: '+job.result.applied_transitions.map(t=>t.bars?`${t.bars} bars (${t.seconds.toFixed(1)}s)`:`short boundary fade (${t.seconds.toFixed(2)}s; no beatmatch)`).join(', '),'help'));
        const download=text('a','Download MP3');download.href=job.result.download_url;download.download='';result.append(download);
        const mixes=text('a','Open Mixes');mixes.href='/mixes';result.append(mixes);
        if(job.result.warnings?.length)result.append(text('p',job.result.warnings.join(' '),'help'));
      }else if(job.result?.model){
        result.append(text('p','Model saved. Select songs and generate a test mix.','help'));
        const choose=text('button','Choose songs for a test mix');choose.type='button';
        choose.addEventListener('click',()=>{modelId=job.result.model.id;el('test-model').value=modelId;renderModel();refreshButtons();el('test-heading').scrollIntoView({block:'start'});});
        result.append(choose);
      }
    }
  });
  const waiting=state.jobs.filter(j=>j.status==='queued').length,running=state.jobs.find(j=>j.status==='running');
  el('worker-summary').textContent=running?`One job running${waiting?` · ${waiting} queued`:''}`:waiting?`${waiting} queued`:'Worker ready';
}
function render(){
  const references=state.references.filter(reference=>reference.draft_id);
  const refSig=references.map(r=>r.draft_id).join(',');
  if(refSig!==referenceSignature){referenceSignature=refSig;el('training-reference').replaceChildren();references.forEach(r=>option(el('training-reference'),r.title,r.draft_id));if(!references.length)option(el('training-reference'),'No prepared reference yet','');}
  referenceId=state.readiness?.draft_id||null;el('training-reference').value=referenceId||'';el('training-reference').disabled=!references.length;
  el('training-counts').textContent=state.readiness?`${state.readiness.examples} included transitions · ${state.readiness.style_examples} style labels (${state.readiness.automatic_style_examples||0} automatic estimates)`:'No prepared reference recording yet';
  el('training-help').textContent=!state.readiness?.can_train?'Complete and include at least two listening reviews to train. Pending timing drafts and excluded transitions stay out.':
    `${state.readiness.counts.excluded} excluded · ${state.readiness.counts.draft_saved||0} timing drafts pending. Training pins your current reviews and supported automatic style estimates. Automatic labels have lower weight; your labels take precedence.`;
  const modelSig=state.models.map(m=>m.id).join(',');
  if(modelSig!==modelSignature){
    const hadModel=Boolean(modelId);modelSignature=modelSig;el('test-model').replaceChildren();
    state.models.forEach((m,i)=>option(el('test-model'),`Version ${state.models.length-i} · ${m.report.examples} included transitions`,m.id));
    if(!state.models.length)option(el('test-model'),'No trained model yet','');
    if(!state.models.some(m=>m.id===modelId)||!hadModel)modelId=state.models[0]?.id||null;
    if(state.models.some(m=>m.id===requestedModelJob)){modelId=requestedModelJob;requestedModelJob=null;}
  }
  el('test-model').value=modelId||'';el('test-model').disabled=!state.models.length;
  const libSig=state.library.map(song=>song.id).join(',');
  if(libSig!==librarySignature){librarySignature=libSig;el('song-picker').replaceChildren();state.library.forEach(song=>option(el('song-picker'),song.name,song.id));if(!state.library.length)option(el('song-picker'),'No songs imported yet','');el('song-picker').disabled=!state.library.length;if(initialized)renderSelection();}
  if(!initialized){selected=state.default_track_ids||[];initialized=true;renderSelection();}
  renderModel();renderJobs();refreshButtons();
}
async function refresh(quiet=false){
  if(polling)return;polling=true;
  try{state=await api('/api/v1/learning/state'+(referenceId?'?draft_id='+encodeURIComponent(referenceId):''));render();if(!quiet||refreshFailed)note();refreshFailed=false;}
  catch(error){refreshFailed=true;note(`${error.message} Use Refresh to retry; saved jobs continue in the background.`,true);}
  finally{polling=false;}
}
async function submit(operation){
  if(posting)return;posting=true;refreshButtons();
  try{await operation();note('Job queued. Progress and results will appear below.');await refresh(true);el('jobs-heading').scrollIntoView({block:'start'});}
  catch(error){note(error.message,true);}
  finally{posting=false;refreshButtons();}
}
async function jobAction(id,action){await submit(()=>post(`/api/v1/learning/jobs/${id}/${action}`,{}));}
el('refresh-learning').addEventListener('click',()=>refresh());
el('training-reference').addEventListener('change',()=>{referenceId=el('training-reference').value;refresh();});
el('test-model').addEventListener('change',()=>{modelId=el('test-model').value;requestedModelJob=null;renderModel();refreshButtons();});
el('train-model').addEventListener('click',()=>submit(async()=>{const job=await post('/api/v1/learning/train',{draft_id:referenceId});requestedModelJob=job.id;}));
el('add-song').addEventListener('click',()=>{if(selected.length<50){selected.push(el('song-picker').value);renderSelection();refreshButtons();}});
['generate-test','generate-baseline'].forEach(id=>el(id).addEventListener('click',()=>submit(()=>post('/api/v1/learning/test-mixes',{
  model_id:modelId,track_ids:selected,seconds:Number(el('test-length').value),baseline:id==='generate-baseline'}))));
el('song-upload').addEventListener('change',async()=>{
  const files=Array.from(el('song-upload').files),added=[],names=[],before=new Set(state.library.map(song=>song.id));el('song-upload').disabled=true;
  try{for(let i=0;i<files.length;i++){
    el('import-status').textContent=`Importing ${i+1} of ${files.length}…`;
    const imported=await api('/api/v1/learning/library',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent(files[i].name)},body:files[i]});if(imported.id)added.push(imported.id);else names.push(imported.imported);
  }el('import-status').textContent=`${files.length} song${files.length===1?'':'s'} added`;await refresh(true);}
  catch(error){note(error.message,true);el('import-status').textContent='Import stopped. Completed songs remain in the library.';await refresh(true);}
  finally{
    if(names.length){
      try{state=await api('/api/v1/learning/state'+(referenceId?'?draft_id='+encodeURIComponent(referenceId):''));render();
        names.forEach(name=>{const song=state.library.find(s=>s.name===name&&!before.has(s.id)&&!added.includes(s.id));if(song)added.push(song.id);});
      }catch(error){note(error.message,true);}
    }
    selected.push(...added.slice(0,Math.max(0,50-selected.length)));renderSelection();refreshButtons();el('song-upload').disabled=false;el('song-upload').value='';
  }
});
refresh();setInterval(()=>refresh(true),2000);
