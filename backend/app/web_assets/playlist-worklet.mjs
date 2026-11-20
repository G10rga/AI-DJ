import {DSP} from './playlist-dsp.mjs';
class PlaylistPlayer extends AudioWorkletProcessor {
  constructor(){
    super();this.playing=false;this.position=0;this.loop=false;this.solo='both';this.tracks=[];
    this.port.onmessage=({data})=>{
      if(data.type==='load') {
        this.tracks=data.tracks.map(t=>({...t,dsp:new DSP(data.module,sampleRate)}));
        this.length=Math.max(...this.tracks.map(t=>t.samples.length/2));this.seek(0);
      }
      if(data.type==='play')this.playing=true;
      if(data.type==='pause')this.playing=false;
      if(data.type==='seek')this.seek(Math.floor(data.seconds*sampleRate));
      if(data.type==='loop')this.loop=data.value;
      if(data.type==='solo')this.solo=data.value;
      if(data.type==='automation'){
        data.segments.forEach((s,i)=>this.tracks[i].segments=s);
      }
    };
  }
  seek(frame){
    this.position=Math.max(0,Math.min(frame,this.length||0));
    // Warm the filter with 250ms of history. Even the slowest 20Hz pole's
    // remaining state decays below float32 precision over this interval.
    const first=Math.max(0,this.position-Math.ceil(sampleRate*.25));
    for(const t of this.tracks){
      t.dsp.reset();
      for(let p=first;p<this.position;p+=128)t.dsp.process(t.samples.subarray(p*2,Math.min(p+128,this.position)*2),p,t.segments);
    }
  }
  process(inputs,outputs){
    const out=outputs[0];if(!this.playing||!this.tracks.length)return true;
    if(this.position>=this.length){if(this.loop)this.seek(0);else{this.playing=false;this.seek(0);this.port.postMessage({ended:true,seconds:0});return true;}}
    const count=Math.min(128,this.length-this.position);
    this.tracks.forEach((t,i)=>{
      const available=t.samples.subarray(this.position*2,(this.position+count)*2);
      const samples=available.length===count*2?available:Float32Array.from({length:count*2},(_,i)=>available[i]||0);
      const result=t.dsp.process(samples,this.position,t.segments);
      if(this.solo!=='both'&&this.solo!==String(i))return;
      for(let f=0;f<count;f++){out[0][f]+=result[f*2]*.7;out[1][f]+=result[f*2+1]*.7;}
    });
    this.position+=count;
    if(this.position%4096<count)this.port.postMessage({seconds:this.position/sampleRate});
    return true;
  }
}
registerProcessor('playlist-player',PlaylistPlayer);
