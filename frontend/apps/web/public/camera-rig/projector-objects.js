import {Box3, BoxGeometry, ConeGeometry, CylinderGeometry, Group, Mesh, MeshStandardMaterial, Plane, Raycaster, SphereGeometry, Vector2, Vector3} from 'three';

function roundedBox() {
  const geometry = new BoxGeometry(1, 1, 1, 10, 10, 10);
  const positions = geometry.getAttribute('position');
  const normals = geometry.getAttribute('normal');
  const radius = .16;
  const inner = .5 - radius;
  const point = new Vector3(), center = new Vector3(), normal = new Vector3();
  for (let i=0; i<positions.count; i++) {
    point.fromBufferAttribute(positions, i);
    center.copy(point).clampScalar(-inner, inner);
    normal.copy(point).sub(center).normalize();
    point.copy(center).addScaledVector(normal, radius);
    positions.setXYZ(i, point.x, point.y, point.z);
    normals.setXYZ(i, normal.x, normal.y, normal.z);
  }
  return geometry;
}

const surfaces = {
  paint: {roughness:.49, metalness:0}, wood: {roughness:.64, metalness:0},
  fabric: {roughness:.94, metalness:0}, metal: {roughness:.38, metalness:.42},
};

/** @param {Group} layer */
export function clearProjectedObjects(layer) {
  layer.traverse(node => {
    if (node instanceof Mesh) {
      node.geometry.dispose();
      node.material.dispose();
    }
  });
  layer.clear();
}

/**
 * @param {Group} layer
 * @param {import('../../app/world/domain').ProjectedObject[]} objects
 * @param {{x:number,y:number,z:number,scale:number}} anchor
 */
export function drawProjectedObjects(layer, objects, anchor) {
  const existing = new Map(layer.children.map(group => [group.userData.id, group]));
  const offsets = {left:0, center:0, right:0};
  for (const object of objects) {
    const design = JSON.stringify(object.parts);
    let group = existing.get(object.id);
    existing.delete(object.id);
    if (group && group.userData.design !== design) {
      clearProjectedObjects(group);
      group.removeFromParent();
      group = undefined;
    }
    if (!group) {
      group = new Group();
      group.userData.id = object.id;
      group.userData.design = design;
      for (const part of object.parts) {
        const geometry = part.shape === 'sphere' ? new SphereGeometry(.5, 16, 12)
          : part.shape === 'cylinder' ? new CylinderGeometry(.5, .5, 1, 16)
          : part.shape === 'cone' ? new ConeGeometry(.5, 1, 16)
          : part.shape === 'shade' ? new CylinderGeometry(.29, .5, 1, 24)
          : part.shape === 'rounded-box' ? roundedBox() : new BoxGeometry(1, 1, 1);
        const mesh = new Mesh(geometry, new MeshStandardMaterial({color:part.color, ...surfaces[part.material??'paint']}));
        mesh.position.fromArray(part.position);
        mesh.scale.fromArray(part.size);
        mesh.rotation.set(...part.rotation.map(degrees => degrees * Math.PI / 180));
        group.add(mesh);
      }
      group.userData.bounds = new Box3().setFromObject(group);
      layer.add(group);
    }
    group.name = object.name;
    const bounds = group.userData.bounds;
    const center = bounds.getCenter(new Vector3());
    const size = bounds.getSize(new Vector3());
    const scale = object.height * anchor.scale / Math.max(size.y, size.x / 2, size.z / 2, .015);
    const index = offsets[object.placement]++;
    const x = object.placement === 'left' ? -1 : object.placement === 'right' ? 1 : 0;
    const [dx,dy,dz] = object.offset ?? [0,0,0];
    group.scale.setScalar(scale);
    const base = new Vector3(anchor.x+x*anchor.scale-center.x*scale,anchor.y-bounds.min.y*scale,
      anchor.z-index*.8*anchor.scale-center.z*scale);
    group.userData.base = base;
    group.userData.unit = anchor.scale;
    group.position.set(base.x+dx*anchor.scale,base.y+dy*anchor.scale,base.z+dz*anchor.scale);
    group.updateWorldMatrix(true, true);
  }
  for (const group of existing.values()) {
    clearProjectedObjects(group);
    group.removeFromParent();
  }
}

/**
 * @param {{canvas:HTMLCanvasElement; camera:import('three').Camera; layer:Group; editable:()=>string|undefined;
 *  pauseOrbit:(paused:boolean)=>void; moved:(id:string,offset:[number,number,number])=>void}} options
 */
export function bindProjectedObjectDrag({canvas,camera,layer,editable,pauseOrbit,moved}) {
  const pointer=new Vector2(), raycast=new Raycaster(), plane=new Plane(), intersection=new Vector3();
  const up=new Vector3(0,1,0);
  let drag=null, pending=null, frame=0;

  function ray(event){
    const box=canvas.getBoundingClientRect();
    pointer.set(2*(event.clientX-box.left)/box.width-1,1-2*(event.clientY-box.top)/box.height);
    camera.updateWorldMatrix(true,false);
    raycast.setFromCamera(pointer,camera);
  }

  function hit(event){
    const id=editable();
    if(!id)return;
    const group=layer.children.find(item=>item.userData.id===id);
    if(!group)return;
    ray(event);
    const intersection=raycast.intersectObject(group,true)[0];
    return intersection?{group,point:intersection.point}:undefined;
  }

  function flush(){
    frame=0;
    if(pending){moved(pending.id,pending.offset);pending=null;}
  }

  function start(event){
    if(drag||event.button!==0||!event.isPrimary)return;
    const picked=hit(event);
    if(!picked)return;
    const {group,point}=picked;
    if(!event.shiftKey&&Math.abs(raycast.ray.direction.y)<1e-5)return;
    plane.setFromNormalAndCoplanarPoint(up,point);
    event.preventDefault();event.stopImmediatePropagation();
    const distance=camera.position.distanceTo(group.position);
    const fov='fov' in camera&&typeof camera.fov==='number'?camera.fov:45;
    drag={id:group.userData.id,group,pointer:event.pointerId,from:group.position.clone(),point,
      vertical:event.shiftKey,startY:event.clientY,perPixel:2*distance*Math.tan(fov*Math.PI/360)/Math.max(1,canvas.clientHeight)};
    pauseOrbit(true);canvas.setPointerCapture(event.pointerId);canvas.style.cursor='grabbing';
  }

  function move(event){
    if(!drag){canvas.style.cursor=hit(event)?'grab':'';return;}
    if(drag.pointer!==event.pointerId)return;
    if(editable()!==drag.id||!drag.group.parent){end(event);return;}
    event.preventDefault();event.stopImmediatePropagation();
    let next;
    if(drag.vertical){
      next=drag.from.clone();next.y+=(drag.startY-event.clientY)*drag.perPixel;
    }else{
      ray(event);
      if(!raycast.ray.intersectPlane(plane,intersection))return;
      next=drag.from.clone().add(intersection.clone().sub(drag.point));
    }
    const {base,unit}=drag.group.userData;
    const values=next.sub(base).divideScalar(unit).clampScalar(-100,100);
    const offset=/** @type {[number,number,number]} */(values.toArray().map(value=>Math.round(value*1000)/1000));
    drag.group.position.copy(base).add(new Vector3(...offset).multiplyScalar(unit));
    pending={id:drag.id,offset};
    if(!frame)frame=requestAnimationFrame(flush);
  }

  function end(event){
    if(!drag||drag.pointer!==event.pointerId)return;
    const pointerId=drag.pointer;
    drag=null;
    if(canvas.hasPointerCapture(pointerId))canvas.releasePointerCapture(pointerId);
    pauseOrbit(false);canvas.style.cursor='';
    if(frame)cancelAnimationFrame(frame);
    flush();
  }

  canvas.addEventListener('pointerdown',start,true);
  canvas.addEventListener('pointermove',move,true);
  for(const event of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(event,end,true);
  return ()=>{
    if(drag){pauseOrbit(false);if(canvas.hasPointerCapture(drag.pointer))canvas.releasePointerCapture(drag.pointer);}
    if(frame)cancelAnimationFrame(frame);
    canvas.style.cursor='';
    canvas.removeEventListener('pointerdown',start,true);
    canvas.removeEventListener('pointermove',move,true);
    for(const event of ['pointerup','pointercancel','lostpointercapture'])canvas.removeEventListener(event,end,true);
  };
}
