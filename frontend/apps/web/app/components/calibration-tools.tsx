'use client';
import {useEffect,useState} from 'react';
import type {Pair} from '../../../../packages/protocol/types';
import {api,type Wizard} from './connection';
import {Icon} from './icons';

export type Lens={id:string;views:number;rms_px:number};
export type Residual={target:Pair;predicted:Pair;error_px:number};
type Diagnostics={
 software_latency:{count:number;p50_ms:number|null;p95_ms:number|null};
 stability:{marker:number;frames:number;p50_mm:number;p95_mm:number}[];
 physical:{time:number;expected:Pair;measured:Pair;dx_mm:number;dy_mm:number;error_mm:number}[];
};
export function LensTool({token,enabled,views,lens}:{token:string;enabled:boolean;views:number;lens:Lens|null}){
 const [feedback,set]=useState(''),[busy,setBusy]=useState(false);
 async function run(path:string,method?:string){
  setBusy(true);set('');
  try{
   const r=await api<{views:number;rms_px?:number}>(token,'/calibration/lens/'+path,method?undefined:{},method);
   set(r.rms_px===undefined?(r.views?'Captured '+r.views+' distinct views.':'View set cleared.'):'Lens fit saved · '+r.rms_px.toFixed(2)+' px RMS. Recalibrate the wall next.');
  }catch(e){set((e as Error).message);}finally{setBusy(false);}
 }
 return <details className="lens-tool"><summary>Optional lens correction · checkerboard</summary>
  <p className="muted">Print the 10 × 7 board with <code>python scripts/checkerboard.py</code>. Show it to the camera at varied distances, tilts and positions. A new lens fit invalidates the wall calibration.</p>
  <div className="inline"><span className="pill">{views}/10 minimum · up to 24</span>
   {lens&&<span className="pill green">Saved lens fit · {lens.rms_px.toFixed(2)} px RMS</span>}
   <button className="btn tiny" disabled={!enabled||busy||views>=24} onClick={()=>run('sample')}>Sample checkerboard</button>
   <button className="btn tiny" disabled={!enabled||busy||views<10} onClick={()=>run('solve')}>Estimate intrinsics</button>
   <button className="btn tiny" disabled={!enabled||busy||!views} onClick={()=>run('samples','DELETE')}>Clear samples</button>
  </div>{feedback&&<p role="status" className="notice">{feedback}</p>}
 </details>;
}
export function ResidualPlot({residuals}:{residuals:Residual[]}){
 if(!residuals.length)return null;
 return <div className="residual-view"><div>
  <svg viewBox="0 0 400 224" aria-label="Projector validation residuals with error vectors magnified by 12">
  <rect x="1" y="1" width="398" height="222" rx="8" fill="#0B111A" stroke="#355061"/>
  {residuals.map(({target,predicted},i)=>{
   const [x,y]=[target[0]*400,target[1]*224], u=x+12*(predicted[0]-target[0])*400,v=y+12*(predicted[1]-target[1])*224;
   return <g key={i}><line x1={x} y1={y} x2={u} y2={v} stroke="#FFD38D" strokeWidth="2"/>
    <circle cx={x} cy={y} r="4" fill="none" stroke="#75DAE9"/><circle cx={u} cy={v} r="2" fill="#FFD38D"/>
    <text x={x+9} y={y-7} fill="#F5F7FA" fontSize="11">{i+1}</text></g>;
  })}</svg>
  <p className="muted">Independent validation crosses · error vectors enlarged ×12</p>
 </div><ol>{residuals.map((r,i)=><li key={i}><span>Cross {i+1}</span><strong className="mono">{r.error_px.toFixed(2)} px</strong></li>)}</ol></div>;
}
export function PhysicalDiagnostics({token,enabled,wizard}:{token:string;enabled:boolean;wizard:Wizard|null}){
 const [data,set]=useState<Diagnostics|null>(null),[expected,want]=useState<Pair>([.6,.4]),[measured,read]=useState<Pair>([.6,.4]);
 const [feedback,msg]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{
  if(!token)return;
  let running=true;
  const poll=()=>api<Diagnostics>(token,'/calibration/diagnostics').then(v=>{if(running)set(v);}).catch(()=>{});
  void poll();const timer=setInterval(poll,1250);
  return()=>{running=false;clearInterval(timer);};
 },[token]);
 const cross=wizard?.kind==='physical'?wizard:null,timing=token?data?.software_latency:null;
 async function run(fn:()=>Promise<unknown>,note:string){setBusy(true);msg('');try{await fn();msg(note);}catch(e){msg((e as Error).message);}finally{setBusy(false);}}
 const edit=(v:Pair,i:number,x:string):Pair=>i===0?[Number(x),v[1]]:[v[0],Number(x)];
 return <section className="panel form-panel"><div className="panel-heading"><span className="step">04</span><div><h2>Check accuracy on the wall</h2><p>Project an independent reference and measure its center from anchor 0. Measurements here are separate from calibration pixel residuals.</p></div></div>
 <div className="fields">{[0,1].map(i=><label key={i}>Expected {i?'Y':'X'} (m)<input type="number" step=".001" disabled={!!cross} value={expected[i]} onChange={e=>want(edit(expected,i,e.target.value))}/></label>)}</div>
 <button className="btn" disabled={!enabled||!!wizard||busy} onClick={()=>run(async()=>{await api(token,'/calibration/physical-target',{xy:expected});read(expected);},'Cross requested. Wait for it on the wall before measuring.')}>Project reference cross</button>
 {cross&&<><div className="fields">{[0,1].map(i=><label key={i}>Measured {i?'Y':'X'} (m)<input type="number" step=".001" value={measured[i]} onChange={e=>read(edit(measured,i,e.target.value))}/></label>)}</div>
  <div className="inline"><button className="btn primary" disabled={!cross.shown||busy} onClick={()=>run(()=>api(token,'/calibration/physical-report',{key:cross.key,xy:measured}),'Ruler measurement saved against this calibration.')}>Save wall measurement</button>
   <button className="btn" disabled={busy} onClick={()=>run(()=>api(token,'/calibration/point/-1',{}),'Reference cancelled.')}>Cancel reference</button></div></>}
 {feedback&&<p role="status" className="notice">{feedback}</p>}
 <div className="quality-grid">
  <div><small>PHYSICAL WALL ERROR</small><strong>{token&&data?.physical.length?Math.max(...data.physical.map(p=>p.error_mm)).toFixed(1)+' mm worst':'Not measured'}</strong><p>{token&&data?.physical.length?data.physical.length+' ruler measurements · current calibration':'Requires a ruler and a projected cross'}</p></div>
  <div><small>SOFTWARE TIMING · NOT PHYSICAL</small><strong>{timing?.count?timing.p50_ms?.toFixed(1)+' / '+timing.p95_ms?.toFixed(1)+' ms':'No samples'}</strong><p>p50 / p95 · camera read to render callback</p></div>
  <div><small>RECENT POSE SPREAD</small><strong>{token&&data?.stability.length?data.stability[0].p95_mm.toFixed(1)+' mm p95':'No stable sample'}</strong><p>{token&&data?.stability.length?'Marker '+data.stability[0].marker+' · '+data.stability[0].frames+' recent frames. Hold it still to measure jitter.':'Hold a visible card still for eight seconds.'}</p></div>
 </div>
 {token&&!!data?.physical.length&&<details className="lens-tool"><summary><Icon name="target" size={13}/> Recorded physical residuals</summary>
  <ul className="diff-list">{data.physical.map(p=><li key={p.time}>({p.expected.map(v=>v.toFixed(3)).join(', ')}) m · {p.error_mm.toFixed(1)} mm total · ΔX {p.dx_mm.toFixed(1)} / ΔY {p.dy_mm.toFixed(1)} mm</li>)}</ul></details>}
 </section>;
}
