// Exercise the outgoing placement marker only in an isolated review fixture.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';
import {Browser,sleep} from 'file:///C:/Users/user/.agents/skills/design-taste-frontend/scripts/lib/cdp.mjs';
const fixture=JSON.parse(readFileSync(process.argv[2],'utf8'));
const test={outgoing_line_end:73.7,incoming_entry:240.06,incoming_at_outgoing:68.249,outgoing_source_out:80.};
const out=join(fixture.root,'adaptive-marker-check');mkdirSync(out,{recursive:true});
const b=await Browser.launch();const p=await b.newPage({width:1440,height:1000});
const assert=(v,m)=>{if(!v)throw Error(m);};
async function until(fn,label){for(let i=0;i<600;i++){const v=await fn();if(v)return v;if(i%30===0)console.log('Waiting: '+label);await sleep(1000);}throw Error(label);}
const base=`http://127.0.0.1:8009/api/v1/learning/jobs/${fixture.job_id}/transition-review`;
const read=()=>p.eval(async u=>(await fetch(u)).json(),base);
try{
 await p.goto(fixture.url);
 await until(()=>p.eval(()=>document.querySelectorAll('.original audio').length===2&&[...document.querySelectorAll('.original audio')].every(a=>a.readyState>=1)),'source metadata');
 await p.eval(test=>{
  const panels=document.querySelectorAll('.original');const audio=document.querySelectorAll('.original audio');
  audio[0].currentTime=test.outgoing_line_end;panels[0].querySelector('.source-tools button').click();
  audio[1].currentTime=test.incoming_entry;panels[1].querySelector('.source-tools button').click();
  audio[0].currentTime=test.incoming_at_outgoing;document.getElementById('mark-incoming-at-outgoing').click();
   audio[0].currentTime=test.outgoing_source_out;document.getElementById('mark-outgoing-finish').click();
 },test);
 await until(()=>p.eval(()=>document.getElementById('placement-feedback').textContent.includes('finishes at 80.000s')),'live placement estimate');
 assert(await p.eval(t=>Math.abs(Number(document.getElementById('incoming-at-outgoing').value)-t)<.002,test.incoming_at_outgoing),'Playhead mark not assigned');
 assert(await p.eval(()=>!!document.querySelector('[data-marker="incoming-at-outgoing"]')),'Dashed marker absent');
 await p.eval(()=>document.getElementById('vocal-confirmed').click());
 await p.eval(()=>document.getElementById('incoming-at-outgoing').dispatchEvent(new Event('change')));
 assert(await p.eval(()=>!document.getElementById('vocal-confirmed').checked),'Changed marker retained stale confirmation');
 await p.eval(()=>{document.getElementById('vocal-confirmed').click();document.getElementById('save-review').click();});
 const saved=await until(async()=>{const r=await read();return r.revision>0&&r.corrections['0']?.incoming_at_outgoing!==undefined&&r;},'marker persisted');
 await p.goto(fixture.url);await until(()=>p.eval(()=>!!document.querySelector('[data-marker="incoming-at-outgoing"]')),'marker reload');
 for(const width of [1440,390]){
  await p.setViewport({width,height:1000,mobile:width===390});await sleep(250);
  assert(await p.eval(()=>document.documentElement.scrollWidth<=innerWidth+1),'Overflow at '+width);
  await p.screenshot({path:join(out,`marker-${width}.png`),format:'png',fullPage:true});
 }
 await until(()=>p.eval(()=>!document.getElementById('preview-join').disabled),'preview enabled');
 await p.eval(()=>document.getElementById('preview-join').click());
 const child=await until(async()=>{const r=await read();return r.children.find(j=>j.payload.review_revision===saved.revision&&['succeeded','needs_review','failed'].includes(j.status));},'checked marker preview');
 assert(child.status==='succeeded',JSON.stringify(child.result?.review_items||child.error));
 const cue=child.result.plan.joins[0].candidate.source_cues[0];
 assert(child.result.plan.sources[0].source_out===80,'First song finish changed');
 assert(child.result.plan.sources[1].source_in===240.06,'Second song source start changed');
 const response=await p.eval(async u=>{const r=await fetch(u,{headers:{Range:'bytes=0-31'}});return {status:r.status,size:(await r.arrayBuffer()).byteLength};},child.result.audio_url);
 assert(response.status===206&&response.size===32,'Preview media range unavailable');
 assert(!p.consoleErrors.length,p.consoleErrors.join('\n'));
 writeFileSync(join(out,'report.json'),JSON.stringify({passed:true,preview_job:child.id,requested:test.incoming_at_outgoing,applied:cue,checks:['playhead marker','dashed marker','confirmation reset','save/reload','desktop/mobile layout','real audio/timing worker','media range'],consoleErrors:p.consoleErrors},null,2));
 console.log('Passed: '+out);
}finally{await b.close();}
