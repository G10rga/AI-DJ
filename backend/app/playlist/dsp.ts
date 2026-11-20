// AssemblyScript source, compiled to playlist-dsp.wasm. Shared server/worklet DSP.
const state = new StaticArray<f64>(8);
export function reset(): void { for(let i=0;i<8;i++) state[i]=0; }
export function alloc(bytes: i32): usize { return heap.alloc(bytes); }
export function process(input: usize, output: usize, frames: i32, rate: f64,
  gain0: f64, gain1: f64, low0: f64, low1: f64, mid0: f64, mid1: f64,
  high0: f64, high1: f64, hp0: f64, hp1: f64, lp0: f64, lp1: f64): void {
  let cl = 1-Math.exp(-2*Math.PI*180/rate);
  let ch = 1-Math.exp(-2*Math.PI*2500/rate);
  for(let i=0;i<frames;i++) {
    let t=<f64>i/<f64>max(1,frames-1);
    let gain=gain0+(gain1-gain0)*t;
    let lo=Math.pow(10,(low0+(low1-low0)*t)/20);
    let mi=Math.pow(10,(mid0+(mid1-mid0)*t)/20);
    let hi=Math.pow(10,(high0+(high1-high0)*t)/20);
    let hp=hp0+(hp1-hp0)*t, lp=lp0+(lp1-lp0)*t;
    let hc=1-Math.exp(-2*Math.PI*hp/rate), lc=1-Math.exp(-2*Math.PI*lp/rate);
    for(let channel=0;channel<2;channel++) {
      let index=channel*4;
      let x=<f64>load<f32>(input+(i*2+channel)*4);
      state[index]+=cl*(x-state[index]);
      state[index+1]+=ch*(x-state[index+1]);
      let y=state[index]*lo+(state[index+1]-state[index])*mi+(x-state[index+1])*hi;
      state[index+2]+=hc*(y-state[index+2]);
      y-=state[index+2]*min(1.0,max(0.0,(hp-20.0)/20.0));
      state[index+3]+=lc*(y-state[index+3]);
      y+=(state[index+3]-y)*min(1.0,max(0.0,(20000.0-lp)/2000.0));
      store<f32>(output+(i*2+channel)*4,<f32>(y*gain));
    }
  }
}
