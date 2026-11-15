'use client';
import Link from 'next/link';
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import type {Commit,Job} from '../../../../packages/protocol/types';
import {Icon} from '../components/icons';
import {localHost,useToken} from '../components/connection';
import {CapturePanel} from './capture-panel';
import {compareScenes,commitDemo,DEFAULT_PROJECTION,DEMO_RIG,DEMO_STEPS,demoCapture,EMPTY_HISTORY,readProjection,sameSceneReference,
  type Asset,type Capture,type Delta,type History,type Projection,type Rig,type RigSettings} from './domain';
import {edgeAdapter} from './edge';
import {HistoryPanel} from './history-panel';
import {ProjectPanel,type ProjectAPI} from './project-panel';
import {ReconstructPanel} from './reconstruct-panel';
import './world.css';

const VIEWS=[
  {id:'capture',label:'Capture',icon:'camera'},
  {id:'versions',label:'Version control',icon:'branch'},
  {id:'reconstruct',label:'Reconstruct',icon:'cube'},
  {id:'project',label:'Project',icon:'screen'},
] as const;
type View=typeof VIEWS[number]['id'];
type Workspace={captures:Capture[];history:History};
const EMPTY:Workspace={captures:[],history:EMPTY_HISTORY};
const KEY='spacegit.newworlds.workspace.v1';
const BEATS:View[]=['capture','capture','versions','capture','versions','reconstruct','project','project','project'];
const HOLD=[3300,2900,3100,3400,5400,5300,4900,3900,0];

function readWorkspace():Workspace {
  try {const data=JSON.parse(localStorage.getItem(KEY)??'null');if(data&&Array.isArray(data.captures)&&Array.isArray(data.history?.commits)&&data.history.branches)return data;}
  catch {}
  return EMPTY;
}

export default function World({projector=false}:{projector?:boolean}) {
  const [view,setView]=useState<View>(projector?'project':'capture'),[mode,setMode]=useState<'auto'|'demo'|'live'>('auto');
  const [demo,setDemo]=useState<Workspace>(EMPTY),[loaded,setLoaded]=useState(false);
  const [rig,setRig]=useState<Rig>(DEMO_RIG),[liveHistory,setLiveHistory]=useState<History>(EMPTY_HISTORY),[liveCaptures,setLiveCaptures]=useState<Capture[]>([]);
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
  const [walkthrough,setWalkthrough]=useState<{step:number;auto:boolean;base:Capture;changed:Capture}|null>(null);
  const live=!!edge&&rig.mode==='live'&&(mode==='live'||mode==='auto'&&rig.enabled);
  const history=live?liveHistory:demo.history, sessions=live?liveCaptures:demo.captures;
  const latest=history.commits.find(c=>c.id===history.branches.main)??history.commits[0];
  const before=history.commits.find(c=>c.id===beforeId),after=history.commits.find(c=>c.id===afterId)??latest;
  const compatible=!!(before&&after&&sameSceneReference(before.scene,after.scene));

  useEffect(()=>{queueMicrotask(()=>{
    const data=readWorkspace();
    setDemo(data);setProjection(readProjection());setAddress(localHost());setLoaded(true);
    setBefore(data.history.commits[1]?.id??'');
    setAfter(data.history.branches.main??data.history.commits[0]?.id??'');
    setProjectScene(data.history.commits.find(c=>c.id===data.history.branches.main)??data.history.commits[0]);
  });},[]);
  useEffect(()=>{
    if(!loaded)return;
    try{localStorage.setItem(KEY,JSON.stringify(demo));}catch{}
  },[demo,loaded]);
  const profile=(next:Projection)=>{
    setProjection(next);
    try{localStorage.setItem('spacegit.world.projection.v1',JSON.stringify(next));}catch{}
  };

  const refreshHistory=useCallback(async()=>{
    if(!edge)return;
    const [history,captures]=await Promise.all([edge.history(),edge.sessions()]);
    setLiveHistory(history);setLiveCaptures(captures);
  },[edge]);
  const refreshJobs=useCallback(async()=>{
    if(!edge)return;
    setJobs((await edge.jobs()).jobs);
  },[edge]);
  useEffect(()=>{
    if(!edge)return;
    let stopped=false,timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{
      const version=rigVersion.current;
      try{
        const status=await edge.rig();
        if(!stopped&&version===rigVersion.current){setRig(status);setEdgeDown(false);}
      }catch{
        if(!stopped&&version===rigVersion.current){
          setRig(old=>({...old,feeds:old.feeds.map(feed=>({...feed,status:feed.status==='unmapped'?'unmapped':'offline',age_ms:null}))}));
          setEdgeDown(true);
        }
      }finally{if(!stopped)timer=setTimeout(poll,1000);}
    };
    queueMicrotask(()=>{
      if(stopped)return;
      void poll();
      void refreshHistory().then(()=>refreshJobs()).catch(()=>{});
    });
    return ()=>{stopped=true;clearTimeout(timer);};
  },[edge,refreshHistory,refreshJobs]);
  useEffect(()=>{
    let disposed=false;
    queueMicrotask(async()=>{
      if(disposed)return;
      setRows([]);
      setDiffStatus('');
      if(!before||!after||!compatible)return;
      if(!live){setRows(compareScenes(before.scene,after.scene));return;}
      setDiffStatus('Loading the edge comparison…');
      try{
        const remote=await edge.compare(before.id,after.id);
        if(!disposed){setRows(compareScenes(before.scene,after.scene,remote));setDiffStatus('');}
      }catch(err){if(!disposed)setDiffStatus(err instanceof Error?err.message:'Edge comparison unavailable.');}
    });
    return ()=>{disposed=true;};
  },[before,after,compatible,live,edge]);
  const run=async(label:string,task:()=>void|Promise<void>)=>{
    setBusy(label);setError('');setNotice('');
    try{await task();}
    catch(err){setError(err instanceof Error?err.message:'That operation failed. Please try again.');}
    finally{setBusy('');}
  };
  const navigate=(next:View)=>{if(next==='project'){setProjectScene(after);setProjectModel(undefined);}setView(next);setWalkthrough(null);setNotice('');setError('');setPresenting(false);};
  const switchSource=(useLive:boolean)=>{
    setMode(useLive?'live':'demo');setActive(null);setBefore('');setAfter('');setError('');setNotice('');setWalkthrough(null);
  };
  const connectCameras=()=>void run('connect',async()=>{
    const session=await connectLocal();
    const status=await edgeAdapter(session).rig();
    setRig(status);
    if(status.mode==='live')switchSource(true);
    else setNotice('The local edge is in simulation mode. Start it in live mode to open camera feeds.');
  });
  async function saveRig(settings:RigSettings) {
    if(!edge)return;
    await run('rig',async()=>{
      const status=await edge.saveRig(settings);
      rigVersion.current++;
      setRig(status);
      switchSource(true);
      setNotice('Camera sequence saved.');
    });
  }
  const captureSession=()=>{
    setWalkthrough(null);
    void run('capture',async()=>{
      const result=live?await edge.capture():demoCapture((demo.captures[0]?.sample??1)+1);
      if(live)setLiveCaptures(old=>[result,...old]);else setDemo(old=>({...old,captures:[result,...old.captures].slice(0,36)}));
      setActive(live?null:result);
      if(result.pointdit?.status==='succeeded')setView('reconstruct');
      setNotice(result.pointdit?.status==='succeeded'?'Session saved and four PLY files generated in your WSL PointDiT output folder.':'Session saved with '+result.feeds.length+' '+(result.mode==='demo'?'simulated':'live')+' frames. Open Version control to save a scene revision.');
    });
  };
  const commit=(branch:string,message:string)=>{
    setWalkthrough(null);
    void run('commit',async()=>{
      const last=history.branches[branch];
      if(live){
        if(!last)throw Error('Select a branch with a current revision.');
        const result=await edge.commit(branch,last,message);setAfter(result.id);setBefore(last);
        await refreshHistory();
      }else{
        if(!active||active.saved)throw Error('Capture an unsaved simulated session first.');
        setDemo(old=>({history:commitDemo(old.history,active,branch,message),captures:old.captures.map(c=>c.id===active.id?{...c,saved:c.id}:c)}));
        setActive({...active,saved:active.id});setAfter(active.id);setBefore(last??'');
      }
      setNotice('Snapshot saved to '+branch+'.');
    });
  };
  const addBranch=(name:string)=>{
    setWalkthrough(null);
    void run('branch',async()=>{
      if(!after||!/^[\w-]{1,64}$/.test(name))throw Error('Choose a revision and a valid branch name.');
      if(Object.hasOwn(history.branches,name))throw Error('A branch with that name already exists.');
      if(live)setLiveHistory(await edge.branch(name,after.id));
      else setDemo(old=>({...old,history:{...old.history,branches:{...old.history.branches,[name]:after.id}}}));
    });
  };

  const showStep=useCallback((step:number,base:Capture,changed:Capture)=>{
    setView(BEATS[step]);setError('');setNotice('');
    if(step===0)setActive(null);
        if(step===1){
      setActive(base);
      setDemo(old=>({...old,captures:[base,...old.captures.filter(c=>c.id!==base.id)].slice(0,36)}));
    }
    if(step===3)setActive({...changed,saved:changed.id});
    if(step===2||step===3){
      const capture=step===2?base:changed;
      setDemo(old=>{
        const branch='guided-demo', label=step===2?'Baseline desk layout':'Move the ceramic mug';
        const history=commitDemo(old.history,capture,branch,label);
        return {history,captures:[{...capture,saved:capture.id},...old.captures.filter(c=>c.id!==capture.id)].slice(0,36)};
      });
      setAfter(capture.id);setBefore(step===3?base.id:'');
    }
    if(step===5)setAfter(changed.id);
    if(step===6){project.current?.office();setPresenting(false);}
    if(step===7)project.current?.present();
    if(step===8)project.current?.play();
  },[]);
  const startDemo=useCallback(()=>{
    const base=demoCapture(0),changed=demoCapture(1);
    setMode('demo');setBefore('');setAfter('');setPresenting(false);
    setWalkthrough({step:0,auto:true,base,changed});showStep(0,base,changed);
  },[showStep]);
  useEffect(()=>{
    if(!walkthrough?.auto || walkthrough.step===8)return;
    const {step,base,changed}=walkthrough;
    const timer=setTimeout(()=>{
      const next=step+1;showStep(next,base,changed);setWalkthrough({...walkthrough,step:next});
    },HOLD[step]);
    return ()=>clearTimeout(timer);
  },[walkthrough,showStep]);
  useEffect(()=>{
    if (new URLSearchParams(window.location.search).get('demo') !== '1') return;
    const url = new URL(window.location.href);
    url.searchParams.delete('demo');
    window.history.replaceState(window.history.state,'',url);
    queueMicrotask(startDemo);
  },[startDemo]);
  useEffect(()=>{
    const key=(event:KeyboardEvent)=>{
      if(event.key.toLowerCase()!=='d'||event.altKey||event.ctrlKey||event.metaKey||event.repeat||(event.target instanceof HTMLElement&&event.target.closest('input,textarea,select,[contenteditable]')))return;
      startDemo();
    };
    document.addEventListener('keydown',key);
    return ()=>document.removeEventListener('keydown',key);
  },[startDemo]);

  return <div className={'nw'+(presenting?' nw-presented':'')}>
    <header className="nw-top">
      <div className="nw-top-inner">
        <Link href="/world" className="nw-brand" aria-label="SpaceGit New Worlds">
          <span className="nw-mark"><Icon name="cube" size={20}/></span><strong>Space<span>Git</span></strong><span className="nw-brand-divider"/><span className="nw-edition">NEW WORLDS</span>
        </Link>
        <div className="nw-top-actions">
          <span className="nw-chip nw-mode"><i/>{live&&!edgeDown?'LOCAL EDGE':live?'EDGE UNAVAILABLE':'SIMULATION MODE'}</span>
          <Link href="/studio" className="nw-legacy">Hardware studio <Icon name="external" size={13}/></Link>
          <button className="nw-btn nw-primary nw-demo-start" onClick={startDemo}><span aria-hidden="true">▶</span> Start Demo <kbd>D</kbd></button>
        </div>
      </div>
    </header>
    <div className="nw-nav-wrap"><nav className="nw-shell nw-nav" aria-label="New Worlds workflow">
      {VIEWS.map((v,i)=><button key={v.id} onClick={()=>navigate(v.id)} aria-current={view===v.id?'page':undefined}><span className="nw-step-no">0{i+1}</span><Icon name={v.icon} size={16}/>{v.label}</button>)}
      <Link href="/image-history" className="nw-history-link"><Icon name="history" size={16}/>Image history</Link>
    </nav></div>
    <main className="nw-shell nw-main">
      {walkthrough&&<section className="nw-guide" aria-label="Guided demo">
        <div><div className="nw-eyebrow"><span/> GUIDED DEMO · {walkthrough.step+1} / 9</div><strong aria-live="polite">{DEMO_STEPS[walkthrough.step]}</strong></div>
        <div className="nw-segments" aria-hidden="true">{DEMO_STEPS.map((s,i)=><span key={s} className={i<=walkthrough.step?'done':''}/>)}</div>
        <div className="nw-actions">
          {walkthrough.step<8&&<>
            <button className="nw-btn nw-tiny" onClick={()=>setWalkthrough({...walkthrough,auto:!walkthrough.auto})}>{walkthrough.auto?'Pause demo':'Resume demo'}</button>
            <button className="nw-btn nw-tiny" onClick={()=>{const step=walkthrough.step+1;showStep(step,walkthrough.base,walkthrough.changed);setWalkthrough({...walkthrough,step});}}>Next stage <Icon name="arrow" size={13}/></button>
          </>}
          <button className="nw-btn nw-tiny" onClick={()=>setWalkthrough(null)}>{walkthrough.step===8?'Dismiss':'End demo'}</button>
        </div>
      </section>}
      {view!=='capture'&&edge&&!walkthrough&&<div className="nw-source"><label>Workspace <select className="nw-field" value={live?'live':'demo'} onChange={e=>switchSource(e.target.value==='live')}><option value="demo">Simulation</option><option value="live">Local edge</option></select></label></div>}
      {error&&<p className="nw-notice" role="alert">{error}</p>}
      {notice&&<p className="nw-notice" role="status">{notice}</p>}
      {live&&edgeDown&&<p className="nw-notice" role="status">The local edge is unavailable. Reconnect it or switch to Simulation to continue.</p>}
      {view==='capture'&&<CapturePanel rig={edge?rig:DEMO_RIG} edge={edge} active={active?.mode===(live?'live':'demo')?active:null} captures={sessions} busy={busy}
        capture={captureSession} choose={setActive} liveSource={live} setLiveSource={switchSource}
        local={addressLocal} connect={connectCameras} saveRig={saveRig}
        toggle={()=>void run('rig',async()=>{
          const result=await (rig.enabled?edge!.stop():edge!.start());
          rigVersion.current++;
          setRig(result);
          switchSource(true);
        })}/>}
      {view==='versions'&&<HistoryPanel history={history} capture={active} source={live?'live':'demo'} latest={latest} before={before} after={after} rows={compatible?rows:[]} diffStatus={diffStatus}
        selectBefore={setBefore} selectAfter={setAfter} commit={commit} addBranch={addBranch}
        checkout={()=>{setProjectScene(after);navigate('reconstruct');setNotice('Checked out '+after!.id.slice(0,8)+' in the scene viewer.');}}
        refresh={()=>void run('pull',refreshHistory)} reconstruct={()=>{setProjectScene(after);navigate('reconstruct');}} busy={busy}/>}
      {view==='reconstruct'&&<ReconstructPanel before={before} after={after} rows={compatible?rows:[]} edge={live?edge:null} jobs={jobs}
        refreshJobs={()=>void run('jobs',refreshJobs)} openProject={(commit,remote,local)=>{navigate('project');setProjectScene(commit);setProjectModel({remote,local});}}/>}
      {(view==='project'||walkthrough&&walkthrough.step>=5)&&<div hidden={view!=='project'}><ProjectPanel commit={walkthrough?after:projectScene??after} edge={edge} connect={connectLocal} model={walkthrough?undefined:projectModel} autoLoadReconstruction={!walkthrough} settings={projection}
        changeSettings={profile} projectRef={project} presenting={presenting} setPresenting={setPresenting} active={view==='project'}/></div>}
    </main>
    <footer className="nw-shell nw-footer"><span><Icon name="cube" size={14}/> SPACEGIT / DURHACK 2026</span><span>CAPTURE → VERSION CONTROL → RECONSTRUCT → PROJECT</span><Link href="/project" target="_blank" rel="noopener">Open projector window <Icon name="external" size={13}/></Link></footer>
  </div>;
}
