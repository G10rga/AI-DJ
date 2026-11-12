// Save/preview controls are exercised only against an isolated review database.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';
import {Browser,sleep} from 'file:///C:/Users/user/.agents/skills/design-taste-frontend/scripts/lib/cdp.mjs';
const fixture=JSON.parse(readFileSync(process.argv[2],'utf8'));
const out=join(fixture.root,'save-preview-controls-check');mkdirSync(out,{recursive:true});
const b=await Browser.launch(),p=await b.newPage({width:1440,height:1000});
const assert=(v,m)=>{if(!v)throw Error(m);};
async function until(fn,label){for(let i=0;i<60;i++){const v=await fn();if(v)return v;await sleep(500);}throw Error(label);}
const base=`http://127.0.0.1:8009/api/v1/learning/jobs/${fixture.job_id}/transition-review`;
const read=()=>p.eval(async u=>(await fetch(u)).json(),base);
try{
 await p.goto(fixture.url);await until(()=>p.eval(()=>document.querySelector('#incoming-entry').value==='240.06'),'fixture loaded');
 const before=await read();
 await p.eval(()=>{const f=document.getElementById('outgoing-finish');f.focus();f.value='74';f.dispatchEvent(new Event('input',{bubbles:true}));});
 assert(await p.eval(()=>!document.getElementById('save-review').disabled),'Typing did not enable Save immediately');
 assert(await p.eval(()=>!document.getElementById('vocal-confirmed').checked),'Typing did not reset confirmation');
 assert(await p.eval(()=>document.getElementById('action-feedback').textContent.includes('listening confirmation')),'Confirmation blocker unexplained');
 await until(()=>p.eval(()=>document.getElementById('placement-feedback').textContent.includes('too early')),'invalid finish feedback');
 await p.eval(()=>document.getElementById('save-review').click());
 const saved=await until(async()=>{const r=await read();return r.revision>before.revision&&r;},'invalid draft saved');
 assert(saved.corrections['0'].outgoing_source_out===74,'Draft finish not saved');
 assert(!saved.corrections['0'].vocal_confirmed,'Draft got implicit confirmation');
 await p.goto(fixture.url);await until(()=>p.eval(()=>document.getElementById('outgoing-finish').value==='74'),'draft reloaded');
 assert(await p.eval(()=>document.getElementById('action-feedback').textContent.includes('changes are saved')),'Saved state unexplained');
 await p.eval(()=>document.getElementById('automatic-finish').click());
 assert(await p.eval(()=>document.getElementById('outgoing-finish').value===''&&!document.getElementById('save-review').disabled),'Automatic finish did not create editable draft');
 assert(await p.eval(()=>document.getElementById('incoming-entry').value==='240.06'),'Automatic finish changed incoming source');
 await until(()=>p.eval(()=>document.getElementById('placement-feedback').textContent.startsWith('Calculated')),'automatic finish estimate');
 for(const width of [1440,390]){
  await p.setViewport({width,height:1000,mobile:width===390});await p.eval(()=>document.getElementById('action-feedback').scrollIntoView({block:'center'}));await sleep(100);
  assert(await p.eval(()=>document.documentElement.scrollWidth<=innerWidth+1),'Horizontal overflow');
  await p.screenshot({path:join(out,`controls-${width}.png`),format:'png'});
 }
 await p.eval(()=>document.getElementById('vocal-confirmed').click());
 await until(()=>p.eval(()=>!document.getElementById('preview-join').disabled),'confirmed preview enabled');
 await p.eval(()=>document.getElementById('preview-join').click());
 const child=await until(async()=>{const r=await read();return r.children.find(j=>j.payload.review_revision>saved.revision);},'Save and Preview queued');
 assert(['queued','running'].includes(child.status),'Preview was not queued');
 await p.eval(async id=>{const r=await fetch(`/api/v1/learning/jobs/${id}/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(!r.ok)throw Error('QA cancel failed');},child.id);
 const final=await read();assert(final.corrections['0'].outgoing_source_out==null,'Automatic finish not persisted');
 assert(final.corrections['0'].vocal_confirmed,'Explicit confirmation not saved');
 assert(p.consoleErrors.length===0,p.consoleErrors.join('\n'));
 writeFileSync(join(out,'report.json'),JSON.stringify({passed:true,preview_job:child.id,preview_cancelled_after_queue_check:true,checks:['input enables Save before blur','input resets confirmation','blocker explanation','invalid draft save/reload','automatic finish preserves other marks','explicit confirmation enables preview','Save and Preview saves/queues','desktop/mobile layout','no console errors']},null,2));
 console.log('Passed '+out);
}finally{await b.close();}
