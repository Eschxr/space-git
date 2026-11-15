'use client';
import {useEffect,useRef,useState} from 'react';
import type {Edge} from './edge';

// Viewer cameras 1–4 correspond to capture slots Floor, Radial A, B, C.
const VIEWER_SLOTS = [4,1,2,3];

export function CameraRigViewer({edge}:{edge:Edge|null}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [ready,setReady] = useState(false);
  const [refresh,setRefresh] = useState(0);
  const [status,setStatus] = useState('Loading camera viewer…');
  const [failed,setFailed] = useState(false);

  useEffect(()=>{
    function message(event:MessageEvent) {
      if(event.origin!==location.origin || event.source!==frame.current?.contentWindow)return;
      if(event.data?.type==='spacegit-rig-ready')setReady(true);
      if(event.data?.type==='spacegit-rig-loaded') {
        setStatus('Loaded Floor, Radial A, Radial B and Radial C with the supplied camera poses.');
        setFailed(false);
      }
      if(event.data?.type==='spacegit-rig-error') {
        setStatus(String(event.data.message));
        setFailed(true);
      }
    }
    window.addEventListener('message',message);
    return ()=>window.removeEventListener('message',message);
  },[]);

  useEffect(()=>{
    if(!ready)return;
    const abort = new AbortController();
    async function load() {
      setFailed(false);
      if(!edge) {
        setStatus('Connect cameras in Capture to load the generated PLY files. You can also use Load PLY in the viewer.');
        return;
      }
      setStatus('Loading the four generated point clouds…');
      try {
        const clouds = await Promise.all(VIEWER_SLOTS.map(async slot=>{
          const blob=await edge!.pointcloud(slot,abort.signal);
          return blob.arrayBuffer();
        }));
        if(!abort.signal.aborted)frame.current?.contentWindow?.postMessage({type:'spacegit-rig-clouds',clouds},location.origin,clouds);
      } catch(error) {
        if(!abort.signal.aborted) {
          setStatus(error instanceof Error?error.message:'Could not load the generated PLY files.');
          setFailed(true);
        }
      }
    }
    void load();
    return ()=>abort.abort();
  },[edge,ready,refresh]);

  return <section className="nw-panel" aria-label="Multi-camera PLY rig">
    <div className="nw-panel-head">
      <div><h2>Multi-camera PLY rig</h2><p>1 FLOOR · 2 RADIAL A · 3 RADIAL B · 4 RADIAL C</p></div>
      <button className="nw-btn nw-tiny" disabled={!ready||!edge} onClick={()=>setRefresh(value=>value+1)}>Reload PLY files</button>
    </div>
    <p className="nw-fine" role={failed?'alert':'status'} style={{padding:'0 16px'}}>{status}</p>
    <iframe ref={frame} src="/camera-rig/index.html" title="Camera poses and generated PLY point clouds"
      allow="fullscreen" style={{display:'block',width:'100%',height:'min(820px, 78vh)',minHeight:560,border:0}}/>
  </section>;
}
