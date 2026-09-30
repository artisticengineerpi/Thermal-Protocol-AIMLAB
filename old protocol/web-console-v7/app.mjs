import {validatePreset,readPresets,savePreset} from './presets.mjs';
import {Experiment,CONDITIONS,RESPONSES} from './protocol.mjs';
import {Uno} from './serial.mjs';
import {masterLevels} from './live.mjs';
const $=id=>document.getElementById(id);
let audio=null,participant=null,session=null,lastView=['idle',{}],mode='hardware',connecting=false,probing=false;
const storageKey='aimlab-last-session-v2';
function settings(){return{motionMs:Math.round(Number($('motion').value)*1000),thermalLeadMs:Number($('lead').value),thermalPwm:Number($('thermal').value),motorPwms:[1,2,3,4].map(i=>Number($('motor'+i).value)),polarity:$('polarity').value};}
let desiredSettings=null,sendingSettings=false;
async function applySettings(){
 if(sendingSettings)return;sendingSettings=true;
 try{while(desiredSettings){const value=desiredSettings;desiredSettings=null;if(await serial.settings(value)){event({event:'settings_applied',...value,t:performance.now(),utc:new Date().toISOString()});$('settingsStatus').textContent='Live settings acknowledged by Uno';}else $('settingsStatus').textContent='Settings ready for the next test';}}
 catch(e){$('settingsStatus').textContent=`Settings not applied: ${e.message}`;if(serial.live)engine.stop();}
 finally{sendingSettings=false;}
}
function changeSettings(){$('thermal').dataset.polarity=$('polarity').value;for(const id of ['thermal','motor1','motor2','motor3','motor4'])$(id+'Value').textContent=$(id).value;const motors=settings().motorPwms;const equal=motors.every(v=>v===motors[0]);$('masterValue').textContent=equal?motors[0]:'Mixed';if(equal)$('master').value=motors[0];desiredSettings=settings();event({event:'settings_requested',...desiredSettings,t:performance.now(),utc:new Date().toISOString()});applySettings();}
const serial=new Uno(line=>{if(line!=='PONG'&&!line.startsWith('Mode:'))event({event:'serial',line,t:performance.now(),utc:new Date().toISOString()});});
function renderRig(){
 const state=serial.telemetry,age=state?performance.now()-state.receivedAt:Infinity,fresh=serial.ready&&age<(serial.live?1000:3500);
 $('rigStatus').textContent=fresh?'Live Uno status':serial.ready?'Status stale / waiting':'Disconnected · no telemetry';
 for(let i=1;i<=4;i++){const value=fresh?state.motors[i-1]:0,el=$('rigMotor'+i);el.style.setProperty('--level',`${value/255*100}%`);el.classList.toggle('active',fresh&&value>0);$('rigValue'+i).textContent=fresh?`${value} / 255`:'—';$('rigBar'+i).value=value;}
 const value=fresh?state.thermal:0,el=$('rigPeltier');el.className='actuator peltier '+(value>0?(state.polarity==='HOT'?'hot':'cold'):'off')+(value>0?' active':'');el.style.setProperty('--level',`${value/255*100}%`);$('rigThermal').textContent=fresh?`${value} / 255`:'—';$('rigPolarity').textContent=fresh?(value?state.polarity:'OFF'):'No status';$('rigThermalBar').value=value;
 if(serial.live&&serial.runStartedAt!=null){const elapsed=performance.now()-serial.runStartedAt;serial.runProgress=Math.min(elapsed/((serial.runDurationMs||5000)+(serial.runLeadMs||0)),1);$('rigTime').textContent=elapsed<(serial.runLeadMs||0)?`Preheat · ${(elapsed/1000).toFixed(1)} s`:`Motion · ${((elapsed-(serial.runLeadMs||0))/1000).toFixed(1)} / ${((serial.runDurationMs||5000)/1000).toFixed(1)} s`;}else $('rigTime').textContent=serial.runProgress===1?'Complete':'Idle / stopped';
 $('rigProgress').value=serial.runProgress||0;
}
setInterval(renderRig,100);
function event(e){if(session){session.events.push(e);localStorage.setItem(storageKey,JSON.stringify(session));}$('events').textContent=(session?.events||[e]).slice(-12).map(x=>`${x.event}${x.condition?' '+x.condition:''}${x.line?' · '+x.line:''}${x.reason?' · '+x.reason:''}`).join('\n');}
function tone(hz){if(!audio||audio.state!=='running')throw new Error('Audio unavailable: click Test cues before starting.');const oscillator=audio.createOscillator(),gain=audio.createGain();oscillator.frequency.value=hz;gain.gain.setValueAtTime(0,audio.currentTime);gain.gain.linearRampToValueAtTime(.12,audio.currentTime+.01);gain.gain.setValueAtTime(.12,audio.currentTime+.13);gain.gain.linearRampToValueAtTime(0,audio.currentTime+.15);oscillator.connect(gain).connect(audio.destination);oscillator.start();oscillator.stop(audio.currentTime+.16);event({event:'audio_cue',hz,durationMs:150,t:performance.now(),utc:new Date().toISOString()});}
async function unlockAudio(){audio??=new AudioContext();await audio.resume();if(audio.state!=='running')throw new Error('Audio could not start');}
function renderView(doc,target,state,data){
 target.replaceChildren();const add=(tag,text,cls)=>{const el=doc.createElement(tag);el.textContent=text;if(cls)el.className=cls;if(tag==='button')el.className='btn btn-outline-primary btn-sm';target.append(el);return el;};
 if(state==='fixation'){add('div','+','fixation');return;}
 if(state==='stimulation')return;
 if(state==='ready'){add('h2',data.block?`Block ${data.block} of 5`:'Ready to begin');add('p','Remain still. Watch the fixation cross and attend to the sensation.');add('p','After each trial, choose the sensation you perceived.');add('button','Continue · Space').onclick=()=>engine.resume();}
 else if(state==='question'||state==='response'){add('h2','What did you feel?');if(state==='response'){RESPONSES.forEach((r,i)=>{add('button',`${i+1} · ${r}`).onclick=()=>engine.response(i+1);});}else add('p','Response options will appear shortly.');}
 else if(state==='break'){add('h2','Rest');add('p',`${data.remaining} seconds remaining`);add('p',`Next: block ${data.nextBlock} of 5`);}
 else if(state==='complete'){add('h2','Session complete');add('p','Thank you. All outputs are off.');}
 else if(state==='aborted'){add('h2','Session stopped');add('p','Please wait for the experimenter.');}
 else{add('h2','Ready');add('p','Remain still and watch the screen.');}
}
function view(state,data={}){lastView=[state,data];$('phase').textContent=`Phase: ${state}${data.remaining?' · '+data.remaining+' s':''}`;renderView(document,$('display'),state,data);if(participant&&!participant.closed)renderView(participant.document,participant.document.getElementById('screen'),state,data);}
function controls(){const locked=engine.active||connecting||probing;document.querySelectorAll('#motion,#loadPreset,#lead,#start,[data-condition],#output,#participant,#seed,#cues,#connect,#disconnect,#audio,#recover').forEach(e=>e.disabled=locked);document.querySelectorAll('#start,[data-condition]').forEach(e=>e.disabled=locked||!serial.ready);$('connect').disabled=locked||serial.ready;$('disconnect').disabled=locked||!serial.port;$('testConnection').disabled=locked||!serial.writer;$('continue').disabled=!engine.acceptContinue;$('connection').textContent=connecting?'Connecting…':probing?'Testing connection…':serial.ready?'CONNECTED · Uno v7.0':'DISCONNECTED';$('connection').className='badge rounded-pill '+(serial.ready?'text-bg-success':'text-bg-secondary');}
const engine=new Experiment({
 log:event,view,tone,settings,
 progress:(trial,total)=>{$('progress').textContent=`Trial ${trial.number}/${total} · Block ${trial.block} · ${trial.condition}: ${CONDITIONS[trial.condition]}`;$('bar').max=total;$('bar').value=trial.number-1;},
 stimulate:(condition,config,signal)=>serial.stimulate(condition,config,signal),
 stop:()=>serial.stop(),
 finished:()=>{if(session?.events.at(-1)?.event==='session_complete')$('bar').value=$('bar').max;controls();}
});
serial.onFault=e=>{event({event:'hardware_fault',reason:e.message});engine.stop();};
serial.onConnectionLost=e=>{$('connectionDetail').textContent=e.message;controls();if(engine.active){event({event:'connection_lost',reason:e.message});engine.stop();}};
async function checkConnection(){if(probing||connecting||serial.live||!serial.writer)return;probing=true;controls();try{const ms=await serial.testConnection();$('connectionDetail').textContent=`PING/PONG passed · ${ms} ms · ${serial.lastCheck.toLocaleTimeString()}`;}catch(e){$('connectionDetail').textContent=`Connection failed: ${e.message}`;}finally{probing=false;controls();}}
async function start(condition=null){
 if(engine.active||connecting||probing)return;
 try{
  const thermalPwm=Number($('thermal').value),seed=Number($('seed').value),participantCode=$('participant').value.trim();
  if(!participantCode||!Number.isInteger(thermalPwm)||thermalPwm<0||thermalPwm>255||!Number.isInteger(seed)||seed<0||seed>4294967295)throw new Error('Enter a session code, integer PWM 0–255 and seed 0–4294967295.');
  if(!serial.ready)throw new Error('Connect the Uno first.');
  await unlockAudio();
  const config={participantCode,seed,...settings(),motorTiming:{soaMs:settings().motionMs/5,durationMs:settings().motionMs*2/5,rampMs:settings().motionMs/10},pins:[5,6,3,11],output:mode,protocolVersion:'7.0-no-eeg',combinedThermalEnd:'motor-sequence-end',cueMs:150};
  session={id:`${new Date().toISOString()}-${participantCode}`,config,events:[]};
  localStorage.setItem(storageKey,JSON.stringify(session));
  $('progress').textContent=condition?`Single condition · ${CONDITIONS[condition]}`:'Full experiment · 160 trials';$('bar').value=0;$('bar').max=condition?1:160;
  const task=engine.run(config,condition,!!condition&&(condition>='E'||!$('cues').checked));controls();await task;
 }catch(e){serial.stop();$('phase').textContent=e.message;}finally{controls();}
}
$('start').onclick=()=>{$('setup').close();start();};document.querySelectorAll('[data-condition]').forEach(b=>b.onclick=()=>start(b.dataset.condition));
for(const id of ['thermal','motor1','motor2','motor3','motor4'])$(id).oninput=changeSettings;$('polarity').onchange=changeSettings;
$('master').oninput=()=>{masterLevels($('master').value).forEach((v,i)=>$('motor'+(i+1)).value=v);changeSettings();};
$('lead').oninput=()=>{$('leadValue').textContent=$('lead').value+' ms';};
$('continue').onclick=()=>engine.resume();$('stop').onclick=()=>engine.stop();
$('connect').onclick=async()=>{connecting=true;controls();try{await serial.connect();$('connectionDetail').textContent=`Firmware verified + PING/PONG passed · ${serial.latencyMs} ms`;}catch(e){$('phase').textContent=e.message;$('connectionDetail').textContent=e.message;}finally{connecting=false;controls();}};
$('testConnection').onclick=checkConnection;
setInterval(()=>{if(serial.ready&&!engine.active&&!connecting)checkConnection();},2000);
$('disconnect').onclick=async()=>{await serial.disconnect();controls();};$('output').onchange=controls;
$('audio').onclick=async()=>{try{await unlockAudio();tone(500);setTimeout(()=>tone(1000),400);}catch(e){$('phase').textContent=e.message;}};
function keys(e){if(e.code==='Escape'){e.preventDefault();engine.stop();return;}if(/INPUT|SELECT|TEXTAREA/.test(e.target.tagName))return;if(e.repeat)return;if(e.code==='Space'){e.preventDefault();engine.resume();}const n=Number(e.key);if(n>=1&&n<=5){e.preventDefault();engine.response(n);}}
document.addEventListener('keydown',keys);
$('participantWindow').onclick=()=>{participant=window.open('','aimlab-participant','width=1100,height=800');if(!participant){$('phase').textContent='Allow the participant popup, then try again.';return;}participant.document.open();participant.document.write('<!doctype html><html><head><title>AIMLAB Participant</title><link rel="stylesheet" href="vendor/bootstrap-5.3.8.min.css"><link rel="stylesheet" href="style.css"><style>body{margin:0;background:#fff}.participant{height:100vh;border:0}h2{font-size:32px}p,button{font-size:22px}</style></head><body><div id="screen" class="participant"></div></body></html>');participant.document.close();participant.document.addEventListener('keydown',keys);renderView(participant.document,participant.document.getElementById('screen'),...lastView);};
function download(name,content,type){const link=document.createElement('a'),url=URL.createObjectURL(new Blob([content],{type}));link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function filename(){return 'AIMLAB-'+(session?.config.participantCode||'session').replace(/[^a-z0-9_-]/gi,'_');}
$('json').onclick=()=>{if(session)download(filename()+'.json',JSON.stringify(session,null,2),'application/json');};
$('csv').onclick=()=>{if(!session)return;const columns=['number','block','inBlock','condition','answer','label','rtMs','event','reason'];const quote=v=>'"'+String(v??'').replaceAll('"','""')+'"';const rows=session.events.filter(e=>e.event==='response'||e.event==='trial_aborted');download(filename()+'.csv',['session,output,'+columns.join(','),...rows.map(r=>[session.id,session.config.output,...columns.map(k=>r[k])].map(quote).join(','))].join('\r\n'),'text/csv');};
$('recover').onclick=()=>{const saved=localStorage.getItem(storageKey);if(saved)download('AIMLAB-recovered-session.json',saved,'application/json');else $('phase').textContent='No saved session found.';};
setInterval(()=>{controls();if(engine.active&&participant?.closed){event({event:'participant_display_closed'});participant=null;engine.stop();}},250);
window.addEventListener('pagehide',()=>engine.stop());window.addEventListener('beforeunload',e=>{if(engine.active){engine.stop();e.preventDefault();e.returnValue='';}});
controls();


document.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>$(b.dataset.open).showModal());
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$(b.dataset.close).close());

$('motion').oninput=()=>{$('motionValue').textContent=Number($('motion').value).toFixed(1)+' s';};
function refreshPresets(selected=''){const list=$('presetList');list.replaceChildren(new Option('Saved presets',''));for(const p of readPresets(localStorage))list.add(new Option(p.name,p.name));list.value=selected;}
try{refreshPresets();}catch(e){$('presetStatus').textContent=e.message;}
$('savePreset').onclick=()=>{try{const name=$('presetName').value.trim()||'Quick preset';savePreset(localStorage,name,{...settings(),masterPwm:Number($('master').value)});refreshPresets(name);$('presetName').value=name;$('presetStatus').textContent='Saved';}catch(e){$('presetStatus').textContent=e.message;}};
$('loadPreset').onclick=()=>{if(engine.active||connecting||probing)return;try{const saved=readPresets(localStorage).find(p=>p.name===$('presetList').value);if(!saved)throw new Error('Choose a preset');const p=validatePreset(saved.settings);$('thermal').value=p.thermalPwm;p.motorPwms.forEach((v,i)=>$('motor'+(i+1)).value=v);$('master').value=p.masterPwm;$('polarity').value=p.polarity;$('lead').value=p.thermalLeadMs;$('motion').value=p.motionMs/1000;$('lead').oninput();$('motion').oninput();$('presetName').value=saved.name;changeSettings();$('presetStatus').textContent='Loaded';}catch(e){$('presetStatus').textContent=e.message;}};

document.querySelectorAll('[data-stop]').forEach(b=>b.onclick=()=>engine.stop());
