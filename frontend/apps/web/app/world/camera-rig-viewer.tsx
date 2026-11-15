'use client';
import {useEffect,useRef,useState} from 'react';
import type {Edge} from './edge';
import type {ProjectedObject} from './domain';
import type {Representation,ViewStyle} from './surface-types';

// Viewer cameras 1–4 correspond to capture slots Floor, Radial A, B, C.
const VIEWER_SLOTS = [4,1,2,3];

export function CameraRigViewer({edge,projection=false,version,objects,editId,onMove,file,surfaceId,representation='original',style}:{
  edge:Edge|null;projection?:boolean;version?:string;objects?:ProjectedObject[];editId?:string;
  onMove?:(id:string,offset:[number,number,number])=>void;file?:File;surfaceId?:string;
  representation?:Representation;style?:ViewStyle;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [ready,setReady] = useState(false);
  const [refresh,setRefresh] = useState(0);
  const [status,setStatus] = useState('Loading camera viewer…');
  const [failed,setFailed] = useState(false);
  const [loaded,setLoaded] = useState(false);
  const [surfaceStatus,setSurfaceStatus] = useState('');

  useEffect(()=>{
    function message(event:MessageEvent) {
      if(event.origin!==location.origin || event.source!==frame.current?.contentWindow)return;
      if(event.data?.type==='spacegit-rig-ready')setReady(true);
      if(event.data?.type==='spacegit-rig-loaded') {
        setLoaded(true);
        setStatus(event.data.single?'Loaded the original PLY in its file coordinates.':'Loaded Floor, Radial A, Radial B and Radial C with the supplied camera poses.');
        setFailed(false);
      }
      if(event.data?.type==='spacegit-surface-loaded')setSurfaceStatus('');
      if(event.data?.type==='spacegit-surface-error')setSurfaceStatus(String(event.data.message));
      if(event.data?.type==='spacegit-rig-error') {
        setStatus(String(event.data.message));
        setFailed(true);
      }
    }
    // The fullscreen projector can own the iframe in a separate window.
    const owner=frame.current?.ownerDocument.defaultView;
    owner?.addEventListener('message',message);
    return ()=>owner?.removeEventListener('message',message);
  },[]);

  useEffect(()=>{
    if(!editId||!onMove)return;
    const id=editId;
    const notify=onMove;
    function move(event:MessageEvent) {
      if(event.origin!==location.origin||event.source!==frame.current?.contentWindow||event.data?.type!=='spacegit-object-moved'||event.data.id!==id)return;
      const offset:unknown=event.data.offset;
      if(Array.isArray(offset)&&offset.length===3&&offset.every(value=>typeof value==='number'&&Number.isFinite(value)&&Math.abs(value)<=100))notify(id,offset as [number,number,number]);
    }
    const owner=frame.current?.ownerDocument.defaultView;
    owner?.addEventListener('message',move);
    return ()=>owner?.removeEventListener('message',move);
  },[editId,onMove]);

  useEffect(()=>{
    if(!ready)return;
    const abort = new AbortController();
    async function load() {
      setFailed(false);setLoaded(false);
      if(file){
        setStatus('Loading the original PLY…');
        try{
          const cloud=await file.arrayBuffer();
          if(!abort.signal.aborted)frame.current?.contentWindow?.postMessage({type:'spacegit-rig-single',cloud},location.origin,[cloud]);
        }catch(error){
          if(!abort.signal.aborted){setStatus(String(error));setFailed(true);}
        }
        return;
      }
      if(!edge) {
        setStatus(projection?'Connect the local edge to project the camera reconstruction.':'Connect cameras in Capture to load the generated PLY files. You can also use Load PLY in the viewer.');
        return;
      }
      setStatus('Loading the four generated point clouds…');
      try {
        const clouds = await Promise.all(VIEWER_SLOTS.map(async slot=>{
          const blob=await edge!.pointcloud(slot,abort.signal,version);
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
  },[edge,ready,refresh,projection,version,file]);

  useEffect(()=>{
    if(!ready||!loaded)return;
    const abort=new AbortController();
    const send=(payload:object,transfer:ArrayBuffer[]=[])=>frame.current?.contentWindow?.postMessage(payload,location.origin,transfer);
    async function show(){
      if(representation==='original'||!surfaceId||!edge){
        send({type:'spacegit-surface',representation:'original'});
        setSurfaceStatus('');
        return;
      }
      setSurfaceStatus(representation==='mesh'?'Loading the smooth surface…':'Loading the cleaned points…');
      try{
        const clouds=await Promise.all((file?[1]:VIEWER_SLOTS).map(async slot=>{
          const blob=await edge.surfaceFile(surfaceId,slot,representation,abort.signal);
          return blob.arrayBuffer();
        }));
        if(!abort.signal.aborted)send({type:'spacegit-surface',representation,clouds},clouds);
      }catch(error){
        if(!abort.signal.aborted){send({type:'spacegit-surface',representation:'original'});setSurfaceStatus(String(error));}
      }
    }
    void show();
    return ()=>abort.abort();
  },[ready,loaded,edge,surfaceId,representation,file]);

  useEffect(()=>{
    if(ready&&style)frame.current?.contentWindow?.postMessage({type:'spacegit-surface-style',style},location.origin);
  },[ready,style]);

  useEffect(()=>{
    if(ready&&projection)frame.current?.contentWindow?.postMessage({type:'spacegit-projected-objects',objects:objects??[],editId},location.origin);
  },[ready,projection,objects,editId]);

  const url='/camera-rig/index.html'+(projection?'?projection=1':'');
  if(projection)return <div className="nw-rig-projection">
    <iframe ref={frame} src={url} title="Projected camera reconstruction"/>
    {!loaded&&<p className="nw-render-note" role={failed?'alert':'status'}>{status}</p>}
    {surfaceStatus&&<p className="nw-render-note" role="status">{surfaceStatus}</p>}
  </div>;

  return <section className="nw-panel" aria-label="Multi-camera PLY rig">
    <div className="nw-panel-head">
      <div><h2>{file?'Point cloud preview':'Multi-camera PLY rig'}</h2><p>{file?file.name:'1 FLOOR · 2 RADIAL A · 3 RADIAL B · 4 RADIAL C'}</p></div>
      <button className="nw-btn nw-tiny" disabled={!ready||(!edge&&!file)} onClick={()=>setRefresh(value=>value+1)}>Reload PLY files</button>
    </div>
    <p className="nw-fine" role={failed?'alert':'status'} style={{padding:'0 16px'}}>{surfaceStatus||status}</p>
    <iframe ref={frame} src={url} title="Camera poses and generated PLY point clouds"
      allow="fullscreen" style={{display:'block',width:'100%',height:'min(820px, 78vh)',minHeight:560,border:0}}/>
  </section>;
}
