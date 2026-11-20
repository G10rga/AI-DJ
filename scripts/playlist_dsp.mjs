// Bounded-memory raw-float processing. Same WASM and interpolation as the worklet.
import fs from 'node:fs';
import {DSP} from '../backend/app/web_assets/playlist-dsp.mjs';
const [input,output,settings]=process.argv.slice(2);
const segments=JSON.parse(fs.readFileSync(settings,'utf8'));
const module=await WebAssembly.compile(fs.readFileSync(new URL('../backend/app/web_assets/playlist-dsp.wasm',import.meta.url)));
const dsp=new DSP(module), source=fs.openSync(input,'r'),target=fs.openSync(output,'w');
const buffer=Buffer.alloc(128*8); let frame=0;
try {
  for(;;) {
    const bytes=fs.readSync(source,buffer,0,buffer.length,null); if(!bytes) break;
    const samples=new Float32Array(buffer.buffer,buffer.byteOffset,bytes/4);
    const result=dsp.process(samples,frame,segments);
    fs.writeSync(target,Buffer.from(result.buffer)); frame+=bytes/8;
  }
} finally {fs.closeSync(source);fs.closeSync(target);}
