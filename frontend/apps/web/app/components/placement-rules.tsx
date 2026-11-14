'use client';
import type {KeepOut,PlacementRules as Rules,Scene} from '../../../../packages/protocol/types';
import {WallPlan} from './wall-plan';
import {Icon} from './icons';

export function PlacementRules({scene,change}:{scene:Scene;change:(value:Rules)=>void}){
 const rules=scene.constraints??{clearance_mm:12,keep_out:[]};
 const update=(id:string,field:keyof KeepOut,value:number|string)=>change({...rules,keep_out:rules.keep_out.map(z=>z.id===id?{...z,[field]:value}:z)});
 return <details className="lens-tool"><summary>Placement rules · clearance and keep-out areas</summary>
  <p className="muted">These rules are committed with the scene. The merge checks target positions; it does not guarantee a collision-free path between them.</p>
  <div className="fields"><label>Minimum object clearance (mm)<input type="number" min={0} max={250} value={rules.clearance_mm}
    onChange={e=>change({...rules,clearance_mm:Number(e.target.value)})}/></label></div>
  {rules.keep_out.map(z=><fieldset className="keep-out-fields" key={z.id}><legend>{z.name}</legend><div className="fields">
    <label>Area name<input value={z.name} onChange={e=>update(z.id,'name',e.target.value)} maxLength={64}/></label>
    {(['x','y','w','h'] as const).map((k,i)=><label key={k}>{['Center X','Center Y','Width','Height'][i]} (m)<input type="number" step=".01" value={z[k]} onChange={e=>update(z.id,k,Number(e.target.value))}/></label>)}
   </div><button className="btn tiny" onClick={()=>change({...rules,keep_out:rules.keep_out.filter(v=>v.id!==z.id)})}>Remove area</button></fieldset>)}
  <button className="btn tiny" disabled={rules.keep_out.length>=12} onClick={()=>change({...rules,keep_out:[...rules.keep_out,
   {id:'area-'+crypto.randomUUID().slice(0,8),name:'Keep-out '+(rules.keep_out.length+1),x:scene.wall[0]*.85,y:scene.wall[1]*.75,w:.16,h:.16}]})}>
   <Icon name="plus" size={14}/> Add keep-out area
  </button>
  {!!rules.keep_out.length&&<WallPlan scene={scene} label="Placement rules preview"/>}
 </details>;
}
