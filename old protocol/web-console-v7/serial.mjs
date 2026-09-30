import {parseStatus} from './live.mjs';
export class Uno {
 constructor(log){this.log=log;this.port=null;this.ready=false;this.pending=new Set();this.chain=Promise.resolve();this.live=false;}
 line(s){const state=parseStatus(s);if(state){this.telemetry={...state,receivedAt:performance.now()};this.onTelemetry?.(this.telemetry);}if(s.startsWith('ACK RUN'))this.runStartedAt=performance.now();if(s.startsWith('DONE RUN')){this.runStartedAt=null;this.runProgress=1;}this.log(s);for(const p of [...this.pending])if(p.match(s)){this.pending.delete(p);p.resolve(s);}if(s.startsWith('FAULT')||s.startsWith('ERROR')||s.startsWith('STOPPED')||s.startsWith('EMERGENCY'))this.fail(new Error(s));}
 fail(e){for(const p of [...this.pending]){this.pending.delete(p);p.reject(e);}if(this.live)this.onFault?.(e);}
 expect(match,timeout=1500,signal){return new Promise((resolve,reject)=>{let timer;const done=(fn,v)=>{clearTimeout(timer);signal?.removeEventListener('abort',abort);this.pending.delete(p);fn(v);};const p={match,resolve:v=>done(resolve,v),reject:e=>done(reject,e)};const abort=()=>p.reject(new Error('Stopped'));if(signal?.aborted)return abort();this.pending.add(p);timer=setTimeout(()=>p.reject(new Error('Uno acknowledgement timed out')),timeout);signal?.addEventListener('abort',abort,{once:true});});}
 async send(s){if(!this.writer)throw new Error('Uno disconnected');const job=this.chain.then(()=>this.writer.write(new TextEncoder().encode(s+'\n')));this.chain=job.catch(()=>{});return job;}
 async connect(){
  if(!navigator.serial)throw new Error('Use Chrome or Edge for the Uno connection. Hardware is required.');
  if(this.port)await this.disconnect();
  this.port=await navigator.serial.requestPort();
  try{await this.port.open({baudRate:115200});this.writer=this.port.writable.getWriter();this.reader=this.port.readable.getReader();this.readTask=this.read();await new Promise(r=>setTimeout(r,1800));
   const identified=this.expect(s=>s==='AIMLAB_COMBINED_V7',2000);identified.catch(()=>{});await this.send('IDENTIFY');await identified;
   const stopped=this.expect(s=>s==='STOPPED: all outputs OFF');stopped.catch(()=>{});await this.send('5');await stopped;
   await this.testConnection();
  }catch(e){await this.disconnect();throw e;}
 }
 async testConnection(){
  if(!this.writer)throw new Error('Connect the Uno first');
  if(this.live)throw new Error('Connection is monitored during stimulation');
  const began=performance.now();
  const pong=this.expect(s=>s==='PONG',1000);pong.catch(()=>{});
  try{await this.send('PING');await pong;this.ready=true;this.lastCheck=new Date();this.latencyMs=Math.round(performance.now()-began);await this.send('STATUS');return this.latencyMs;}
  catch(e){this.ready=false;this.fail(e);this.onConnectionLost?.(e);throw e;}
 }
 async read(){let buffer='';const decoder=new TextDecoder();try{while(true){const {value,done}=await this.reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let i;while((i=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,i).trim();buffer=buffer.slice(i+1);if(line)this.line(line);}if(buffer.length>4096)throw new Error('Invalid serial stream');}}catch(e){this.fail(e);}finally{this.ready=false;const e=new Error('Uno connection closed');this.fail(e);this.onConnectionLost?.(e);}}
 async stimulate(condition,config,signal){
  if(!this.ready)throw new Error('Connect Uno and upload firmware v7.0 first');
  this.runLeadMs=condition==='D'?Number(config.thermalLeadMs||0):0;
  if(!Number.isInteger(this.runLeadMs)||this.runLeadMs<0||this.runLeadMs>2000)throw new Error('Invalid Peltier lead');
  this.runDurationMs=['C','D'].includes(condition)?Number(config.motionMs??5000):5000;
  if(!Number.isInteger(this.runDurationMs)||this.runDurationMs<1000||this.runDurationMs>8000||this.runDurationMs%100)throw new Error('Invalid motion duration');
  this.live=true;this.runStartedAt=null;this.runProgress=0;const began=performance.now();
  const ack=this.expect(s=>s===`ACK RUN ${condition}`,1200,signal);
  const done=this.expect(s=>s===`DONE RUN ${condition}`,1500+this.runDurationMs+this.runLeadMs,signal);
  // Attach rejection handlers immediately; both promises can reject on abort.
  ack.catch(()=>{});done.catch(()=>{});
  const pulse=setInterval(()=>this.send('PING\nSTATUS').catch(e=>this.fail(e)),200);
  try{await this.send(`RUN ${condition} ${config.polarity} ${config.thermalPwm} ${(config.motorPwms||[255,255,255,255]).join(' ')} ${this.runLeadMs} ${this.runDurationMs}`);await ack;const ackDelayMs=performance.now()-began;await done;return{ackDelayMs,elapsedMs:performance.now()-began,output:'hardware'};}
  finally{clearInterval(pulse);this.live=false;this.runStartedAt=null;this.send('5\nSTATUS').catch(()=>{});}
 }
 async settings(config){
  if(!this.live)return false;
  const ack=this.expect(s=>s==='ACK SET',1000);ack.catch(()=>{});
  try{await this.send(`SET ${config.polarity} ${config.thermalPwm} ${config.motorPwms.join(' ')}`);await ack;return true;}
  catch(e){this.fail(e);throw e;}
 }
 stop(){this.live=false;this.runStartedAt=null;this.fail(new Error('Stopped'));if(this.writer)this.send('!\n5\nSTATUS').catch(()=>{});}
 async disconnect(){this.stop();this.ready=false;try{await this.chain;await this.reader?.cancel();await this.readTask;this.reader?.releaseLock();this.writer?.releaseLock();await this.port?.close();}catch{}this.reader=null;this.writer=null;this.port=null;}
}
