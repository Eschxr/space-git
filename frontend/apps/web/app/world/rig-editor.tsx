'use client';

import {useEffect,useState} from 'react';
import {CAMERAS, type CameraDevice, type CameraSource, type RigSettings} from './domain';
import type {Edge} from './edge';

export function RigEditor({edge, settings, disabled, save}:{
  edge:Edge; settings:RigSettings; disabled:boolean; save:(settings:RigSettings)=>void;
}) {
  const [draft,setDraft]=useState(settings);
  const [devices,setDevices]=useState<CameraDevice[]>([]);
  const [deviceStatus,setDeviceStatus]=useState('Finding cameras…');
  const [scan,setScan]=useState(0);

  useEffect(()=>{
    let cancelled=false;
    void edge.devices().then(({cameras})=>{
      if(cancelled)return;
      setDevices(cameras.filter(camera=>camera.index>=0&&camera.index<=15));
      setDeviceStatus(cameras.length?'':'No camera devices detected.');
    }).catch(()=>{
      if(!cancelled)setDeviceStatus('Could not list cameras. Check the local edge and refresh.');
    });
    return ()=>{cancelled=true;};
  },[edge,scan]);

  const assigned=draft.sources.filter(source=>source!==null);
  const duplicate=assigned.length!==new Set(assigned).size;
  const dirty=draft.sources.some((source,index)=>source!==settings.sources[index])
    || draft.order.some((id,index)=>id!==settings.order[index]);
  function move(index:number, offset:number) {
    const order=[...draft.order];
    const destination=index+offset;
    [order[index],order[destination]]=[order[destination],order[index]];
    setDraft({...draft,order});
  }

  return <details className="nw-rig-editor">
    <summary>Edit camera sequence</summary>
    <p>Assign each USB device to its physical view. Move a view up or down to change its position in the preview grid.</p>
    <form onSubmit={event=>{event.preventDefault();void save(draft);}}>
      <ol>
        {draft.order.map((id,index)=>{
          const camera=CAMERAS.find(camera=>camera.id===id)!;
          const source=draft.sources[id-1];
          const detected=devices.some(device=>device.index===source);
          return <li key={id}>
            <label>
              <span>Camera {id} · {camera.direction}</span>
              <select className="nw-field" disabled={disabled} value={source??''} onChange={event=>{
                const value=event.target.value;
                const next:CameraSource=value==='primary'?'primary':value===''?null:Number(value);
                const sources=[...draft.sources];
                sources[id-1]=next;
                setDraft({...draft,sources});
              }}>
                <option value="">Unassigned</option>
                <option value="primary">Tracking camera from Setup</option>
                {typeof source==='number'&&!detected&&<option value={source}>Device {source} (not detected)</option>}
                {devices.map(device=><option key={device.index} value={device.index}>{device.index} · {device.label}</option>)}
              </select>
            </label>
            <div className="nw-order-buttons">
              <button type="button" className="nw-btn nw-tiny" aria-label={'Move camera '+id+' earlier'} disabled={disabled||index===0} onClick={()=>move(index,-1)}>↑</button>
              <button type="button" className="nw-btn nw-tiny" aria-label={'Move camera '+id+' later'} disabled={disabled||index===3} onClick={()=>move(index,1)}>↓</button>
            </div>
          </li>;
        })}
      </ol>
      {duplicate&&<p role="alert">Assign each device to only one camera.</p>}
      {deviceStatus&&<p role="status">{deviceStatus}</p>}
      <div className="nw-actions">
        <button className="nw-btn nw-primary nw-tiny" disabled={disabled||!dirty||duplicate}>Save sequence</button>
        <button type="button" className="nw-btn nw-tiny" disabled={disabled} onClick={()=>{setDeviceStatus('Finding cameras…');setScan(n=>n+1);}}>Refresh devices</button>
      </div>
    </form>
  </details>;
}
