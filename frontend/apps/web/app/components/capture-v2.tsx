'use client';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import {useEffect,useState} from 'react';
import type {Job,JobQuality,Pair} from '../../../../packages/protocol/types';
import {api,apiBase,localHost} from './connection';
import {download} from './io';
import {Icon} from './icons';
import type {HistoryData,Run} from './workflows';

const Cloud=dynamic(()=>import('./sparse-preview'),{ssr:false,loading:()=> <p className="blank">Loading cloud viewer…</p>});
type Metadata={resolution:Pair;display_resolution:Pair;orientation:number;device:string;bytes:number};
type Photo={id:string;commit:string;session?:string;metadata?:Metadata|null};
type Session={id:string;commit:string;source:string;count:number;photos:string[];request_quality?:JobQuality|null};
type Paired={count:number;expires_s:number;request_quality?:JobQuality|null};
type Item={key:string;file:File;state:'ready'|'uploading'|'failed'|'saved';progress:number;error?:string;photo?:Photo};
const modes:Record<JobQuality,string>={sparse:'Sparse point cloud',mesh:'CPU surface mesh',mesh_textured:'Textured CPU mesh from sparse tracks',dense:'Dense cloud + mesh (GPU)',textured:'Textured GLB + dense cloud (GPU)'};
const artifactLabels:Record<string,string>={'sparse.ply':'Sparse PLY','dense.ply':'Dense PLY','mesh.ply':'Mesh PLY','model.obj':'OBJ','model.glb':'GLB','textured-obj.zip':'Textured OBJ + atlas'};

async function prepare(file:File){
 if(['image/jpeg','image/png',''].includes(file.type)&&file.size<=15*1024*1024)return file;
 let image:ImageBitmap;
 try{image=await createImageBitmap(file,{imageOrientation:'from-image'});}
 catch{throw Error('This photo format could not be decoded. Export it as JPEG and retry.');}
 try{
  const scale=Math.min(1,2800/Math.max(image.width,image.height)),canvas=document.createElement('canvas');
  canvas.width=Math.max(1,Math.round(image.width*scale));canvas.height=Math.max(1,Math.round(image.height*scale));
  const ctx=canvas.getContext('2d');if(!ctx)throw Error('Photo conversion is unavailable.');
  ctx.drawImage(image,0,0,canvas.width,canvas.height);
  const blob=await new Promise<Blob|null>(resolve=>canvas.toBlob(resolve,'image/jpeg',.92));
  if(!blob)throw Error('The photo could not be converted.');
  return new File([blob],file.name.replace(/\.[^.]+$/,'')+'.jpg',{type:'image/jpeg'});
 }finally{image.close();}
}
async function upload(file:File,token:string,commit:string,paired:boolean,session:string,onProgress:(p:number)=>void){
 const image=await prepare(file);
 return new Promise<Photo>((resolve,reject)=>{
  const req=new XMLHttpRequest(),form=new FormData();
  form.append('image',image);
  if(!paired){form.append('commit',commit);if(session)form.append('session',session);}
  req.open('POST',(paired?'':apiBase())+'/api/v1/capture/photos');req.timeout=60000;
  req.setRequestHeader('Authorization','Bearer '+token);
  req.upload.onprogress=e=>{if(e.lengthComputable)onProgress(Math.min(99,Math.round(e.loaded/e.total*100)));};
  req.onload=()=>{let body;try{body=JSON.parse(req.responseText);}catch{}if(req.status>=200&&req.status<300&&body?.id)resolve(body);else reject(Error(typeof body?.detail==='string'?body.detail:'Upload failed. Reconnect and retry this photo.'));};
  req.onerror=req.ontimeout=()=>reject(Error('Upload interrupted. Reconnect and retry.'));
  req.send(form);
 });
}
async function pairApi<T>(key:string,path:string,quality?:JobQuality){
 const r=await fetch('/api/v1/capture/paired'+path,{method:quality?'POST':'GET',headers:{Authorization:'Bearer '+key,
  ...(quality?{'Content-Type':'application/json'}:{})},body:quality?JSON.stringify({quality}):undefined,cache:'no-store',signal:AbortSignal.timeout(8000)});
 if(!r.ok){const d=await r.json().catch(()=>({}));throw Error(typeof d.detail==='string'?d.detail:'Paired gateway is unavailable.');}
 return r.json() as Promise<T>;
}

export function Capture({data,token,run}:{data:HistoryData;token:string;run:Run}){
 const [items,setItems]=useState<Item[]>([]),[rev,setRev]=useState(''),[photos,setPhotos]=useState<Photo[]>([]),
 [jobs,setJobs]=useState<Job[]>([]),[sessions,setSessions]=useState<Session[]>([]),[colmap,setColmap]=useState(false),
 [pair,setPair]=useState(''),[lease,setLease]=useState<Paired|null>(null),[link,setLink]=useState(''),
 [status,setStatus]=useState(''),[busy,setBusy]=useState(false),[checks,setChecks]=useState<string[]>([]),
 [secure,setSecure]=useState(false),[quality,setQuality]=useState<JobQuality>('sparse'),[session,setSession]=useState(''),
 [cloud,setCloud]=useState<{id:string;name:string}|null>(null);
 const revision=data.commits.find(c=>c.id===rev)?.id??data.branches.main??'';
 const active=items.filter(i=>i.state==='ready'||i.state==='failed');
 useEffect(()=>{queueMicrotask(()=>{
  setSecure(window.isSecureContext);
  if(window.location.protocol==='https:'&&!localHost())setPair(new URLSearchParams(location.hash.slice(1)).get('pair')??'');
 });},[]);
 useEffect(()=>{
  if(!token)return;
  let alive=true;
  const poll=async()=>{try{
   const [p,j,s]=await Promise.all([api<Photo[]>(token,'/capture/photos'),api<{jobs:Job[];colmap:boolean}>(token,'/reconstructions'),api<Session[]>(token,'/capture/sessions')]);
   if(alive){setPhotos(p);setJobs(j.jobs);setColmap(j.colmap);setSessions(s);}
  }catch{}};
  void poll();const timer=setInterval(poll,1500);return()=>{alive=false;clearInterval(timer);};
 },[token]);
 useEffect(()=>{
  if(!pair)return;
  let alive=true;
  const poll=()=>pairApi<Paired>(pair,'').then(d=>{if(alive)setLease(d);}).catch(()=>{});
  void poll();const timer=setInterval(poll,2500);return()=>{alive=false;clearInterval(timer);};
 },[pair]);
 const visiblePhotos=photos.filter(p=>p.commit===revision),chosen=checks.filter(id=>visiblePhotos.some(p=>p.id===id));
 function choose(files:FileList|null){
  if(!files)return;
  const append=Array.from(files).map(file=>({file,key:crypto.randomUUID(),state:'ready' as const,progress:0}));
  setItems(old=>[...old,...append].slice(0,80));setStatus('');
 }
 function patch(key:string,change:Partial<Item>){setItems(old=>old.map(i=>i.key===key?{...i,...change}:i));}
 async function uploadBatch(){
  setBusy(true);setStatus('');
  let done=0,sessionId=session;
  try{
   if(!pair&&!sessionId){sessionId=(await api<Session>(token,'/capture/sessions/'+revision,{})).id;setSession(sessionId);}
   for(const item of active){
    patch(item.key,{state:'uploading',progress:0,error:undefined});
    try{const p=await upload(item.file,pair||token,revision,!!pair,sessionId,n=>patch(item.key,{progress:n}));
      patch(item.key,{state:'saved',progress:100,photo:p});done++;
    }catch(e){patch(item.key,{state:'failed',error:(e as Error).message});}
   }
   if(pair)void pairApi<Paired>(pair,'').then(setLease).catch(()=>{});
   setStatus(done===active.length?done+' photo(s) attached to the revision.':done+' attached · '+(active.length-done)+' need a retry.');
  }catch(e){setStatus((e as Error).message);}
  finally{setBusy(false);}
 }
 return <div className="stack">
 <div className="split-view">
 <section className="panel form-panel capture-session"><div className="panel-heading"><span className="step"><Icon name="camera" size={18}/></span><div><h2>Capture evidence</h2><p>Keep the scene fixed and move the camera between shots. One photo is evidence; overlapping views are needed for 3D.</p></div></div>
 {token&&<label>Revision<select disabled={busy} value={revision} onChange={e=>{setRev(e.target.value);setLink('');setChecks([]);setItems([]);setSession('');}}>{data.commits.map(c=><option key={c.id} value={c.id}>{c.message} · {c.id.slice(0,8)}</option>)}</select></label>}
 {pair?<div className="inline"><span className="pill green">Paired capture · upload only</span>{lease&&<span className="pill">{lease.count} saved · {Math.ceil(lease.expires_s/60)} min left</span>}</div>:!token?<p className="warning">Open a paired HTTPS capture link from your workstation to upload here.</p>:null}
 {!secure&&<p className="muted">Phone camera capture requires HTTPS.</p>}
 <label className="capture-picker"><Icon name="camera"/> Take a photo<input aria-label="Take a photo" type="file" accept="image/*" capture="environment" disabled={busy} onChange={e=>{choose(e.target.files);e.target.value='';}}/></label>
 <label className="capture-picker"><Icon name="plus"/> Or choose photos<input aria-label="Choose photos" type="file" accept="image/*" multiple disabled={busy} onChange={e=>{choose(e.target.files);e.target.value='';}}/></label>
 {!!items.length&&<div className="upload-list">{items.map(i=><div className="upload-item" key={i.key}>
   <div><strong>{i.file.name}</strong><small>{i.state==='saved'?'Attached':i.state==='uploading'?i.progress+'% uploaded':i.error??'Ready to upload'}</small></div>
   {i.state==='uploading'?<progress max={100} value={i.progress} aria-label={'Upload '+i.file.name}/>:i.state==='saved'?<Icon name="check" size={15}/>:<button className="btn tiny" disabled={busy} onClick={()=>setItems(old=>old.filter(v=>v.key!==i.key))}>Remove</button>}
  </div>)}</div>}
 <div className="inline"><button className="btn primary" disabled={busy||!active.length||(!pair&&(!token||!revision))} onClick={uploadBatch}>{active.length&&active.every(i=>i.state==='failed')?'Retry':'Upload'} {active.length||''} {active.length===1?'photo':'photos'} <Icon name="arrow"/></button>
 {token&&session&&<button className="btn" disabled={busy} onClick={()=>{setSession('');setItems([]);setStatus('Ready for a new capture session.');}}>New session</button>}</div>
 {status&&<p role="status" className="notice">{status}</p>}
 {token&&<><button className="btn" disabled={!revision||busy} onClick={()=>run(async()=>setLink((await api<{url:string}>(token,'/capture/pair/'+revision,{})).url))}>Create phone link</button>{link&&<label>Phone link (expires in 10 minutes)<input readOnly value={link} onFocus={e=>e.target.select()}/></label>}</>}
 </section>
 <section className="panel form-panel"><div className="panel-heading"><span className="step"><Icon name="cube" size={18}/></span><div><h2>Multi-view reconstruction</h2><p>Use 30–80 sharp views with good overlap. Geometry starts in an unregistered coordinate frame.</p></div></div>
 <label>Reconstruction output<select value={quality} onChange={e=>setQuality(e.target.value as JobQuality)}>{Object.entries(modes).map(([k,v])=><option value={k} key={k}>{v}</option>)}</select></label>
 {pair?<><p className="muted">Request a reconstruction from the local operator. The link cannot start GPU work directly.</p><button className="btn" disabled={(lease?.count??0)<6||!!lease?.request_quality} onClick={async()=>{
   try{await pairApi(pair,'/request',quality);setLease(await pairApi<Paired>(pair,''));setStatus('Reconstruction requested. The workstation operator can queue it.');}
   catch(e){setStatus((e as Error).message);}
  }}>{lease?.request_quality?'Request sent':'Request reconstruction'}</button></>:<>
 <div className={'pill '+(colmap?'green':'warning')}>{colmap?'COLMAP detected by edge':'COLMAP not detected by edge'}</div>
 {sessions.filter(s=>s.commit===revision&&s.count).map(s=><button className="btn tiny" key={s.id} onClick={()=>{setChecks(s.photos);if(s.request_quality)setQuality(s.request_quality);}}>
  Select {s.source==='paired-phone'?'phone':'desktop'} session · {s.count} {s.request_quality?' · requested '+modes[s.request_quality]:''}
 </button>)}
 <div className="photo-list">{visiblePhotos.map(p=><div className="inline" key={p.id}>
  <label className="checkline"><input type="checkbox" checked={checks.includes(p.id)} onChange={e=>setChecks(e.target.checked?[...checks,p.id]:checks.filter(id=>id!==p.id))}/>
  <span className="mono">Photo {p.id.slice(0,8)}{p.metadata?' · '+p.metadata.display_resolution.join('×')+' · '+p.metadata.device:''}</span></label>
  <button className="btn tiny" onClick={()=>run(async()=>{await api(token,'/capture/photos/'+p.id,undefined,'DELETE');setPhotos(photos.filter(f=>f.id!==p.id));})}>Delete</button></div>)}</div>
 <button className="btn" disabled={chosen.length<6||chosen.length>80} onClick={()=>run(async()=>{const job=await api<Job>(token,'/reconstructions',{photos:chosen,quality});setJobs([job,...jobs]);})}>Queue reconstruction · {chosen.length} selected</button>
 </>}
 </section></div>
 {jobs.length>0&&<section className="panel form-panel"><h2>Worker jobs</h2>{jobs.map(j=>{
  const artifacts=j.artifacts?.length?j.artifacts:j.asset?[{name:'sparse.ply',bytes:0}]:[];
  const terminal=['complete','partial','failed','cancelled'].includes(j.stage);
  return <details key={j.id} className="job"><summary><span className="mono">{j.id.slice(0,8)}</span> · {j.count} photos · <strong>{j.cancel_requested?'Cancelling':j.stage.replaceAll('_',' ')}</strong> · {j.message}{j.duration_s!==undefined?` · ${j.duration_s.toFixed(1)} s`:''}</summary>
  {!terminal&&<button className="btn tiny" disabled={j.cancel_requested} onClick={()=>run(async()=>{
   const job=await api<Job>(token,'/reconstructions/'+j.id+'/cancel',{});
   setJobs(current=>current.map(item=>item.id===job.id?job:item));
  })}>Cancel reconstruction</button>}
  {terminal&&j.stage!=='complete'&&<button className="btn tiny" onClick={()=>run(async()=>{
   const job=await api<Job>(token,'/reconstructions/'+j.id+'/retry',{});
   setJobs(current=>[job,...current]);
  })}>Retry with the same photos</button>}
  {j.progress&&<div className="inline"><progress value={j.progress.done} max={j.progress.total} aria-label="Reconstruction stages complete"/><span className="mono muted">{j.progress.done} / {j.progress.total} stages</span></div>}
  {!!(j.current_log?.length||j.logs.length)&&<pre>{[...j.logs,...(j.current_log??[])].join('\n')}</pre>}
  {!!artifacts.length&&<div className="inline">{artifacts.map(a=><button key={a.name} className="btn tiny" onClick={()=>run(async()=>{
   const r=await fetch(apiBase()+'/api/v1/assets/'+j.id+'/'+a.name,{headers:{Authorization:'Bearer '+token}});if(!r.ok)throw Error('Asset is unavailable');download(await r.blob(),a.name);
  })}><Icon name="download" size={13}/>{artifactLabels[a.name]??a.name}</button>)}
  {artifacts.filter(a=>['sparse.ply','dense.ply'].includes(a.name)).map(a=><button className="btn tiny" key={a.name} onClick={()=>setCloud(cloud?.id===j.id&&cloud.name===a.name?null:{id:j.id,name:a.name})}>Preview {a.name==='dense.ply'?'dense':'sparse'} cloud</button>)}
  {j.commit&&artifacts.some(a=>a.name==='model.glb')&&<Link className="btn primary tiny" href={'/studio/3d?revision='+j.commit+'&asset='+j.id}>Open mesh in 3D</Link>}
  </div>}{cloud?.id===j.id&&<Cloud id={j.id} name={cloud.name} key={j.id+cloud.name} token={token}/>}</details>;
 })}</section>}
 </div>;
}
