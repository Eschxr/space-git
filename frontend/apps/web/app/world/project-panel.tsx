'use client';
import Link from 'next/link';
import {useCallback,useEffect,useMemo,useRef,useState,type RefObject} from 'react';
import type {Commit,Job} from '../../../../packages/protocol/types';
import {Icon} from '../components/icons';
import {requestDisplayFullscreen,screenKey,useProjectorDisplays} from '../components/projector-displays';
import {type ProjectedObject,type Projection,type RigModel} from './domain';
import type {Edge} from './edge';
import {RenderScene,useSceneAsset} from './render-scene';
import {ProjectorOutput,useProjectorWindow} from './projector-window';
import {CameraRigViewer} from './camera-rig-viewer';
import {ProjectorChat,type ProjectorCommand} from './projector-chat';
import type {Representation,SurfaceJob} from './surface-types';

export type ProjectAPI={present:()=>void};
const EMPTY_OBJECTS:ProjectedObject[]=[];
const ORIGINAL_VIEW_KEY='spacegit.projector.original-views.v1';
const ACTIVE_OBJECT_KEY='spacegit.projector.active-objects.v1';
type Offset=[number,number,number];
type PositionDraft={scene:string;id:string;offset:Offset;limits:Offset};
const POSITION_LABELS=['X position','Y position','Z position'] as const;

function PositionSlider({label,value,limit,disabled,change}:{label:string;value:number;limit:number;disabled:boolean;change:(value:number)=>void}){
  const slider=useRef<HTMLInputElement>(null);
  useEffect(()=>{
    const element=slider.current;
    if(!element||disabled)return;
    const move=(event:WheelEvent)=>{
      if(document.activeElement!==element||!event.deltaY||event.ctrlKey)return;
      event.preventDefault();
      const next=Math.round((element.valueAsNumber-Math.sign(event.deltaY)*.05)*100)/100;
      change(Math.max(-limit,Math.min(limit,next)));
    };
    element.addEventListener('wheel',move,{passive:false});
    return ()=>element.removeEventListener('wheel',move);
  },[change,disabled,limit]);
  return <label>{label}
    <input ref={slider} type="range" min={-limit} max={limit} step="any" disabled={disabled} value={value}
      onChange={event=>change(Math.round(event.currentTarget.valueAsNumber*100)/100)}/>
    <output>{Number(value.toFixed(2))}</output>
  </label>;
}

export function ProjectPanel({commit,edge,chatEdge,localChat,connectChat,forceRig,jobs,rigAvailable,settings,changeSettings,projectRef,presenting,setPresenting,active=true}:{commit?:Commit;edge:Edge|null;chatEdge:Edge|null;localChat:boolean;connectChat:()=>Promise<string>;forceRig:boolean;jobs?:Job[];rigAvailable:boolean;settings:Projection;changeSettings:(settings:Projection)=>void;
  projectRef:RefObject<ProjectAPI|null>;presenting:boolean;setPresenting:(on:boolean)=>void;active?:boolean}) {
  const surface=useRef<HTMLDivElement>(null);
  const [modelChoice,setModelChoice]=useState('');
  const [models,setModels]=useState<{id:string;file:File}[]>([]);
  const [versions,setVersions]=useState<RigModel[]|null>(null);
  const [versionError,setVersionError]=useState('');
  const [savingVersion,setSavingVersion]=useState(false);
  const [rigRefresh,setRigRefresh]=useState(0);
  const hasRig=rigAvailable||!!(edge&&versions?.length);
  const addedModel=models.find(item=>item.id===modelChoice)?.file;
  const versionId=modelChoice.startsWith('rig:')?modelChoice.slice(4):undefined;
  const showingRig=!!versionId||modelChoice==='rig'||(!modelChoice&&(forceRig||hasRig));
  const activeVersion=versionId??(!modelChoice&&edge?versions?.[0]?.id:undefined);
  const [surfaces,setSurfaces]=useState<Record<string,SurfaceJob|null>>({});
  const [surfaceModes,setSurfaceModes]=useState<Record<string,Representation>>({});
  const enhanced=activeVersion?surfaces[activeVersion]:null;
  const representation=enhanced&&activeVersion?surfaceModes[activeVersion]??'mesh':'original';
  const artifacts=useMemo(()=>(jobs??[]).filter(job=>job.asset).flatMap(job=>
    (job.artifacts??[{name:'sparse.ply'}]).filter(artifact=>/\.(ply|glb|gltf)$/i.test(artifact.name)).map(artifact=>({
      id:job.asset!,name:artifact.name,label:artifact.name+' · '+job.id.slice(0,6),key:'artifact:'+job.asset+':'+artifact.name,
    }))),[jobs]);
  const remote=artifacts.find(item=>item.key===modelChoice)??null;
  const local=addedModel??null;
  const [fingerprint,setFingerprint]=useState<{file:File;id:string}|null>(null);
  const [objectsByScene,setObjectsByScene]=useState<Record<string,ProjectedObject[]>>({});
  const [objectsError,setObjectsError]=useState('');
  const [regenerating,setRegenerating]=useState('');
  const [position,setPosition]=useState<PositionDraft|null>(null);
  const [savingPosition,setSavingPosition]=useState(false);
  const [originalViews,setOriginalViews]=useState<string[]|null>(null);
  const [activeObjectIds,setActiveObjectIds]=useState<Record<string,string>|null>(null);
  const restoreCount=useRef(new Map<string,number>());
  const sceneId=showingRig ? activeVersion&&'rig-'+activeVersion
    : local ? (fingerprint?.file===local?fingerprint.id:undefined)
    : remote ? 'asset-'+(remote.id+'-'+remote.name).replace(/[^a-zA-Z0-9_-]/g,'_').slice(0,58)
    : commit ? 'revision-'+commit.id : 'projector-workspace';
  const projectedObjects=(sceneId&&objectsByScene[sceneId])||EMPTY_OBJECTS;
  const activeId=sceneId?activeObjectIds?.[sceneId]:undefined;
  const activeObject=projectedObjects.find(item=>item.id===activeId)??projectedObjects.at(-1);
  const draft=position?.scene===sceneId?position:null;
  const originalView=!!sceneId&&!!originalViews?.includes(sceneId);
  const visibleObjects=useMemo(()=>{
    if(originalView||!activeObject)return EMPTY_OBJECTS;
    return [draft?.id===activeObject.id?{...activeObject,offset:draft.offset}:activeObject];
  },[activeObject,draft,originalView]);
  const moveDraft=useCallback((id:string,offset:Offset)=>{
    setPosition(current=>{
      if(!current||current.scene!==sceneId||current.id!==id)return current;
      const limits=offset.map((value,axis)=>Math.max(current.limits[axis],Math.ceil(Math.abs(value)))) as Offset;
      return {...current,offset,limits};
    });
  },[sceneId]);
  const modelName=showingRig?'Camera rig reconstruction':local?.name??remote?.name??commit?.message??'Project workspace';
  const [message,setMessage]=useState('');
  const asset=useSceneAsset(edge,remote,local);
  const [pageVisible,setPageVisible]=useState(true);
  const [full,setFull]=useState(false);
  const [blackedOut,setBlackedOut]=useState(false);
  const [displayAction,setDisplayAction]=useState('');
  const displays=useProjectorDisplays();
  const projector=useProjectorWindow();
  useEffect(()=>{
    queueMicrotask(()=>{
      try {
        const saved:unknown=JSON.parse(localStorage.getItem(ORIGINAL_VIEW_KEY)??'[]');
        setOriginalViews(Array.isArray(saved)?saved.filter((value):value is string=>typeof value==='string'):[]);
      } catch {setOriginalViews([]);}
      try {
        const saved:unknown=JSON.parse(localStorage.getItem(ACTIVE_OBJECT_KEY)??'{}');
        const entries=saved&&typeof saved==='object'&&!Array.isArray(saved)?Object.entries(saved):[];
        setActiveObjectIds(Object.fromEntries(entries.filter((entry):entry is [string,string]=>typeof entry[1]==='string')));
      } catch {setActiveObjectIds({});}
    });
  },[]);
  useEffect(()=>{
    if(!originalViews)return;
    try{localStorage.setItem(ORIGINAL_VIEW_KEY,JSON.stringify(originalViews));}catch{}
  },[originalViews]);
  useEffect(()=>{
    if(!activeObjectIds)return;
    try{localStorage.setItem(ACTIVE_OBJECT_KEY,JSON.stringify(activeObjectIds));}catch{}
  },[activeObjectIds]);
  function setOriginalView(id:string,enabled:boolean){
    setOriginalViews(previous=>{
      const current=previous??[];
      return enabled?[...new Set([...current,id])]:current.filter(scene=>scene!==id);
    });
  }
  function toggleOriginalView(){
    if(!sceneId)return;
    if(!originalView)restoreCount.current.set(sceneId,(restoreCount.current.get(sceneId)??0)+1);
    setPosition(null);
    setOriginalView(sceneId,!originalView);
  }
  function showGeneratedObject(scene:string,id:string){
    setActiveObjectIds(previous=>({...previous,[scene]:id}));
    setPosition(current=>current?.scene===scene&&current.id!==id?null:current);
    setOriginalView(scene,false);
  }
  function rememberObjects(id:string,items:ProjectedObject[]){
    setObjectsByScene(previous=>{
      const merged=new Map(previous[id]?.map(item=>[item.id,item]));
      for(const item of items)merged.set(item.id,item);
      return {...previous,[id]:[...merged.values()]};
    });
  }
  useEffect(()=>{
    if(!local||local.size>64*1024*1024)return;
    let cancelled=false;
    local.arrayBuffer().then(buffer=>crypto.subtle.digest('SHA-256',buffer)).then(digest=>{
      if(!cancelled)setFingerprint({file:local,id:'file-'+Array.from(new Uint8Array(digest).slice(0,24),byte=>byte.toString(16).padStart(2,'0')).join('')});
    }).catch(()=>{if(!cancelled)setObjectsError('Could not identify this file for saving generated objects.');});
    return ()=>{cancelled=true;};
  },[local]);
  useEffect(()=>{
    if(!chatEdge||!sceneId||!active)return;
    let cancelled=false;
    chatEdge.projectorObjects(sceneId).then(items=>{
      if(!cancelled){rememberObjects(sceneId,items);setObjectsError('');}
    }).catch(error=>{
      if(!cancelled)setObjectsError(error.message==='Not Found'?'Restart the SpaceGit edge to load generated objects.':error.message);
    });
    return ()=>{cancelled=true;};
  },[chatEdge,sceneId,active]);

  async function generateObject(prompt:string,requestId:string){
    if(!chatEdge)throw Error('Connect this workstation to generate 3D objects.');
    if(!sceneId)throw Error(showingRig?'Save the current PointDiT output as a version first.':'Wait for the model file to finish loading.');
    if((local||remote)&&!asset.data)throw Error('Open a valid model file before adding objects.');
    const restoreAtStart=restoreCount.current.get(sceneId);
    const result=await chatEdge.generateProjectorObject(sceneId,prompt,requestId);
    rememberObjects(sceneId,[result]);
    if(restoreAtStart===restoreCount.current.get(sceneId))showGeneratedObject(sceneId,result.id);
    return result.name;
  }

  async function regenerateObject(id:string){
    if(!chatEdge||!sceneId||regenerating)return;
    const restoreAtStart=restoreCount.current.get(sceneId);
    setRegenerating(id);setObjectsError('');
    try {
      const updated=await chatEdge.regenerateProjectorObject(sceneId,id);
      rememberObjects(sceneId,[updated]);
      if(restoreAtStart===restoreCount.current.get(sceneId))showGeneratedObject(sceneId,id);
    } catch(error){setObjectsError((error as Error).message);}
    finally {setRegenerating('');}
  }

  async function savePosition(){
    if(!chatEdge||!draft||savingPosition)return;
    setSavingPosition(true);setObjectsError('');
    try {
      const updated=await chatEdge.positionProjectorObject(draft.scene,draft.id,draft.offset);
      rememberObjects(draft.scene,[updated]);
      setPosition(current=>current===draft?null:current);
    } catch(error){setObjectsError((error as Error).message);}
    finally {setSavingPosition(false);}
  }
  useEffect(()=>{
    if(!edge||!active)return;
    let cancelled=false;
    edge.rigModels().then(items=>{
      if(!cancelled){setVersions(items);setVersionError('');}
    }).catch(error=>{
      if(!cancelled){setVersions([]);setVersionError(error.message==='Not Found'?'Restart the SpaceGit edge to load saved 3D models.':error.message);}
    });
    return ()=>{cancelled=true;};
  },[edge,active,rigRefresh]);
  useEffect(()=>{
    if(!edge||!activeVersion||!active)return;
    let cancelled=false;
    edge.latestSurface(activeVersion).then(item=>{
      if(!cancelled)setSurfaces(current=>({...current,[activeVersion]:item}));
    }).catch(()=>{});
    return ()=>{cancelled=true;};
  },[edge,active,activeVersion,rigRefresh]);
  const exit=()=>{
    if(document.fullscreenElement===surface.current) void document.exitFullscreen().catch(()=>{});
    setPresenting(false);
  };
  useEffect(()=>{
    const changed=()=>{
      const on=document.fullscreenElement===surface.current;
      setFull(on);
      if(!on)setPresenting(false);
    };
    const visible=()=>setPageVisible(!document.hidden);
    document.addEventListener('fullscreenchange',changed);
    document.addEventListener('visibilitychange',visible);
    return ()=>{document.removeEventListener('fullscreenchange',changed);document.removeEventListener('visibilitychange',visible);};
  },[setPresenting]);
  useEffect(()=>{
    const present=()=>{
      setPresenting(true);
      surface.current?.focus({preventScroll:true});
      if (!surface.current?.requestFullscreen) {
        setMessage('Fullscreen is unavailable here. Use your browser’s fullscreen shortcut for the projector.');
        return;
      }
      if(document.fullscreenElement!==surface.current)void requestDisplayFullscreen(surface.current).then(()=>{surface.current?.focus({preventScroll:true});}).catch(()=>{
        setMessage('Presentation mode is active. Press F or click Fullscreen to enter browser fullscreen.');
      });
    };
    projectRef.current={present};
    return ()=>{projectRef.current=null;};
  },[projectRef,setPresenting]);
  useEffect(()=>{
    if(!active)return;
    const key=(e:KeyboardEvent)=>{
      if(e.defaultPrevented||e.altKey||e.metaKey||e.ctrlKey||e.repeat||(e.target instanceof HTMLElement&&(e.target.closest('input,select,textarea,button,a,[contenteditable]'))))return;
      if(e.key.toLowerCase()==='f'){e.preventDefault();projectRef.current?.present();}
      if(e.key.toLowerCase()==='h'){if(document.fullscreenElement===surface.current)void document.exitFullscreen().catch(()=>{});setPresenting(!presenting);}
      if(e.key.toLowerCase()==='b')setBlackedOut(value=>!value);
      if(e.key==='Escape'&&document.fullscreenElement!==surface.current)setPresenting(false);
    };
    document.addEventListener('keydown',key);
    return ()=>document.removeEventListener('keydown',key);
  },[active,projectRef,presenting,setPresenting]);
  const openProjector=()=>{
    try {
      projector.open(displays.selectedScreen());
      setDisplayAction('');
    } catch (error) {
      setDisplayAction(error instanceof Error ? error.message : 'Check the selected projector display.');
    }
  };
  function showModel(choice:string){
    setModelChoice(choice);setPosition(null);setBlackedOut(false);
  }
  async function saveCurrentRig(){
    if(!edge||savingVersion)return;
    setSavingVersion(true);setVersionError('');
    try {
      const saved=await edge.saveCurrentRig();
      setVersions(previous=>[saved,...(previous??[]).filter(item=>item.id!==saved.id)].sort((a,b)=>b.created-a.created));
      showModel('rig:'+saved.id);
    } catch(error){setVersionError((error as Error).message);}
    finally {setSavingVersion(false);}
  }
  function command(action:ProjectorCommand){
    if(action==='reconstruction'){showModel('');return 'Showing the current reconstruction.';}
    if(action==='blackout'){setBlackedOut(true);return 'Output blacked out.';}
    setBlackedOut(false);return 'Showing the output again.';
  }
  const outputLabel=modelName;
  const registeredObjects=!showingRig&&!local&&!remote?commit?.scene.objects.map(item=>item.name).slice(0,30):undefined;
  function renderImage(editable:boolean){
    const editId=editable&&!savingPosition?draft?.id:undefined;
    return <div className="nw-project-image" style={{filter:`brightness(${settings.brightness}%) contrast(${settings.contrast}%)`}}>
      {blackedOut&&!editable&&<div className="nw-projector-blackout" aria-label="Output blacked out"/>}
      {showingRig?edge&&versions===null&&!versionId?<div className="nw-render-note" role="status">Loading saved model versions…</div>:
          <CameraRigViewer key={(activeVersion??'current')+':'+rigRefresh} edge={edge} projection version={activeVersion}
            surfaceId={enhanced?.id} representation={representation} objects={visibleObjects} editId={editId} onMove={moveDraft}/>:
        asset.data||(!local&&!remote&&commit)||visibleObjects.length?<RenderScene scene={commit?.scene} simulated={commit?.evidence?.mode==='demo'&&!asset.data} asset={asset.data} cloud={!!asset.data&&'geometry' in asset.data} lowPower={settings.lowPower} visible={active&&(!!projector.output||pageVisible)} projectedObjects={visibleObjects} editId={editId} onMove={moveDraft}/>:
          <div className="nw-render-note" role={asset.error?'alert':'status'}>{asset.message||'Open a reconstruction or add a 3D model to project it here.'}</div>}
    </div>;
  }
  return <>
    <div className="nw-titlebar">
      <div><div className="nw-eyebrow"><span/> 04 / PROJECTION</div><h1>Project</h1><p>Choose a reconstruction and add objects with chat.</p></div>
      <div className="nw-actions">
        <button className="nw-btn" disabled={!!projector.output} onClick={()=>{setPresenting(true);surface.current?.focus({preventScroll:true});}}>Hide controls</button>
        <button className="nw-btn" disabled={!!projector.output} onClick={()=>projectRef.current?.present()}>Fullscreen</button>
        <button className="nw-btn nw-primary" onClick={openProjector}><Icon name="screen"/>{projector.output?'Focus projector window':'Open projector window'}</button>
      </div>
    </div>
    {message&&<p className="nw-notice" role="status">{message}</p>}
    <div className="nw-workspace-grid nw-project-grid">
      <section className="nw-panel nw-view-panel">
        <div className="nw-panel-head"><h2>{modelName}</h2></div>
        <div className={'nw-output'+(presenting?' is-presenting':'')} ref={surface} tabIndex={-1} data-testid="projector-surface">
          {projector.output&&!draft ? <div className="nw-render-note">Output is on the projector window.</div> : renderImage(!!draft)}
          {presenting&&<div className="nw-presentation-exit">
            {!full&&<button className="nw-btn nw-tiny" onClick={()=>projectRef.current?.present()}>Fullscreen</button>}
            <button className="nw-btn nw-tiny" onClick={exit}>Exit presentation</button>
          </div>}
        </div>
        <div className="nw-panel-foot">
          <span>1920 × 1080 REFERENCE <b>·</b> 16:9</span>
          <span><kbd>F</kbd> Fullscreen <kbd>B</kbd> Blackout</span>
        </div>
      </section>
      <div className="nw-side-stack">
        <section className="nw-panel" aria-label="Projector models">
          <div className="nw-panel-head"><h2>3D models</h2><Icon name="cube"/></div>
          <div className="nw-display-controls">
            <label>Model version<select className="nw-field" value={modelChoice} onChange={event=>showModel(event.target.value)}>
              <option value="">Current reconstruction</option>
              {edge&&<option value="rig">Current PointDiT output</option>}
              {edge&&!!versions?.length&&<optgroup label="Saved camera reconstructions">{versions.map(version=><option key={version.id} value={'rig:'+version.id}>
                {version.capture_id?'Capture '+version.capture_id.slice(0,8):'Imported output'} · {new Date(version.created*1000).toLocaleString()}
              </option>)}</optgroup>}
              {!!artifacts.length&&<optgroup label="Worker models">{artifacts.map(artifact=><option key={artifact.key} value={artifact.key}>{artifact.label}</option>)}</optgroup>}
              {models.map(model=><option key={model.id} value={model.id}>{model.file.name}</option>)}
            </select></label>
            {activeVersion&&enhanced&&<label>Scan representation <select className="nw-field" aria-label="Scan representation" value={representation}
              onChange={event=>{const value=event.target.value as Representation;setSurfaceModes(current=>({...current,[activeVersion]:value}));}}>
              <option value="original">Original points</option><option value="cleaned">Cleaned points</option><option value="mesh">Smooth mesh</option>
            </select></label>}
            {edge&&versionId&&<p role="status">Saved version {versionId.slice(0,16)} · four point clouds</p>}
            {versionError&&edge&&<p role="alert">{versionError}</p>}
            <label className="nw-upload">Add 3D models<input type="file" multiple accept=".ply,.glb,.gltf" onChange={event=>{
              const files=Array.from(event.target.files??[]).map(file=>({id:crypto.randomUUID(),file}));
              if(files.length){setModels(previous=>[...previous,...files]);showModel(files[0].id);}
              event.target.value='';
            }}/></label>
            <div className="nw-actions">
              <button className="nw-btn nw-tiny" onClick={()=>showModel('')}>Show current reconstruction</button>
              {edge&&<button className="nw-btn nw-tiny" onClick={()=>setRigRefresh(value=>value+1)}>Refresh versions</button>}
              {edge&&<button className="nw-btn nw-tiny" disabled={savingVersion} onClick={()=>void saveCurrentRig()}>{savingVersion?'Saving point clouds…':'Save current PointDiT output'}</button>}
              {addedModel&&<button className="nw-btn nw-tiny" onClick={()=>{setModels(previous=>previous.filter(model=>model.id!==modelChoice));showModel('');}}>Remove selected model</button>}
            </div>
            <p>PLY, GLB or self-contained glTF. Models are kept for this Project session.</p>
          </div>
        </section>
        <ProjectorChat edge={chatEdge} local={localChat} connect={connectChat} command={command} outputLabel={outputLabel} blackedOut={blackedOut}
          sceneId={sceneId} generateObject={generateObject} objects={[...(registeredObjects??[]),...visibleObjects.map(item=>item.name)].slice(0,30)}/>
        {!!projectedObjects.length&&<section className="nw-panel" aria-label="Generated objects">
          <div className="nw-panel-head"><h2>Generated objects</h2></div>
          <div className="nw-original-toggle">
            <button className="nw-btn nw-tiny" disabled={!sceneId||savingPosition} onClick={toggleOriginalView}>
              {originalView?'Show generated objects':'Restore original model'}</button>
            <p role="status">{originalView?'Original model showing. Your additions are saved.':'Showing '+activeObject?.name+'.'}</p>
          </div>
          {!originalView&&<ul className="nw-generated-list">{projectedObjects.map(item=><li key={item.id}>
            <span>{item.name}</span>
            <div className="nw-actions">
              {activeObject?.id!==item.id&&<button className="nw-btn nw-tiny" disabled={savingPosition||!sceneId}
                aria-label={'Show '+item.name} onClick={()=>{if(sceneId)showGeneratedObject(sceneId,item.id);}}>Show</button>}
              <button className="nw-btn nw-tiny" disabled={!sceneId||savingPosition||!!regenerating} aria-pressed={draft?.id===item.id}
                onClick={()=>{
                  if(!sceneId)return;
                  const offset=item.offset??[0,0,0];
                  showGeneratedObject(sceneId,item.id);
                  setPosition({scene:sceneId,id:item.id,offset,limits:offset.map(value=>Math.max(5,Math.ceil(Math.abs(value)))) as Offset});
                }}>Edit position</button>
              <button className="nw-btn nw-tiny" disabled={!chatEdge||!!regenerating||!!draft}
                aria-label={'Regenerate '+item.name} onClick={()=>void regenerateObject(item.id)}>{regenerating===item.id?'Regenerating…':'Regenerate'}</button>
            </div>
          </li>)}</ul>}
          {!originalView&&draft&&<form className="nw-position-form" aria-label="Object position" onSubmit={event=>{event.preventDefault();void savePosition();}}>
            <p>Drag the object in the 3D preview to move it across the floor. Hold Shift while dragging to raise or lower it.</p>
            <div className="nw-position-fields">{POSITION_LABELS.map((label,index)=><PositionSlider key={label} label={label}
              limit={draft.limits[index]} disabled={savingPosition} value={draft.offset[index]} change={value=>{
                setPosition(current=>{
                  if(!current||current.id!==draft.id||current.scene!==draft.scene)return current;
                  const offset=[...current.offset] as Offset;
                  offset[index]=value;
                  return {...current,offset};
                });
              }}/>)}</div>
            <div className="nw-actions">
              <button className="nw-btn nw-tiny nw-primary" disabled={!chatEdge||savingPosition}>{savingPosition?'Saving…':'Save position'}</button>
              <button className="nw-btn nw-tiny" type="button" disabled={savingPosition} onClick={()=>setPosition(current=>current?{...current,offset:[0,0,0]}:null)}>Reset offsets</button>
              <button className="nw-btn nw-tiny" type="button" disabled={savingPosition} onClick={()=>setPosition(null)}>Cancel</button>
            </div>
          </form>}
        </section>}
        {objectsError&&chatEdge&&<p className="nw-notice" role="alert">{objectsError}</p>}
        <section className="nw-panel">
          <div className="nw-panel-head"><h2>Projector display</h2><Icon name="screen"/></div>
          <div className="nw-display-controls">
            <div className="nw-actions">
              <button className="nw-btn nw-tiny" disabled={!!projector.output} onClick={()=>{setDisplayAction('');void displays.detect();}}>Detect displays</button>
              <button className="nw-btn nw-tiny" aria-pressed={blackedOut} onClick={()=>setBlackedOut(value=>!value)}>{blackedOut?'Show output':'Blackout'}</button>
              {projector.output&&<button className="nw-btn nw-tiny" onClick={projector.close}>Close projector window</button>}
            </div>
            {displays.screens.length>0&&<label>Output display<select className="nw-field" value={displays.selected} disabled={!!projector.output} onChange={e=>displays.select(e.target.value)}>
              <option value="">Place window manually</option>
              {displays.screens.map((screen,index)=><option value={screenKey(screen)} key={screenKey(screen)}>{screen.label||'Display '+(index+1)} · {screen.width} × {screen.height}{screen.isPrimary?' · primary':''}</option>)}
            </select></label>}
            <p role="status">{displayAction||projector.error||displays.issue||(projector.output
              ? 'Use Enter fullscreen in the projector window. You can keep adjusting the output here.'
              : 'Connect an external display and choose Extend. Detect displays to send the projector window there.')}</p>
            {process.env.NEXT_PUBLIC_SPACEGIT_PUBLIC!=='1'&&<Link href="/setup#projector-calibration" target="_blank" rel="noopener">Calibrate for wall tracking <Icon name="external" size={13}/></Link>}
          </div>
        </section>
        <section className="nw-panel"><div className="nw-panel-head"><div><h2>Projection controls</h2><p>OUTPUT PROFILE</p></div><Icon name="target"/></div>
          <div className="nw-profile">
            <label>Brightness <span>{settings.brightness}%</span><input type="range" min={40} max={160} value={settings.brightness} onChange={e=>changeSettings({...settings,brightness:Number(e.target.value)})}/></label>
            <label>Contrast <span>{settings.contrast}%</span><input type="range" min={60} max={160} value={settings.contrast} onChange={e=>changeSettings({...settings,contrast:Number(e.target.value)})}/></label>
            <label className="nw-check"><input type="checkbox" checked={settings.lowPower} onChange={e=>changeSettings({...settings,lowPower:e.target.checked})}/>Reduce quality</label>
          </div>
        </section>
      </div>
    </div>
    {projector.output&&<ProjectorOutput output={projector.output} close={projector.close}>{renderImage(false)}</ProjectorOutput>}
  </>;
}
