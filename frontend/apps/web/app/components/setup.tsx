'use client';
import {useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import type {Live,Pair} from '../../../../packages/protocol/types';
import {api,apiBase,type Wizard} from './connection';
import {Icon} from './icons';
import {LensTool,PhysicalDiagnostics,ResidualPlot,type Lens,type Residual} from './calibration-tools';

type AutomaticCalibration =
 | {state:'running'|'cancelled';completed:number}
 | {state:'complete';completed:number;max_px:number}
 | {state:'failed';completed:number;error:string};
type Monitor={id:string;rect:number[];primary:boolean};
type Fit={id:string;mean_px:number;max_px:number;limit_px?:number;residuals?:Residual[]};
type Workspace={wall:Pair;units:'m'|'normalized';corners:Pair[]};
type CameraMetrics={fps:number|null;sharpness:number;brightness:number;underexposed:number;overexposed:number;grade:string;delivery_shortfall:number|null;processing_ms:number};
type Status={live:Live|null;camera_error:string;camera_signature:{index:number;resolution:Pair}|null;projector:{width:number;height:number;fullscreen:boolean;screen_label?:string|null;automatic_calibration?:boolean}|null;wizard:Wizard|null;calibration:Fit|null;projection_preview?:Fit|null;intrinsics:Lens|null;lens_views:number;automatic_calibration?:AutomaticCalibration|null;display_count?:number|null;monitors?:Monitor[];workspace?:Workspace|null;camera_metrics?:CameraMetrics|null};
type Devices={cameras:{index:number;label:string}[];displays:number|null;monitors?:Monitor[]};

export function CameraPreview({token,onPoint,wallAspect,projection=false,outline,boxes=[]}:{token:string;onPoint?:(p:Pair)=>void;wallAspect?:number;projection?:boolean;outline?:Pair[];boxes?:{id:string;name:string;bbox:[number,number,number,number];active:boolean}[]}){
 const [url,set]=useState(''),[failed,fail]=useState(false),img=useRef<HTMLImageElement>(null);
 const [dimensions,setDimensions]=useState<Pair>([1280,720]);
 useEffect(()=>{
  if(!token)return;
  let done=false,current='',timer:ReturnType<typeof setTimeout>;
  const loop=async()=>{
   try{const query=projection?'?projection=true':wallAspect===undefined?'':'?wall_aspect='+wallAspect;
    const r=await fetch(apiBase()+'/api/v1/preview'+query,{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(2500),cache:'no-store'});
    if(!r.ok)throw Error(); const blob=await r.blob(); if(done)return;
    const previous=current;current=URL.createObjectURL(blob);set(current);fail(false);if(previous)URL.revokeObjectURL(previous);
   }catch{if(!done)fail(true);}
   if(!done)timer=setTimeout(loop,160);
  };void loop();
  return()=>{done=true;clearTimeout(timer);if(current)URL.revokeObjectURL(current);};
 },[token,wallAspect,projection]);
 return <div className="camera-preview">{url&&!failed?
 <div className="camera-image" style={{width:`min(100%, ${dimensions[0]}px, ${440*dimensions[0]/dimensions[1]}px)`}}>
 {/* eslint-disable-next-line @next/next/no-img-element */}
 <img ref={img} src={url} alt="Live camera preview" onLoad={e=>{
  const {naturalWidth,naturalHeight}=e.currentTarget;
  if(naturalWidth&&naturalHeight)setDimensions(old=>old[0]===naturalWidth&&old[1]===naturalHeight?old:[naturalWidth,naturalHeight]);
 }} onClick={e=>{if(!onPoint||!img.current)return;const r=img.current.getBoundingClientRect();onPoint([(e.clientX-r.left)*img.current.naturalWidth/r.width,(e.clientY-r.top)*img.current.naturalHeight/r.height]);}} className={onPoint?'crosshair':''}/>
 {(outline?.length||boxes.length)?<svg aria-hidden="true" viewBox={`0 0 ${dimensions[0]} ${dimensions[1]}`}>
  {outline&&<><polyline points={(outline.length===4?[...outline,outline[0]]:outline).map(p=>p.join(',')).join(' ')} className="workspace-outline"/>{outline.map(([x,y],i)=><g key={i}><circle cx={x} cy={y} r={7}/><text x={x+11} y={y-5}>{i+1}</text></g>)}</>}
  {boxes.map(b=><g key={b.id} className={b.active?'tracked-box':'uncertain-box'}><rect x={b.bbox[0]} y={b.bbox[1]} width={b.bbox[2]-b.bbox[0]} height={b.bbox[3]-b.bbox[1]}/><text x={b.bbox[0]+5} y={b.bbox[1]+20}>{b.name}</text></g>)}
 </svg>:null}
 </div>:
 <div className="blank"><Icon name="camera" size={30}/><strong>Camera preview unavailable</strong><span>Open a live camera in Setup. Frames stay on this workstation.</span></div>}</div>;
}

export function Setup({token,connect,connectLocal}:{token:string;connect:(v:string)=>void;connectLocal:()=>Promise<string>}){
 const [key,setKey]=useState(''),[status,setStatus]=useState<Status|null>(null),[devices,setDevices]=useState<Devices|null>(null),[notice,setNotice]=useState('');
 const s=token?status:null;
 const [index,setIndex]=useState<number|null>(null),[manualIndex,setManualIndex]=useState(false);
 const [deviceRefresh,refreshDevices]=useState(0),[deviceError,setDeviceError]=useState(false);
 const [width,setWidth]=useState(1280),[height,setHeight]=useState(720),[dictionary,setDict]=useState('DICT_4X4_250');
 const [w,sw]=useState(2.4),[h,sh]=useState(1.4),[marker,sm]=useState(.06),[limit,sl]=useState(12),[points,setPoints]=useState<Pair[]>([]),[pending,setPending]=useState(false);
 const [pixel,setPixel]=useState<Pair>([0,0]);
 const [rectify,setRectify]=useState(true);
 const [anchored,setAnchored]=useState(false);
 const [workspacePoints,setWorkspacePoints]=useState<Pair[]|null>(null);
 const [workspaceWidth,setWorkspaceWidth]=useState(''),[workspaceHeight,setWorkspaceHeight]=useState('');
 useEffect(()=>{
  if(!token)return;
  let alive=true;
  const get=()=>api<Status>(token,'/status').then(r=>{if(alive)setStatus(r);}).catch(()=>{if(alive)setStatus(null);});
  void get();const interval=setInterval(get,500);
  return()=>{alive=false;clearInterval(interval);};
 },[token]);
 useEffect(()=>{
  if(!token)return;
  let alive=true;
  api<Devices>(token,'/devices').then(d=>{
   if(alive){setDevices(d);setDeviceError(false);}
  }).catch(()=>{if(alive){setDevices(null);setDeviceError(true);}});
  return()=>{alive=false;};
 },[token,deviceRefresh]);
 async function run(fn:()=>Promise<void>){setPending(true);setNotice('');try{await fn();}catch(e){setNotice((e as Error).message);}finally{setPending(false);}}
 const demo=s?.live?.mode==='demo',cal=s?.calibration;
 const automatic=s?.automatic_calibration;
 const autoRunning=automatic?.state==='running';
 const manualWizard=!!s?.wizard&&!s.wizard.kind;
 const cameraOptions=token?devices?.cameras??[]:[];
 const activeCamera=s?.camera_signature?.index;
 const selectedCamera=index??activeCamera??cameraOptions[0]?.index??0;
 const cameraLabel=(id:number)=>cameraOptions.find(camera=>camera.index===id)?.label??('Camera '+id);
 const cameraBusy=!s||demo||pending||autoRunning;
 const metrics=s?.camera_metrics;
 const monitors=s?.monitors??(token?devices?.monitors:undefined)??[];
 const displayCount=s?.display_count??(token?devices?.displays:undefined);
 const projectorStatus=s?.projector?.fullscreen
  ? `Projector fullscreen · ${s.projector.screen_label?`${s.projector.screen_label} · `:''}${s.projector.width} × ${s.projector.height}`
  : s?.projector ? 'Projector window open. Waiting for fullscreen.' : 'Waiting for the projector window';
 const ratio=w/h;
 const wallAspect=anchored&&rectify&&ratio>=.025&&ratio<=40?ratio:undefined;
 const projection=rectify&&!anchored;
 const canCalibrate=!!(s?.projector?.fullscreen&&s.live?.camera&&(!anchored||s.live.anchors.length===4)&&!demo);
 const readyForPoint=!!(manualWizard&&s?.wizard?.shown&&s.wizard.index===points.length&&!pending&&!autoRunning&&points.length<12);
 const missingAutoRequirement = !s || demo ? 'Connect to the local edge in live mode.'
  : s.display_count===1 ? 'Only one display detected. Connect the projector and select Extend with Win + P.'
  : !s.projector?.fullscreen ? 'Open the projector page on the external display and enter fullscreen.'
  : !s.projector.automatic_calibration ? 'Refresh the projector page and enter fullscreen again.'
  : !s.live?.camera ? 'Open the webcam first.'
  : anchored&&s.live.anchors.length!==4 ? 'The camera must see wall markers 0–3.'
  : s.wizard && !autoRunning ? 'Finish or cancel the current calibration.' : '';
 const startAutomatic=()=>run(async()=>{
  const result=await api<AutomaticCalibration>(token,'/calibration/automatic',
   anchored?{wall:[w,h],marker_m:marker,limit_px:limit}:{limit_px:limit});
  setStatus(current=>current?{...current,automatic_calibration:result}:current);
  setPoints([]);
 });
 const markPoint=(p:Pair)=>run(async()=>{
  const next=[...points,p];if(next.length<12)await api(token,'/calibration/point/'+next.length,{});setPoints(next);
 });
 if(process.env.NEXT_PUBLIC_SPACEGIT_PUBLIC==='1')return <section className="panel form-panel"><div className="panel-heading"><Icon name="lock"/><div><h2>Hardware setup runs locally</h2><p>This public demo cannot connect to a camera or projector. Start the local SpaceGit app on the projector workstation to calibrate.</p></div></div><Link className="btn primary" href="/studio/3d">Explore the demo wall <Icon name="arrow"/></Link></section>;
 return <div className="stack">
 <section className="panel form-panel"><div className="panel-heading"><span className="step">01</span><div><h2>Connect the local edge</h2><p>Connect on this workstation or use the operator key printed by the start script.</p></div></div>
 {!token&&<div><button className="btn primary" disabled={pending} onClick={()=>void run(async()=>{await connectLocal();})}>Connect this workstation</button></div>}
 <form className="inline" onSubmit={e=>{e.preventDefault();setStatus(null);connect(key.trim());setKey('');}}><input aria-label="Operator key" type="password" placeholder="Local operator key" value={key} onChange={e=>setKey(e.target.value)} required/><button className="btn primary">Connect</button>{token&&<button className="btn" type="button" onClick={()=>{setStatus(null);connect('');}}>Disconnect</button>}<span className={'pill '+(s?'green':'')}>{s?demo?'DEMO / SIMULATED':'Edge connected':token?'Waiting for edge':'Offline'}</span></form></section>
 <section className="panel form-panel"><div className="panel-heading"><span className="step">02</span><div><h2>Set up the camera</h2><p>Mount the camera firmly and frame the entire work surface.</p></div></div>
 <div className="fields">
  <label>Camera<select aria-label="Camera" disabled={cameraBusy} value={manualIndex?'manual':selectedCamera} onChange={e=>{
   if(e.target.value==='manual'){setIndex(selectedCamera);setManualIndex(true);}
   else {setIndex(Number(e.target.value));setManualIndex(false);}
  }}>
   {!manualIndex&&!cameraOptions.some(d=>d.index===selectedCamera)&&<option value={selectedCamera}>Camera {selectedCamera}</option>}
   {cameraOptions.map(d=><option key={d.index} value={d.index}>{d.label}（{d.index}）</option>)}
   <option value="manual">Enter a camera index</option>
  </select></label>
  {manualIndex&&<label>Camera index<input type="number" min={0} max={15} value={Number.isNaN(selectedCamera)?'':selectedCamera} disabled={cameraBusy} onChange={e=>setIndex(e.target.valueAsNumber)}/></label>}
  <label>Resolution preset<select value={['640x480','1280x720','1920x1080','3840x2160'].includes(width+'x'+height)?width+'x'+height:'custom'} onChange={e=>{
   if(e.target.value==='custom')return;
   const [w,h]=e.target.value.split('x').map(Number);setWidth(w);setHeight(h);
  }}><option value="640x480">640 × 480</option><option value="1280x720">1280 × 720 (recommended)</option><option value="1920x1080">1920 × 1080</option><option value="3840x2160">3840 × 2160</option><option value="custom" disabled>Custom</option></select></label>
  <label>Width<input type="number" min={320} max={3840} value={width} onChange={e=>setWidth(+e.target.value)}/></label><label>Height<input type="number" min={240} max={2160} value={height} onChange={e=>setHeight(+e.target.value)}/></label>
  {anchored&&<label>Marker dictionary<select value={dictionary} onChange={e=>setDict(e.target.value)}>{['DICT_4X4_250','DICT_5X5_250','DICT_6X6_250'].map(v=><option key={v}>{v}</option>)}</select></label>}
 </div>
 <div className="inline">
  <button className="btn" disabled={cameraBusy||!Number.isInteger(selectedCamera)||selectedCamera<0||selectedCamera>15} onClick={()=>run(async()=>{
   await api(token,'/devices/camera',{index:selectedCamera,width,height,dictionary});
   setIndex(selectedCamera);
  })}><Icon name="camera"/>{activeCamera!==undefined&&activeCamera!==selectedCamera?'Switch camera':'Open camera'}</button>
  <button className="btn" disabled={cameraBusy} onClick={()=>refreshDevices(v=>v+1)}>Refresh cameras</button>
  <button className="btn" disabled={!s?.live?.camera||pending||autoRunning} onClick={()=>run(async()=>{await api(token,'/devices/camera',undefined,'DELETE');})}>Stop camera</button>
 </div>
 {s&&!demo&&<p className="muted" role="status">{s.camera_signature?'Active camera: '+cameraLabel(s.camera_signature.index)+' · '+s.camera_signature.resolution.join(' × ')+(anchored?' · Wall markers '+[...(s.live?.anchors??[])].sort().join(', '):''):s.camera_error}</p>}
 {metrics&&<section aria-label="Camera diagnostics" className="camera-diagnostics">
  <strong>Camera diagnostics · {metrics.grade}</strong>
  <p>{metrics.fps?.toFixed(1)??'Measuring'} fps · Brightness {metrics.brightness.toFixed(0)}/255 · Sharpness {metrics.sharpness.toFixed(0)}</p>
  <p className="muted">{Math.round(metrics.underexposed*100)}% dark · {Math.round(metrics.overexposed*100)}% clipped bright · {metrics.processing_ms.toFixed(0)} ms edge processing{metrics.delivery_shortfall!==null?` · ${Math.round(metrics.delivery_shortfall*100)}% below reported FPS`:''}</p>
  {['Limited','Unsuitable'].includes(metrics.grade)&&<p className="warning">Improve lighting or focus. Choose a lower resolution if the frame rate stays low.</p>}
 </section>}
 {s&&!demo&&(deviceError||devices&&!cameraOptions.length)&&<p className="muted">No cameras were listed. Connect a webcam and refresh, or enter its index.</p>}
 {!manualWizard&&<>
  <label className="inline"><input type="checkbox" checked={rectify} onChange={e=>setRectify(e.target.checked)}/>Crop and straighten preview</label>
  {projection&&s?.live?.camera&&<p className="muted">{s.projection_preview?'Preview aligned to the projected image.':'Calibrate the projector to crop and straighten this preview.'}</p>}
  <CameraPreview key={activeCamera} token={s?.live?.camera?token:''} wallAspect={workspacePoints?undefined:wallAspect} projection={projection&&!workspacePoints} outline={workspacePoints??(!s?.projection_preview?s?.workspace?.corners:undefined)} onPoint={workspacePoints&&workspacePoints.length<4?p=>setWorkspacePoints([...workspacePoints,p]):undefined}/>
 </>}
 {!demo&&<div className="stack">
  <div className="inline"><button className="btn" disabled={cameraBusy||!s?.live?.camera||!!s.wizard} onClick={()=>setWorkspacePoints([])}>Define camera workspace</button>
   {s?.workspace&&<span className="pill green">{s.workspace.units==='m'?`Workspace · ${s.workspace.wall.join(' × ')} m`:'Workspace · normalized coordinates'}</span>}
   {s?.workspace&&<Link className="btn" href="/studio/live">Start tracking</Link>}</div>
  {workspacePoints&&<><p>Select the top-left, top-right, bottom-right, and bottom-left corners in the camera preview ({workspacePoints.length}/4).</p>
   <div className="fields"><label>Measured width (m)<input type="number" min=".01" step=".01" value={workspaceWidth} onChange={e=>setWorkspaceWidth(e.target.value)}/></label><label>Measured height (m)<input type="number" min=".01" step=".01" value={workspaceHeight} onChange={e=>setWorkspaceHeight(e.target.value)}/></label></div>
   <p className="muted">Leave both dimensions blank to use normalized coordinates. Enter both to save measured layouts and restore them.</p>
   <div className="inline"><button className="btn primary" disabled={cameraBusy||workspacePoints.length!==4||!!workspaceWidth!==!!workspaceHeight} onClick={()=>run(async()=>{
    await api(token,'/workspace',{corners:workspacePoints,size_m:workspaceWidth?[Number(workspaceWidth),Number(workspaceHeight)]:null});
    setWorkspacePoints(null);
   })}>Save workspace</button><button className="btn" onClick={()=>setWorkspacePoints(workspacePoints.slice(0,-1))}>Undo corner</button><button className="btn" onClick={()=>setWorkspacePoints(null)}>Cancel</button></div>
  </>}
 </div>}
 <LensTool token={token} enabled={!!(s?.live?.camera&&!demo&&!autoRunning)} lens={s?.intrinsics??null} views={s?.lens_views??0}/>
 </section>
 <section className="panel form-panel" id="projector-calibration"><div className="panel-heading"><span className="step">03</span><div><h2>Register the projector</h2><p>Frame the entire projection in the camera. Enter fullscreen on the projector, then run automatic calibration.</p></div></div>
 <div className="inline"><Link className="btn" href="/projector" target="_blank"><Icon name="screen"/> Open projector <Icon name="external" size={14}/></Link><span className={'pill '+(s?.projector?.fullscreen?'green':'')} role="status">{projectorStatus}</span></div>
 <p className="muted">{displayCount==null?'Display status unavailable':`${displayCount} active displays detected`}</p>
 {!!monitors.length&&<div className="inline">{monitors.map(m=><span className="pill" key={m.id}>{m.id.replace(/^.*DISPLAY/i,'Display ')} · {m.rect.slice(2).join('×')}{m.primary?' · primary':''}</span>)}</div>}
 {displayCount===1&&<p className="warning">Windows reports one active display. Press Win + P and select Extend.</p>}
 {!!displayCount&&displayCount>1&&!s?.projector?.fullscreen&&<p className="muted">In the projector window, detect displays and choose your projector. You can also move the window there manually before entering fullscreen.</p>}
 <label className="checkline"><input type="checkbox" checked={anchored} disabled={pending||autoRunning||manualWizard} onChange={e=>setAnchored(e.target.checked)}/> Use ArUco anchors for a measured wall (advanced)</label>
 <div className="fields">{anchored&&<><label>Anchor span X (m)<input type="number" step=".01" min=".1" value={w} onChange={e=>sw(+e.target.value)}/></label><label>Anchor span Y (m)<input type="number" step=".01" min=".1" value={h} onChange={e=>sh(+e.target.value)}/></label><label>Black marker edge (m)<input type="number" step=".001" min=".006" value={marker} onChange={e=>sm(+e.target.value)}/></label></>}<label>Worst error limit (px)<input type="number" min={2} max={25} value={limit} onChange={e=>sl(+e.target.value)}/></label></div>
 <div className="inline">
  <button className="btn primary" disabled={!!missingAutoRequirement||pending||autoRunning} onClick={startAutomatic}>Automatic calibration</button>
  {autoRunning?<button className="btn" disabled={pending} onClick={()=>run(async()=>{
   const result=await api<AutomaticCalibration>(token,'/calibration/automatic',undefined,'DELETE');
   setStatus(current=>current?{...current,automatic_calibration:result}:current);
  })}>Cancel automatic calibration</button>:<button className="btn" disabled={!canCalibrate||pending||!!s?.wizard&&!manualWizard} onClick={()=>run(async()=>{await api(token,'/calibration/point/0?projection_only='+!anchored,{});setPoints([]);})}>{manualWizard?'Restart manual calibration':'Manual calibration'}</button>}
  {manualWizard&&<button className="btn" disabled={pending} onClick={()=>run(async()=>{await api(token,'/calibration/point/-1',{});setPoints([]);})}>Cancel</button>}
 </div>
 {missingAutoRequirement&&<p className="muted">{missingAutoRequirement}</p>}
 {autoRunning&&<><progress className="calibration-progress" max={12} value={automatic.completed} aria-label="Automatic calibration progress"/><p role="status">Captured {automatic.completed}/12 projected points</p></>}
 {automatic?.state==='complete'&&<p role="status" className="notice">Calibration saved. Worst validation error {automatic.max_px.toFixed(2)} px.</p>}
 {automatic?.state==='failed'&&<p role="alert" className="warning">{automatic.error}</p>}
 {automatic?.state==='cancelled'&&<p role="status" className="muted">Automatic calibration cancelled.</p>}
 {manualWizard&&<progress className="calibration-progress" max={12} value={points.length} aria-label="Marked projector correspondences"/>}
 {manualWizard&&points.length<12&&<p className="muted">{readyForPoint?'Click the cross center in the fresh camera image, or enter its pixel coordinates.':'Waiting for projector acknowledgement…'}</p>}
 {manualWizard&&<CameraPreview key={activeCamera} token={s?.live?.camera?token:''} onPoint={readyForPoint?markPoint:undefined}/>}
 {readyForPoint&&<div className="inline"><label>Camera pixel X<input type="number" min={0} value={pixel[0]} onChange={e=>setPixel([Number(e.target.value),pixel[1]])}/></label><label>Camera pixel Y<input type="number" min={0} value={pixel[1]} onChange={e=>setPixel([pixel[0],Number(e.target.value)])}/></label><button className="btn" onClick={()=>markPoint(pixel)}>Mark pixel</button></div>}
 {manualWizard&&<button className="btn primary" disabled={points.length!==12||pending||!s?.projector?.fullscreen} onClick={()=>run(async()=>{
  if(!s?.projector)return;
  const samples={fit:points.slice(0,6),check:points.slice(6),limit_px:limit};
  const r=await api<Fit>(token,anchored?'/calibration/solve':'/calibration/projection',
   anchored?{...samples,wall:[w,h],marker_m:marker,output:[s.projector.width,s.projector.height]}:samples);
  setNotice('Calibration saved · mean '+r.mean_px.toFixed(2)+' px · worst '+r.max_px.toFixed(2)+' px');
  setPoints([]);
 })}>Validate and save</button>}
 {s?.projection_preview&&!anchored&&<><p role="status">Projector alignment active · worst error {s.projection_preview.max_px.toFixed(2)} px</p><ResidualPlot residuals={s.projection_preview.residuals??[]}/></>}
 {anchored&&cal&&!demo&&<><div className="inline"><span className={'pill '+(s?.live?.calibration?.id===cal.id&&!s.live.calibration_reason?'green':'warning')}>{s?.live?.calibration?.id===cal.id&&!s.live.calibration_reason?'ACTIVE FIT · VALIDATED IN PIXELS':'SAVED FIT'}</span><span className="mono muted">Saved {cal.id.slice(0,8)} · mean {cal.mean_px.toFixed(2)} px · worst {cal.max_px.toFixed(2)} px · limit {cal.limit_px??'—'} px</span></div><ResidualPlot residuals={cal.residuals??[]}/></>}
 {s?.live?.calibration_reason&&!demo&&!autoRunning&&!manualWizard&&<p className="warning">{s.live.calibration_reason}</p>}
 {notice&&<p role="status" className="notice">{notice}</p>}
 </section><PhysicalDiagnostics token={token} enabled={!!(s?.live?.camera&&s.live.projection_ready&&!demo)} wizard={s?.wizard??null}/></div>;
}
