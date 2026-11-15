'use client';
import {useState} from 'react';
import type {Commit} from '../../../../packages/protocol/types';
import {Icon} from '../components/icons';
import {type Edge} from './edge';
import {RenderScene} from './render-scene';
import {SurfacePanel} from './surface-panel';

export function ReconstructPanel({edge,demo,openProject}:{
  edge:Edge|null; demo?:Commit; openProject:()=>void;
}) {
  const [selected,setSelected]=useState('');
  const object=demo?.scene.objects.find(item=>item.id===selected);
  return <>
    <div className="nw-titlebar">
      <div>
        <h1>Reconstruct</h1>
        <p>{demo?'Inspect the reconstructed study.':'Inspect the scan or build a smooth surface from its points.'}</p>
      </div>
      <button className="nw-btn nw-primary" onClick={openProject}><Icon name="screen"/>Open projector view</button>
    </div>
    {demo ? <div className="nw-workspace-grid">
      <section className="nw-panel nw-view-panel" aria-label="Reconstruction">
        <div className="nw-panel-head"><h2>Reconstructed study</h2></div>
        <div className="nw-viewport" data-testid="reconstruction">
          <RenderScene scene={demo.scene} simulated selected={selected} select={setSelected}/>
        </div>
      </section>
      <section className="nw-panel">
        <div className="nw-panel-head"><h2>Object inspector</h2></div>
        <div className="nw-object-select">{demo.scene.objects.map(item=><button key={item.id}
          className="nw-btn nw-tiny" aria-pressed={item.id===selected} onClick={()=>setSelected(item.id)}>{item.name}</button>)}</div>
        {object&&<dl className="nw-meta"><div><dt>Identity</dt><dd>{object.id}</dd></div></dl>}
      </section>
    </div> : <SurfacePanel edge={edge}/>}
  </>;
}
