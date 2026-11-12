// Read-only verification of current versus earlier preview status.
import {mkdirSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {Browser,sleep} from 'file:///C:/Users/user/.agents/skills/design-taste-frontend/scripts/lib/cdp.mjs';
const [url,out]=process.argv.slice(2);mkdirSync(out,{recursive:true});
const assert=(value,label)=>{if(!value)throw Error(label);};
const browser=await Browser.launch();const page=await browser.newPage({width:1440,height:1000});
try{
 await page.goto(url);let ready=false;
 for(let i=0;i<180;i++){
  ready=await page.eval(()=>document.getElementById('review-revision')?.textContent.includes('Transition preview ready'));
  if(ready)break;await sleep(1000);
 }
 assert(ready,'Newest successful preview is not shown as ready');
 assert(await page.eval(()=>document.getElementById('review-reasons').textContent.trim()===''),'Obsolete failure shown as current');
 assert(await page.eval(()=>!!document.querySelector('#review-previews .preview-row:first-child audio')),'Newest preview has no player');
 assert(await page.eval(()=>[...document.querySelectorAll('#review-previews .preview-row')].slice(1).every(row=>row.textContent.startsWith('Earlier attempt'))),'Older attempt status is ambiguous');
 for(const width of [1440,390]){
  await page.setViewport({width,height:1000,mobile:width===390});await page.eval(()=>scrollTo(0,0));await sleep(200);
  assert(await page.eval(()=>document.documentElement.scrollWidth<=innerWidth+1),'Horizontal overflow');
  await page.screenshot({path:join(out,`status-${width}.png`),format:'png'});
  await page.eval(()=>document.getElementById('review-previews').scrollIntoView());await sleep(100);
  await page.screenshot({path:join(out,`history-${width}.png`),format:'png'});
 }
 assert(page.consoleErrors.length===0,page.consoleErrors.join('\n'));
 writeFileSync(join(out,'report.json'),JSON.stringify({passed:true,checks:['current preview ready','old failures not current','latest player available','earlier attempts labelled','desktop/mobile overflow','no console errors'],consoleErrors:page.consoleErrors},null,2));
 console.log('UI status checks passed: '+out);
}finally{await browser.close();}
