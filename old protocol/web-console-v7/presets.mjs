export const KEY='aimlab-presets-v1';
export function validatePreset(p){
 const integer=(v,min,max,step=1)=>Number.isInteger(v)&&v>=min&&v<=max&&v%step===0;
 if(!p||!integer(p.thermalPwm,0,255)||!Array.isArray(p.motorPwms)||p.motorPwms.length!==4||!p.motorPwms.every(v=>integer(v,0,255))||!['H','C'].includes(p.polarity)||!integer(p.masterPwm,0,255)||!integer(p.thermalLeadMs,0,2000,10)||!integer(p.motionMs,1000,8000,100))throw new Error('Invalid preset values');
 return {thermalPwm:p.thermalPwm,motorPwms:[...p.motorPwms],masterPwm:p.masterPwm,polarity:p.polarity,thermalLeadMs:p.thermalLeadMs,motionMs:p.motionMs};
}
export function readPresets(storage){const data=JSON.parse(storage.getItem(KEY)||'[]');if(!Array.isArray(data))throw new Error('Invalid preset storage');return data.map(p=>{if(typeof p.name!=='string'||!p.name.trim()||p.name.length>60)throw new Error('Invalid preset name');return{name:p.name,settings:validatePreset(p.settings)};});}
export function savePreset(storage,name,settings){if(typeof name!=='string'||!name.trim()||name.trim().length>60)throw new Error('Enter a preset name');name=name.trim();const all=readPresets(storage),record={name,settings:validatePreset(settings)},index=all.findIndex(p=>p.name===name);if(index<0)all.push(record);else all[index]=record;storage.setItem(KEY,JSON.stringify(all));return record;}
