'use client';
import {useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {api, useLive,useToken,type Wizard} from '../components/connection';
import {OverlayView} from '../components/overlay';
import {requestDisplayFullscreen,screenKey,useProjectorDisplays,type ScreenDetails} from '../components/projector-displays';
import type {Pair} from '../../../../packages/protocol/types';
type Paint={seq:number;paint_ms:number};
function geometry(details:ScreenDetails|null){
 const d=window.devicePixelRatio,s=details?.currentScreen;
 return {width:Math.round(innerWidth*d),height:Math.round(innerHeight*d),fullscreen:!!document.fullscreenElement,
  screen:[s?.left??window.screenX,s?.top??window.screenY],display_key:s?screenKey(s):null,screen_label:s?.label.slice(0,160)??null};
}
export default function Projector(){
 const [token]=useToken(), {event,error}=useLive(token,350);
 const [wizard,setWizard]=useState<Wizard|null>(null),[size,setSize]=useState<Pair>([1600,900]),[full,setFull]=useState(false),[issue,setIssue]=useState('');
 const [actionIssue,setActionIssue]=useState('');
 const [bound,setBound]=useState(false),[allowed,setAllowed]=useState(false);
 const {detailsRef, screens, selected, select, selectedScreen, detect, issue:displayIssue}=useProjectorDisplays();
 const ack=useRef<string|null>(null),paint=useRef<Paint[]>([]);
 const wizardKey=wizard?.key;
 useEffect(()=>{
  if(!full||!bound||!wizardKey)return;
  let id=requestAnimationFrame(()=>{
   id=requestAnimationFrame(()=>{ack.current=wizardKey;});
  });
  return ()=>cancelAnimationFrame(id);
 },[wizardKey,full,bound]);
 const seq=event?.seq,liveOverlay=event?.mode==='live'&&!!event.overlay;
 useEffect(()=>{
  if(!full||!bound||!liveOverlay||seq===undefined)return;
  const id=requestAnimationFrame(()=>{paint.current.push({seq,paint_ms:Date.now()});if(paint.current.length>20)paint.current.shift();});
  return ()=>cancelAnimationFrame(id);
 },[seq,liveOverlay,full,bound]);
 useEffect(()=>{
  if(!token)return;
  const id=crypto.randomUUID();
  let done=false, pending=false,lastSuccess=0,current='';
  const reconcile=()=>{
   const g=geometry(detailsRef.current), key=JSON.stringify(g);
   setFull(g.fullscreen);setSize(old=>old[0]===g.width&&old[1]===g.height?old:[g.width,g.height]);
   if(key!==current||performance.now()-lastSuccess>700||document.hidden){
    setBound(false);ack.current=null;
   }
   return {g,key};
  };
  async function register(){
   if(done)return;
   const {g,key}=reconcile();
   if(pending||document.hidden)return;
   pending=true;
   try{const data=await api<{wizard:Wizard|null;allow_guidance:boolean}>(token,'/projector',{...g,id,wizard_key:ack.current,automatic_calibration:true,paint:paint.current.splice(0)});
    if(!done&&JSON.stringify(geometry(detailsRef.current))===key){
     current=key;lastSuccess=performance.now();setBound(true);setAllowed(data.allow_guidance);setWizard(data.wizard);setIssue('');
    }
   }
   catch(e){if(!done){setBound(false);setWizard(null);setIssue((e as Error).message);}}
   finally{pending=false;}
  }
  const refresh=()=>{void register();};
  queueMicrotask(refresh);const timer=setInterval(refresh,160);
  window.addEventListener('resize',refresh);document.addEventListener('fullscreenchange',refresh);document.addEventListener('visibilitychange',refresh);
  return()=>{done=true;clearInterval(timer);window.removeEventListener('resize',refresh);document.removeEventListener('fullscreenchange',refresh);document.removeEventListener('visibilitychange',refresh);};
 },[token,detailsRef]);
 async function fullscreen(){
  try{
   await requestDisplayFullscreen(document.documentElement, selectedScreen());
   setActionIssue('');
  }catch(e){setActionIssue((e as Error).message+' Open the projector page in Chrome or Edge if fullscreen is unavailable.');}
 }
 const visible=event?.mode==='demo'?event:(full&&bound&&!issue?allowed?event:event&&{...event,overlay:null,state:'SETUP_REQUIRED' as const}:null);
 return <main className={'projection '+(full?'fullscreen':'')}>
  <OverlayView event={visible} wizard={!issue&&full&&bound?wizard:null} output={full?size:event?.calibration?.output??size}/>
  {full&&(!bound||!wizard&&!allowed)&&event?.mode!=='demo'&&<div className="projector-test">
   <strong>SpaceGit projection test</strong>
   <span>{size.join(' × ')}</span>
   <span>{issue||(!bound?'Connecting to the local edge…':'Start calibration in Setup · Esc exits fullscreen')}</span>
  </div>}
  {!full&&<div className="projector-controls"><Link className="btn" href="/setup">Back to Setup</Link>
   {token&&<button className="btn" onClick={()=>{setActionIssue('');void detect();}}>Detect displays</button>}
   {screens.length>0&&<label>Projector display<select value={selected} onChange={e=>select(e.target.value)}><option value="">Current display</option>{screens.map((s,i)=><option value={screenKey(s)} key={screenKey(s)}>{s.label||'Display '+(i+1)} · {s.width}×{s.height}{s.isPrimary?' · primary':''}</option>)}</select></label>}
   <button className="btn primary" disabled={!token} onClick={fullscreen}>Enter fullscreen</button><span role="status">{actionIssue||displayIssue||issue||error||(!token?'Connect the local edge in Setup first.':'Select the projector display or move this window there manually.')}</span></div>}
 </main>;
}
