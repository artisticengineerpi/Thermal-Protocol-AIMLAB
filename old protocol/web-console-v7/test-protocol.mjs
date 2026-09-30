import assert from 'node:assert/strict';
import {plan,LATIN,Experiment} from './protocol.mjs';
const sequence=plan();assert.equal(sequence.length,160);
for(let b=1;b<=5;b++)for(const c of 'ABCD')assert.equal(sequence.filter(t=>t.block===b&&t.condition===c).length,8);
for(let col=0;col<4;col++)assert.equal(new Set(LATIN.map(r=>r[col])).size,4);
const pairs=LATIN.flatMap(r=>[r.slice(0,2),r.slice(1,3),r.slice(2,4)]);assert.equal(new Set(pairs).size,12);
let time=0,logs=[],tones=[],views=[],stim=[],engine;
const config={seed:42,thermalPwm:159,polarity:'C'};
engine=new Experiment({now:()=>time,wait:async(ms)=>{time+=ms;},log:e=>logs.push(e),tone:f=>tones.push(f),progress:()=>{},stop:()=>{},finished:()=>{},stimulate:async(c)=>{stim.push(c);time+=5000;return{};},view:(s)=>{views.push(s);if(s==='ready')queueMicrotask(()=>engine.resume());if(s==='response')queueMicrotask(()=>{time+=250;engine.response(3);});}});
await engine.run(config);
assert.equal(logs.filter(e=>e.event==='response').length,160);assert.equal(stim.join(''),sequence.map(t=>t.condition).join(''));assert.equal(tones.length,480);assert.deepEqual(tones.slice(0,3),[500,1000,500]);assert.equal(views.filter(v=>v==='break').length,240);assert.equal(logs.at(-1).event,'session_complete');assert.ok(logs.filter(e=>e.event==='fixation').every(e=>e.ms>=3000&&e.ms<=4500));assert.ok(logs.filter(e=>e.event==='response').every(e=>e.rtMs===250));
for(const c of 'ABCD'){logs=[];tones=[];await engine.run(config,c,true);assert.equal(logs.filter(e=>e.event==='stimulus_complete').length,1);assert.equal(tones.length,0);assert.equal(logs.at(-1).event,'session_complete');}
let stops=0;
engine=new Experiment({log:e=>logs.push(e),view:s=>{if(s==='ready')queueMicrotask(()=>engine.resume());if(s==='fixation')queueMicrotask(()=>engine.stop());},tone:()=>{},progress:()=>{},stimulate:()=>{throw new Error('Should not stimulate after abort');},stop:()=>stops++,finished:()=>{}});
logs=[];await engine.run(config,'D');assert.equal(logs.at(-1).event,'session_aborted');assert.equal(logs.filter(e=>e.event==='response').length,0);assert.ok(stops>=1);
console.log('PASS: 160 trials, block counts, Latin positions and within-row carryover, all cues, breaks, responses, 4 debug modes, abort.');
