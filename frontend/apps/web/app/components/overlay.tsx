import type {Live,Pair} from '../../../../packages/protocol/types';
import type {Wizard} from './connection';
export const statusLabel:Record<string,string>={READY:'Ready',MOVING:'Move to target',NEAR_TARGET:'Hold position',VERIFIED:'Verified',TRACKING_LOST:'Tracking lost',CALIBRATION_DRIFT:'Calibration drift',SETUP_REQUIRED:'Setup required',DISCONNECTED:'Disconnected',CONFLICT:'Target blocked'};
export function OverlayView({event,wizard,output=[1600,900]}:{event:Live|null;wizard?:Wizard|null;output?:Pair}){
 const [w,h]=output;
 const pos=(p:Pair)=>[p[0]*w,p[1]*h];
 const state=event?.state??'DISCONNECTED';
 const danger=['TRACKING_LOST','SETUP_REQUIRED','DISCONNECTED','CALIBRATION_DRIFT','CONFLICT'].includes(state);
 const color=danger?'#FFD38D':'#55FF95';
 const o=danger?null:event?.overlay;
 const s=w/1600;
 const curve=o?.arrow?'M'+pos(o.arrow[0])+' Q'+pos(o.arrow[1])+' '+pos(o.arrow[2]):null;
 return <svg className="overlay" viewBox={'0 0 '+w+' '+h} preserveAspectRatio="none" aria-label="Projection guidance" style={{color}}>
  <defs><marker id="direction" markerWidth="7" markerHeight="7" refX="8" refY="5" viewBox="0 0 10 10" orient="auto"><path d="M0 0 10 5 0 10z" fill="currentColor"/></marker></defs>
  {wizard?.kind==='auto_blank'?null:wizard?.kind==='auto_spot'?
   <circle cx={wizard.point[0]*w} cy={wizard.point[1]*h} r={Math.min(w,h)*.011} fill="white"/>:
   wizard?<g transform={'translate('+pos(wizard.point).join(' ')+')'} stroke="#75DAE9" strokeWidth={4*s}><path d={'M'+(-22*s)+' 0h'+44*s+' M0 '+(-22*s)+'v'+44*s}/><circle r={30*s} fill="none" opacity=".6"/><text x={42*s} y={11*s} stroke="none" fill="#75DAE9" fontSize={30*s}>{wizard.kind==='physical'?'MEASURE':(wizard.index<6?'FIT ':'CHECK ')+(wizard.index%6+1)+'/6'}</text></g>:<>
  {o&&<><polygon points={o.outline.map(p=>pos(p).join(',')).join(' ')} fill="none" stroke="currentColor" strokeWidth={5*s} strokeDasharray={state==='MOVING'?11*s:undefined}/>
   {curve&&<><path d={curve} fill="none" stroke="currentColor" strokeWidth={7*s} markerEnd="url(#direction)"/><path d={curve} className="projection-flow" pathLength="100" fill="none" stroke="#e0ffeb" strokeWidth={2.5*s} strokeDasharray="4 16"/></>}
   {o.from&&state==='MOVING'&&<circle cx={pos(o.from)[0]} cy={pos(o.from)[1]} r={9*s} fill="currentColor"/>}
   {(state==='NEAR_TARGET'||state==='VERIFIED')&&o.ticks.map(([a,b],i)=><path key={i} d={'M'+pos(a)+' L'+pos(b)} stroke="currentColor" strokeWidth={4*s}/>)}
   {state==='NEAR_TARGET'&&<circle cx={pos(o.to)[0]} cy={pos(o.to)[1]} r={31*s} pathLength={100} fill="none" stroke="currentColor" strokeWidth={4*s} strokeDasharray={(o.dwell??0)*100+' 100'} transform={'rotate(-90 '+pos(o.to).join(' ')+')'}/>}
   {state==='VERIFIED'&&<g className="projection-check"><circle cx={pos(o.to)[0]} cy={pos(o.to)[1]} r={29*s} stroke="currentColor" fill="#0B111A" strokeWidth={3*s}/><text x={pos(o.to)[0]} y={pos(o.to)[1]+14*s} fill="currentColor" fontSize={43*s} textAnchor="middle">✓</text></g>}
   <text x={pos(o.to)[0]} y={pos(o.to)[1]+Math.max(26*s,h*.045)} fill="currentColor" textAnchor="middle" fontSize={30*s}>{o.name}</text>
   <path d={'M'+[w*.28,h*.92]+'h'+w*.44*o.progress} stroke="currentColor" strokeWidth={6*s}/>
  </>}
  <text x={w*.04} y={h*.095} fontSize={37*s} fill="currentColor">{event?.plan?.done&&state==='VERIFIED'?'Revision deployed':statusLabel[state]}{o?.distance_m!==undefined&&state==='MOVING'?' · '+(o.distance_m*100).toFixed(1)+' cm':''}</text>
  </>}
 </svg>;
}
