// Values reported by firmware are commanded PWM, not measured temperature/motion.
export function parseStatus(line){
 const m=/^Mode: (.+) \| Peltier PWM=(\d+) polarity=(HOT|COLD) \| Motors PWM=(\d+),(\d+),(\d+),(\d+)$/.exec(line);
 if(!m)return null;
 const values=[m[2],...m.slice(4)].map(Number);
 if(values.some(v=>v<0||v>255))return null;
 return{mode:m[1],thermal:values[0],polarity:m[3],motors:values.slice(1)};
}
export function masterLevels(value){const n=Number(value);if(!Number.isInteger(n)||n<0||n>255)throw new Error('PWM must be 0..255');return[n,n,n,n];}
