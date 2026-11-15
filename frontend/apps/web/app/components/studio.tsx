'use client';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import {useRouter} from 'next/navigation';
import {useCallback,useEffect,useRef,useState} from 'react';
import type {Object3D} from 'three';
import type {Card,Commit,Live,Scene,VisualPlacement} from '../../../../packages/protocol/types';
import {Brand,Icon} from './icons';
import {api,apiBase,useLive,useToken} from './connection';
import {OverlayView,statusLabel} from './overlay';
import {Setup} from './setup';
import {Tracking} from './tracking';
import {History,MergeFlow,type HistoryData,type Run} from './workflows';
import {Capture} from './capture-v2';
import {download,exportGLB,importModel,parseModel} from './io';
import {VisualLayer,defaultPlacement} from './visual-layer';
import {PlacementRules} from './placement-rules';

const View=dynamic(()=>import('./scene-view'),{ssr:false,loading:()=> <div className="blank skeleton">Loading the 3D workspace…</div>});
const empty:HistoryData={branches:{},commits:[]};
const nav=[
 ['overview','/studio','grid','Overview'],['live','/studio/live','live','Live tracking'],['model','/studio/3d','cube','3D workspace'],['history','/studio/history','history','History'],['merge','/studio/merge','branch','Branch & merge'],['capture','/studio/capture','camera','Phone capture'],['setup','/setup','target','Hardware setup']
] as const;
type Mode=typeof nav[number][0];
const subtitles:Record<Mode,string>={overview:'Inspect your space, review revisions, and guide your next move.',live:'Follow camera observations and projector guidance in real time.',model:'Inspect measured geometry and edit a branch layout.',history:'Browse, compare, and physically restore saved layouts.',merge:'Compare layout proposals and resolve physical conflicts.',capture:'Attach photos to a revision or queue a reconstruction from overlapping views.',setup:'Connect a camera and register your projector to a measured wall.'};

function LivePanel({event,token,run,data,refresh}:{event:Live|null;token:string;run:Run;data:HistoryData;refresh:()=>Promise<void>}){
 const [plan,setPlan]=useState(''),[events,setEvents]=useState<{object:string;distance_m:number;mode:string;dwell_s:number}[]>([]),[choice,choose]=useState('');
 useEffect(()=>{const id=new URLSearchParams(location.search).get('revision');if(id)queueMicrotask(()=>choose(id));},[]);
 const rev=data.commits.find(c=>c.id===choice)?.id??data.branches.main;
 const [tolerance,setTolerance]=useState(25),[dwell,setDwell]=useState(.7);
 const pid=event?.plan?.id??plan;
 useEffect(()=>{if(!token||!pid)return;let done=false;const poll=()=>api<{events:typeof events}>(token,'/deployments/'+pid).then(r=>{if(!done)setEvents(r.events);}).catch(()=>{});void poll();const timer=setInterval(poll,600);return()=>{done=true;clearInterval(timer);};},[pid,token]);
 const command=async()=>{if(!rev)throw Error('Save a scene first');const p=await api<{id:string}>(token,'/deployments',{commit:rev,tolerance_mm:tolerance,dwell_s:dwell});setPlan(p.id);setEvents([]);};
 return <div className="stack"><div className="split-view"><section className="panel form-panel"><div className="panel-heading"><Icon name="target"/><div><h2>Projection monitor</h2><p>Local view of the edge service’s overlay.</p></div></div>
 <div className="projection-preview"><OverlayView event={event} output={event?.calibration?.output}/></div>
 <div className="inline"><Link className="btn" href="/projector" target="_blank"><Icon name="screen"/> Open projector</Link>{event?.plan&&<button className="btn" onClick={()=>run(async()=>{await api(token,'/deployments/active',undefined,'DELETE');})}>Stop guidance</button>}</div>
 <label>Restore revision<select value={rev??''} onChange={e=>choose(e.target.value)}>{data.commits.map(c=><option key={c.id} value={c.id}>{c.message} · {c.id.slice(0,8)}</option>)}</select></label>
 <div className="fields"><label>Position tolerance (mm)<input type="number" min={5} max={75} value={tolerance} onChange={e=>setTolerance(Number(e.target.value))}/></label><label>Stable dwell (s)<input type="number" min={.35} max={5} step={.05} value={dwell} onChange={e=>setDwell(Number(e.target.value))}/></label></div>
 {event?.calibration_reason&&<p className="warning">{event.calibration_reason}</p>}
 {event?.overlay?.confidence!==undefined&&<p className="mono muted">Tracking confidence {Math.round(event.overlay.confidence*100)}%{event.overlay.distance_m!==undefined?' · '+(event.overlay.distance_m*1000).toFixed(1)+' mm remaining':''}</p>}
 <button className="btn primary" disabled={!event||event.projection_ready===false||['DISCONNECTED','SETUP_REQUIRED','CALIBRATION_DRIFT'].includes(event.state)||!rev||!data.commits.find(c=>c.id===rev)?.scene.objects.length} onClick={()=>run(()=>command())}>Start restore</button>
 {event?.mode==='live'&&event.plan?.done&&!event.plan.saved&&event.state==='VERIFIED'&&<button className="btn primary" onClick={()=>run(async()=>{
  await api(token,'/deployments/active/confirm',{});await refresh();
 })}>Save verified restore</button>}
 </section><section className="panel form-panel"><div className="panel-heading"><Icon name="camera"/><div><h2>Camera observations</h2><p>Select a textured object to track its position and rotation.</p></div></div>
 {<Tracking event={event} token={token} data={data} run={run} refresh={refresh}/>}
 {!event?.tracked?.length&&event?.poses.length?<div className="object-list">{event.poses.map(p=><div key={p.marker}><span className="marker-num">{p.marker}</span><div><strong>Marker {p.marker}</strong><small>{p.x.toFixed(3)}, {p.y.toFixed(3)} m</small></div><span className="mono muted">{Math.round(p.confidence*100)}%</span></div>)}</div>:null}
 </section></div>
 <section className="panel form-panel"><h2>Verification evidence</h2>{event?.plan?.saved&&<p className="notice">Measured layout saved as revision <Link href={'/studio/3d?revision='+event.plan.saved}>{event.plan.saved.slice(0,8)}</Link>.</p>}{event?.plan?.save_error&&<p className="notice warning">{event.plan.save_error}</p>}{events.length?<ul className="diff-list">{events.filter(e=>e.mode==='live').map(e=><li key={e.object}><span className="green-text">✓ {e.object.toUpperCase()}</span> · {(e.distance_m*1000).toFixed(1)} mm · {e.dwell_s.toFixed(2)} s dwell · camera verified</li>)}</ul>:<p className="muted">A verification appears after fresh observations hold within tolerance.</p>}</section>
 </div>;
}

export default function Studio({mode}:{mode:Mode}){
 const router=useRouter();
 const viewport=useRef<HTMLDivElement>(null);
 const [token,setToken,connectLocal]=useToken(),{event,error}=useLive(mode==='setup'||mode==='capture'||mode==='merge'||mode==='history'?'':token);
 const [data,setData]=useState<HistoryData>(empty),[issue,report]=useState(''),[note,setNote]=useState(''),[branch,setBranch]=useState('main'),[selected,setSelected]=useState('a'),[edit,setEdit]=useState<Scene|null>(null),[revision,setRevision]=useState(''),[message,setMessage]=useState(''),[reset,setReset]=useState(0),[extra,setExtra]=useState<Object3D|null>(null),[busy,setBusy]=useState(false),[observed,setObserved]=useState(false),[compare,setCompare]=useState('');
 const [asset,setAsset]=useState(''),[opened,setOpened]=useState(''),[placement,setPlacement]=useState<VisualPlacement>(()=>defaultPlacement()),[focus,setFocus]=useState(false);
 const refresh=useCallback(async()=>{if(token)setData(await api<HistoryData>(token,'/commits'));},[token]);
 useEffect(()=>{queueMicrotask(()=>{void refresh().catch(e=>report((e as Error).message));});},[refresh]);
 useEffect(()=>{
  if(mode!=='model'||!token||!asset||!revision||!/^[\w-]{1,64}$/.test(asset)||!/^[\w-]{1,64}$/.test(revision))return;
  const ctl=new AbortController();
  const file=fetch(apiBase()+'/api/v1/assets/'+asset+'/model.glb',{headers:{Authorization:'Bearer '+token},signal:ctl.signal})
   .then(async r=>{if(!r.ok)throw Error('The registered mesh is unavailable.');return parseModel(await r.arrayBuffer());});
  Promise.all([file,api<VisualPlacement>(token,'/assets/'+asset+'/placement/'+revision)])
   .then(([m,p])=>{if(!m.mesh)throw Error('The asset has no visual geometry.');if(!ctl.signal.aborted){setExtra(m.mesh);setPlacement(p);setFocus(true);setOpened(asset);}})
   .catch(e=>{if(!ctl.signal.aborted)report((e as Error).message);});
  return()=>ctl.abort();
 },[mode,token,asset,revision]);
 const run:Run=async fn=>{report('');setNote('');setBusy(true);try{await fn();}catch(e){report((e as Error).message);}finally{setBusy(false);}};
 const connected=!!token&&data.commits.length>0;
 const tip=connected?data.branches[branch]:'';
 const current=connected?data.commits.find(c=>c.id===(revision||tip)):undefined;
 const base=current?.scene;
 const calWall=event?.mode==='live'&&base?.objects.length===0&&event.calibration&&event.state!=='CALIBRATION_DRIFT';
 const scene=edit??base;
 const baseline=data.commits.find(c=>c.id===compare);
 const changed=baseline&&scene?new Set(scene.objects.filter(o=>JSON.stringify(o)!==JSON.stringify(baseline.scene.objects.find(p=>p.id===o.id))).map(o=>o.id)):undefined;
 const active=scene?.objects.find(o=>o.id===selected)??scene?.objects[0];
 const name=nav.find(([k])=>k===mode)?.[3]??'Overview';
 const model=mode==='model', workspace=mode==='overview'||model;
 const meshView=!!extra&&focus;
 const label=event?.mode==='live'?(event.camera?'CAMERA ACTIVE':'CAMERA OFF'):connected?'EDGE CONNECTED':'EDGE DISCONNECTED';
 const update=(field:keyof Card,value:string|number)=>{if(!active||!scene)return;setEdit({...scene,objects:scene.objects.map(o=>o.id===active.id?{...o,[field]:value}:o)});};
 async function save(fromCamera=false){
  if(!scene)throw Error('Load a real scene first.');
  const c=await api<Commit>(token,'/commits',{scene,branch,expected:tip,observed:fromCamera,message:message.trim()||(fromCamera?'Capture observed layout':'Update wall layout')});
  setEdit(null);setRevision('');setMessage('');setNote('Saved revision '+c.id.slice(0,8));await refresh();
 }
 function add(){
  if(!scene)return;
  const marker=Array.from({length:246},(_,i)=>i+4).find(m=>!scene.objects.some(o=>o.marker===m));if(marker===undefined)return;
  const seen=event?.poses.find(p=>!scene.objects.some(o=>o.marker===p.marker));
  const id='object-'+crypto.randomUUID().slice(0,8);
  const card={id,marker:seen?.marker??marker,name:'Object '+(scene.objects.length+1),x:seen?.x??scene.wall[0]/2,y:seen?.y??scene.wall[1]/2,w:.18,h:.12,d:.02,angle:seen?.angle??0};
  setEdit({...scene,objects:[...scene.objects,card]});setSelected(id);
 }
 return <div className="studio">
 <aside className="sidebar"><Brand/><div className="workspace-id"><span className="workspace-icon"><Icon name="cube" size={20}/></span><div><strong>{base?.name??'No saved scene'}</strong><small>LOCAL WORKSPACE</small></div></div>
 <div className="nav-label">WORKSPACE</div><nav aria-label="Studio">{nav.slice(0,6).map(([key,url,icon,title])=><Link href={url} className={mode===key?'active':''} aria-current={mode===key?'page':undefined} key={key}><Icon name={icon}/><span>{title}</span></Link>)}</nav>
 <div className="nav-label hardware">DEVICES</div><nav aria-label="Hardware"><Link href="/setup" aria-current={mode==='setup'?'page':undefined} className={mode==='setup'?'active':''}><Icon name="target"/><span>Hardware setup</span></Link><Link href="/projector" target="_blank"><Icon name="screen"/><span>Projector</span><Icon name="external" size={12}/></Link></nav>
 <div className="side-bottom"><span className="signal-dot"/><div><strong>{connected?'Local edge':'Disconnected'}</strong><small>{connected?'Operator session':'Connect in Hardware setup'}</small></div></div>
 </aside>
 <div className="studio-main">
 <header className="studio-bar"><div className="breadcrumb"><span>Workspace</span><Icon name="chevron" size={13}/><strong>{name}</strong></div><div><span className={'pill '+(event?.mode==='live'&&event.camera?'green':'warning')}><span className="signal-dot"/> {label}</span><Link className="btn tiny top-action" href="/projector" target="_blank"><Icon name="screen" size={15}/> Projector</Link></div></header>
 <main className="studio-content">
 <div className="title-row"><div><div className="eyebrow">{mode==='setup'?'DEVICE ONBOARDING':'SPATIAL VERSION CONTROL'}</div><h1>{mode==='overview'?'Scene overview':name}</h1><p>{subtitles[mode]}</p></div>{mode==='overview'&&<Link className="btn primary" href={connected?'/studio/live':'/setup'}><Icon name={connected?'live':'target'}/>{connected?'Open live tracking':'Connect local edge'}<Icon name="arrow" size={16}/></Link>}</div>
 {issue&&<p role="alert" className="notice warning">{issue}</p>}{note&&<p role="status" className="notice">{note}</p>}
 {mode==='setup'&&<Setup token={token} connectLocal={connectLocal} connect={v=>{setToken(v);if(!v)setData(empty);report('');}}/>}
 {mode==='capture'&&<Capture data={data} token={token} run={run}/>}
 {mode==='history'&&<History data={data} token={token} run={run} refresh={refresh} open={id=>router.push('/studio/3d?revision='+encodeURIComponent(id))}/>}
 {mode==='merge'&&<MergeFlow data={data} token={token} run={run} refresh={refresh}/>}
 {mode==='live'&&<>{error&&<p className="notice warning">{error}</p>}{token?<LivePanel event={event} token={token} run={run} data={data} refresh={refresh}/>:<section className="panel blank">Connect the live edge in Hardware setup to view camera observations.</section>}</>}
 {workspace&&scene&&<>
 {model&&<RevisionParam select={setRevision} asset={setAsset}/>}
 <div className="workspace-grid"><section className="panel viewport-panel"><div className="viewport-top"><div><Icon name="cube"/><strong>{meshView?'Visual layer':scene.name}</strong><span className="pill">{meshView?opened?'RECONSTRUCTED MESH':'IMPORTED MESH':'PARAMETRIC 3D'}</span></div><button className="btn tiny" onClick={()=>setReset(reset+1)}><Icon name="rotate" size={15}/> Reset view</button></div>
 <div className="viewport" ref={viewport}><View scene={observed&&event?.poses.length?{...scene,objects:scene.objects.map(o=>{const p=event.poses.find(p=>p.marker===o.marker);return p?{...o,x:p.x,y:p.y,angle:p.angle}:o;})}:scene} selected={active?.id??''} onSelect={setSelected} reset={reset} extra={extra} changed={changed} visualOnly={!!extra&&focus} placement={placement}/><div className="view-label"><span className="signal-dot"/> {extra&&focus?'VISUAL GEOMETRY':observed&&event?.poses.length?'OBSERVED POSES':'WALL FRAME'} <span> / </span> {extra&&focus?'RAW FRAME':'METERS'}</div><div className="view-axes"><span>X</span><span>Y</span><span>Z</span></div></div>
 <div className="viewport-bottom"><span><Icon name="rotate" size={14}/> Drag to orbit · scroll to zoom</span><span className="mono">{meshView?'Unregistered model units':scene.wall[0].toFixed(2)+' × '+scene.wall[1].toFixed(2)+' m'}</span></div></section>
 <section className="panel inspector"><div className="viewport-top"><div><Icon name="target"/><strong>Object inspector</strong></div><span className="pill">{scene.objects.length}</span></div>
 {active?<><div className="inspector-selected"><div className="marker-icon"><Icon name="cube" size={22}/></div><div><strong>{active.name}</strong><small className="mono">OBJECT / {active.id.slice(0,8)}</small></div></div>
 <div className="coordinate-grid">{[['X',active.x],['Y',active.y],['YAW',active.angle]].map(([k,v])=><div key={k}><small>{k}</small><strong>{Number(v).toFixed(3)}</strong></div>)}</div></>:<p className="muted inspector-pad">No registered objects. Add a card in the 3D workspace.</p>}
 <div className="object-list selectable">{scene.objects.map(o=><button key={o.id} className={o.id===active?.id?'selected':''} onClick={()=>setSelected(o.id)}><span className="marker-num">{o.marker}</span><strong>{o.name}</strong><Icon name="chevron" size={14}/></button>)}</div>
 {!model&&<Link className="btn inspector-link" href="/studio/3d">Open 3D workspace <Icon name="arrow" size={16}/></Link>}
 {model&&active&&connected&&!revision&&<div className="form-panel compact">
 <div className="fields"><label>Object name<input value={active.name} onChange={e=>update('name',e.target.value)} maxLength={80}/></label><label>Marker ID<input type="number" min={4} max={249} value={active.marker} onChange={e=>update('marker',+e.target.value)}/></label>
 {([['x','X (m)'],['y','Y (m)'],['angle','Yaw (rad)'],['w','Width (m)'],['h','Height (m)'],['d','Depth (m)']] as const).map(([k,label])=><label key={k}>{label}<input type="number" step=".01" value={Number(active[k].toFixed(4))} onChange={e=>update(k,+e.target.value)}/></label>)}</div>
 <button className="btn tiny" onClick={()=>setEdit({...scene,objects:scene.objects.filter(o=>o.id!==active.id)})}>Remove object</button></div>}
 </section></div>
 {model?<section className="panel form-panel">
 <div className="panel-heading"><Icon name="branch"/><div><h2>Layout and assets</h2><p>Save a branch edit, capture measured poses, or exchange a model file.</p></div></div>
 {connected&&<><div className="fields"><label>Branch<select value={branch} onChange={e=>{setBranch(e.target.value);setRevision('');setEdit(null);setAsset('');setOpened('');setExtra(null);}}>{Object.keys(data.branches).map(b=><option key={b}>{b}</option>)}</select></label><label>Revision<select value={revision} onChange={e=>{setRevision(e.target.value);setEdit(null);setAsset('');setOpened('');setExtra(null);}}><option value="">Branch tip (editable)</option>{data.commits.map(c=><option key={c.id} value={c.id}>{c.message} · {c.id.slice(0,8)}</option>)}</select></label><label>Highlight changes from<select value={compare} onChange={e=>setCompare(e.target.value)}><option value="">None</option>{data.commits.map(c=><option key={c.id} value={c.id}>{c.message} · {c.id.slice(0,8)}</option>)}</select></label></div>
 {!revision&&<><div className="fields"><label>Wall width (m)<input type="number" step=".01" value={scene.wall[0]} onChange={e=>setEdit({...scene,wall:[+e.target.value,scene.wall[1]]})}/></label><label>Wall height (m)<input type="number" step=".01" value={scene.wall[1]} onChange={e=>setEdit({...scene,wall:[scene.wall[0],+e.target.value]})}/></label><label>Commit message<input placeholder="Describe the layout" value={message} maxLength={120} onChange={e=>setMessage(e.target.value)}/></label></div>
 <div className="inline"><button className="btn" disabled={scene.objects.length>=40} onClick={add}><Icon name="plus"/> Add object</button><button className="btn primary" disabled={!edit||busy} onClick={()=>run(()=>save())}>Commit layout</button><button className="btn" disabled={!event?.poses.length||!scene.objects.length||busy} onClick={()=>run(()=>save(true))}>Commit observed poses</button>{calWall&&<span className="muted">Observed commits use the calibrated wall size.</span>}</div>
 <PlacementRules scene={scene} change={constraints=>setEdit({...scene,constraints})}/></>}
 <label className="checkline"><input type="checkbox" checked={observed} onChange={e=>setObserved(e.target.checked)}/> Preview current observed poses</label></>}
 <div className="inline"><button className="btn" onClick={()=>download(new Blob([JSON.stringify(scene,null,2)],{type:'application/json'}),'spacegit-scene.json')}><Icon name="download"/> Scene JSON</button><button className="btn" disabled={busy} onClick={()=>run(()=>exportGLB(scene))}><Icon name="download"/> Export GLB</button>
 <button className="btn" onClick={()=>run(async()=>{
  const canvas=viewport.current?.querySelector('canvas');
  if(!canvas)throw Error('Open the 3D viewport before exporting a screenshot.');
  const png=await new Promise<Blob|null>(resolve=>canvas.toBlob(resolve,'image/png'));
  if(!png)throw Error('The viewport could not be exported.');
  download(png,'spacegit-view.png');
 })}><Icon name="download"/> Export screenshot</button>
 <label className="file-button btn">Import model<input type="file" accept=".glb,.json" aria-label="Import model" onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)run(async()=>{const r=await importModel(file);if(r.scene){setEdit({...r.scene,id:base?.id??r.scene.id});setRevision('');setNote('Imported scene with '+r.scene.objects.length+' stable object IDs.');}if(r.mesh){setAsset('');setOpened('');setPlacement(defaultPlacement());setExtra(r.mesh);setFocus(true);setNote('Imported auxiliary geometry. It is not registered to the wall.');}});}}/></label>{extra&&<button className="btn" onClick={()=>{setExtra(null);setAsset('');setOpened('');}}>Remove auxiliary model</button>}</div>
 </section>:<div className="summary-grid"><Link className="panel metric" href="/studio/live"><Icon name="live"/><div><small>TRACKING</small><strong>{event?statusLabel[event.state]:'Disconnected'}</strong></div><Icon name="chevron" size={15}/></Link><Link className="panel metric" href="/studio/history"><Icon name="history"/><div><small>REVISION</small><strong>{current?.message??'No saved revision'}</strong></div><Icon name="chevron" size={15}/></Link><Link className="panel metric" href="/setup"><Icon name="target"/><div><small>CALIBRATION</small><strong>{event?.calibration?'Validated geometry':'Hardware setup'}</strong></div><Icon name="chevron" size={15}/></Link></div>}
 </>}
 {workspace&&!scene&&<section className="panel blank"><h2>No recorded scene</h2><p>Connect the live edge and select a saved revision, or open a reconstruction file in the workspace.</p><Link className="btn primary" href="/world">Open workspace</Link></section>}
 {model&&extra&&<VisualLayer key={opened||extra.uuid} value={placement} change={setPlacement} focus={focus} setFocus={setFocus} registered={!!opened} busy={busy}
  save={()=>run(async()=>{const saved=await api<VisualPlacement>(token,'/assets/'+opened+'/placement',placement);setPlacement(saved);setNote('Visual placement saved for this revision.');})}/>}
 </main></div></div>;
}
function RevisionParam({select,asset}:{select:(v:string)=>void;asset:(v:string)=>void}){
 useEffect(()=>{const q=new URLSearchParams(location.search),id=q.get('revision'),a=q.get('asset');if(id)select(id);if(a)asset(a);},[select,asset]);
 return null;
}
