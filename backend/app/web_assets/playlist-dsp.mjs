// Identical control interpolation and WASM core in Node and AudioWorklet.
export const controls=['gain','low','mid','high','hp','lp'];
export const defaults=[1,0,0,0,20,20000];
export function value(points,t) {
  if(t<=points[0][0]) return points[0][1];
  for(let i=1;i<points.length;i++) if(t<=points[i][0]) {
    const a=points[i-1],b=points[i]; return a[1]+(b[1]-a[1])*(t-a[0])/(b[0]-a[0]);
  }
  return points.at(-1)[1];
}
export class DSP {
  constructor(module,rate=44100) {
    this.core=new WebAssembly.Instance(module,{env:{abort(){throw new Error('DSP aborted');}}}).exports;
    this.rate=rate; this.input=this.core.alloc(128*8); this.output=this.core.alloc(128*8);
  }
  reset(){this.core.reset();}
  process(samples,frame,segments) {
    const n=samples.length/2;
    new Float32Array(this.core.memory.buffer,this.input,n*2).set(samples);
    const settings=t=>{
      let result=defaults.slice();
      for(const segment of segments) {
        if(t<segment.start || t>segment.end) continue;
        const x=(t-segment.start)/(segment.end-segment.start);
        result=controls.map(k=>value(segment.curves[k],x));
      }
      return result;
    };
    const a=settings(frame/this.rate),b=settings((frame+n-1)/this.rate);
    this.core.process(this.input,this.output,n,this.rate,...a.flatMap((v,i)=>[v,b[i]]));
    return new Float32Array(this.core.memory.buffer,this.output,n*2).slice();
  }
}
