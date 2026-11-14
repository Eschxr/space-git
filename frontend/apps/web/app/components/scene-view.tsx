'use client';
import {Canvas,useThree} from '@react-three/fiber';
import {useEffect} from 'react';
import {Box3,PerspectiveCamera,Vector3} from 'three';
import type {Object3D} from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import type {Scene,VisualPlacement} from '../../../../packages/protocol/types';
const cameraOptions={fov:45};
function setClipping(camera:PerspectiveCamera,radius:number){
 camera.near=Math.max(.00001,radius*.001);
 camera.far=radius*50;
 camera.updateProjectionMatrix();
}

function Controls({wall,reset,focus}:{wall:Scene['wall'];reset:number;focus?:Object3D|null}){
 const {camera,gl,invalidate}=useThree();
 const w=wall[0], h=wall[1];
 useEffect(()=>{
  const controls=new OrbitControls(camera,gl.domElement);
  controls.target.set(w*.50,h*.5,0);camera.position.set(w*1.12,h*1.08,Math.max(w,h)*.98);
  let radius=Math.max(w,h);
  if(focus){
   const b=new Box3().setFromObject(focus);
   if(!b.isEmpty()){
    const c=b.getCenter(new Vector3());radius=Math.max(.001,b.getSize(new Vector3()).length()/2);
    controls.target.copy(c);camera.position.copy(c).add(new Vector3(radius*1.3,radius*.85,radius*2.75));
   }
  }
  if(camera instanceof PerspectiveCamera)setClipping(camera,radius);
  controls.minDistance=radius*.07;controls.maxDistance=radius*7;
  const redraw=()=>invalidate();
  controls.update();redraw();controls.addEventListener('change',redraw);
  return ()=>controls.dispose();
 },[camera,gl,invalidate,w,h,reset,focus]);
 return null;
}
export default function SceneView({scene,selected,onSelect,reset,changed,extra,visualOnly,placement}:{scene:Scene;selected:string;onSelect:(id:string)=>void;reset:number;changed?:Set<string>;extra?:Object3D|null;visualOnly?:boolean;placement?:VisualPlacement}){
 const [w,h]=scene.wall;
 return <Canvas frameloop="demand" dpr={[1,1.65]} camera={cameraOptions} gl={{preserveDrawingBuffer:true}} fallback={<div className="webgl-fail">WebGL is unavailable. Use the object inspector to edit the measured layout.</div>}>
  <color attach="background" args={['#101923']}/>
  <ambientLight intensity={1.2}/><directionalLight color="#d0e9ff" intensity={2.2} position={[0,h,4]}/><directionalLight color="#69f0a5" intensity={.55} position={[w,0,1]}/>
  <Controls wall={scene.wall} reset={reset} focus={visualOnly?extra:null}/>
  {!visualOnly&&<><gridHelper args={[Math.max(w,h)*5,40,'#274957','#1b2e3e']} position={[w/2,-.11,0]}/>
  <axesHelper args={[Math.min(w,h)*.24]} position={[0,0,.06]}/>
  <group name="SpaceGit">
    <mesh name="Metric wall" position={[w/2,h/2,-.026]}><boxGeometry args={[w,h,.05]}/><meshStandardMaterial color="#294454" metalness={.24} roughness={.77}/></mesh>
    <gridHelper args={[w,24,'#587380','#3a5b68']} rotation={[Math.PI/2,0,0]} scale={[1,1,h/w]} position={[w/2,h/2,.002]}/>
    {scene.constraints?.keep_out.map(z=><mesh key={z.id} position={[z.x,z.y,.003]}><planeGeometry args={[z.w,z.h]}/><meshBasicMaterial color="#FF8F91" transparent opacity={.27} depthWrite={false}/></mesh>)}
    {scene.objects.map((o,i)=><group key={o.id} name={o.name} userData={{stable_id:o.id,marker_id:o.marker}} position={[o.x,o.y,o.d/2]} rotation={[0,0,o.angle]}
      onPointerDown={e=>{e.stopPropagation();onSelect(o.id);}}>
      <mesh><boxGeometry args={[o.w,o.h,o.d]}/><meshStandardMaterial color={selected===o.id?'#42b47c':changed?.has(o.id)?'#d4a16c':i%2?'#3c6573':'#486e80'} metalness={.25} roughness={.46}/></mesh>
      <mesh position={[-o.w*.25,o.h*.23,o.d/2+.001]}><planeGeometry args={[Math.min(o.w,o.h)*.24,Math.min(o.w,o.h)*.24]}/><meshBasicMaterial color={selected===o.id?'#d0ffdc':'#c8e6e6'}/></mesh>
      <mesh position={[-o.w*.25,o.h*.23,o.d/2+.002]}><planeGeometry args={[Math.min(o.w,o.h)*.13,Math.min(o.w,o.h)*.13]}/><meshBasicMaterial color="#253943"/></mesh>
    </group>)}
  </group></>}
  {extra&&<group position={!visualOnly?placement?.position_m:undefined} scale={!visualOnly?Math.max(.000001,placement?.scale??1):undefined}
    rotation={!visualOnly&&placement?placement.rotation_deg.map(v=>v*Math.PI/180) as [number,number,number]:undefined}>
    <primitive object={extra}/>
  </group>}
 </Canvas>;
}
