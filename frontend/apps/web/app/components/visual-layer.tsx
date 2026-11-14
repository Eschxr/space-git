'use client';
import {useState} from 'react';
import type {VisualPlacement} from '../../../../packages/protocol/types';
import {Icon} from './icons';

export const defaultPlacement=(commit=''):VisualPlacement=>({commit,position_m:[0,0,0],rotation_deg:[0,0,0],scale:1,reference_m:null,reference_units:null});
export function VisualLayer({value,change,focus,setFocus,registered,save,busy}:{
 value:VisualPlacement;change:(v:VisualPlacement)=>void;focus:boolean;setFocus:(v:boolean)=>void;registered:boolean;save:()=>void;busy:boolean;
}){
 const [refMeters,setMeters]=useState(value.reference_m??1),[refUnits,setUnits]=useState(value.reference_units??1);
 const setAxis=(field:'position_m'|'rotation_deg',axis:number,n:number)=>{
  const tuple=[...value[field]] as VisualPlacement[typeof field];tuple[axis]=n;change({...value,[field]:tuple});
 };
 const fit=refMeters/refUnits,canFit=refMeters>0&&refMeters<=30&&refUnits>0&&refUnits<=1000000&&fit>=.000001&&fit<=10000;
 return <section className="panel form-panel">
  <div className="panel-heading"><Icon name="cube"/><div><h2>Visual geometry layer</h2><p>Orbit the raw reconstruction or place a visual reference over the wall. These controls never change marker positions or revision history.</p></div></div>
  <div className="inline"><button className={'btn '+(focus?'primary':'')} onClick={()=>setFocus(true)}>Orbit mesh</button>
   <button className={'btn '+(!focus?'primary':'')} onClick={()=>setFocus(false)}>Overlay on wall</button>
   <span className="pill">{value.reference_m?'SCALE SET BY REFERENCE':'ARBITRARY SCALE'}</span></div>
  <div className="fields">{(['X','Y','Z'] as const).map((axis,i)=><label key={axis}>Position {axis} (m)<input type="number" min={-100} max={100} step=".01" value={value.position_m[i]} onChange={e=>setAxis('position_m',i,Number(e.target.value))}/></label>)}</div>
  <div className="fields">{(['X','Y','Z'] as const).map((axis,i)=><label key={axis}>Rotation {axis} (°)<input type="number" min={-360} max={360} step="1" value={value.rotation_deg[i]} onChange={e=>setAxis('rotation_deg',i,Number(e.target.value))}/></label>)}</div>
  <div className="fields"><label>Scale factor<input type="number" min=".000001" max={10000} step="any" value={value.scale} onChange={e=>change({...value,scale:Number(e.target.value),reference_m:null,reference_units:null})}/></label>
   <label>Known reference (m)<input type="number" step=".01" min="0.001" max="30" value={refMeters} onChange={e=>setMeters(Number(e.target.value))}/></label>
   <label>Same span in model units<input type="number" min=".000001" step="any" value={refUnits} onChange={e=>setUnits(Number(e.target.value))}/></label></div>
  <div className="inline"><button className="btn" disabled={!canFit} onClick={()=>{change({...value,scale:fit,reference_m:refMeters,reference_units:refUnits});setFocus(false);}}>Apply reference scale</button>
   {registered?<button className="btn primary" disabled={busy} onClick={save}>Save visual placement</button>:<span className="muted">Imported file · this placement is a session preview.</span>}</div>
 </section>;
}
