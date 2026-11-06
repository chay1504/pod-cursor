// Uses the original author's orientation and three-point calibration unchanged.
import fs from 'node:fs';
import readline from 'node:readline';
const original=new URL('../Sources/AirPointer/Session/Orientation.js',import.meta.url);
const source=fs.readFileSync(fs.existsSync(original)?original:new URL('./Orientation.js',import.meta.url),'utf8');
const {Orientation,Grip}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
let orientation=new Orientation(),grip=new Grip();
function state(){return {ready:orientation.ready,progress:orientation.settling(),q:orientation.q,
 gravity:orientation.accel?.vector??null,point:grip.point(orientation.q),calibrated:!!(grip.center&&grip.edges)};}
export function command(value){
 if(value.cmd==='reset'){orientation=new Orientation();grip=new Grip();}
 else if(value.cmd==='rows'){
  if(!Array.isArray(value.rows)||value.rows.length>4096)throw Error('Invalid motion batch');
  for(const row of value.rows){
   if(!Array.isArray(row)||row.length!==7||!row.every(Number.isFinite))throw Error('Invalid sensor row');
   orientation.feed(row);
  }
 }else if(['center','right','up'].includes(value.cmd)){
  if(!orientation.ready)throw Error('Set the case down until the sensor offset is ready.');
  if(value.cmd==='center')grip.setCenter(orientation.q,orientation.referenceGravity);
  else grip.setAxis(value.cmd,orientation.q);
 }else if(value.cmd!=='status')throw Error('Unknown orientation command');
 return state();
}
if(process.argv.includes('--self-test')){
 const assert=(value,message)=>{if(!value)throw Error(message);};
 const g=new Grip();g.setCenter([1,0,0,0],[0,0,-1]);
 const angle=.3;g.setAxis('right',[Math.cos(angle/2),0,0,Math.sin(angle/2)]);
 g.setAxis('up',[Math.cos(angle/2),0,Math.sin(angle/2),0]);
 assert(Math.abs(g.point([1,0,0,0])[0]-.5)<1e-8,'center X');
 assert(Math.abs(g.point([Math.cos(angle/2),0,0,Math.sin(angle/2)])[0]-1)<1e-8,'right edge');
 assert(Math.abs(g.point([Math.cos(angle/2),0,Math.sin(angle/2),0])[1])<1e-8,'top edge');
 const o=new Orientation();
 for(let i=1;i<=400;i++){
  o.feed([i*2,11,i*5000,i/200,0,0,-100000]);
  o.feed([i*2+1,12,i*5000,i/200,0,0,0]);
 }
 assert(o.ready,'still calibration');
 console.log('Original orientation: 4 offline checks passed');
}else{
 for await(const line of readline.createInterface({input:process.stdin,crlfDelay:Infinity})){
  try{console.log(JSON.stringify(command(JSON.parse(line))));}
  catch(error){console.log(JSON.stringify({error:String(error.message)}));}
 }
}
