'use client';
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import CaptureReview from '../image-history/capture-review';
import {VisionStatusPanel} from '../image-history/vision-status';
import {completeSession,rigSessionUpload,trackerClient,TrackerError,type CameraCommit} from '../image-history/client';
import {date,short,words} from '../image-history/evidence';
import type {Capture} from './domain';
import type {Edge} from './edge';
import '../image-history/history.css';

const BASE=process.env.NEXT_PUBLIC_SCENE_TRACKER_URL||'http://127.0.0.1:8001';

export function CameraCommits({edge,sessions,active}:{edge:Edge;sessions:Capture[];active:Capture|null}) {
  const api=useMemo(()=>trackerClient(BASE),[]);
  const [commits,setCommits]=useState<CameraCommit[]>([]),[selected,setSelected]=useState('');
  const [sourceId,setSource]=useState(''),[message,setMessage]=useState('');
  const [busy,setBusy]=useState(''),[readError,setReadError]=useState(''),[writeError,setWriteError]=useState(''),[notice,setNotice]=useState('');
  const [loaded,setLoaded]=useState(false),[more,setMore]=useState(false);
  const locked=useRef(false);
  const available=sessions.filter(completeSession);
  const source=available.find(item=>item.id===sourceId)??(active&&completeSession(active)?active:available[0]);
  const pushed=source&&commits.find(item=>item.source_session_id===source.id);
  const current=commits.find(item=>item.id===selected)??commits[0];
  const defaultMessage=source?'Camera snapshot '+new Date(source.created*1000).toLocaleString():'';

  const refresh=useCallback(async(signal?:AbortSignal)=>{
    const page=await api.cameraCommits(0,signal);
    if(signal?.aborted)return;
    setCommits(old=>[...page.items,...old.filter(item=>!page.items.some(next=>next.id===item.id))]);
    setMore(page.items.length===page.limit);setLoaded(true);setReadError('');
    return page.items;
  },[api]);

  useEffect(()=>{
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>;
    async function poll() {
      try {await refresh(controller.signal);}
      catch(error) {if(!controller.signal.aborted)setReadError((error as Error).message);}
      if(!controller.signal.aborted)timer=setTimeout(()=>void poll(),3000);
    }
    void poll();
    return ()=>{controller.abort();clearTimeout(timer);};
  },[refresh]);

  const run=useCallback((label:string,action:()=>Promise<void>)=>{
    if(locked.current)return;
    locked.current=true;setBusy(label);setWriteError('');setNotice('');
    void action().catch(error=>setWriteError((error as Error).message)).finally(()=>{locked.current=false;setBusy('');});
  },[]);

  async function push() {
    if(!source)return;
    const controller=new AbortController();
    try {
      const upload=await rigSessionUpload(source,edge.preview,controller.signal);
      let result:CameraCommit;
      try {
        result=await api.pushCameraCommit(source.id,message.trim()||defaultMessage,upload);
      } catch(error) {
        if(error instanceof TrackerError&&error.status<500)throw error;
        const saved=(await refresh())?.find(item=>item.source_session_id===source.id);
        if(!saved||saved.message!==(message.trim()||defaultMessage))throw error;
        result=saved;
      }
      setCommits(old=>[result,...old.filter(item=>item.id!==result.id)]);setSelected(result.id);setMessage('');
      setNotice('Committed and pushed all four camera images. Select the commit below to inspect what happened.');
      if(result.processing_error)setWriteError('Images are committed. Analysis could not start: '+result.processing_error);
    } finally {controller.abort();}
  }

  return <div className="ih">
    <div className="nw-titlebar"><div><h1>Version control</h1><p>Commit the saved camera session and inspect its changes.</p></div>
      <button className="nw-btn" disabled={!!busy} onClick={()=>run('Refreshing history',async()=>{await refresh();})}>Refresh history</button>
    </div>
    <VisionStatusPanel api={api}/>
    <section className="nw-panel">
      <div className="nw-panel-head"><div><h2>Commit and push</h2><p>CAMERA RIG · FOUR ORIGINAL IMAGES</p></div></div>
      <form className="ih-form" onSubmit={event=>{event.preventDefault();run('Committing and pushing images',push);}}>
        {!!available.length&&<label>Saved camera session<select className="nw-field" value={source?.id??''} disabled={!!busy} onChange={event=>{setSource(event.target.value);setMessage('');}}>
          {available.map(item=><option key={item.id} value={item.id}>{date(new Date(item.created*1000).toISOString())} · {short(item.id)} · 4/4 images</option>)}
        </select></label>}
        {!available.length&&<p>Capture a complete four-camera session to commit its images.</p>}
        <label>Commit message<input className="nw-field" placeholder={defaultMessage||'Record the room'} maxLength={2000} value={message} disabled={!!busy||!!pushed} onChange={event=>setMessage(event.target.value)}/></label>
        <button className="nw-btn nw-primary" disabled={!!busy||!source||!!pushed}>
          {pushed?'Session committed and pushed':'Commit and push'}
        </button>
        <p>The four saved images are transferred automatically and analysis starts on the server.</p>
        {pushed&&<button type="button" className="nw-btn nw-tiny" onClick={()=>setSelected(pushed.id)}>View this commit</button>}
      </form>
    </section>
    {busy&&<p className="nw-notice" role="status">{busy}…</p>}
    {notice&&<p className="nw-notice" role="status">{notice}</p>}
    {(readError||writeError)&&<p className="nw-notice" role="alert">{writeError||readError}</p>}
    <div className="ih-layout" style={{marginTop:20}}>
      <aside className="nw-panel ih-pad">
        <h2>Camera commits</h2>
        {!loaded&&!readError&&<p>Loading history…</p>}
        {loaded&&!commits.length&&<p>No camera commits yet. Commit your latest saved session above.</p>}
        <ol className="nw-timeline">{commits.map(item=><li key={item.id}><span className="nw-commit-node"/>
          <button className="nw-revision" aria-pressed={current?.id===item.id} onClick={()=>setSelected(item.id)}>
            <span className="nw-revision-title">{item.message}</span>
            <span className="nw-revision-detail">{short(item.id)} · {date(item.created_at)}</span>
            <span className="nw-revision-detail">{item.run?(item.run.provider==='real'?'Real analysis':'Simulated analysis')+' · '+words(item.run.status):'Images saved · analysis awaiting start'}</span>
            {item.parent_id&&<span className="nw-revision-detail">Parent {short(item.parent_id)}</span>}
          </button>
        </li>)}</ol>
        {more&&<button className="nw-btn nw-tiny" disabled={!!busy} onClick={()=>run('Loading older commits',async()=>{
          const page=await api.cameraCommits(commits.length);setCommits(old=>[...old,...page.items.filter(item=>!old.some(existing=>existing.id===item.id))]);setMore(page.items.length===page.limit);
        })}>Older commits</button>}
      </aside>
      <div className="ih-content">{current?<CaptureReview key={current.id+':'+(current.run?.id??'pending')} api={api} space={current.environment_id} capture={current.capture_id} busy={!!busy} run={run} readOnly committed={async()=>{await refresh();}}/>:
        <section className="nw-panel ih-empty"><h2>See what happened</h2><p>Select a camera commit to inspect its four original images, analysis status and proposed changes.</p></section>}
      </div>
    </div>
  </div>;
}
