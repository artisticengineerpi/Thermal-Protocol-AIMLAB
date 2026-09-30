import assert from 'node:assert/strict';
import {KEY,savePreset,readPresets} from './presets.mjs';
const db=new Map(),storage={getItem:k=>db.get(k),setItem:(k,v)=>db.set(k,v)};
const p={thermalPwm:164,motorPwms:[83,90,80,70],masterPwm:83,polarity:'C',thermalLeadMs:2000,motionMs:8100};
assert.throws(()=>savePreset(storage,'test',p));p.motionMs=8000;savePreset(storage,'Demo',p);assert.deepEqual(readPresets(storage)[0].settings,p);
savePreset(storage,'Demo',{...p,motionMs:1000});assert.equal(readPresets(storage).length,1);assert.equal(readPresets(storage)[0].settings.motionMs,1000);
savePreset(storage,'Second',{...p,motionMs:5100});assert.equal(readPresets(storage).length,2);assert.throws(()=>savePreset(storage,'Bad',{...p,motorPwms:[1,2,3]}));
const broken={getItem:()=>'{broken'};assert.throws(()=>readPresets(broken));assert.ok(db.has(KEY));console.log('PASS: preset roundtrip, named replacement, separate records, range validation and malformed storage');
