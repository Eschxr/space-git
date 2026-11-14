'use client';
import {Canvas, useFrame, useThree} from '@react-three/fiber';
import {Component, useEffect, useRef, type ReactNode, type RefObject} from 'react';
import {Box3, Group, Mesh, MeshStandardMaterial, PerspectiveCamera, PointLight, Texture, Vector3, type Camera, type BufferGeometry, type Object3D} from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {PLYLoader} from 'three/addons/loaders/PLYLoader.js';
import type {Card, Scene} from '../../../../packages/protocol/types';
import {parseModel} from '../components/io';
import {isNormalized, type Delta, type Projection} from './domain';
import {Engine, type Agent} from './engine';

type XYZ = [number,number,number];
type Loaded = {geometry: BufferGeometry}|{model:Object3D}|{scene:Scene};
const PALE = '#cecece';
const CAMS: Record<Projection['angle'],{pos:XYZ;look:XYZ}> = {
  Portal:{pos:[0,2.17,9.9],look:[0,1.42,-.7]},Corner:{pos:[5.9,3.05,8.2],look:[-.8,1.25,-.9]},
  Wide:{pos:[-3.4,4.85,11.2],look:[.15,1.05,-.7]},
};
const revealSeconds = 2.08;
const fade = (time:number, start:number, end:number) => {
  const t = Math.max(0, Math.min(1, (time-start)/(end-start)));
  return t*t*(3-2*t);
};
type RevealClock = RefObject<number>;

export default function Viewport({office=false, scene, simulated=false, lowPower=false, angle='Portal', engine, agents=[], selected, select, diff=[], cloud=false, reset=0, asset, visible=true, reveal=0, reducedMotion=false, onReveal}:{
  office?:boolean; scene?:Scene; simulated?:boolean; lowPower?:boolean; angle?:Projection['angle'];
  engine?:RefObject<Engine|null>; agents?:Agent[]; selected?:string; select?:(id:string)=>void; diff?:Delta[];
  cloud?:boolean; reset?:number; asset?:Loaded|null; visible?:boolean;
  reveal?:number; reducedMotion?:boolean; onReveal?:(reveal:number)=>void;
}) {
  const current = asset && 'scene' in asset ? asset.scene : scene;
  const fallback=<Fallback reveal={reveal} onReveal={onReveal}/>;
  return <RenderBoundary fallback={fallback}>
    <Canvas dpr={lowPower ? 1 : [1,1.5]} frameloop={visible?'always':'never'} shadows={!lowPower && office}
      camera={{position:office?CAMS.Portal.pos:[5,3.2,7.2],fov:44,near:.05,far:130}}
      gl={{antialias:!lowPower,powerPreference:'low-power'}} fallback={fallback}
      aria-label={office?'Virtual office 3D viewport':'Physical scene 3D viewport'}
      onPointerMissed={()=>select?.('')}>
      <color attach="background" args={[office?'#171717':'#111']}/>
      <ambientLight intensity={office?.42:.88}/><hemisphereLight args={['#ececec','#515151',office?.52:1]}/>
      {office && engine ?
        <OfficeScene {...{angle, lowPower, engine, agents, reveal, reducedMotion, onReveal}}/> : <>
        <InspectionCamera reset={reset} view={current?.id} asset={asset}/>
        <directionalLight position={[1,7,5]} intensity={2}/>
        {(!asset || 'scene' in asset || 'geometry' in asset && !cloud) && current &&
          <Study scene={current} simulated={simulated && !(asset && 'scene' in asset)} {...{selected,select,diff,cloud:cloud&&!asset}}/>}
        {asset && 'model' in asset && <primitive object={asset.model}/>}
        {asset && 'geometry' in asset && cloud && <points geometry={asset.geometry}>
          <pointsMaterial size={.024} sizeAttenuation color={asset.geometry.hasAttribute('color')?'white':'#d6d6d6'} vertexColors={asset.geometry.hasAttribute('color')}/>
        </points>}
      </>}
    </Canvas>
  </RenderBoundary>;
}

function Fallback({reveal,onReveal}:{reveal:number;onReveal?:(reveal:number)=>void}) {
  useEffect(()=>{onReveal?.(reveal);},[onReveal,reveal]);
  return <div className="nw-render-note" role="status">3D rendering needs WebGL. Scene details and the projection test pattern are still available.</div>;
}
class RenderBoundary extends Component<{children:ReactNode;fallback:ReactNode},{failed:boolean}> {
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  render(){return this.state.failed?this.props.fallback:this.props.children;}
}

function OfficeScene({angle,lowPower,engine,agents,reveal,reducedMotion,onReveal}:{
  angle:Projection['angle'];lowPower:boolean;engine:RefObject<Engine|null>;agents:Agent[];
  reveal:number;reducedMotion:boolean;onReveal?:(reveal:number)=>void;
}) {
  const clock=useRef(revealSeconds);
  const lastReveal=useRef<number|null>(null);
  const startedAt=useRef(0);
  useFrame(()=>{
    const now=performance.now();
    if(lastReveal.current!==reveal){
      lastReveal.current=reveal;
      startedAt.current=now;
      onReveal?.(reveal);
    }
    const elapsed=(now-startedAt.current)/1000;
    clock.current=reducedMotion?revealSeconds:Math.min(revealSeconds,elapsed);
  },-3);
  return <><OfficeCamera angle={angle} clock={clock}/><Office lowPower={lowPower} clock={clock}/>
    <Actors engine={engine} agents={agents} clock={clock}/></>;
}

function OfficeCamera({angle,clock}:{angle:Projection['angle'];clock:RevealClock}) {
  const camera = useThree(state=>state.camera);
  const view = useRef(new Vector3(...CAMS.Portal.look));
  useFrame((_,dt)=>moveCamera(camera,view.current,angle,dt,clock.current));
  return null;
}
function moveCamera(camera:Camera, point:Vector3, angle:Projection['angle'], dt:number, time:number){
    const desired=CAMS[angle], alpha=1-Math.exp(-dt*3.1);
    camera.position.x+=(desired.pos[0]-camera.position.x)*alpha;
    camera.position.y+=(desired.pos[1]-camera.position.y)*alpha;
    camera.position.z+=(desired.pos[2]-camera.position.z)*alpha;
    point.x+=(desired.look[0]-point.x)*alpha;
    point.y+=(desired.look[1]-point.y)*alpha;
    point.z+=(desired.look[2]-point.z)*alpha;
    camera.lookAt(point);
    if(camera instanceof PerspectiveCamera){
      const zoom=.89+.11*fade(time,.39,1.78);
      if(camera.zoom!==zoom){camera.zoom=zoom;camera.updateProjectionMatrix();}
    }
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
function Desk({x,clock,wake}:{x:number;clock:RevealClock;wake:number}) {
  const screen=useRef<MeshStandardMaterial>(null), lamp=useRef<MeshStandardMaterial>(null);
  const glow=useRef<PointLight>(null), markings=useRef<Group>(null);
  useFrame(()=>{
    const time=clock.current;
    const lampLevel=fade(time,wake,wake+.18);
    const rise=fade(time,wake+.19,wake+.48);
    const flicker=1-.22*Math.sin((time-wake)*65)**2*(1-fade(time,wake+.30,wake+.53));
    if(lamp.current)lamp.current.emissiveIntensity=2.4*lampLevel;
    if(glow.current)glow.current.intensity=1.6*lampLevel;
    if(screen.current)screen.current.emissiveIntensity=.92*rise*flicker;
    if(markings.current)markings.current.visible=rise>.45;
  });
  return <group position={[x,0,-2.25]}>
    <Block p={[0,.87,0]} s={[2.15,.09,1.05]} c="#b9b9b9"/>
    {[-.91,.91].flatMap(dx=>[-.38,.38].map(dz=><Block key={dx+':'+dz} p={[dx,.43,dz]} s={[.055,.83,.055]} c="#343434"/>))}
    <Block p={[.15,1.27,-.25]} s={[.96,.54,.055]} c="#212121"/>
    <mesh position={[.15,1.27,-.218]}><planeGeometry args={[.87,.45]}/><meshStandardMaterial ref={screen} color="#242424" emissive="#b8b8b8" emissiveIntensity={0}/></mesh>
    <group ref={markings}>{[0,1,2,3,4].map((i)=><Block key={i} p={[.029+(i%2)*.08,1.40-i*.064,-.216]} s={[.5-(i%3)*.09,.011,.005]} c={i===0?'#131313':'#4a4a4a'} cast={false}/>)}</group>
    <Block p={[-.79,.93,-.23]} s={[.23,.045,.19]} c="#343434"/>
    <Block p={[-.79,1.12,-.26]} s={[.035,.35,.036]} c="#545454"/>
    <Block p={[-.68,1.30,-.25]} s={[.27,.065,.16]} c="#3b3b3b"/>
    <mesh position={[-.67,1.261,-.25]}><boxGeometry args={[.22,.012,.13]}/>
      <meshStandardMaterial ref={lamp} color="#5a5a5a" emissive="#efefef" emissiveIntensity={0}/>
    </mesh>
    <pointLight ref={glow} position={[-.67,1.235,-.24]} intensity={0} distance={1.45}/>
    <Block p={[.15,1,-.25]} s={[.045,.21,.06]} c="#363636"/><Block p={[.15,.925,-.23]} s={[.3,.02,.19]} c="#2b2b2b"/>
    <Block p={[.12,.93,.175]} s={[.44,.025,.13]} c="#4a4a4a"/><Block p={[.51,.93,.2]} s={[.075,.03,.11]} c="#444"/>
    <Block p={[-.61,.96,-.06]} s={[.26,.075,.195]} c="#737373"/><Block p={[-.61,1.006,-.055]} s={[.24,.015,.17]} c="#dedede"/>
    <Block p={[0,.48,.86]} s={[.49,.07,.37]} c="#555"/><Block p={[0,.73,1.025]} s={[.48,.42,.06]} c="#505050"/>
    <Block p={[0,.23,.89]} s={[.09,.45,.09]} c="#383838"/><Block p={[0,.05,.89]} s={[.43,.05,.32]} c="#383838"/>
  </group>;
}
function Plant({x,y=0,z}:{x:number;y?:number;z:number}) {
  return <group position={[x,y,z]}>
    <mesh position={[0,.13,0]} castShadow><cylinderGeometry args={[.16,.115,.26,10]}/><meshStandardMaterial color="#686868"/></mesh>
    {[0,1,2,3,4,5].map(i=><mesh key={i} position={[Math.cos(i*2.4)*.125,.33+i%3*.08,Math.sin(i*2.4)*.125]}
      rotation={[Math.cos(i*2.4)*.65,0,Math.sin(i*2.4)*.72]} scale={[.095,.26,.07]} castShadow>
      <icosahedronGeometry args={[1,1]}/><meshStandardMaterial color={i%2?'#545454':'#393939'} roughness={1}/></mesh>)}
  </group>;
}
function Office({lowPower,clock}:{lowPower:boolean;clock:RevealClock}) {
  return <>
    <directionalLight position={[-2,5,3.4]} intensity={2.2} castShadow={!lowPower}
      shadow-mapSize={lowPower?[512,512]:[1024,1024]} shadow-camera-left={-7} shadow-camera-right={7}
      shadow-camera-top={6} shadow-camera-bottom={-7} shadow-normalBias={.035}/>
    <OfficeLight clock={clock}/>
    <Block p={[0,-.12,-.15]} s={[11.8,.24,8.7]} c="#888" cast={false}/>
    <Block p={[0,1.92,-4.34]} s={[12,3.84,.22]} c="#8c8c8" cast={false}/>
    <Block p={[-5.89,1.92,-1.37]} s={[.18,3.84,6]} c="#636363" cast={false}/>
    <Block p={[5.89,1.92,-1.37]} s={[.18,3.84,6]} c="#505050" cast={false}/>
    {Array.from({length:19},(_,i)=><Block key={i} p={[-5.7+i*.63,.004,-.13]} s={[.011,.008,8.45]} c="#646464" cast={false}/>)}
    {[-3.2,1.7,4.25].map(z=><Block key={z} p={[0,.004,z]} s={[11.78,.008,.012]} c="#686868" cast={false}/>)}
    <Block p={[0,.095,-4.19]} s={[11.8,.19,.075]} c="#505050"/>
    <Block p={[0,3.75,-3.23]} s={[11.8,.21,2.1]} c="#686868" cast={false}/>
    {[-3,0,3].map(x=><group key={x}>
      <Block p={[x,3.61,-2.71]} s={[1.95,.06,.26]} c="#404040" cast={false}/>
      <mesh position={[x,3.57,-2.71]}><boxGeometry args={[1.83,.024,.19]}/><meshStandardMaterial color="#e6e6e6" emissive="white" emissiveIntensity={1.05}/></mesh>
    </group>)}
    {[-3.3,-1.64,0,1.64].map((x,i)=><group key={x} position={[x,2.47,-4.16]}>
      <Block p={[0,0,0]} s={[1.58,1.6,.08]} c="#303030"/>
      <Block p={[0,0,.052]} s={[1.48,1.49,.03]} c={i%2?'#bababa':'#c7c7c7'}/>
      <Block p={[0,-.04,.074]} s={[1.48,.026,.014]} c="#555"/>
      {[0,1,2,3,4,5,6].map(j=><Block key={j} p={[-.64+j*.205,-.58+(j*7%5)*.05,.071]} s={[.14,.44+(j*7%5)*.10,.016]} c={j%2?'#868686':'#959595'} cast={false}/>)}
    </group>)}
    <group position={[4.24,0,-4.10]}>
      <Block p={[0,1.3,0]} s={[1.39,2.60,.14]} c="#303030"/>
      <Block p={[0,1.245,.09]} s={[1.19,2.44,.07]} c="#656565"/>
      <Block p={[0,1.76,.135]} s={[.31,.63,.022]} c="#a2a2a2"/>
      <Block p={[-.43,1.13,.15]} s={[.18,.05,.085]} c="#cdcdcd"/>
      <Block p={[0,2.83,.03]} s={[.59,.135,.075]} c="#303030"/>
      <Block p={[0,2.83,.079]} s={[.30,.025,.018]} c="#bebebe"/>
    </group>
    {[-2.8,0,2.8].map((x,index)=><Desk key={x} x={x} clock={clock} wake={.65+index*.30}/>)}
    <group position={[-4.97,0,1.02]}>
      <Block p={[0,.92,0]} s={[.55,1.84,1.45]} c="#535353"/>
      {[.36,.75,1.14,1.53].map(y=><group key={y}>
        <Block p={[.295,y,0]} s={[.055,.36,1.36]} c="#757575"/>
        <Block p={[.34,y,.07]} s={[.046,.045,.29]} c="#303030"/>
      </group>)}
    </group>
    <mesh position={[.18,.81,2.53]} castShadow receiveShadow><cylinderGeometry args={[.69,.69,.085,32]}/><meshStandardMaterial color="#a1a1a1"/></mesh>
    <mesh position={[.18,.41,2.53]} castShadow><cylinderGeometry args={[.095,.26,.81,12]}/><meshStandardMaterial color="#4a4a4a"/></mesh>
    <Block p={[.26,.879,2.52]} s={[.28,.042,.20]} c="#494949"/>
    <Plant x={-5.08} z={-2.65}/><Plant x={4.98} z={-1.90}/><Plant x={-3.75} z={-2.6} y={.92}/>
  </>;
}

function OfficeLight({clock}:{clock:RevealClock}) {
  const light=useRef<PointLight>(null);
  useFrame(()=>{if(light.current)light.current.intensity=4+18*fade(clock.current,.41,1.61);});
  return <pointLight ref={light} position={[.2,3.1,-1]} intensity={4} distance={14} decay={2}/>;
}

function Actors({engine,agents,clock}:{engine:RefObject<Engine|null>;agents:Agent[];clock:RevealClock}) {
  useFrame((_,dt)=>{
    if(clock.current>=revealSeconds)engine.current?.tick(dt);
  },-1);
  return <>{agents.map((agent,index)=><Actor key={agent.id} agent={agent} engine={engine} clock={clock} glanceAt={.73+index*.115}/>)}</>;
}
function Actor({agent,engine,clock,glanceAt}:{agent:Agent;engine:RefObject<Engine|null>;clock:RevealClock;glanceAt:number}) {
  const head=useRef<Group>(null);
  const root=useRef<Group>(null), torso=useRef<Group>(null), left=useRef<Group>(null), right=useRef<Group>(null),
    leftLeg=useRef<Group>(null),rightLeg=useRef<Group>(null),rib=useRef<Group>(null);
  useFrame(()=>{
    const p=engine.current?.actors.get(agent.id)?.pose;
    if(!p||!head.current||!root.current||!torso.current||!left.current||!right.current||!leftLeg.current||!rightLeg.current||!rib.current)return;
    const swing=p.action==='walk'?Math.sin(p.step)*.55:0;
    const time=clock.current;
    const glance=fade(time,glanceAt,glanceAt+.29)*(1-fade(time,1.58,2.04));
    const towardOpening=Math.atan2(-p.x,8-p.z)-p.yaw;
    const look=Math.atan2(Math.sin(towardOpening),Math.cos(towardOpening))*glance;
    root.current.position.set(p.x,0,p.z);root.current.rotation.y=p.yaw+look*.75;
    head.current.rotation.y=look*.25;
    head.current.rotation.x=-.08*glance;
    torso.current.position.y=.69-p.sit*.19 + (p.action==='walk' ? Math.abs(Math.sin(p.step))*.033 : Math.sin(p.time*2.4)*.011);
    rib.current.rotation.x=p.action==='inspect'?.24 : p.sit*.12;
    left.current.rotation.x=-swing-p.sit*.89;right.current.rotation.x=swing-p.sit*.92+(p.action==='talk'?-.45-Math.sin(p.time*5)*.38:0)+(p.action==='work'?Math.sin(p.time*13)*.10:0);
    leftLeg.current.rotation.x=swing-p.sit*1.17;rightLeg.current.rotation.x=-swing-p.sit*1.17;
  });
  return <group ref={root}><group ref={torso}><group ref={rib}>
    <mesh position={[0,.306,0]} castShadow><capsuleGeometry args={[.19,.32,4,12]}/><meshStandardMaterial color={agent.tone}/></mesh>
    <group ref={head} position={[0,.79,0]}>
      <mesh castShadow><sphereGeometry args={[.172,16,12]}/><meshStandardMaterial color="#c6c6c6"/></mesh>
      <mesh position={[0,.003,.13]} scale={[.137,.069,.07]}><sphereGeometry args={[1,14,10]}/><meshStandardMaterial color="#252525"/></mesh>
      <Block p={[0,.012,.191]} s={[.12,.016,.012]} c="#bdbdbd" cast={false}/>
    </group>
    <Block p={[0,.409,.174]} s={[.093,.035,.018]} c="#d7d7d7" cast={false}/>
    <group ref={left} position={[-.23,.51,0]}><Arm tone={agent.tone}/></group>
    <group ref={right} position={[.23,.51,0]}><Arm tone={agent.tone}/></group>
  </group>
    <group ref={leftLeg} position={[-.097,0,0]}><Leg/></group>
    <group ref={rightLeg} position={[.097,0,0]}><Leg/></group>
  </group></group>;
}

function Arm({tone}:{tone:string}){
  return <><mesh position={[0,-.205,.025]} castShadow><capsuleGeometry args={[.052,.30,3,8]}/><meshStandardMaterial color={tone}/></mesh>
    <mesh position={[0,-.403,.028]}><sphereGeometry args={[.049,10,8]}/><meshStandardMaterial color="#bababa"/></mesh></>;
}
function Leg(){
  return <><mesh position={[0,-.19,0]} castShadow><capsuleGeometry args={[.073,.28,3,8]}/><meshStandardMaterial color="#555"/></mesh>
    <mesh position={[0,-.49,.017]} castShadow><capsuleGeometry args={[.06,.24,3,8]}/><meshStandardMaterial color="#626262"/></mesh>
    <Block p={[0,-.64,.079]} s={[.145,.094,.24]} c="#3b3b3b"/></>;
}
function Study({scene,simulated,selected,select,diff,cloud}:{scene:Scene;simulated:boolean;selected?:string;select?:(id:string)=>void;diff:Delta[];cloud:boolean}) {
  const [w,h]=scene.wall;
  const factor=Math.min(1,7/Math.max(w,h));
  const coord=(card:Card):XYZ=>[ (card.x-(isNormalized(scene)?.5:w/2))*(isNormalized(scene)?w:1), card.y*(isNormalized(scene)?h:1), simulated?-.24:card.d/2+.02 ];
  const moved=diff.filter(row=>row.kind==='moved'||row.kind==='missing');
  return <group scale={factor}>
    <gridHelper args={[22,44,'#484848','#2a2a2a']}/>
    <Block p={[0,h/2,-.10-(simulated?1:0)]} s={[w,h,.12]} c="#6e6e6e"/>
    {simulated && <>
      <Block p={[0,-.086,.45]} s={[w,.17,3.3]} c="#666"/>
      <Block p={[-w/2,h/2,-.54]} s={[.13,h,1.05]} c="#525252"/>
      <Block p={[-.27,.81,-.25]} s={[3.98,.10,.88]} c="#a7a7a7"/>
      {[-2.12,1.55].map(x=><Block key={x} p={[x,.4,-.03]} s={[.09,.8,.09]} c="#4b4b4b"/>)}
      <Block p={[-.15,2.12,-.993]} s={[1.07,.74,.045]} c="#343434"/><Block p={[-.15,2.12,-.967]} s={[.96,.63,.022]} c="#aaa"/>
      <Block p={[1.79,1.83,-.986]} s={[.94,1.21,.043]} c="#383838"/><Block p={[1.79,1.83,-.958]} s={[.84,1.10,.033]} c="#bababa"/>
      <Block p={[1.79,1.83,-.938]} s={[.029,1.1,.018]} c="#626262"/><Block p={[1.79,1.83,-.938]} s={[.84,.025,.018]} c="#626262"/>
    </>}
    {moved.map(row=>row.before&&<mesh key={row.id} position={coord(row.before)} rotation={[0,0,row.before.angle]}>
      <boxGeometry args={[row.before.w,safe(row.before.h),row.before.d]}/><meshBasicMaterial wireframe color="#e6e6e6" transparent opacity={.68}/>
    </mesh>)}
    {scene.objects.map(card=><group key={card.id} position={coord(card)} rotation={[0,0,card.angle]}
      onClick={event=>{event.stopPropagation();select?.(card.id);}}>
      <StudyObject card={card} simulated={simulated} emphasized={selected===card.id||diff.some(row=>row.id===card.id&&row.kind!=='unchanged')}/>
    </group>)}
    {cloud&&simulated&&<SamplePoints width={w} height={h}/>}
  </group>;
}
const safe=(n:number)=>Math.max(n,.012);
function StudyObject({card,simulated,emphasized}:{card:Card;simulated:boolean;emphasized:boolean}) {
  const color=emphasized?'#f2f2f2':'#a6a6a6';
  if(!simulated)return <Block p={[0,0,0]} s={[card.w,safe(card.h),card.d]} c={color}/>;
  if(card.id==='plant')return <Plant x={0} z={0} y={-.38}/>;
  if(card.id==='mug')return <group>
    <mesh><cylinderGeometry args={[.068,.058,.15,22]}/><meshStandardMaterial color={color}/></mesh>
    <mesh position={[0,.076,0]} rotation={[-Math.PI/2,0,0]}><circleGeometry args={[.052,22]}/><meshStandardMaterial color="#444"/></mesh>
    <mesh position={[.083,.004,0]}><torusGeometry args={[.035,.01,9,16]}/><meshStandardMaterial color={color}/></mesh>
  </group>;
  if(card.id==='task-lamp')return <group>
    <Block p={[0,-.42,0]} s={[.26,.034,.23]} c={color}/>
    <mesh position={[0,-.20,0]} rotation={[0,0,-.28]}><cylinderGeometry args={[.016,.016,.44,11]}/><meshStandardMaterial color="#343434"/></mesh>
    <mesh position={[.10,.033,0]} rotation={[0,0,-.55]}><cylinderGeometry args={[.064,.126,.12,18]}/><meshStandardMaterial color={color}/></mesh>
  </group>;
  return <Block p={[0,-.09,0]} s={[card.w,card.h,card.d]} c={color}/>;
}
function SamplePoints({width,height}:{width:number;height:number}) {
  const bits=new Float32Array(48*28*3);
  for(let i=0;i<48*28;i++){
    bits[i*3]=(i%48/47-.5)*width+.025*Math.sin(i*9);bits[i*3+1]=Math.floor(i/48)/27*height;
    bits[i*3+2]=-1.025+.04*Math.sin(i*13);
  }
  return <points><bufferGeometry><bufferAttribute attach="attributes-position" args={[bits,3]}/></bufferGeometry>
    <pointsMaterial size={.022} color="#d0d0d0" transparent opacity={.72}/></points>;
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
