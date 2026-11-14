import type {Change,Scene} from '../../../../packages/protocol/types';

export function WallPlan({scene,label,changed=[],conflicts=[]}:{scene:Scene;label:string;changed?:string[];conflicts?:string[]}){
 const [w,h]=scene.wall, ratio=w/h;
 const scale=Math.min(420/w,220/h),dw=w*scale,dh=h*scale;
 return <figure className="wall-plan"><figcaption><strong>{label}</strong><span className="mono muted">{w.toFixed(2)} × {h.toFixed(2)} m</span></figcaption>
  <svg role="img" aria-label={label+' · '+scene.objects.length+' objects and '+(scene.constraints?.keep_out.length??0)+' keep-out areas'} viewBox={'-14 -14 '+(dw+28)+' '+(dh+28)} style={{aspectRatio:ratio}}>
   <rect width={dw} height={dh} fill="#101b26" stroke="#355061" rx="3"/>
   {Array.from({length:9},(_,i)=><path key={i} d={'M'+dw*(i+1)/10+' 0v'+dh+' M0 '+dh*(i+1)/10+'h'+dw} stroke="#213240" strokeWidth=".5"/>)}
   {scene.constraints?.keep_out.map(z=><g key={z.id}><rect x={(z.x-z.w/2)*scale} y={(h-z.y-z.h/2)*scale} width={z.w*scale} height={z.h*scale}
       fill="#FF8F912b" stroke="#FF8F91" strokeDasharray="4 3"/><title>{z.name}</title></g>)}
   {scene.objects.map(o=>{
    const c=conflicts.includes(o.id)?'#FF8F91':changed.includes(o.id)?'#55FF95':'#75DAE9';
    return <g key={o.id} transform={'translate('+o.x*scale+' '+(h-o.y)*scale+') rotate('+(-o.angle*180/Math.PI)+')'}>
     <rect x={-o.w*scale/2} y={-o.h*scale/2} width={o.w*scale} height={o.h*scale} rx="3" fill={c+'23'} stroke={c} strokeWidth="1.2"/>
     <text y="4" textAnchor="middle" fill={c} fontSize="10" fontFamily="monospace">{o.marker}</text><title>{o.name}</title>
    </g>;
   })}
  </svg>
  <figcaption><span>{scene.objects.length} objects</span><span>{scene.constraints?.clearance_mm??12} mm clearance</span></figcaption>
 </figure>;
}
export function ChangeList({changes}:{changes:Change[]}){
 return <ul className="diff-list">{changes.length?changes.map(d=><li key={d.id}>
  <strong>{d.after?.name??d.before?.name}</strong> <span className="mono muted">{d.kind} {d.fields.join(', ')}</span>
  {d.before&&d.after&&<div className="delta-fields">{d.fields.filter(f=>f in d.before!&&f in d.after!).map(f=>{
   const key=f as keyof NonNullable<Change['before']>;
   const a=d.before![key],b=d.after![key];
   const info=typeof a==='number'&&typeof b==='number'&&['x','y','w','h','d','angle'].includes(f)
    ?f==='angle'?((b-a)*180/Math.PI).toFixed(1)+'°':((b-a)*1000).toFixed(1)+' mm':String(a)+' → '+String(b);
   return <span className="pill" key={f}>{f} · {info}</span>;
  })}</div>}
 </li>):<li>No object changes.</li>}</ul>;
}
