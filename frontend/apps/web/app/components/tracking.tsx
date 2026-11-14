'use client';

import {useState} from 'react';
import Link from 'next/link';
import type {Live,Pair} from '../../../../packages/protocol/types';
import {api} from './connection';
import {CameraPreview} from './setup';
import type {HistoryData,Run} from './workflows';

type Box=[number,number,number,number];

export function Tracking({event,token,data,run,refresh}:{event:Live|null;token:string;data:HistoryData;run:Run;refresh:()=>Promise<void>}){
 const [points,setPoints]=useState<Pair[]>([]),[name,setName]=useState(''),[selecting,setSelecting]=useState(false);
 const [objectId,setObjectId]=useState(''),[branch,setBranch]=useState('main'),[message,setMessage]=useState('');
 const [busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const tracked=event?.tracked??[];
 const previous=[...new Map(data.commits.flatMap(rev=>rev.scene.objects.map(object=>[object.id,object] as const))).values()];
 const box:Box|null=points.length===2?[
  Math.min(points[0][0],points[1][0]),Math.min(points[0][1],points[1][1]),
  Math.max(points[0][0],points[1][0]),Math.max(points[0][1],points[1][1]),
 ]:null;
 const boxes=tracked.map(t=>({id:t.id,name:t.name,bbox:t.bbox,active:t.confidence>=.65}));
 if(box)boxes.push({id:'selection',name:'Selection',bbox:box,active:false});
 const available=!!(event?.camera&&event.calibration&&event.units);
 const units=event?.units==='normalized'?'workspace units':'m';
 const pick=(p:Pair)=>setPoints(points.length===2?[p]:[...points,p]);
 async function apply(action:()=>Promise<void>){
  setBusy(true);setNotice('');
  try{await run(action);}finally{setBusy(false);}
 }
 return <>
  <CameraPreview token={event?.camera?token:''} boxes={boxes} onPoint={selecting?pick:undefined}/>
  {!available&&<p className="muted">Connect a camera and define a workspace before selecting an object. <Link href="/setup">Open Setup</Link></p>}
  {available&&<div className="inline"><button className="btn" disabled={busy} onClick={()=>{setPoints([]);setSelecting(true);setObjectId('');setName('');}}>Select object</button>
   {tracked.length>0&&<span className="muted">{tracked.filter(t=>t.confidence>=.65).length}/{tracked.length} confidently tracked</span>}</div>}
  {selecting&&<div className="stack">
   <p>Click two opposite corners to box the object. Select again or edit the box before confirming.</p>
   <div className="fields"><label>Object name<input value={name} maxLength={80} onChange={e=>setName(e.target.value)}/></label>
    <label>Identity<select value={objectId} onChange={e=>{setObjectId(e.target.value);setName(previous.find(o=>o.id===e.target.value)?.name??'');}}>
     <option value="">New object</option>{previous.map(o=><option key={o.id} value={o.id}>{o.name}</option>)}
    </select></label>
   </div>
   {box&&<div className="fields">{['Left','Top','Right','Bottom'].map((label,i)=><label key={label}>{label} (px)<input type="number" min={0} value={Math.round(box[i])} onChange={e=>{
    const adjusted=[...box];adjusted[i]=e.target.valueAsNumber;
    setPoints([[adjusted[0],adjusted[1]],[adjusted[2],adjusted[3]]]);
   }}/></label>)}</div>}
   <div className="inline"><button className="btn primary" disabled={!available||busy||!box||!name.trim()} onClick={()=>void apply(async()=>{
    await api(token,'/tracking',{name:name.trim(),box,object_id:objectId||null});
    setSelecting(false);setPoints([]);
   })}>Start tracking</button><button className="btn" onClick={()=>{setSelecting(false);setPoints([]);}}>Cancel selection</button></div>
  </div>}
  {tracked.length>0&&<ul className="diff-list">{tracked.map(t=><li key={t.id}>
   <strong>{t.name}</strong> · {t.status} · {Math.round(t.confidence*100)}% confidence
   {t.confidence>=.65&&<span> · {t.x.toFixed(3)}, {t.y.toFixed(3)} {units}</span>}
   <div className="inline"><button className="btn tiny" onClick={()=>{setObjectId(t.id);setName(t.name);setPoints([]);setSelecting(true);}}>Reselect</button>
    <button className="btn tiny" onClick={()=>void apply(async()=>{await api(token,'/tracking/'+t.marker,undefined,'DELETE');})}>Stop tracking</button></div>
  </li>)}</ul>}
  {tracked.length>0&&event?.units==='normalized'&&<p className="muted">Positions are normalized. Enter measured dimensions in Setup to commit a metric layout and restore it.</p>}
  {tracked.length>0&&event?.units==='m'&&<div className="stack">
   <div className="fields"><label>Commit branch<select value={branch} onChange={e=>setBranch(e.target.value)}>{Object.keys(data.branches).map(b=><option key={b}>{b}</option>)}</select></label>
    <label>Commit message<input value={message} onChange={e=>setMessage(e.target.value)} maxLength={120} placeholder="Describe the observed layout"/></label></div>
   <button className="btn primary" disabled={busy||!message.trim()||!data.branches[branch]||tracked.some(t=>t.confidence<.65)} onClick={()=>void apply(async()=>{
    const result=await api<{id:string}>(token,'/tracking/commit',{branch,expected:data.branches[branch],message:message.trim()});
    await refresh();setMessage('');setNotice('Observed layout saved as '+result.id.slice(0,8)+'.');
   })}>Commit observed layout</button>
  </div>}
  {notice&&<p role="status">{notice}</p>}
 </>;
}
