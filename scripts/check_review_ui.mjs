// Isolated real-browser workflow verification, using the skill's zero-dependency CDP client.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';
import {Browser,sleep} from 'file:///C:/Users/user/.agents/skills/design-taste-frontend/scripts/lib/cdp.mjs';
const fixture=JSON.parse(readFileSync(process.argv[2],'utf8'));
const out=join(fixture.root,'browser-check');mkdirSync(out,{recursive:true});
const browser=await Browser.launch();const page=await browser.newPage({width:1440,height:1000});
const assert=(v,m)=>{if(!v)throw Error(m);};
async function until(fn,label,seconds=180){for(let i=0;i<seconds;i++){const v=await fn();if(v)return v;if(i%20===0)console.log('Waiting: '+label);await sleep(1000);}throw Error('Timed out: '+label);}
const base=`http://127.0.0.1:8009/api/v1/learning/jobs/${fixture.job_id}/transition-review`;
const review=()=>page.eval(async url=>(await fetch(url)).json(),base);
try{
 await page.goto(fixture.url);await until(()=>page.eval(()=>document.querySelectorAll('.original audio').length===2),'review evidence');
 await until(()=>page.eval(()=>[...document.querySelectorAll('.original audio')].every(a=>a.readyState>=1)),'original playback metadata',30);
 const savedRevision=(await review()).revision+1;
 await page.eval(()=>{const a=document.querySelectorAll('.original audio');a[0].currentTime=73.7;a[1].currentTime=240.06;});await sleep(500);
 await page.eval(()=>{document.querySelectorAll('.source-tools button').forEach(b=>b.click());document.getElementById('vocal-confirmed').click();document.getElementById('save-review').click();});
 await until(()=>page.eval(rev=>document.getElementById('review-revision').textContent.includes('revision '+rev)&&!document.getElementById('preview-join').disabled,savedRevision),'saved correction revision');
 await page.screenshot({path:join(out,'desktop.png'),format:'png',fullPage:true});
 await page.eval(()=>document.getElementById('preview-join').click());
 let s=await until(async()=>{const r=await review();return r.children.find(c=>c.kind==='join_preview'&&c.payload.review_revision===savedRevision&&['succeeded','needs_review','failed'].includes(c.status));},'checked preview');
 assert(s.status==='succeeded',JSON.stringify(s.result?.review_items||s.error));console.log('Preview passed '+s.id);
 await until(()=>page.eval(()=>!!document.querySelector('#review-previews audio')),'preview player');
 await page.eval(()=>[...document.querySelectorAll('#review-previews button')].find(b=>b.textContent==='Play from handoff').click());await sleep(1200);
 assert(await page.eval(()=>[...document.querySelectorAll('#review-previews audio')].some(a=>!a.paused&&a.currentTime>1)),'Preview did not play');
 const preview=s;await page.eval(()=>document.querySelectorAll('audio').forEach(a=>a.pause()));
 const conflict=await page.eval(async url=>{let r=await (await fetch(url)).json();await fetch(url+'/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:r.revision,corrections:r.corrections})});return (await fetch(url+'/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:r.revision,corrections:r.corrections})})).status;},base);
 assert(conflict===409,'Stale revision was not rejected');
 await page.goto(fixture.url);await until(()=>page.eval(rev=>document.getElementById('review-revision').textContent.includes('revision '+rev)&&!document.getElementById('resume-mix').disabled,savedRevision+1),'review reload');
 await page.eval(()=>document.getElementById('resume-mix').click());
 s=await until(async()=>{const r=await review();return r.children.find(c=>c.kind==='test_mix'&&c.payload.review_revision===savedRevision+1&&['succeeded','needs_review','failed'].includes(c.status));},'resumed generation');
 assert(s.status==='succeeded',JSON.stringify(s.result?.review_items||s.error));console.log('Resumed generation passed '+s.id);
 const media=await page.eval(async url=>{const r=await fetch(url,{headers:{Range:'bytes=0-31'}});return {status:r.status,length:(await r.arrayBuffer()).byteLength};},s.result.audio_url);
 assert(media.status===206&&media.length===32,'Preview download/range failed');
 await page.goto('http://127.0.0.1:8009/mixes');assert(await page.eval(async id=>(await (await fetch('/api/v1/mixes')).json()).mixes.some(m=>m.id==='workflow-'+id),s.id),'Resumed mix missing from Mixes');
 await page.goto(fixture.url);await until(()=>page.eval(()=>!!document.querySelector('#review-previews audio')),'history reload');
 for(const width of [768,390]){await page.setViewport({width,height:900,mobile:width===390});await sleep(200);assert(await page.eval(()=>document.documentElement.scrollWidth<=innerWidth+1),'Horizontal overflow at '+width);await page.screenshot({path:join(out,`review-${width}.png`),format:'png',fullPage:true});}
 const before=(await review()).children.map(j=>j.id);await page.eval(()=>document.getElementById('preview-join').click());
 await until(async()=>{const r=await review();return r.children.some(j=>!before.includes(j.id)&&['queued','running'].includes(j.status));},'cancellable preview');
 await until(()=>page.eval(()=>[...document.querySelectorAll('#review-previews button')].some(b=>b.textContent==='Cancel')),'cancel control');
 await page.eval(()=>[...document.querySelectorAll('#review-previews button')].find(b=>b.textContent==='Cancel').click());
 await until(async()=>{const r=await review();return r.children.some(j=>!before.includes(j.id)&&j.status==='cancelled');},'preview cancellation');
 assert(await page.eval(async url=>(await fetch(url)).status,preview.result.audio_url)===200,'Earlier playable preview was lost');
 await page.goto('http://127.0.0.1:8009/learning');await until(()=>page.eval(()=>!!document.getElementById('mixer-pipeline')),'generation pipeline option');
 assert(await page.eval(()=>[...document.getElementById('mixer-pipeline').options].some(o=>o.textContent==='Improved transitions — experimental')),'Experimental option missing');
 await page.goto('http://127.0.0.1:8009/compare');await until(()=>page.eval(()=>!!document.getElementById('mixer-pipeline')),'comparison option');
 await until(()=>page.eval(()=>document.querySelectorAll('.comparison-alternative audio').length===2),'comparison players');
 await page.eval(()=>{document.querySelector('.comparison-feedback button[data-choice="tie"]').click();});
 await until(()=>page.eval(()=>document.querySelector('.feedback-state')?.textContent.includes('Listening review only')),'isolated comparison feedback');
 await page.eval(()=>{const s=document.getElementById('mixer-pipeline');s.value='improved-transitions-1';s.dispatchEvent(new Event('change'));});assert(await page.eval(()=>document.getElementById('use-preferences').disabled),'Incompatible learned ranking was enabled');
 assert(page.consoleErrors.length===0,page.consoleErrors.join('\n'));
 writeFileSync(join(out,'report.json'),JSON.stringify({passed:true,preview_job:preview.id,resumed_job:s.id,checks:['source marking','save','preview','play','stale revision','reload','resume','download/ranges','Mixes','mobile/tablet','cancel','history','pipeline options'],consoleErrors:page.consoleErrors},null,2));console.log('Browser checks passed: '+out);
}finally{await browser.close();}
