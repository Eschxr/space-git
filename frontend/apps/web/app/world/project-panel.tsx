'use client';
import Link from 'next/link';
import {useEffect,useRef,useState,type RefObject} from 'react';
import type {Commit} from '../../../../packages/protocol/types';
import {Icon} from '../components/icons';
import {requestDisplayFullscreen,screenKey,useProjectorDisplays} from '../components/projector-displays';
import {type Asset,type Projection} from './domain';
import {ACTIONS, EXTRA_NAMES, AGENTS, Engine, STATUS, type Action, type Agent, type Target} from './engine';
import type {Edge} from './edge';
import {RenderScene,useSceneAsset} from './render-scene';
import {ProjectorOutput,useProjectorWindow} from './projector-window';
import {PortalOffice} from './portal-office';

const targets:Record<Target,string>={desk_01:'Desk 01',desk_02:'Desk 02',desk_03:'Desk 03',archive:'Archive',door:'Door',meeting:'Meeting table'};
export type ProjectAPI={present:()=>void;play:()=>void;office:()=>void};
export function ProjectPanel({commit,edge,model,settings,changeSettings,projectRef,presenting,setPresenting,active=true}:{commit?:Commit;edge:Edge|null;model?:{remote:Asset|null;local:File|null};settings:Projection;changeSettings:(settings:Projection)=>void;
  projectRef:RefObject<ProjectAPI|null>;presenting:boolean;setPresenting:(on:boolean)=>void;active?:boolean}) {
  const engine=useRef<Engine|null>(null);
  const surface=useRef<HTMLDivElement>(null);
  const [agents,setAgents]=useState<Agent[]>(AGENTS),[running,setRunning]=useState(false),[world,setWorld]=useState<'office'|'physical'>('office');
  const [pattern,setPattern]=useState(false),[message,setMessage]=useState(''),[statuses,setStatuses]=useState<Record<string,string>>({});
  const [agent,setAgent]=useState(AGENTS[0].id),[action,setAction]=useState<Action>('inspect'),[target,setTarget]=useState<Target>('archive');
  const asset=useSceneAsset(edge,world==='physical'?model?.remote??null:null,world==='physical'?model?.local??null:null);
  const [duration,setDuration]=useState(3000);
  const [pageVisible,setPageVisible]=useState(true);
  const [full,setFull]=useState(false);
  const [reveal,setReveal]=useState(0);
  const [blackedOut,setBlackedOut]=useState(false);
  const [displayAction,setDisplayAction]=useState('');
  const displays=useProjectorDisplays();
  const projector=useProjectorWindow();
  const exit=()=>{
    if(document.fullscreenElement===surface.current) void document.exitFullscreen().catch(()=>{});
    setPresenting(false);
  };
  useEffect(()=>{
    engine.current=new Engine();
    return ()=>{engine.current=null;};
  },[]);
  useEffect(()=>{
    const changed=()=>{
      const on=document.fullscreenElement===surface.current;
      setFull(on);
      if(on)setReveal(value=>value+1);
      else setPresenting(false);
    };
    const visible=()=>setPageVisible(!document.hidden);
    document.addEventListener('fullscreenchange',changed);
    document.addEventListener('visibilitychange',visible);
    return ()=>{document.removeEventListener('fullscreenchange',changed);document.removeEventListener('visibilitychange',visible);};
  },[setPresenting]);
  useEffect(()=>{
    if(engine.current)engine.current.running=running;
    if(!active||!running)return;
    const sample=setInterval(()=>{
      const actors=engine.current?.actors;
      if(!actors)return;
      setStatuses(Object.fromEntries([...actors].map(([id,{pose}])=>[id,STATUS[pose.action]+' · '+targets[pose.target]])));
    },280);
    return ()=>clearInterval(sample);
  },[active,running]);
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
    projectRef.current={present,play:()=>setRunning(true),office:()=>{setWorld('office');setPattern(false);}};
    return ()=>{projectRef.current=null;};
  },[projectRef,setPresenting]);
  useEffect(()=>{
    if(!active)return;
    const key=(e:KeyboardEvent)=>{
      if(e.defaultPrevented||e.altKey||e.metaKey||e.ctrlKey||e.repeat||(e.target instanceof HTMLElement&&(e.target.closest('input,select,textarea,button,a,[contenteditable]'))))return;
      if(e.key.toLowerCase()==='w'){setWorld(w=>w==='office'?'physical':'office');setPattern(false);}
      if(e.key.toLowerCase()==='f'){e.preventDefault();projectRef.current?.present();}
      if(e.key.toLowerCase()==='h'){if(document.fullscreenElement===surface.current)void document.exitFullscreen().catch(()=>{});setPresenting(!presenting);}
      if(e.key.toLowerCase()==='g')setPattern(v=>!v);
      if(e.key.toLowerCase()==='b')setBlackedOut(value=>!value);
      if(e.code==='Space'){e.preventDefault();setRunning(v=>!v);}
      if(e.key==='Escape'&&document.fullscreenElement!==surface.current)setPresenting(false);
    };
    document.addEventListener('keydown',key);
    return ()=>document.removeEventListener('keydown',key);
  },[active,projectRef,presenting,setPresenting]);
  const add=()=>{
    if(agents.length>=6)return;
    const i=agents.length-3;
    const next:Agent={id:'guest_'+(i+1),name:EXTRA_NAMES[i],role:'Visiting researcher',home:('desk_0'+(i+1)) as Target,tone:['#c4c4c4','#818181','#555'][i]};
    engine.current?.add(next);setAgents([...agents,next]);setAgent(next.id);
  };
  const run=()=>{
    try {engine.current?.command({agent_id:agent,action,target,duration_ms:duration});setRunning(true);setMessage('Command queued for '+(agents.find(a=>a.id===agent)?.name??agent)+'.');}
    catch(error){setMessage(error instanceof Error?error.message:'Invalid command.');}
  };
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
    {pattern?<Pattern/>:world==='office'?<PortalOffice engine={engine} agents={agents} angle={settings.angle} lowPower={settings.lowPower} reveal={reveal} outputWindow={projector.output?.window} visible={active&&(!!projector.output||pageVisible)}/>:
      commit||asset.data?<RenderScene scene={commit?.scene} simulated={commit?.evidence?.mode==='demo'&&!asset.data} asset={asset.data} cloud={!!asset.data&&'geometry' in asset.data} lowPower={settings.lowPower} visible={active&&(!!projector.output||pageVisible)}/>:
        <div className="nw-render-note">{asset.message||'Open a physical revision or model in Reconstruct to project it here.'}</div>}
  </div>;
  return <>
    <div className="nw-titlebar">
      <div><div className="nw-eyebrow"><span/> 04 / PROJECTION</div><h1>Project</h1><p>Open a window into another world.</p></div>
      <div className="nw-actions">
        <button className="nw-btn" disabled={!!projector.output} onClick={()=>{setPresenting(true);surface.current?.focus({preventScroll:true});}}>Hide controls</button>
        <button className="nw-btn" disabled={!!projector.output} onClick={()=>projectRef.current?.present()}>Fullscreen</button>
        <button className="nw-btn nw-primary" onClick={openProjector}><Icon name="screen"/>{projector.output?'Focus projector window':'Open projector window'}</button>
      </div>
    </div>
    <div className="nw-workspace-grid nw-project-grid">
      <section className="nw-panel nw-view-panel">
        <div className="nw-panel-head"><div><h2>{pattern?'Alignment pattern':world==='office'?'Office 01 · The other side':'Physical scene'}</h2><p>{pattern?'PROJECTOR TEST':world==='office'?'VIRTUAL ENVIRONMENT · LOCAL SIMULATION':commit?.evidence?.mode==='demo'?'SIMULATED RECONSTRUCTION':'SAVED SPATIAL REVISION'}</p></div>
          <div className="nw-actions">
            <button className="nw-btn nw-tiny" aria-pressed={world==='office'&&!pattern} onClick={()=>{setWorld('office');setPattern(false);}}>Virtual office</button>
            <button className="nw-btn nw-tiny" aria-pressed={world==='physical'&&!pattern} onClick={()=>{setWorld('physical');setPattern(false);}}>Physical world</button>
            <button className="nw-btn nw-tiny" aria-pressed={pattern} onClick={()=>setPattern(v=>!v)}><Icon name="grid" size={13}/>Test pattern</button>
          </div>
        </div>
        <div className={'nw-output'+(presenting?' is-presenting':'')} ref={surface} tabIndex={-1} data-testid="projector-surface">
          {projector.output ? <div className="nw-render-note">Output is on the projector window.</div> : image}
          {presenting&&<div className="nw-presentation-exit">
            {!full&&<button className="nw-btn nw-tiny" onClick={()=>projectRef.current?.present()}>Fullscreen</button>}
            <button className="nw-btn nw-tiny" onClick={exit}>Exit presentation</button>
          </div>}
        </div>
        <div className="nw-panel-foot">
          <span>1920 × 1080 REFERENCE <b>·</b> 16:9</span>
          <span><kbd>F</kbd> Fullscreen <kbd>W</kbd> World <kbd>G</kbd> Grid <kbd>B</kbd> Blackout <kbd>Space</kbd> Play</span>
        </div>
      </section>
      <div className="nw-side-stack">
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
            <label>Viewing angle<select className="nw-field" value={settings.angle} onChange={e=>changeSettings({...settings,angle:e.target.value as Projection['angle']})}><option>Portal</option><option>Corner</option><option>Wide</option></select></label>
            <label>Brightness <span>{settings.brightness}%</span><input type="range" min={40} max={160} value={settings.brightness} onChange={e=>changeSettings({...settings,brightness:Number(e.target.value)})}/></label>
            <label>Contrast <span>{settings.contrast}%</span><input type="range" min={60} max={160} value={settings.contrast} onChange={e=>changeSettings({...settings,contrast:Number(e.target.value)})}/></label>
            <label className="nw-check"><input type="checkbox" checked={settings.lowPower} onChange={e=>changeSettings({...settings,lowPower:e.target.checked})}/>Reduce quality</label>
          </div>
        </section>
        <section className="nw-panel"><div className="nw-panel-head"><div><h2>World engine</h2><p>DETERMINISTIC ACTION PLANNER</p></div><span className="nw-chip"><i/>{running?'RUNNING':'PAUSED'}</span></div>
          <div className="nw-agent-list">{agents.map(a=><div className="nw-agent" key={a.id}><span className="nw-avatar" aria-hidden="true">{a.name[0]}</span><div><strong>{a.name} <small>{a.role}</small></strong><p>{running?statuses[a.id]??'Ready':'Standing by'}</p></div></div>)}</div>
          <div className="nw-actions nw-sim-actions">
            <button className="nw-btn nw-primary nw-tiny" onClick={()=>{if(!running){setWorld('office');setPattern(false);}setRunning(!running);}}>{running?'Pause':'Start simulation'}</button>
            <button className="nw-btn nw-tiny" onClick={()=>{engine.current=new Engine(agents);setRunning(false);setStatuses({});setMessage('Simulation reset.');}}>Reset</button>
            <button className="nw-btn nw-tiny" disabled={agents.length>=6} onClick={add}><Icon name="plus" size={14}/>Add agent</button>
          </div>
          <details className="nw-command"><summary>Command an agent</summary><form onSubmit={e=>{e.preventDefault();run();}}>
            <label>Agent<select className="nw-field" value={agent} onChange={e=>setAgent(e.target.value)}>{agents.map(a=><option value={a.id} key={a.id}>{a.name}</option>)}</select></label>
            <label>Action<select className="nw-field" value={action} onChange={e=>setAction(e.target.value as Action)}>{ACTIONS.map(x=><option key={x}>{x}</option>)}</select></label>
            <label>Target<select className="nw-field" value={target} onChange={e=>setTarget(e.target.value as Target)}>{Object.keys(targets).map(x=><option value={x} key={x}>{targets[x as Target]}</option>)}</select></label>
            <label>Duration (ms)<input className="nw-field" type="number" min={500} max={15000} step={1} required value={duration} onChange={e=>setDuration(+e.target.value)}/></label>
            <button className="nw-btn nw-tiny nw-primary">Send command</button>
          </form></details>
          {message&&<p className="nw-fine" role="status">{message}</p>}
        </section>
      </div>
    </div>
    {projector.output&&<ProjectorOutput output={projector.output} close={projector.close} replay={()=>setReveal(value=>value+1)}>{image}</ProjectorOutput>}
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
