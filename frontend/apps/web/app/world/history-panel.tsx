'use client';
import Link from 'next/link';
import {useState} from 'react';
import type {Commit} from '../../../../packages/protocol/types';
import {Icon} from '../components/icons';
import {explainDiff,sameSceneReference,type Capture,type Delta,type History} from './domain';

const rowSymbols={added:'+',missing:'−',moved:'↗',modified:'~',unchanged:'='};
export function HistoryPanel({history, capture, latest, before, after, rows, selectBefore, selectAfter,
  commit, checkout, addBranch, refresh, reconstruct, busy, diffStatus}:{
  history:History;capture:Capture|null;latest:Commit|undefined;before:Commit|undefined;after:Commit|undefined;
  rows:Delta[];selectBefore:(id:string)=>void;selectAfter:(id:string)=>void;commit:(branch:string,message:string)=>void;
  checkout:()=>void;addBranch:(name:string)=>void;refresh:()=>void;reconstruct:()=>void;busy:string;diffStatus:string;
}) {
  const [target,setTarget]=useState('main'),[message,setMessage]=useState(''),[name,setName]=useState('');
  const branches=Object.entries(history.branches);
  const frame=before&&after&&before.scene.frame===after.scene.frame?after.scene.frame:null;
  const compatible=before&&after&&sameSceneReference(before.scene,after.scene);
  return <>
    <div className="nw-titlebar">
      <div><div className="nw-eyebrow"><span/> 02 / REVISION CONTROL</div><h1>Version control</h1><p>Browse the room’s history and compare recorded layouts.</p></div>
      <div className="nw-actions">{<button className="nw-btn" disabled={!!busy} onClick={refresh}><Icon name="rotate"/>Pull from edge</button>}
        <button className="nw-btn nw-primary" disabled={!after} onClick={reconstruct}><Icon name="cube"/>Open 3D scene</button></div>
    </div>
    <div className="nw-history-grid">
      <section className="nw-panel"><div className="nw-panel-head"><div><h2>Commit graph</h2><p>{history.commits.length} REVISIONS <b>·</b> {branches.length} BRANCHES</p></div><Icon name="branch"/></div>
        {!history.commits.length&&<p className="nw-fine">No revisions yet. Capture a session and save its first snapshot.</p>}
        <ol className="nw-timeline">{history.commits.map(c=><li key={c.id}><span className="nw-commit-node"/>
          <button className="nw-revision" aria-pressed={after?.id===c.id} onClick={()=>selectAfter(c.id)}>
            <span className="nw-revision-title">{c.message}</span><span className="nw-revision-detail">{c.id.slice(0,8)} · {new Date(c.time*1000).toLocaleString()}</span>
            <span className="nw-branches">{branches.filter(([,id])=>id===c.id).map(([branch])=><span key={branch}><Icon name="branch" size={11}/>{branch}</span>)}</span>
            {c.parents.length>0&&<span className="nw-revision-detail">parent{c.parents.length>1?'s':''} {c.parents.map(id=>id.slice(0,8)).join(' + ')}</span>}
          </button>
        </li>)}</ol>
        {after&&<form className="nw-inline-form" onSubmit={e=>{e.preventDefault();addBranch(name.trim());setName('');}}>
          <input className="nw-field" value={name} onChange={e=>setName(e.target.value)} placeholder="Branch name" aria-label="New branch name" required pattern="[A-Za-z0-9_\-]{1,64}"/>
          <button className="nw-btn nw-tiny" disabled={!!busy}><Icon name="branch" size={14}/>Create branch</button>
        </form>}
        {<p className="nw-fine"><Link href="/studio/merge">Inspect merge conflicts and resolve on the edge ↗</Link></p>}
      </section>
      <div className="nw-side-stack">
        <section className="nw-panel"><div className="nw-panel-head"><div><h2>Spatial diff</h2><p>EDGE REVISION DATA</p></div><Icon name="cube"/></div>
          <div className="nw-history-select"><label>Base revision<select className="nw-field" value={before?.id??''} onChange={e=>selectBefore(e.target.value)}><option value="">Choose revision</option>{history.commits.map(c=><option key={c.id} value={c.id}>{c.message} · {c.id.slice(0,6)}</option>)}</select></label>
            <label>Compare to<select className="nw-field" value={after?.id??''} onChange={e=>selectAfter(e.target.value)}><option value="">Choose revision</option>{history.commits.map(c=><option key={c.id} value={c.id}>{c.message} · {c.id.slice(0,6)}</option>)}</select></label></div>
          {rows.length>0&&<ul className="nw-diff">{rows.map(row=><li key={row.id}><span>{rowSymbols[row.kind]}</span><strong>{row.label}</strong><small>{row.kind}</small></li>)}</ul>}
          <div className="nw-assistant"><div className="nw-eyebrow"><Icon name="bolt" size={14}/> SPATIAL ASSISTANT <span className="nw-chip">RULE BASED</span></div>
            <p>{diffStatus||(!before||!after?'Select two revisions to explain their differences.':!compatible?'These revisions use different spatial references; positions cannot be compared.':explainDiff(rows,(!before.evidence?.calibration||!after.evidence?.calibration)?null:frame))}</p>
            {rows.length>0&&<small>Describes stored snapshots. Objects absent from a snapshot may still be present in the room.</small>}
          </div>
          <div className="nw-panel-foot"><button className="nw-btn nw-tiny" disabled={!after} onClick={checkout}>Checkout digital scene</button>{latest&&<span>MAIN {latest.id.slice(0,8)}</span>}</div>
        </section>
        <section className="nw-panel"><div className="nw-panel-head"><div><h2>Commit a snapshot</h2><p>{capture ? 'SESSION '+capture.id.slice(0,8).toUpperCase() : 'AWAITING CAPTURE'}</p></div><Icon name="plus"/></div>
          <form className="nw-inline-form nw-commit-form" onSubmit={e=>{e.preventDefault();if(message.trim()){commit(target,message.trim());setMessage('');}}}>
            <label>Branch<select className="nw-field" value={target} onChange={e=>setTarget(e.target.value)}>{(branches.length?branches:[['main','']]).map(([branch])=><option key={branch}>{branch}</option>)}</select></label>
            <label>Message<input className="nw-field" placeholder={'Save observed layout'} value={message} onChange={e=>setMessage(e.target.value)} required maxLength={120}/></label>
            <button className="nw-btn nw-primary" disabled={!!busy||!latest}>Push observed commit</button>
          </form>
          {<p className="nw-fine">Uses fresh calibrated wall tracking. The four camera images alone do not produce object poses.</p>}
        </section>
      </div>
    </div>
  </>;
}
