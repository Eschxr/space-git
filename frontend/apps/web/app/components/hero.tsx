'use client';
import {useState} from 'react';
import {Icon} from './icons';
const cards=[[78,78,70,48],[197,68,65,45],[316,69,75,60],[96,180,68,57],[221,193,61,42],[340,181,66,44]];
function xy(x:number,y:number,z=0){return [124+x*.97+y*.63,125+y*.59-x*.34-z];}
function rect(x:number,y:number,w:number,h:number,z=0){return [xy(x,y,z),xy(x+w,y,z),xy(x+w,y+h,z),xy(x,y+h,z)].map(p=>p.join(',')).join(' ');}
export default function Hero(){
 const [index,set]=useState(0);
 const card=cards[index], target=[card[0]+57,card[1]+53], from=xy(card[0]+card[2]/2,card[1]+card[3]/2,8), to=xy(target[0]+card[2]/2,target[1]+card[3]/2,5);
 return <div className="hero-visual">
  <div className="visual-top"><span><span className="signal-dot"/> SCENE PREVIEW</span><span>SIMULATED</span></div>
  <svg className="hero-diagram" viewBox="75 -64 704 470" role="img" aria-label="Isometric sample wall with six cards and a green route to a target">
   <defs><linearGradient id="plane" x2="1" y2="1"><stop stopColor="#1b3040"/><stop offset="1" stopColor="#10212c"/></linearGradient><linearGradient id="card" x2=".7" y2="1"><stop stopColor="#284855"/><stop offset="1" stopColor="#172a36"/></linearGradient><pattern id="floor" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="#24404b" strokeOpacity=".45"/></pattern><filter id="glow"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter><marker id="head" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="m0 0 10 5-10 5z" fill="#55FF95"/></marker></defs>
   <rect x="78" y="-60" width="690" height="456" fill="url(#floor)" opacity=".7"/>
   <polygon points={rect(-22,-16,497,287,-13)} fill="#080e15" stroke="#29414f"/>
   <polygon points={rect(-22,-16,497,287)} fill="url(#plane)" stroke="#537481" strokeWidth="1.1"/>
   {Array.from({length:18},(_,i)=><path key={'x'+i} d={'M'+xy(i*27-10,-16)+'L'+xy(i*27-10,271)} stroke="#4d7883" strokeOpacity=".23"/>)}
   {Array.from({length:11},(_,i)=><path key={'y'+i} d={'M'+xy(-22,i*27-16)+'L'+xy(475,i*27-16)} stroke="#4d7883" strokeOpacity=".23"/>)}
   {[[3,3],[440,3],[440,242],[3,242]].map(([x,y],i)=><g key={i}><polygon points={rect(x,y,15,15)} fill="#78dae9"/><polygon points={rect(x+3,y+3,9,9)} fill="#122635"/></g>)}
   {cards.map(([x,y,w,h],i)=><g key={i}><polygon points={rect(x,y,w,h,-7)} fill="#080f16" stroke="#15242d"/><polygon points={rect(x,y,w,h,8)} fill={i===index?'#1f443a':'url(#card)'} stroke={i===index?'#55ff95':'#578089'} strokeWidth="1.25"/><polygon points={rect(x+8,y+8,14,14,9)} fill={i===index?'#55ff95':'#79a1a5'}/><polygon points={rect(x+11,y+11,8,8,9)} fill="#152331"/><path d={'M'+xy(x+9,y+h-11,9)+'L'+xy(x+w-9,y+h-11,9)} stroke={i===index?'#55ff95':'#63858e'} opacity=".55"/></g>)}
   <polygon points={rect(target[0],target[1],card[2],card[3],4)} fill="#55ff9523" stroke="#55ff95" strokeWidth="1.7" strokeDasharray="5 4" filter="url(#glow)"/>
   <path d={'M'+from+' Q'+(from[0]+20)+','+(from[1]+60)+' '+to} fill="none" stroke="#55ff95" strokeWidth="3.2" markerEnd="url(#head)" filter="url(#glow)"/>
   <circle cx={from[0]} cy={from[1]} r="4" fill="#55ff95"/>
   <path d="M158 338h70m-35-20v42M676 266h31m-15-15v31" fill="none" stroke="#416071" strokeWidth="1"/>
   <text x="255" y="352" fill="#8fb3bc" fontSize="12" fontFamily="monospace">WALL FRAME / X · Y · Z</text>
  </svg>
  <div className="visual-bottom"><div><span className="muted mono">GUIDANCE PREVIEW</span><strong>Exhibit {String.fromCharCode(65+index)} <span>→</span> Target position</strong></div><button className="btn tiny" onClick={()=>set((index+1)%cards.length)} aria-label="Preview next object"><Icon name="rotate" size={15}/> Next object</button></div>
 </div>;
}
