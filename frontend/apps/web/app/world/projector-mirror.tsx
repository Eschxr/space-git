'use client';

import {useEffect,useRef,useState} from 'react';

/** Mirror the one renderer: keep the preview and output on the same camera. */
export function ProjectorMirror({root}:{root:HTMLDivElement}){
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
  return <div className="nw-mirror">
    <video ref={video} autoPlay muted playsInline aria-label="Live projector preview" onClick={()=>{void video.current?.play().then(()=>setIssue(''));}}/>
    {issue&&<div className="nw-render-note" role="status">{issue}</div>}
  </div>;
}
