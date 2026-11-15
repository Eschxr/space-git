'use client';

import {useEffect,useRef,useState} from 'react';
import {CameraRigViewer} from './camera-rig-viewer';
import type {RigModel} from './domain';
import type {Edge} from './edge';
import {originalView,type Representation,type SurfaceAction,type SurfaceJob,type SurfaceSettings} from './surface-types';

const initial:SurfaceSettings={outliers:true,outlier_strength:2.5,voxel:0,depth:9,density_percent:2,
  support:4,smoothing:3,smoothing_intensity:.45};
const representations:Record<Representation,string>={original:'Original points',cleaned:'Cleaned points',mesh:'Smooth mesh'};
const slotNames=['','Radial A','Radial B','Radial C','Floor'];

function Range({label,value,min,max,step=1,change}:{label:string;value:number;min:number;max:number;step?:number;change:(n:number)=>void}) {
  return <label className="nw-surface-range"><span>{label}<output>{value}</output></span>
    <input type="range" value={value} min={min} max={max} step={step} onChange={event=>change(Number(event.target.value))}/>
  </label>;
}

export function SurfacePanel({edge}:{edge:Edge|null}) {
  const [versions,setVersions]=useState<RigModel[]>([]);
  const [selected,setSelected]=useState('');
  const [local,setLocal]=useState<{file:File;key:string;source?:string}>();
  const [settings,setSettings]=useState(initial);
  const [style,setStyle]=useState(originalView);
  const [mode,setMode]=useState<Representation>('original');
  const [job,setJob]=useState<SurfaceJob>();
  const [saved,setSaved]=useState<SurfaceJob>();
  const [preview,setPreview]=useState<SurfaceJob>();
  const [analysis,setAnalysis]=useState<SurfaceJob>();
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [exportSlot,setExportSlot]=useState(1);
  const upload=useRef<AbortController|null>(null);
  const version=selected||versions[0]?.id;
  const source=local?local.source:version;
  const pending=job?.status==='queued'||job?.status==='running';
  const pendingId=pending?job?.id:undefined;
  const available=preview?.source===source?preview:saved?.source===source?saved:undefined;
  const summary=available??(analysis?.source===source?analysis:undefined);

  useEffect(()=>{
    if(!edge)return;
    let stop=false;
    edge.rigModels().then(items=>{if(!stop)setVersions(items);}).catch(()=>{});
    return ()=>{stop=true;};
  },[edge]);

  useEffect(()=>{
    if(!edge||!source||local)return;
    let stop=false;
    edge.latestSurface(source).then(item=>{if(!stop&&item)setSaved(item);}).catch(()=>{});
    return ()=>{stop=true;};
  },[edge,source,local]);

  useEffect(()=>{
    if(!edge||!pendingId)return;
    let stop=false;
    let timer:ReturnType<typeof setTimeout>;
    async function check(){
      try{
        const item=await edge!.surfaceJob(pendingId!);
        if(stop)return;
        setJob(item);
        if(item.status==='queued'||item.status==='running'){timer=setTimeout(check,800);return;}
        if(item.status==='failed')setError(item.error||'Surface reconstruction failed.');
        if(item.status!=='complete')return;
        if(item.action==='analyse'){
          setAnalysis(item);
          const recommended=Math.max(...Object.values(item.reports??{}).map(report=>report.recommended_depth));
          if(Number.isFinite(recommended))setSettings(value=>({...value,depth:recommended}));
        }else{
          if(item.action==='smooth')setPreview(item);else{setSaved(item);setPreview(undefined);}
          setMode('mesh');
        }
      }catch(problem){
        if(!stop){setError(problem instanceof Error?problem.message:'Could not check progress.');timer=setTimeout(check,2500);}
      }
    }
    timer=setTimeout(check,500);
    return ()=>{stop=true;clearTimeout(timer);};
  },[edge,pendingId]);

  useEffect(()=>()=>upload.current?.abort(),[]);

  function chooseFile(file?:File) {
    if(!file)return;
    if(file.size>192*1024*1024){setError('Choose a PLY smaller than 192 MiB.');return;}
    setLocal({file,key:crypto.randomUUID()});setMode('original');setJob(undefined);setError('');
  }

  async function run(action:SurfaceAction) {
    if(!edge)return;
    setBusy(true);setError('');
    try{
      let input=source;
      if(!input&&local){
        upload.current=new AbortController();
        const uploaded=await edge.uploadCloud(local.file,upload.current.signal);
        input=uploaded.source;
        setLocal({...local,source:input});
      }
      if(!input)throw Error('Select a saved camera version or load a PLY.');
      setJob(await edge.startSurface(input,action,settings,action==='smooth'?available?.id:undefined));
    }catch(problem){if(!(problem instanceof DOMException&&problem.name==='AbortError'))setError(problem instanceof Error?problem.message:'Could not start processing.');}
    finally{upload.current=null;setBusy(false);}
  }

  async function saveCurrent() {
    if(!edge)return;
    setBusy(true);setError('');
    try{
      const item=await edge.saveCurrentRig();
      setVersions(current=>[item,...current.filter(value=>value.id!==item.id)]);
      setSelected(item.id);setLocal(undefined);setMode('original');
    }catch(problem){setError(String(problem));}
    finally{setBusy(false);}
  }

  async function exportFile(artifact:Representation|'report') {
    if(!edge||!available)return;
    setError('');
    try{
      const slot=available.slots.includes(exportSlot)?exportSlot:available.slots[0];
      const blob=await edge.surfaceFile(available.id,slot,artifact);
      const url=URL.createObjectURL(blob);
      const link=document.createElement('a');
      link.href=url;
      link.download=slot+'-'+({original:'original.ply',cleaned:'cleaned_pointcloud.ply',mesh:'reconstructed_mesh.ply',report:'reconstruction_report.json'}[artifact]);
      document.body.appendChild(link);
      link.click();link.remove();
      setTimeout(()=>URL.revokeObjectURL(url),5000);
    }catch(problem){setError(String(problem));}
  }

  async function applyPreview() {
    if(!edge||!preview)return;
    try{setSaved(await edge.applySurface(preview.id));setPreview(undefined);}
    catch(problem){setError(String(problem));}
  }

  function update<K extends keyof SurfaceSettings>(key:K,value:SurfaceSettings[K]){setSettings(current=>({...current,[key]:value}));}
  const canRun=!!edge&&!!(local||version)&&!busy&&!pending;
  const preset=({0:'off',3:'light',8:'balanced',15:'strong'} as Record<number,string>)[settings.smoothing]??'custom';
  return <div className="nw-surface-workspace">
    <section className="nw-panel" aria-label="Surface reconstruction">
      <div className="nw-panel-head"><div><h2>Surface reconstruction</h2><p>Open3D · CPU processing</p></div></div>
      <div className="nw-surface-controls">
        <div className="nw-actions">
          <label>Load PLY <input className="nw-field" type="file" accept=".ply" disabled={busy||pending} onChange={event=>{chooseFile(event.target.files?.[0]);event.target.value='';}}/></label>
          {!!versions.length&&<label>Saved camera scan <select className="nw-field" value={local?'':version} disabled={busy||pending}
            onChange={event=>{setSelected(event.target.value);setLocal(undefined);setMode('original');setJob(undefined);setError('');}}>
            {local&&<option value="" disabled>Local PLY</option>}
            {versions.map((item,index)=><option value={item.id} key={item.id}>{index===0?'Latest · ':''}{new Date(item.created*1000).toLocaleString()}</option>)}
          </select></label>}
          {edge&&!versions.length&&!local&&<button className="nw-btn nw-tiny" disabled={busy} onClick={()=>void saveCurrent()}>Save current PointDiT output</button>}
        </div>
        <div className="nw-actions" aria-label="Scan representation">
          {(Object.keys(representations) as Representation[]).map(value=><button className="nw-btn nw-tiny" type="button" key={value}
            aria-pressed={(available?mode:'original')===value} disabled={value!=='original'&&!available} onClick={()=>setMode(value)}>{representations[value]}</button>)}
        </div>
        <div className="nw-actions">
          <button className="nw-btn nw-tiny" disabled={!canRun} onClick={()=>void run('analyse')}>Analyse scan</button>
          <button className="nw-btn nw-primary" disabled={!canRun} onClick={()=>void run('reconstruct')}>Build smooth mesh</button>
          {pendingId&&<button className="nw-btn nw-tiny" onClick={()=>void edge?.cancelSurface(pendingId).catch(problem=>setError(String(problem)))}>Cancel processing</button>}
          {busy&&<button className="nw-btn nw-tiny" disabled={!local||!!local.source} onClick={()=>upload.current?.abort()}>Cancel upload</button>}
        </div>
        {!edge&&<p className="nw-fine">Connect the local edge in Capture to process a scan. You can still preview a PLY here.</p>}
        {job&&<p className="nw-fine" role="status">{job.status==='cancelled'?'Processing cancelled.':job.stage}
          {pending&&job.slot&&job.model?` · ${slotNames[job.slot]} · ${job.completed}/${job.slots.length} views`:''}</p>}
        {error&&<p className="nw-fine" role="alert">{error}</p>}
        {summary?.reports&&<details>
          <summary>Scan analysis and validation</summary>
          {Object.entries(summary.reports).map(([slot,report])=><p className="nw-fine" key={slot}>
            {summary.model?slotNames[Number(slot)]+' · ':''}{report.input.points.toLocaleString()} original points
            {report.cleaned_points!==undefined?` · ${report.cleaned_points.toLocaleString()} cleaned`:''}
            {report.mesh?` · ${report.mesh.triangles.toLocaleString()} triangles · ${Math.round(report.mesh.supported_fraction*100)}% supported`:''}
            {' · '}Spacing {report.input.spacing.toPrecision(3)} in input units · depth {report.recommended_depth} recommended
            {report.warnings.length>0&&<><br/>{report.warnings.join(' ')}</>}
          </p>)}
        </details>}
        <details>
          <summary>Reconstruction settings</summary>
          <div className="nw-surface-fields">
            <label><input type="checkbox" checked={settings.outliers} onChange={event=>update('outliers',event.target.checked)}/> Remove outliers</label>
            <Range label="Outlier tolerance (standard deviations)" value={settings.outlier_strength} min={1.5} max={6} step={.25} change={n=>update('outlier_strength',n)}/>
            <Range label="Voxel size × point spacing (0 = off)" value={settings.voxel} min={0} max={12} step={.5} change={n=>update('voxel',n)}/>
            <Range label="Poisson depth" value={settings.depth} min={5} max={11} change={n=>update('depth',n)}/>
            <Range label="Lowest density to trim (%)" value={settings.density_percent} min={0} max={10} step={.5} change={n=>update('density_percent',n)}/>
            <Range label="Gap support × local spacing" value={settings.support} min={1.5} max={8} step={.5} change={n=>update('support',n)}/>
          </div>
        </details>
        <details>
          <summary>Mesh smoothing</summary>
          <div className="nw-surface-fields">
            <label>Smoothing preset <select className="nw-field" value={preset} onChange={event=>update('smoothing',({off:0,light:3,balanced:8,strong:15} as Record<string,number>)[event.target.value])}>
              <option value="off">Off</option><option value="light">Light</option><option value="balanced">Balanced</option><option value="strong">Strong</option>
              {preset==='custom'&&<option value="custom">Custom</option>}
            </select></label>
            <Range label="Smoothing iterations" value={settings.smoothing} min={0} max={15} change={n=>update('smoothing',n)}/>
            <Range label="Smoothing intensity" value={settings.smoothing_intensity} min={.1} max={.5} step={.05} change={n=>update('smoothing_intensity',n)}/>
          </div>
          <div className="nw-actions">
            <button className="nw-btn nw-tiny" disabled={!canRun||!available} onClick={()=>void run('smooth')}>Preview smoothing</button>
            {preview&&preview.source===source&&<>
              <button className="nw-btn nw-tiny" onClick={()=>void applyPreview()}>Apply preview</button>
              <button className="nw-btn nw-tiny" onClick={()=>setPreview(undefined)}>Discard preview</button>
            </>}
          </div>
        </details>
        <details>
          <summary>Display settings</summary>
          <div className="nw-surface-fields">
            <Range label="Point size" value={style.pointSize} min={.25} max={3} step={.05} change={n=>setStyle({...style,pointSize:n})}/>
            <Range label="Point opacity" value={style.pointOpacity} min={.1} max={1} step={.05} change={n=>setStyle({...style,pointOpacity:n})}/>
            <Range label="Mesh opacity" value={style.meshOpacity} min={.1} max={1} step={.05} change={n=>setStyle({...style,meshOpacity:n})}/>
            <Range label="Mesh colour intensity" value={style.colour} min={.3} max={1.4} step={.05} change={n=>setStyle({...style,colour:n})}/>
            <Range label="Light intensity" value={style.lighting} min={.3} max={1.6} step={.05} change={n=>setStyle({...style,lighting:n})}/>
            <label>Background <input type="color" value={style.background} onChange={event=>setStyle({...style,background:event.target.value})}/></label>
          </div>
        </details>
        {available&&<div className="nw-actions" aria-label="Download surface files">
          {available.model&&<label>Export view <select className="nw-field" value={exportSlot} onChange={event=>setExportSlot(Number(event.target.value))}>
            {available.slots.map(slot=><option key={slot} value={slot}>{slotNames[slot]}</option>)}
          </select></label>}
          <button className="nw-btn nw-tiny" onClick={()=>void exportFile('mesh')}>Download mesh</button>
          <button className="nw-btn nw-tiny" onClick={()=>void exportFile('cleaned')}>Download cleaned PLY</button>
          <button className="nw-btn nw-tiny" onClick={()=>void exportFile('original')}>Download original</button>
          <button className="nw-btn nw-tiny" onClick={()=>void exportFile('report')}>Download report</button>
        </div>}
      </div>
    </section>
    <CameraRigViewer key={local?.key??version??'current'} edge={edge} version={version} file={local?.file} surfaceId={available?.id}
      representation={available?mode:'original'} style={style}/>
  </div>;
}
