'use client';
import Link from 'next/link';
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import type {Commit,Job} from '../../../../packages/protocol/types';
import {Icon} from '../components/icons';
import {localHost,useToken} from '../components/connection';
import {CapturePanel} from './capture-panel';
import {compareScenes,DEFAULT_PROJECTION,EMPTY_RIG,EMPTY_HISTORY,readProjection,sameSceneReference,realHistory,
  type Asset,type Capture,type Delta,type History,type Projection,type Rig,type RigSettings} from './domain';
import {edgeAdapter} from './edge';
import {HistoryPanel} from './history-panel';
import {ProjectPanel,type ProjectAPI} from './project-panel';
import {ReconstructPanel} from './reconstruct-panel';
import './world.css';

const VIEWS=[{id:'capture',label:'Capture',icon:'camera'},{id:'versions',label:'Version control',icon:'branch'},
  {id:'reconstruct',label:'Reconstruct',icon:'cube'},{id:'project',label:'Project',icon:'screen'}] as const;
type View=typeof VIEWS[number]['id'];

export default function World({projector=false}:{projector?:boolean}) {
  const [view,setView]=useState<View>(projector?'project':'capture');
  const [rig,setRig]=useState<Rig>(EMPTY_RIG),[history,setHistory]=useState<History>(EMPTY_HISTORY),[captures,setCaptures]=useState<Capture[]>([]);
  const [active,setActive]=useState<Capture|null>(null),[beforeId,setBefore]=useState(''),[afterId,setAfter]=useState(''),[projectScene,setProjectScene]=useState<Commit>();
  const [projectModel,setProjectModel]=useState<{remote:Asset|null;local:File|null}>();
  const [rows,setRows]=useState<Delta[]>([]),[diffStatus,setDiffStatus]=useState(''),[jobs,setJobs]=useState<Job[]>([]);
  const [busy,setBusy]=useState(''),[notice,setNotice]=useState(''),[error,setError]=useState('');
  const [addressLocal,setAddress]=useState(false),[edgeDown,setEdgeDown]=useState(false);
  const [token,,connectLocal]=useToken();
  const edge=useMemo(()=>token?edgeAdapter(token):null,[token]);
  const rigVersion=useRef(0);
  const [projection,setProjection]=useState<Projection>(DEFAULT_PROJECTION),[presenting,setPresenting]=useState(false);
  const project=useRef<ProjectAPI|null>(null);
  const latest=history.commits.find(c=>c.id===history.branches.main)??history.commits[0];
  const before=history.commits.find(c=>c.id===beforeId),after=history.commits.find(c=>c.id===afterId)??latest;
  const compatible=!!(before&&after&&sameSceneReference(before.scene,after.scene));
  useEffect(()=>{queueMicrotask(()=>{setProjection(readProjection());setAddress(localHost());});},[]);
  const profile=(next:Projection)=>{setProjection(next);try{localStorage.setItem('spacegit.world.projection.v1',JSON.stringify(next));}catch{}};
  const refreshHistory=useCallback(async()=>{
    if(!edge)return;
    await edge.rig();
    const [saved,sessions]=await Promise.all([edge.history(),edge.sessions()]);
    setHistory(realHistory(saved));setCaptures(sessions.filter(item=>item.mode==='live'));
  },[edge]);
  const refreshJobs=useCallback(async()=>{if(edge)setJobs((await edge.jobs()).jobs);},[edge]);
  useEffect(()=>{
    if(!edge)return;
    let stopped=false,timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{
      const version=rigVersion.current;
      try{const status=await edge.rig();if(!stopped&&version===rigVersion.current){setRig(status);setEdgeDown(false);}}
      catch{if(!stopped&&version===rigVersion.current){setRig(EMPTY_RIG);setEdgeDown(true);}}
      finally{if(!stopped)timer=setTimeout(poll,1000);}
    };
    queueMicrotask(()=>{
      if(stopped)return;
      setHistory(EMPTY_HISTORY);setCaptures([]);setJobs([]);
      void poll();void refreshHistory().then(refreshJobs).catch(err=>{if(!stopped)setError(err.message);});
    });
    return ()=>{stopped=true;clearTimeout(timer);};
  },[edge,refreshHistory,refreshJobs]);
  useEffect(()=>{
    let disposed=false;
    queueMicrotask(async()=>{
      if(disposed)return;setRows([]);setDiffStatus('');
      if(!before||!after||!compatible||!edge)return;
      setDiffStatus('Loading the edge comparison…');
      try{const remote=await edge.compare(before.id,after.id);if(!disposed){setRows(compareScenes(before.scene,after.scene,remote));setDiffStatus('');}}
      catch(err){if(!disposed)setDiffStatus(err instanceof Error?err.message:'Edge comparison unavailable.');}
    });
    return ()=>{disposed=true;};
  },[before,after,compatible,edge]);
  const run=async(label:string,task:()=>void|Promise<void>)=>{
    setBusy(label);setError('');setNotice('');try{await task();}catch(err){setError(err instanceof Error?err.message:'Operation failed.');}finally{setBusy('');}
  };
  const navigate=(next:View)=>{setView(next);setNotice('');setError('');setPresenting(false);};
  const connectCameras=()=>void run('connect',async()=>{const session=await connectLocal();setRig(await edgeAdapter(session).rig());});
  async function saveRig(settings:RigSettings){if(edge)await run('rig',async()=>{setRig(await edge.saveRig(settings));rigVersion.current++;setActive(null);setNotice('Camera sequence saved.');});}
  const captureSession=()=>void run('capture',async()=>{
    if(!edge)throw Error('Connect the local edge before capturing.');
    await edge.rig();const result=await edge.capture();
    if(result.mode!=='live')throw Error('The edge did not return a live capture. Start it in live mode.');
    setCaptures(old=>[result,...old]);setActive(result);
    if(result.pointdit?.status==='succeeded')setView('reconstruct');
    setNotice(result.pointdit?.status==='succeeded'?'Session saved and four PLY files generated.':'Session saved with '+result.feeds.length+' camera frames.');
  });
  const commit=(branch:string,message:string)=>void run('commit',async()=>{
    if(!edge)throw Error('Connect the local edge first.');const last=history.branches[branch];
    if(!last)throw Error('Select a branch with a current revision.');
    await edge.rig();const result=await edge.commit(branch,last,message);setAfter(result.id);setBefore(last);await refreshHistory();setNotice('Snapshot saved to '+branch+'.');
  });
  const addBranch=(name:string)=>void run('branch',async()=>{
    if(!edge||!after||!/^\w[\w-]{0,63}$/.test(name))throw Error('Choose a revision and a valid branch name.');
    if(Object.hasOwn(history.branches,name))throw Error('A branch with that name already exists.');
    setHistory(realHistory(await edge.branch(name,after.id)));
  });
  return <div className={'nw'+(presenting?' nw-presented':'')}>
    <header className="nw-top"><div className="nw-top-inner">
      <Link href="/world" className="nw-brand" aria-label="SpaceGit workspace"><span className="nw-mark"><Icon name="cube" size={20}/></span><strong>Space<span>Git</span></strong></Link>
      <div className="nw-top-actions"><span className="nw-chip nw-mode"><i/>{edgeDown?'EDGE UNAVAILABLE':edge?'LOCAL EDGE':'EDGE DISCONNECTED'}</span><Link href="/studio" className="nw-legacy">Hardware studio <Icon name="external" size={13}/></Link></div>
    </div></header>
    <div className="nw-nav-wrap"><nav className="nw-shell nw-nav" aria-label="Workspace workflow">
      {VIEWS.map((item,index)=><button key={item.id} onClick={()=>navigate(item.id)} aria-current={view===item.id?'page':undefined}><span className="nw-step-no">0{index+1}</span><Icon name={item.icon} size={16}/>{item.label}</button>)}
      <Link href="/image-history" className="nw-history-link"><Icon name="history" size={16}/>Image history</Link>
    </nav></div>
    <main className="nw-shell nw-main">
      {error&&<p className="nw-notice" role="alert">{error}</p>}{notice&&<p className="nw-notice" role="status">{notice}</p>}
      {edgeDown&&<p className="nw-notice" role="status">The live edge is unavailable. Start it in live mode and reconnect.</p>}
      {view==='capture'&&<CapturePanel rig={rig} edge={edgeDown?null:edge} active={active} captures={captures} busy={busy} capture={captureSession} choose={setActive}
        local={addressLocal} connect={connectCameras} saveRig={saveRig} toggle={()=>void run('rig',async()=>{if(!edge)return;setRig(await (rig.enabled?edge.stop():edge.start()));rigVersion.current++;setActive(null);})}/>}
      {view==='versions'&&<HistoryPanel history={history} capture={active} latest={latest} before={before} after={after} rows={compatible?rows:[]} diffStatus={diffStatus}
        selectBefore={setBefore} selectAfter={setAfter} commit={commit} addBranch={addBranch} checkout={()=>{setProjectScene(after);navigate('reconstruct');}}
        refresh={()=>void run('pull',refreshHistory)} reconstruct={()=>{setProjectScene(after);navigate('reconstruct');}} busy={busy}/>}
      {view==='reconstruct'&&<ReconstructPanel before={before} after={after} rows={compatible?rows:[]} edge={edgeDown?null:edge} jobs={jobs}
        refreshJobs={()=>void run('jobs',refreshJobs)} openProject={(saved,remote,local)=>{setProjectScene(saved);setProjectModel({remote,local});navigate('project');}}/>}
      {view==='project'&&<ProjectPanel commit={projectScene??after} edge={edge} connect={connectLocal} model={projectModel} settings={projection} changeSettings={profile}
        projectRef={project} presenting={presenting} setPresenting={setPresenting}/>}
    </main>
    <footer className="nw-shell nw-footer"><span><Icon name="cube" size={14}/> SPACEGIT</span><span>CAPTURE → VERSION CONTROL → RECONSTRUCT → PROJECT</span><Link href="/project" target="_blank" rel="noopener">Open Project <Icon name="external" size={13}/></Link></footer>
  </div>;
}
