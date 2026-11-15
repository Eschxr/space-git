'use client';
import {Canvas, useFrame, useThree} from '@react-three/fiber';
import {Component, useEffect, useMemo, useRef, type ReactNode} from 'react';
import {Box3, Mesh, PerspectiveCamera, Texture, Vector3, type Camera, type BufferGeometry, type Object3D} from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {PLYLoader} from 'three/addons/loaders/PLYLoader.js';
import type {Card, Scene} from '../../../../packages/protocol/types';
import {parseModel} from '../components/io';
import {isNormalized, type Delta} from './domain';
import {ProjectionLayer, type ProjectionBounds} from './projection-layer';
import type {ProjectionObject} from './projection-objects';

type XYZ = [number,number,number];
type Loaded = {geometry: BufferGeometry}|{model:Object3D}|{scene:Scene};
const PALE = '#cecece';
export default function Viewport({scene,lowPower=false,selected,select,diff=[],cloud=false,reset=0,asset,visible=true,additions=[],animationPlaying=true}:{
  scene?:Scene;lowPower?:boolean;selected?:string;select?:(id:string)=>void;diff?:Delta[];
  cloud?:boolean;reset?:number;asset?:Loaded|null;visible?:boolean;additions?:ProjectionObject[];animationPlaying?:boolean;
}) {
  const current = asset && 'scene' in asset ? asset.scene : scene;
  const bounds=useMemo<ProjectionBounds>(()=>{
    const box=asset&&'model' in asset?new Box3().setFromObject(asset.model):asset&&'geometry' in asset?asset.geometry.boundingBox:null;
    if(box&&!box.isEmpty())return {center:box.getCenter(new Vector3()).toArray(),radius:Math.max(.01,box.getSize(new Vector3()).length()*.35)};
    return {center:[0,1.5,0],radius:2};
  },[asset]);
  const fallback=<Fallback/>;
  return <RenderBoundary fallback={fallback}>
    <Canvas dpr={lowPower ? 1 : [1,1.5]} frameloop={visible?'always':'never'}
      camera={{position:[5,3.2,7.2],fov:44,near:.05,far:130}}
      gl={{antialias:!lowPower,powerPreference:'low-power'}} fallback={fallback}
      aria-label="Physical scene 3D viewport"
      onPointerMissed={()=>select?.('')}>
      <color attach="background" args={['#111']}/>
      <ambientLight intensity={.88}/><hemisphereLight args={['#ececec','#515151',1]}/>
        <InspectionCamera reset={reset} view={current?.id} asset={asset}/>
        <directionalLight position={[1,7,5]} intensity={2}/>
        {(!asset || 'scene' in asset || 'geometry' in asset && !cloud) && current &&
          <Study scene={current} {...{selected,select,diff}}/>}
        {asset && 'model' in asset && <primitive object={asset.model}/>}
        {asset && 'geometry' in asset && cloud && <points geometry={asset.geometry}>
          <pointsMaterial size={.024} sizeAttenuation color={asset.geometry.hasAttribute('color')?'white':'#d6d6d6'} vertexColors={asset.geometry.hasAttribute('color')}/>
        </points>}
      <ProjectionLayer objects={additions} playing={animationPlaying} bounds={bounds}/>
    </Canvas>
  </RenderBoundary>;
}

function Fallback() {return <div className="nw-render-note" role="status">3D rendering needs WebGL. Open this page in Chrome or Edge with graphics acceleration enabled.</div>;}
class RenderBoundary extends Component<{children:ReactNode;fallback:ReactNode},{failed:boolean}> {
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  render(){return this.state.failed?this.props.fallback:this.props.children;}
}

function InspectionCamera({reset,view,asset}:{reset:number;view?:string;asset?:Loaded|null}) {
  const {camera,gl}=useThree();
  const control=useRef<OrbitControls|null>(null);
  useEffect(()=>{
    const controls=new OrbitControls(camera,gl.domElement);
    controls.enableDamping=true;controls.minDistance=.12;controls.maxDistance=100;controls.maxPolarAngle=Math.PI*.89;
    control.current=controls;
    return ()=>{control.current=null;controls.dispose();};
  },[camera,gl]);
  useEffect(()=>{if (control.current) frameScene(camera,control.current,asset);},[camera,reset,view,asset]);
  useFrame(()=>control.current?.update());
  return null;
}
function frameScene(camera:Camera,controls:OrbitControls,asset?:Loaded|null){
    let center=new Vector3(0,1.12,-.35), radius=3.15;
    if (asset && 'model' in asset) {
      const box=new Box3().setFromObject(asset.model);
      if(!box.isEmpty()){center=box.getCenter(new Vector3());radius=box.getSize(new Vector3()).length()*.58 || 1;}
    } else if (asset && 'geometry' in asset) {
      const box=asset.geometry.boundingBox;
      if(box && !box.isEmpty()){center=box.getCenter(new Vector3());radius=box.getSize(new Vector3()).length()*.58 || 1;}
    }
    controls.target.copy(center);
    camera.position.set(center.x+radius*1.35,center.y+radius*.68,center.z+radius*1.85);
    controls.maxDistance=Math.max(radius*10,10);
    if (camera instanceof PerspectiveCamera) {camera.far=Math.max(100,radius*40);camera.updateProjectionMatrix();}
    controls.update();
}

function Block({p,s,c=PALE,cast=true,metal=0}:{p:XYZ;s:XYZ;c?:string;cast?:boolean;metal?:number}) {
  return <mesh position={p} castShadow={cast} receiveShadow><boxGeometry args={s}/><meshStandardMaterial color={c} metalness={metal} roughness={.79}/></mesh>;
}
function Study({scene,selected,select,diff}:{scene:Scene;selected?:string;select?:(id:string)=>void;diff:Delta[]}) {
  const [w,h]=scene.wall;
  const factor=Math.min(1,7/Math.max(w,h));
  const coord=(card:Card):XYZ=>[(card.x-(isNormalized(scene)?.5:w/2))*(isNormalized(scene)?w:1),card.y*(isNormalized(scene)?h:1),card.d/2+.02];
  return <group scale={factor}>
    <gridHelper args={[22,44,'#484848','#2a2a2a']}/><Block p={[0,h/2,-.10]} s={[w,h,.12]} c="#6e6e6e"/>
    {diff.filter(row=>row.kind==='moved'||row.kind==='missing').map(row=>row.before&&<mesh key={row.id} position={coord(row.before)} rotation={[0,0,row.before.angle]}>
      <boxGeometry args={[row.before.w,Math.max(row.before.h,.012),row.before.d]}/><meshBasicMaterial wireframe color="#e6e6e6" transparent opacity={.68}/>
    </mesh>)}
    {scene.objects.map(card=><group key={card.id} position={coord(card)} rotation={[0,0,card.angle]} onClick={event=>{event.stopPropagation();select?.(card.id);}}>
      <Block p={[0,0,0]} s={[card.w,Math.max(card.h,.012),card.d]} c={selected===card.id?'#f2f2f2':'#a6a6a6'}/>
    </group>)}
  </group>;
}

export async function loadAsset(blob:Blob, name:string):Promise<Loaded> {
  if(blob.size>64*1024*1024) throw Error('Choose a model under 64 MB.');
  const extension=name.split('.').pop()?.toLowerCase();
  if(extension==='ply'){
    const bytes=await blob.arrayBuffer();
    const header=new TextDecoder().decode(bytes.slice(0,16384)).split('end_header')[0];
    const count=Number(header.match(/^element vertex (\d+)\s*$/m)?.[1]);
    if(!/^ply\r?\n/.test(header)||!count||count>1500000)throw Error('Provide a PLY with 1 to 1,500,000 vertices.');
    const geometry=new PLYLoader().parse(bytes);
    geometry.computeBoundingBox();
    if(!geometry.attributes.position.count || !Number.isFinite(geometry.boundingBox?.min.lengthSq()) || !Number.isFinite(geometry.boundingBox?.max.lengthSq())){
      geometry.dispose();throw Error('The point cloud has no valid positions.');
    }
    return {geometry};
  }
  if(extension==='glb'){
    const result=await parseModel(await blob.arrayBuffer());
    if(result.scene)return {scene:result.scene};
    if(result.mesh)return {model:result.mesh};
  }
  if(extension==='gltf') {
    const data=JSON.parse(await blob.text());
    if(data.asset?.version!=='2.0'||data.nodes?.length>200||data.images?.length||
      data.accessors?.some((item:{count:number;sparse?:unknown})=>!Number.isInteger(item.count)||item.count<1||item.count>1500000||item.sparse)||
      data.extensionsUsed?.some((extension:string)=>extension!=='KHR_materials_unlit')||
      data.buffers?.some((item:{uri?:string})=>!/^data:application\/(octet-stream|gltf-buffer);base64,[a-z\d+/=]+$/i.test(item.uri??'')))
      throw Error('Use a self-contained glTF with inline geometry, or a GLB with embedded textures.');
    return {model:(await new GLTFLoader().parseAsync(JSON.stringify(data),'')).scene};
  }
  throw Error('Choose a PLY, GLB or self-contained glTF file.');
}

export function disposeAsset(asset:Loaded|null) {
  if (!asset) return;
  if ('geometry' in asset) asset.geometry.dispose();
  if ('model' in asset) asset.model.traverse(node=>{
    if(!(node instanceof Mesh))return;
    node.geometry.dispose();
    for(const material of Array.isArray(node.material)?node.material:[node.material]){
      for(const value of Object.values(material))if(value instanceof Texture){const data=value.source.data;if(typeof data?.close==='function')data.close();value.dispose();}
      material.dispose();
    }
  });
}
