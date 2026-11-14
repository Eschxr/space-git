import type {Object3D} from 'three';
import type {Card,Scene} from '../../../../packages/protocol/types';

export function download(data:Blob,name:string){
 const url=URL.createObjectURL(data), a=document.createElement('a');
 a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);
}
function validScene(raw:unknown):Scene{
 if(!raw||typeof raw!=='object')throw Error('The file has no SpaceGit scene.');
 const s=raw as Scene;
 const finite=(n:unknown)=>typeof n==='number'&&Number.isFinite(n);
 const size=(n:number)=>finite(n)&&n>0&&n<=30;
 const isId=(s:unknown)=>typeof s==='string'&&/^[\w-]{1,64}$/.test(s);
 const isName=(s:unknown)=>typeof s==='string'&&s.length>0&&s.length<=80;
 if(s.version!==1||!isId(s.id)||!isName(s.name)||s.frame!=='wall-world-meters'||!Array.isArray(s.wall)||s.wall.length!==2||!s.wall.every(size)||!Array.isArray(s.objects)||s.objects.length>40)throw Error('Unsupported scene format.');
 const cards=s.objects.map((o:Card)=>{
  if(!o||!isId(o.id)||!isName(o.name)||!Number.isInteger(o.marker)||o.marker<4||o.marker>249||![o.x,o.y,o.angle].every(finite)||Math.abs(o.angle)>6.284||![o.w,o.h,o.d].every(size))throw Error('Invalid object dimensions or identity.');
  const {id,marker,name,x,y,angle,w,h,d}=o;return {id,marker,name,x,y,angle,w,h,d};
 });
 if(new Set(cards.map(c=>c.id)).size!==cards.length||new Set(cards.map(c=>c.marker)).size!==cards.length)throw Error('Scene contains duplicate object identities.');
 let constraints:Scene['constraints']=undefined;
 if(s.constraints){
  const c=s.constraints;
  if(!finite(c.clearance_mm)||c.clearance_mm<0||c.clearance_mm>250||!Array.isArray(c.keep_out)||c.keep_out.length>12)throw Error('Invalid placement rules.');
  const keep=c.keep_out.map(z=>{
   if(!z||!isId(z.id)||!isName(z.name)||z.name.length>64||![z.x,z.y].every(finite)||![z.w,z.h].every(size))throw Error('Invalid keep-out area.');
   return {id:z.id,name:z.name,x:z.x,y:z.y,w:z.w,h:z.h};
  });
  if(new Set(keep.map(z=>z.id)).size!==keep.length)throw Error('Duplicate keep-out area.');
  constraints={clearance_mm:c.clearance_mm,keep_out:keep};
 }
 return {id:s.id,name:s.name,version:1,frame:s.frame,wall:s.wall,objects:cards,...(constraints?{constraints}:{})};
}
export async function exportGLB(raw:Scene){
 const scene=validScene(raw);
 const [{BoxGeometry,Group,Mesh,MeshStandardMaterial},{GLTFExporter}]=await Promise.all([import('three'),import('three/addons/exporters/GLTFExporter.js')]);
 const root=new Group();root.name='SpaceGit';root.userData={spacegit:scene};
 const wallMaterial=new MeshStandardMaterial({color:'#294454'}),cardMaterial=new MeshStandardMaterial({color:'#486e80'});
 const mesh=(name:string,w:number,h:number,d:number,material:typeof wallMaterial)=>{
  const m=new Mesh(new BoxGeometry(w,h,d),material);m.name=name;root.add(m);return m;
 };
 const wall=mesh('Metric wall',...scene.wall,.05,wallMaterial);
 wall.position.set(scene.wall[0]/2,scene.wall[1]/2,-.025);
 for(const o of scene.objects){
  const card=mesh(o.name,o.w,o.h,o.d,cardMaterial);
  card.userData={stable_id:o.id,marker_id:o.marker};
  card.position.set(o.x,o.y,o.d/2);card.rotation.z=o.angle;
 }
 try{
  const result=await new GLTFExporter().parseAsync(root,{binary:true});
  download(new Blob([result as ArrayBuffer],{type:'model/gltf-binary'}),'spacegit-wall.glb');
 }finally{
  for(const node of root.children)if(node instanceof Mesh)node.geometry.dispose();
  wallMaterial.dispose();cardMaterial.dispose();
 }
}
export async function importModel(file:File):Promise<{scene?:Scene;mesh?:Object3D}>{
 if(file.size>64*1024*1024)throw Error('Choose a file under 64 MB.');
 if(file.name.toLowerCase().endsWith('.json')&&file.size>1024*1024)throw Error('Scene JSON exceeds 1 MB.');
 if(file.name.toLowerCase().endsWith('.json'))return {scene:validScene(JSON.parse(await file.text()))};
 return parseModel(await file.arrayBuffer());
}
function rasterSize(bytes:Uint8Array,mime:string){
 const v=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
 if(mime==='image/png'&&bytes.length>=24&&v.getUint32(0)===0x89504e47&&v.getUint32(12)===0x49484452)return [v.getUint32(16),v.getUint32(20)];
 if(mime==='image/jpeg'&&bytes.length>=8&&v.getUint16(0)===0xffd8){
  for(let i=2;i+9<bytes.length;){
   if(bytes[i++]!==255)break;
   const mark=bytes[i++],len=v.getUint16(i);
   if(len<2||i+len>bytes.length)break;
   if([0xc0,0xc1,0xc2].includes(mark)&&len>=8)return [v.getUint16(i+5),v.getUint16(i+3)];
   if(mark===0xda)break;
   i+=len;
  }
 }
 throw Error('GLB contains an invalid embedded image.');
}
export async function parseModel(buf:ArrayBuffer):Promise<{scene?:Scene;mesh?:Object3D}>{
 if(buf.byteLength>64*1024*1024)throw Error('Model exceeds 64 MB.');
 const v=new DataView(buf);
 if(v.byteLength<20||v.getUint32(0,true)!==0x46546c67||v.getUint32(4,true)!==2||v.getUint32(8,true)!==v.byteLength||v.getUint32(16,true)!==0x4e4f534a)throw Error('Choose a valid glTF 2.0 binary file.');
 const bytes=v.getUint32(12,true);
 if(bytes>1024*1024||20+bytes>buf.byteLength)throw Error('Model metadata is too large or incomplete.');
 const doc=JSON.parse(new TextDecoder().decode(new Uint8Array(buf,20,bytes)));
 const embedded=doc.nodes?.find((n:{extras?:{spacegit?:unknown}})=>n.extras?.spacegit)?.extras?.spacegit;
 if(embedded)return {scene:validScene(embedded)};
 // Only bounded self-contained assets; GLTFLoader cannot resolve outside resources here.
 const start=20+bytes+8;
 if(start>v.byteLength||v.getUint32(start-4,true)!==0x004e4942||v.getUint32(start-8,true)!==v.byteLength-start||
  doc.extensionsUsed?.some((e:string)=>!['KHR_materials_unlit','KHR_texture_transform'].includes(e))||
  !Array.isArray(doc.buffers)||doc.buffers.length!==1||'uri' in doc.buffers[0]||doc.nodes?.length>200||doc.images?.length>8||
  doc.accessors?.length>160||doc.accessors?.some((a:{count:number;sparse?:unknown})=>!Number.isInteger(a.count)||a.count<1||a.count>1500000||a.sparse))throw Error('GLB must be bounded, self-contained and use supported geometry.');
 let pixels=0;
 for(const im of doc.images??[]){
  const b=doc.bufferViews?.[im.bufferView],offset=b?.byteOffset??0,n=b?.byteLength;
  if('uri' in im||!b||b.buffer!==0||!Number.isInteger(offset)||!Number.isInteger(n)||offset<0||n<1||start+offset+n>v.byteLength)throw Error('GLB images must be embedded in the binary chunk.');
  const [w,h]=rasterSize(new Uint8Array(buf,start+offset,n),im.mimeType);
  pixels+=w*h;
  if(!w||!h||Math.max(w,h)>8192||pixels>40_000_000)throw Error('Embedded texture exceeds the image limit.');
 }
 const {GLTFLoader}=await import('three/addons/loaders/GLTFLoader.js');
 const asset=await new GLTFLoader().parseAsync(buf,'');
 return {mesh:asset.scene};
}
