'use client';
import {useEffect,useState} from 'react';
import Link from 'next/link';
import {Icon} from '../components/icons';
import {CAMERAS, CAMERA_ORDER, type Capture, type Rig, type RigSettings} from './domain';
import type {Edge} from './edge';
import {RigDiagram,RigLabels} from './previews';
import {RigEditor} from './rig-editor';

export function CapturePanel({rig, edge, active, captures, busy, capture, choose, toggle, local, connect, saveRig}:{
  rig:Rig; edge:Edge|null; active:Capture|null; captures:Capture[]; busy:string; capture:()=>void; choose:(item:Capture|null)=>void;
  toggle:()=>void; local:boolean; connect:()=>void;
  saveRig:(settings:RigSettings)=>void;
}) {
  const liveCount=rig.feeds.filter(f=>f.status==='live').length;
  const order=active?.order ?? (active ? CAMERA_ORDER : rig.settings?.order??CAMERA_ORDER);
  return <>
    <div className="nw-titlebar">
      <div><div className="nw-eyebrow"><span/> 01 / ACQUISITION</div><h1>Capture</h1><p>Record the room from a single camera pole.</p></div>
      <div className="nw-actions">
        {local && !edge && <button className="nw-btn" disabled={!!busy} onClick={connect}>{busy==='connect'?'Connecting…':'Connect cameras'}</button>}
        {edge && rig.mode==='live' && <button className="nw-btn" onClick={toggle} disabled={!!busy}>{rig.enabled?'Stop live previews':'Start live previews'}</button>}
        <button className="nw-btn nw-primary" onClick={capture} disabled={!!busy||!edge||!liveCount}><Icon name="camera" size={17}/>{busy==='capture'?'Capturing frames…':'Capture session'}</button>
      </div>
    </div>
    <div className="nw-capture-layout">
      <section className="nw-panel nw-feed-panel" aria-label="Camera feeds">
        <div className="nw-panel-head"><div><h2>Camera feeds</h2><p>POLE 01 <b>·</b> {active ? 'SESSION ' + active.id.slice(0,8).toUpperCase() : 'MONITOR'}</p></div>
          <div className="nw-actions nw-small-actions">
            {active && <button className="nw-btn nw-tiny" onClick={()=>choose(null)}>Back to monitor</button>}
            <span className="nw-chip"><i/>{active ? active.feeds.length+'/4 SAVED' : liveCount+'/4 LIVE'}</span>
          </div>
        </div>
        {busy==='capture'&&<><progress className="nw-progress" aria-label="Capture progress"/><p role="status">Saving the session and waiting for any configured PLY generation to finish.</p></>}
        <div className="nw-feeds">{order.map(id=>{
          const cam=CAMERAS.find(camera=>camera.id===id)!;
          const feed=rig.feeds.find(f=>f.id===cam.id);
          const status=active ? active.feeds.includes(cam.id) ? 'captured' : 'no frame' : feed?.status ?? 'offline';
          return <article className="nw-feed" key={cam.id}>
            <div className="nw-feed-view">
              {(status==='live'||status==='captured')&&edge ?
                <LiveFrame key={active?.id??String(rig.settings?.sources[cam.id-1])} id={cam.id} edge={edge} capture={active?.id}/> :
                <div className="nw-feed-empty"><Icon name="camera" size={27}/><span>{status==='unmapped'?'No camera assigned':status==='waiting'?'Waiting for a fresh frame':'No live frame'}</span></div>}
              <span className="nw-feed-tag"><i/>{status}</span><span className="nw-feed-angle">{cam.angle}</span>
            </div>
            <div className="nw-feed-caption"><span className="nw-feed-number">{String(cam.id).padStart(2,'0')}</span><div><h3>{cam.name}</h3><p>{cam.direction}</p></div>
              <span className="nw-feed-age" title="Age of the latest frame at the edge">{status==='live'&&feed?.age_ms!=null ? feed.age_ms+' ms' : status==='captured'?'SAVED':'—'}</span></div>
            {!active&&feed?.error&&feed.status!=='live'&&<p className="nw-feed-error">{feed.error}</p>}
          </article>;
        })}</div>
      </section>
      <div className="nw-side-stack">
        <section className="nw-panel"><div className="nw-panel-head"><div><h2>Pole layout</h2><p>SINGLE AXIS <b>·</b> FOUR CAMERAS</p></div><Icon name="target" size={20}/></div>
          <RigDiagram/><RigLabels/>
          {edge && rig.mode==='live' && rig.settings && <RigEditor key={JSON.stringify(rig.settings)} edge={edge} settings={rig.settings} disabled={!!busy} save={saveRig}/>}
          {local && !edge && <p className="nw-fine"><Link href="/setup">Connect with an operator key in Hardware Setup</Link></p>}
        </section>
        <section className="nw-panel"><div className="nw-panel-head"><div><h2>Recent sessions</h2><p>LOCAL EDGE</p></div><Icon name="history" size={19}/></div>
          {!captures.length ? <p className="nw-fine">No sessions yet. Capture a frame from each available feed to begin.</p> :
            <div className="nw-sessions">{captures.slice(0,6).map(item=><button key={item.id} className="nw-session" aria-pressed={active?.id===item.id} onClick={()=>choose(item)}>
              <span><strong>Live capture</strong><small>{new Date(item.created*1000).toLocaleString()}</small></span><span>{item.feeds.length}/4 <Icon name="chevron" size={13}/></span>
            </button>)}</div>}
          {<p className="nw-fine">Object observations require a calibrated workspace. <Link href="/setup">Open hardware setup ↗</Link></p>}
        </section>
      </div>
    </div>
  </>;
}

function LiveFrame({edge,id,capture}:{edge:Edge;id:number;capture?:string}) {
  const [url,setUrl]=useState(''),[error,setError]=useState(false);
  useEffect(()=>{
    const abort=new AbortController();
    let timeout: ReturnType<typeof setTimeout>, current:string|undefined;
    const update=async()=>{
      const started=performance.now();
      try{
        const frame=await edge.preview(id,abort.signal,capture);
        if(abort.signal.aborted)return;
        const next=URL.createObjectURL(frame);
        if(current)URL.revokeObjectURL(current);
        current=next;setUrl(next);setError(false);
      }catch{
        if(!abort.signal.aborted){
          if(current)URL.revokeObjectURL(current);
          current=undefined;setUrl('');setError(true);
        }
      }finally{
        if(!capture&&!abort.signal.aborted)timeout=setTimeout(update,Math.max(0,125-(performance.now()-started)));
      }
    };
    queueMicrotask(()=>{if(!abort.signal.aborted){setUrl('');setError(false);void update();}});
    return ()=>{abort.abort();clearTimeout(timeout);if(current)URL.revokeObjectURL(current);};
  },[edge,id,capture]);
  // The edge supplies a private blob URL rather than a public or optimizable image.
  // eslint-disable-next-line @next/next/no-img-element
  return url?<img className="nw-feed-art nw-camera-image" src={url} alt={'Camera '+id+' preview'}/>:<div className="nw-feed-empty">{error?'Frame unavailable':'Loading camera frame…'}</div>;
}
