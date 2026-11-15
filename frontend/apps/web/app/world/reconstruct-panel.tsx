'use client';
import Link from 'next/link';
import {useState} from 'react';
import type {Commit,Job} from '../../../../packages/protocol/types';
import {Icon} from '../components/icons';
import {isNormalized,type Asset,type Delta} from './domain';
import {type Edge} from './edge';
import {RenderScene,useSceneAsset} from './render-scene';
import {CameraRigViewer} from './camera-rig-viewer';

export function ReconstructPanel({before,after,rows,edge,jobs,openProject,refreshJobs}:{before?:Commit;after?:Commit;rows:Delta[];edge:Edge|null;jobs:Job[];openProject:(commit:Commit|undefined,remote:Asset|null,local:File|null)=>void;refreshJobs:()=>void}) {
  const [comparison,setComparison]=useState<'after'|'before'|'overlay'>('after');
  const [viewer,setViewer]=useState<'rig'|'scene'>(edge?'rig':'scene');
  const [selected,setSelected]=useState(''),[cloud,setCloud]=useState(false),[low,setLow]=useState(false),[reset,setReset]=useState(0);
  const [local,setLocal]=useState<File|null>(null),[remote,setRemote]=useState<Asset|null>(null);
  const pick=comparison==='before'?before:after;
  const asset=useSceneAsset(edge,remote,local);
  const scene=asset.data&&'scene' in asset.data?asset.data.scene:pick?.scene;
  const simulated=pick?.evidence?.mode==='demo'&&!asset.data;
  const object=scene?.objects.find(card=>card.id===selected);
  const availableAssets=jobs.filter(job=>job.asset&&job.commit===pick?.id).flatMap(job=>
    (job.artifacts??[{name:'sparse.ply'}]).filter(a=>/\.(ply|glb|gltf)$/i.test(a.name)).map(a=>({id:job.asset!,name:a.name,label:a.name+' · '+job.id.slice(0,6),job})));
  const displayPoints=cloud&&(!asset.data||'geometry' in asset.data);
  return <>
    <div className="nw-titlebar">
      <div><div className="nw-eyebrow"><span/> 03 / SPATIAL MODEL</div><h1>Reconstruct</h1><p>Explore scene geometry and inspect how the room changed.</p></div>
      <div className="nw-actions">
        <button className="nw-btn" aria-pressed={viewer==='rig'} onClick={()=>setViewer('rig')}>Camera rig</button>
        <button className="nw-btn" aria-pressed={viewer==='scene'} onClick={()=>setViewer('scene')}>Scene revision</button>
        <button className="nw-btn nw-primary" onClick={()=>openProject(pick,asset.data?remote:null,asset.data?local:null)}><Icon name="screen"/>Open projector view</button>
      </div>
    </div>
    {viewer==='rig'?<CameraRigViewer edge={edge}/>:<div className="nw-workspace-grid">
      <section className="nw-panel nw-view-panel" aria-label="Reconstruction">
        <div className="nw-panel-head"><div><h2>Scene viewport</h2><p>{asset.data ? 'MODEL ASSET' : simulated ? 'SIMULATED STUDY' : 'STORED LAYOUT GEOMETRY'}</p></div>
          <div className="nw-actions">
            <button className="nw-btn nw-tiny" disabled={!before} aria-pressed={comparison==='before'&&!asset.data} onClick={()=>{setLocal(null);setRemote(null);setComparison('before');setSelected('');}}>Previous</button>
            <button className="nw-btn nw-tiny" disabled={!after} aria-pressed={comparison==='after'&&!asset.data} onClick={()=>{setLocal(null);setRemote(null);setComparison('after');setSelected('');}}>Current</button>
            <button className="nw-btn nw-tiny" disabled={!before||!after} aria-pressed={comparison==='overlay'&&!asset.data} onClick={()=>{setLocal(null);setRemote(null);setComparison('overlay');setSelected('');}}>Compare</button>
            <button className="nw-btn nw-tiny" onClick={()=>setReset(n=>n+1)}><Icon name="rotate" size={14}/>Reset view</button>
          </div>
        </div>
        <div className="nw-viewport" data-testid="reconstruction">
          {scene||asset.data ? <RenderScene scene={scene} simulated={simulated} selected={selected} select={setSelected}
            cloud={displayPoints} asset={asset.data} lowPower={low} reset={reset}
            diff={comparison==='overlay'&&!asset.data?rows:[]}/> : <div className="nw-render-note">Commit a snapshot or open a PLY, GLB or glTF model to inspect it here.</div>}
          {(scene||asset.data)&&<div className="nw-view-corner">ORBIT · PAN · ZOOM</div>}
        </div>
        <div className="nw-panel-foot">
          <label className="nw-check"><input type="checkbox" checked={cloud} onChange={e=>setCloud(e.target.checked)} disabled={!simulated&&!(asset.data&&'geometry' in asset.data)}/>Point cloud</label>
          <label className="nw-check"><input type="checkbox" checked={low} onChange={e=>setLow(e.target.checked)}/>Reduce quality</label>
          <span>{comparison==='overlay'&&!asset.data?'WIREFRAME = PREVIOUS POSITION':'DRAG TO ORBIT · RIGHT DRAG TO PAN'}</span>
        </div>
      </section>
      <div className="nw-side-stack">
        <section className="nw-panel"><div className="nw-panel-head"><div><h2>Provenance</h2><p>RECONSTRUCTION STATUS</p></div><Icon name="cube"/></div>
          <dl className="nw-meta"><div><dt>Source</dt><dd>{local?local.name:remote?.name??pick?.message??'Awaiting scene'}</dd></div>
            <div><dt>Confidence</dt><dd>{remote?.job ? remote.job.stage+' · unverified geometry' : asset.data ? 'Unverified asset' : simulated ? 'Fixture geometry' : scene ? 'Saved layout · no dense estimate' : 'Unavailable'}</dd></div>
            <div><dt>Coordinates</dt><dd>{asset.data ? 'Asset units unless calibrated' : simulated ? 'Synthetic metres' : scene?.frame==='wall-world-meters'&&pick?.evidence?.calibration?'Calibrated wall metres':isNormalized(scene)?'Normalized wall':'Layout units'}</dd></div>
            <div><dt>Capture</dt><dd>{pick?.evidence?.timestamp ? new Date(pick.evidence.timestamp*1000).toLocaleString() : 'No capture timestamp'}</dd></div></dl>
          {asset.message&&<p role={asset.error?'alert':'status'} className="nw-fine">{asset.message}</p>}
          {edge&&<div className="nw-asset-actions">
            {availableAssets.length>0&&<label>Edge artifact<select className="nw-field" value={remote?remote.id+':'+remote.name:''} onChange={e=>{
              setLocal(null); const choice=availableAssets.find(a=>a.id+':'+a.name===e.target.value);setRemote(choice??null);setCloud(!!choice?.name.endsWith('.ply'));setSelected('');
            }}><option value="">Layout only</option>{availableAssets.map(a=><option key={a.id+':'+a.name} value={a.id+':'+a.name}>{a.label}</option>)}</select></label>}
            <button className="nw-btn nw-tiny" onClick={refreshJobs}>Refresh worker jobs</button><Link className="nw-btn nw-tiny" href="/studio/capture">Open reconstruction tools ↗</Link>
          </div>}
          <label className="nw-upload">Open local model<input type="file" accept=".ply,.glb,.gltf" onChange={e=>{const file=e.target.files?.[0];if(file){setRemote(null);setLocal(file);setCloud(file.name.toLowerCase().endsWith('.ply'));setSelected('');}e.target.value='';}}/></label>
          {(remote||local)&&<button className="nw-btn nw-tiny nw-clear-asset" onClick={()=>{setLocal(null);setRemote(null);setCloud(false);setSelected('');}}>Return to layout</button>}
        </section>
        <section className="nw-panel"><div className="nw-panel-head"><div><h2>Object inspector</h2><p>{scene?.objects.length??0} REGISTERED OBJECTS</p></div><Icon name="target"/></div>
          {scene?.objects.length&&(!asset.data||'scene' in asset.data||'geometry' in asset.data&&!cloud)?<>
            <div className="nw-object-select">{scene.objects.map(card=><button key={card.id} className="nw-btn nw-tiny" aria-pressed={selected===card.id} onClick={()=>setSelected(card.id)}>{card.name}</button>)}</div>
            {object ? <dl className="nw-meta"><div><dt>Identity</dt><dd>{object.id}</dd></div><div><dt>Wall X / Y</dt><dd>{object.x.toFixed(2)} / {object.y.toFixed(2)}</dd></div><div><dt>Width / H / D</dt><dd>{object.w.toFixed(2)} / {object.h.toFixed(2)} / {object.d.toFixed(2)}</dd></div></dl> : <p className="nw-fine">Select an object in the scene or from the list.</p>}
          </>:<p className="nw-fine">No stable object identities are attached to this geometry.</p>}
        </section>
      </div>
    </div>}
  </>;
}
