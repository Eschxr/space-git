'use client';
import Link from 'next/link';
import {useEffect,useRef,useState,type RefObject} from 'react';
import type {Commit} from '../../../../packages/protocol/types';
import {Icon} from '../components/icons';
import {requestDisplayFullscreen,screenKey,useProjectorDisplays} from '../components/projector-displays';
import {CAMERAS,type Asset,type Projection} from './domain';
import type {Edge} from './edge';
import {RenderScene,useSceneAsset} from './render-scene';
import {ProjectorOutput,useProjectorWindow} from './projector-window';
import {ProjectionAssistant} from './projection-assistant';
import {ProjectorMirror} from './projector-mirror';
import type {ProjectionObject} from './projection-objects';

export type ProjectAPI={present:()=>void};
export function ProjectPanel({commit,edge,connect,model,settings,changeSettings,projectRef,presenting,setPresenting,active=true}:{commit?:Commit;edge:Edge|null;connect:()=>Promise<unknown>;model?:{remote:Asset|null;local:File|null};settings:Projection;changeSettings:(settings:Projection)=>void;
  projectRef:RefObject<ProjectAPI|null>;presenting:boolean;setPresenting:(on:boolean)=>void;active?:boolean}) {
  const surface=useRef<HTMLDivElement>(null);
  const [localScene,setLocalScene]=useState<File|null>(null);
  const [source,setSource]=useState<'handoff'|'file'|'latest'>(model?.remote||model?.local?'handoff':'latest');
  const [camera,setCamera]=useState(1),[sourceRefresh,setSourceRefresh]=useState(0),[sourceIssue,setSourceIssue]=useState('');
  const [objects,setObjects]=useState<ProjectionObject[]>([]),[undoStack,setUndoStack]=useState<ProjectionObject[][]>([]);
  const [animationPlaying,setAnimationPlaying]=useState(true);
  const changeObjects=(next:ProjectionObject[])=>{setUndoStack(stack=>[...stack,objects].slice(-40));setObjects(next);};
  const [pattern,setPattern]=useState(false),[message,setMessage]=useState('');
  const asset=useSceneAsset(edge,source==='handoff'?model?.remote??null:null,
    source==='file'?localScene:source==='handoff'?model?.local??null:null,
    source==='latest'?camera:undefined,sourceRefresh);
  const hasAssetSource=source==='latest'||source==='file'||!!(model?.local||model?.remote);
  const sourceLabel=source==='latest'?`Latest reconstruction · cam_0${camera} · ${CAMERAS.find(view=>view.id===camera)?.name}`:
    source==='file'?localScene?.name:model?.local?.name??model?.remote?.label;
  const loadLatest=async()=>{
    setSourceIssue('');setSource('latest');setPattern(false);setSourceRefresh(value=>value+1);
    if(!edge)try{await connect();}catch(error){setSourceIssue(error instanceof Error?error.message:'Could not connect to the edge.');}
  };
  const [pageVisible,setPageVisible]=useState(true);
  const [full,setFull]=useState(false);
  const [blackedOut,setBlackedOut]=useState(false);
  const [displayAction,setDisplayAction]=useState('');
  const displays=useProjectorDisplays();
  const projector=useProjectorWindow();
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
      if(e.key.toLowerCase()==='g')setPattern(v=>!v);
      if(e.key.toLowerCase()==='b')setBlackedOut(value=>!value);
      if(e.code==='Space'){e.preventDefault();setAnimationPlaying(value=>!value);}
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
  const image=<div className="nw-project-image" style={{filter:pattern?undefined:`brightness(${settings.brightness}%) contrast(${settings.contrast}%)`}}>
    {blackedOut&&<div className="nw-projector-blackout" aria-label="Output blacked out"/>}
    {pattern?<Pattern/>:
      asset.error||(hasAssetSource&&!asset.data)?<div className="nw-render-note" role={asset.error?'alert':'status'}>{source==='latest'&&!edge?'Connect the local edge to load the current reconstruction.':asset.message||'Loading geometry…'}</div>:
      (commit&&commit.evidence?.mode!=='demo')||asset.data?<RenderScene scene={commit?.evidence?.mode==='demo'?undefined:commit?.scene} additions={objects} animationPlaying={animationPlaying} asset={asset.data} cloud={!!asset.data&&'geometry' in asset.data} lowPower={settings.lowPower} visible={active&&(!!projector.output||pageVisible)}/>:
        <div className="nw-render-note">{asset.message||'Open a physical revision or model in Reconstruct to project it here.'}</div>}
  </div>;
  return <>
    <div className="nw-titlebar">
      <div><div className="nw-eyebrow"><span/> 04 / PROJECTION</div><h1>Project</h1><p>Project the reconstructed space and add 3D features with Ollama.</p></div>
      <div className="nw-actions">
        <button className="nw-btn" disabled={!!projector.output} onClick={()=>{setPresenting(true);surface.current?.focus({preventScroll:true});}}>Hide controls</button>
        <button className="nw-btn" disabled={!!projector.output} onClick={()=>projectRef.current?.present()}>Fullscreen</button>
        <button className="nw-btn nw-primary" onClick={openProjector}><Icon name="screen"/>{projector.output?'Focus projector window':'Open projector window'}</button>
      </div>
    </div>
    <div className="nw-workspace-grid nw-project-grid">
      <section className="nw-panel nw-view-panel">
        <div className="nw-panel-head"><div><h2>{pattern?'Alignment pattern':'Reconstructed scene'}</h2><p>{pattern?'PROJECTOR TEST':source==='latest'?`CURRENT RECONSTRUCTION · CAM_0${camera}`:asset.data?'IMPORTED SCENE · VIEWER COORDINATES':'RECONSTRUCTION UNAVAILABLE'}</p></div>
          <div className="nw-actions">
            <button className="nw-btn nw-tiny" aria-pressed={pattern} onClick={()=>setPattern(v=>!v)}><Icon name="grid" size={13}/>Test pattern</button>
          </div>
        </div>
        <div className={'nw-output'+(presenting?' is-presenting':'')} ref={surface} tabIndex={-1} data-testid="projector-surface">
          {projector.output&&!pattern ? <div className="nw-project-image" style={{filter:`brightness(${settings.brightness}%) contrast(${settings.contrast}%)`}}>
            <ProjectorMirror root={projector.output.root}/>
            {blackedOut&&<div className="nw-projector-blackout" aria-label="Output blacked out"/>}
          </div> : image}
          {presenting&&<div className="nw-presentation-exit">
            {!full&&<button className="nw-btn nw-tiny" onClick={()=>projectRef.current?.present()}>Fullscreen</button>}
            <button className="nw-btn nw-tiny" onClick={exit}>Exit presentation</button>
          </div>}
        </div>
        <div className="nw-panel-foot">
          <span>{projector.output?'LIVE PROJECTOR PREVIEW':'PROJECTOR PREVIEW'} <b>·</b> 16:9</span>
          <span><kbd>F</kbd> Fullscreen <kbd>G</kbd> Grid <kbd>B</kbd> Blackout <kbd>Space</kbd> Play</span>
        </div>
        <div className="nw-project-source">
          <div className="nw-actions">
            <label>Reconstruction view<select className="nw-field" value={camera} onChange={event=>{setCamera(+event.target.value);void loadLatest();}}>
              {CAMERAS.map(view=><option key={view.id} value={view.id}>cam_0{view.id} · {view.name}{view.id===4?' · overhead':''}</option>)}
            </select></label>
            <button className="nw-btn nw-tiny" onClick={()=>void loadLatest()}>{edge?'Load current reconstruction':'Connect and load reconstruction'}</button>
          </div>
          <label>Open reconstructed scene<input type="file" accept=".ply,.glb,.gltf" onChange={event=>{const file=event.target.files?.[0];if(file){setLocalScene(file);setSource('file');setSourceIssue('');setPattern(false);}event.target.value='';}}/></label>
          <p>{sourceLabel??'Connect to the reconstruction service or open a saved model file.'} · One source view at a time. Added objects use relative viewer positions.</p>
          {sourceIssue&&<p role="alert">{sourceIssue}</p>}
          {source==='latest'&&asset.error&&<p>Generate this view on the reconstruction laptop, set SPACEGIT_POINTDIT_OUTPUT_DIR on its edge service, then reload. You can also open its PLY file above.</p>}
          {hasAssetSource&&<Link className="nw-fine" href="/world">Open reconstruction workspace</Link>}
        </div>
      </section>
      <div className="nw-side-stack">
        <ProjectionAssistant sceneReady={!!asset.data&&!asset.error} edge={edge} connect={connect} objects={objects} change={changeObjects} canUndo={!!undoStack.length}
          undo={()=>{const previous=undoStack.at(-1);if(previous){setObjects(previous);setUndoStack(stack=>stack.slice(0,-1));}}}
          playing={animationPlaying} setPlaying={setAnimationPlaying} activate={()=>setPattern(false)}/>
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
    {message&&<p className="nw-fine" role="status">{message}</p>}
    {projector.output&&<ProjectorOutput output={projector.output} close={projector.close}>{image}</ProjectorOutput>}
  </>;
}

function Pattern(){
  return <svg className="nw-pattern" viewBox="0 0 1920 1080" role="img" aria-label="Projection alignment grid with crop marks, grayscale ramp and centre crosshair">
    <defs><pattern id="nw-grid" width="120" height="120" patternUnits="userSpaceOnUse"><path d="M120 0H0v120" stroke="#747474" strokeWidth="2" fill="none"/></pattern></defs>
    <rect width="1920" height="1080" fill="#101010"/><rect width="1920" height="1080" fill="url(#nw-grid)"/>
    <rect x="3" y="3" width="1914" height="1074" fill="none" stroke="#fff" strokeWidth="6"/>
    <rect x="96" y="54" width="1728" height="972" fill="none" stroke="#ccc" strokeWidth="3" strokeDasharray="16 10"/>
    <circle cx="960" cy="540" r="195" fill="none" stroke="#ddd" strokeWidth="3"/>
    <path d="M830 540h260m-130-130v260M70 125V70h110m1670 55V70h-110M70 955v55h110m1670-55v55h-110" fill="none" stroke="white" strokeWidth="5"/>
    {Array.from({length:10},(_,i)=><rect x={560+80*i} y="881" width="80" height="66" key={i} fill={`rgb(${i*28} ${i*28} ${i*28})`} stroke="#aaa"/>)}
    <text x="960" y="813" fill="#eee" textAnchor="middle" fontFamily="monospace" fontSize="32">SPACEGIT / PROJECTOR ALIGNMENT / 16:9</text>
  </svg>;
}
