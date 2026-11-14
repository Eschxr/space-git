'use client';
import Link from 'next/link';
import {useEffect,useState} from 'react';
import gallery from '../../../../fixtures/gallery.json';
import replay from '../../../../fixtures/replay.json';
import type {Live,Pair} from '../../../../packages/protocol/types';
import {OverlayView} from './overlay';
import {Icon} from './icons';

const card=gallery.objects[0], length=replay.offsets_m.length, duration=replay.period_ms*length;
const project=(x:number,y:number):Pair=>[.08+.84*x/gallery.wall[0],.91-.82*y/gallery.wall[1]];
const dest=project(card.x,card.y);
const outline=([[-1,-1],[1,-1],[1,1],[-1,1]] as Pair[]).map(([x,y])=>project(card.x+x*card.w/2,card.y+y*card.h/2));
function sample(ms:number):Live{
 const i=Math.min(length-1,Math.floor(ms/replay.period_ms)),offset=replay.offsets_m[i],x=card.x+offset,y=card.y-offset*.4,
   moved=Math.hypot(offset,offset*.4),hold=i>=13,done=ms>=duration;
 const start=project(x,y);
 return {version:1,scene_version:1,seq:i,timestamp:0,received_ms:0,device:'bundled-gallery',mode:'demo',camera:false,poses:[],
  anchors:[],calibration:null,plan:null,state:done?'VERIFIED':hold?'NEAR_TARGET':'MOVING',
  overlay:{from:start,to:dest,arrow:hold?undefined:[start,project((x+card.x)/2,(y+card.y)/2+.08),dest],
   outline,ticks:[[project(card.x-.03,card.y),project(card.x+.03,card.y)],[project(card.x,card.y-.03),project(card.x,card.y+.03)]],
   distance_m:moved,name:card.name,dwell:Math.max(0,Math.min(1,(i-13)/14)),progress:done?1:0}};
}
export function Rehearsal(){
 const [ms,setMs]=useState(0),[playing,play]=useState(false);
 useEffect(()=>{
  if(!playing)return;
  const start=performance.now();
  const timer=setInterval(()=>{
   const elapsed=performance.now()-start;
   setMs(Math.min(elapsed,duration));if(elapsed>=duration){play(false);clearInterval(timer);}
  },replay.period_ms);
  return()=>clearInterval(timer);
 },[playing]);
 return <div className="split-view"><section className="panel form-panel">
  <div className="panel-heading"><Icon name="target"/><div><h2>Rehearse a move</h2><p>Follow a saved sequence from the bundled gallery. This preview works without hardware.</p></div></div>
  <div className="projection-preview"><OverlayView event={sample(ms)}/></div>
  <button className="btn primary" disabled={playing} onClick={()=>{setMs(0);play(true);}}><Icon name="rotate"/> Play simulated move</button>
  <p className="muted" role="status">{ms>=duration?'Replay verified · simulated only':playing?'Playing bundled poses…':'Demo fixture · no camera or projector connected'}</p>
 </section><section className="panel form-panel"><div className="panel-heading"><Icon name="screen"/><div><h2>From screen to wall</h2><p>The local workstation calibrates both devices against the same wall and uses fresh frames for each physical check.</p></div></div>
  <Link className="btn" href="/setup">Hardware setup <Icon name="arrow"/></Link><Link className="btn" href="/studio/3d">Explore the gallery in 3D <Icon name="arrow"/></Link>
 </section></div>;
}
