export const CONDITIONS={A:'No stimulation',B:'Thermal only',C:'Vibrotactile only',D:'Thermal + vibrotactile motion',E:'Motor 1 only',F:'Motor 2 only',G:'Motor 3 only',H:'Motor 4 only'};
export const RESPONSES=['No stimulation','Thermal only','Vibrotactile only','Thermal motion',"I don’t know"];
export const LATIN=['ABDC','BCAD','CDBA','DACB'];
export function plan(){return Array.from({length:160},(_,i)=>({number:i+1,block:Math.floor(i/32)+1,inBlock:i%32+1,row:Math.floor(i%16/4)+1,repetition:Math.floor(i%32/16)+1,condition:LATIN[Math.floor(i%16/4)][i%4]}));}
export function rng(seed){let x=seed>>>0;return()=>{x+=0x6D2B79F5;let t=x;t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return((t^(t>>>14))>>>0)/4294967296;};}
export function wait(ms,signal){return new Promise((resolve,reject)=>{if(signal.aborted)return reject(new Error('Stopped'));const abort=()=>{clearTimeout(t);reject(new Error('Stopped'));};const t=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve();},ms);signal.addEventListener('abort',abort,{once:true});});}
export class Experiment {
 constructor(io){this.io=io;this.active=false;this.acceptResponse=null;this.acceptContinue=null;}
 response(n){if(this.acceptResponse && Number.isInteger(n)&&n>=1&&n<=5){const f=this.acceptResponse;this.acceptResponse=null;f(n);}}
 resume(){if(this.acceptContinue){const f=this.acceptContinue;this.acceptContinue=null;f();}}
 stop(){this.abort?.abort();this.acceptResponse=null;this.acceptContinue=null;this.io.stop();}
 input(kind,signal){return new Promise((resolve,reject)=>{const key=kind==='response'?'acceptResponse':'acceptContinue';const cancel=()=>{this[key]=null;reject(new Error('Stopped'));};this[key]=v=>{signal.removeEventListener('abort',cancel);this[key]=null;resolve(v);};signal.addEventListener('abort',cancel,{once:true});});}
 async run(config,condition=null,debug=false){
  if(this.active)throw new Error('A session is already running');
  this.active=true;this.abort=new AbortController();const signal=this.abort.signal;
  const clock=this.io.now||(()=>performance.now()),sleep=this.io.wait||wait,random=rng(config.seed);
  const list=condition?[{number:1,block:1,inBlock:1,row:null,repetition:null,condition}]:plan();
  const log=(event,fields={})=>this.io.log({event,t:clock(),utc:new Date().toISOString(),...fields});
  let current=null,answered=false;
  try{
   log('session_start',{config,debug,trialCount:list.length,plan:list});
   if(!debug){const ready=this.input('continue',signal);this.io.view('ready',{total:list.length});await ready;}
   for(const trial of list){
    current=trial;answered=false;log('trial_start',trial);this.io.progress(trial,list.length);
    if(!debug){const fixation=3000+random()*1500;log('fixation',{ms:fixation});this.io.view('fixation');this.io.tone(500);await sleep(fixation,signal);}
    this.io.view('stimulation');if(!debug)this.io.tone(1000);
    const settings=this.io.settings?this.io.settings():config;
    log('stimulus_requested',{...trial,motionMs:['C','D'].includes(trial.condition)?(settings.motionMs??5000):5000,thermalLeadMs:trial.condition==='D'?(settings.thermalLeadMs||0):0,thermalPwm:settings.thermalPwm,motorPwms:settings.motorPwms||[255,255,255,255],polarity:settings.polarity});
    const result=await this.io.stimulate(trial.condition,settings,signal);log('stimulus_complete',{...trial,...result});
    if(!debug){
     this.io.view('question');this.io.tone(500);await sleep(1000,signal);
     const answerPromise=this.input('response',signal);const shown=clock();this.io.view('response',{options:RESPONSES});log('response_options');
     const answer=await answerPromise;log('response',{...trial,answer,label:RESPONSES[answer-1],rtMs:clock()-shown});
    }
    answered=true;log('trial_complete',trial);
    if(!condition && trial.inBlock===32 && trial.number<160){
     for(let remaining=60;remaining>0;--remaining){this.io.view('break',{remaining,nextBlock:trial.block+1});await sleep(1000,signal);}
     const next=this.input('continue',signal);this.io.view('ready',{block:trial.block+1});await next;
    }
   }
   log('session_complete');this.io.view('complete');
  }catch(e){if(current&&!answered)log('trial_aborted',{...current,reason:e.message});log('session_aborted',{reason:e.message});this.io.view('aborted',{reason:e.message});}
  finally{this.io.stop();this.active=false;this.acceptResponse=null;this.acceptContinue=null;this.io.finished();}
 }
}
