'use client';
import {Canvas,useThree} from '@react-three/fiber';
import {useEffect,useState} from 'react';
import type {BufferGeometry} from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {PLYLoader} from 'three/addons/loaders/PLYLoader.js';
import {apiBase} from './connection';

function Orbit(){
 const {camera,gl,invalidate}=useThree();
 useEffect(()=>{
  camera.position.set(1.4,1.05,2.55);
  const orbit=new OrbitControls(camera,gl.domElement);
  orbit.update();orbit.minDistance=.15;orbit.maxDistance=10;
  const redraw=()=>invalidate();
  orbit.addEventListener('change',redraw);redraw();
  return ()=>orbit.dispose();
 },[camera,gl,invalidate]);
 return null;
}
export default function SparsePreview({id,token,name='sparse.ply'}:{id:string;token:string;name?:string}){
 const [geometry,setGeometry]=useState<BufferGeometry|null>(null),[error,setError]=useState('');
 useEffect(()=>{
  const control=new AbortController();let pending:BufferGeometry|undefined;
  async function load(){
   const r=await fetch(apiBase()+'/api/v1/assets/'+id+'/'+name,{headers:{Authorization:'Bearer '+token},signal:control.signal});
   if(!r.ok)throw Error('The registered PLY could not be opened.');
   const blob=await r.blob();
   if(blob.size>32*1024*1024)throw Error('The cloud is too large for the browser preview. Download the PLY instead.');
   const buf=await blob.arrayBuffer();if(control.signal.aborted)return;
   pending=new PLYLoader().parse(buf);pending.computeBoundingSphere();
   const sphere=pending.boundingSphere;
   if(!sphere||!Number.isFinite(sphere.radius)||sphere.radius<=0||pending.attributes.position.count>500000)throw Error('This cloud cannot be previewed safely. Download the PLY instead.');
   pending.translate(-sphere.center.x,-sphere.center.y,-sphere.center.z);pending.scale(1/sphere.radius,1/sphere.radius,1/sphere.radius);
   setGeometry(pending);
  }
  void load().catch(e=>{if(!control.signal.aborted)setError((e as Error).message);});
  return()=>{control.abort();pending?.dispose();};
 },[id,token,name]);
 if(error)return <p className="notice warning">{error}</p>;
 return <div className="cloud-preview"><span className="pill">{name==='dense.ply'?'DENSE':'SPARSE'} CLOUD · NORMALIZED PREVIEW · UNREGISTERED</span>
 {geometry?<Canvas frameloop="demand" camera={{fov:45}} fallback={<p>WebGL unavailable. Download the PLY.</p>}><color attach="background" args={['#0B111A']}/><Orbit/><points geometry={geometry}><pointsMaterial size={.015} vertexColors={!!geometry.attributes.color} color={geometry.attributes.color?'#fff':'#69F0A5'}/></points></Canvas>:<p className="blank">Loading sparse geometry…</p>}
 </div>;
}
