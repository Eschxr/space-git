'use client';

import {useEffect,useRef,useState} from 'react';

/** Mirror the one renderer: do not tick a second simulation or change its camera. */
export function ProjectorMirror({root,office}:{root:HTMLDivElement;office:boolean}){
  const video=useRef<HTMLVideoElement>(null);
  const [issue,setIssue]=useState('Connecting live preview…');
  useEffect(()=>{
    const element=video.current;
    let canvas:HTMLCanvasElement|null=null,stream:MediaStream|undefined;
    const stop=()=>{stream?.getTracks().forEach(track=>track.stop());stream=undefined;};
    const update=()=>{
      const next=root.querySelector('canvas');
      if(next&&next===canvas)return;
      stop();canvas=next;
      if(!next||!element){setIssue(root.querySelector('.nw-render-note')?.textContent||'Waiting for the projector renderer…');return;}
      try{
        stream=next.captureStream(30);
        element.srcObject=stream;
        void element.play().then(()=>setIssue('')).catch(()=>setIssue('Click the preview to resume it.'));
      }catch{setIssue('Live preview requires canvas capture support in Chrome or Edge.');}
    };
    const observer=new MutationObserver(update);
    observer.observe(root,{childList:true,subtree:true});update();
    return ()=>{observer.disconnect();stop();if(element)element.srcObject=null;};
  },[root]);
  return <div className={office?'nw-portal':'nw-mirror'}>
    <video ref={video} autoPlay muted playsInline aria-label="Live projector preview" onClick={()=>{void video.current?.play().then(()=>setIssue(''));}}/>
    {office&&<div className="nw-portal-frame" aria-hidden="true"/>}
    {issue&&<div className="nw-render-note" role="status">{issue}</div>}
  </div>;
}
