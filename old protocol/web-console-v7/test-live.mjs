import assert from 'node:assert/strict';
import {parseStatus,masterLevels} from './live.mjs';
assert.deepEqual(parseStatus('Mode: PROTOCOL | Peltier PWM=160 polarity=HOT | Motors PWM=190,80,0,0'),{mode:'PROTOCOL',thermal:160,polarity:'HOT',motors:[190,80,0,0]});
assert.equal(parseStatus('Mode: IDLE | Peltier PWM=0 polarity=COLD | Motors PWM=0,0,0,0').polarity,'COLD');
assert.equal(parseStatus('PONG'),null);assert.equal(parseStatus('Mode: IDLE | Peltier PWM=256 polarity=HOT | Motors PWM=0,0,0,0'),null);
assert.deepEqual(masterLevels(190),[190,190,190,190]);assert.deepEqual(masterLevels(0),[0,0,0,0]);assert.throws(()=>masterLevels(256));
console.log('PASS: reported PWM parser, hot/cold/off states, invalid status, master motor levels.');
