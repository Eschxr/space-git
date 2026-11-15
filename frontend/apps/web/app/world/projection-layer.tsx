'use client';

import {useRef} from 'react';
import {useFrame} from '@react-three/fiber';
import type {Mesh} from 'three';
import type {ProjectionObject} from './projection-objects';

export type ProjectionBounds = {center:[number,number,number];radius:number};
export function ProjectionLayer({objects,playing,bounds}:{objects:ProjectionObject[];playing:boolean;bounds:ProjectionBounds}){
  return <group name="projection-additions">{objects.map(item=><Decoration key={item.id} {...{item,playing,bounds}}/>)}</group>;
}
function Decoration({item,playing,bounds}:{item:ProjectionObject;playing:boolean;bounds:ProjectionBounds}){
  const mesh=useRef<Mesh>(null),time=useRef(0);
  useFrame((_,delta)=>{
    if(!mesh.current)return;
    if(playing)time.current+=Math.min(delta,.1);
    const t=time.current,r=bounds.radius;
    mesh.current.position.set(...item.position.map((value,index)=>bounds.center[index]+value*r*.7) as [number,number,number]);
    if(item.animation==='float')mesh.current.position.y+=Math.sin(t*1.8)*r*.07;
    mesh.current.rotation.set(item.animation==='spin'?t*.3:0,item.animation==='spin'?t*.8:0,0);
    mesh.current.scale.setScalar(item.size*r*(item.animation==='pulse'?1+Math.sin(t*2)*.18:1));
  });
  return <mesh ref={mesh} name={item.id}>
    {item.shape==='sphere'?<sphereGeometry args={[1,28,20]}/>:item.shape==='cube'?<boxGeometry args={[1.6,1.6,1.6]}/>:item.shape==='torus'?<torusGeometry args={[.8,.24,12,36]}/>:<coneGeometry args={[.85,1.7,28]}/>}
    <meshStandardMaterial color={item.color} emissive={item.color} emissiveIntensity={.22} metalness={.35} roughness={.3}/>
  </mesh>;
}
