'use client';

import {useEffect, useRef, useState} from 'react';
import type {Edge} from './edge';
import {validateObjects, type ProjectionMessage, type ProjectionObject} from './projection-objects';

export function ProjectionAssistant({sceneReady,edge,connect,objects,change,undo,canUndo,playing,setPlaying,activate}:{
  sceneReady:boolean;edge:Edge|null;connect:()=>Promise<unknown>;objects:ProjectionObject[];change:(next:ProjectionObject[])=>void;
  undo:()=>void;canUndo:boolean;playing:boolean;setPlaying:(value:boolean)=>void;activate:()=>void;
}) {
  const [models,setModels]=useState<string[]>([]),[model,setModel]=useState('');
  const [messages,setMessages]=useState<ProjectionMessage[]>([]),[prompt,setPrompt]=useState('');
  const [busy,setBusy]=useState(false),[loading,setLoading]=useState(false),[issue,setIssue]=useState('');
  const [selected,setSelected]=useState('');
  const mounted=useRef(true),pending=useRef(false);
  const log=useRef<HTMLDivElement>(null);
  const item=objects.find(value=>value.id===selected)??objects.at(-1);
  useEffect(()=>{mounted.current=true;return ()=>{mounted.current=false;};},[]);
  useEffect(()=>{log.current?.scrollTo({top:log.current.scrollHeight,behavior:'smooth'});},[messages,busy]);
  useEffect(()=>{
    let stopped=false;
    queueMicrotask(()=>{
      if(stopped)return;
      if(!edge){setModels([]);setModel('');setLoading(false);return;}
      setLoading(true);
      edge.projectionModels().then(result=>{
      if(stopped)return;
      setModels(result.models);setModel(current=>result.models.includes(current)?current:result.models[0]??'');
      setIssue(result.models.length?'':'No installed Ollama models. Install a chat model on the edge host, then refresh.');
    }).catch(error=>{if(!stopped)setIssue(error.message);}).finally(()=>{if(!stopped)setLoading(false);});
    });
    return ()=>{stopped=true;};
  },[edge]);
  async function refresh(){
    setLoading(true);setIssue('');
    try{
      if(!edge){await connect();return;}
      const result=await edge.projectionModels();
      setModels(result.models);setModel(current=>result.models.includes(current)?current:result.models[0]??'');
      if(!result.models.length)setIssue('No installed Ollama models. Install a chat model on the edge host, then refresh.');
    }catch(error){setIssue(error instanceof Error?error.message:'Could not connect to Ollama.');}
    finally{if(mounted.current)setLoading(false);}
  }
  async function send(){
    if(!sceneReady||!edge||!model||!prompt.trim()||pending.current)return;
    pending.current=true;setBusy(true);setIssue('');
    const request=prompt.trim();
    try{
      const result=await edge.projectionChat(model,request,objects,messages.slice(-12));
      if(!mounted.current)return;
      const next=validateObjects(result.objects);
      if(typeof result.reply!=='string'||!result.reply.length||result.reply.length>2000)throw Error('The model returned an invalid reply.');
      if(JSON.stringify(next)!==JSON.stringify(objects)){change(next);activate();}
      setMessages(current=>[...current,{role:'user',content:request},{role:'assistant',content:result.reply}].slice(-24) as ProjectionMessage[]);
      setPrompt('');
    }catch(error){if(mounted.current)setIssue(error instanceof Error?error.message:'The model request failed.');}
    finally{pending.current=false;if(mounted.current)setBusy(false);}
  }
  function add(shape:ProjectionObject['shape']){
    const next:ProjectionObject={id:crypto.randomUUID(),name:shape[0].toUpperCase()+shape.slice(1),shape,color:'#72d5ef',animation:'float',position:[0,0,0],size:.18};
    change([...objects,next]);setSelected(next.id);activate();
  }
  function edit(patch:Partial<ProjectionObject>){if(item)change(objects.map(value=>value.id===item.id?{...value,...patch}:value));}
  return <section className="nw-panel nw-scene-assistant" aria-label="Scene assistant">
    <div className="nw-panel-head"><div><h2>Scene assistant</h2><p>CREATE WITH OLLAMA</p></div><span className="nw-chip">{busy?'THINKING':models.length?'READY':'OFFLINE'}</span></div>
    <div className="nw-assistant-body">
      <p className="nw-fine">Describe what to add to the scene. Shape, color, position and motion — then refine it together.</p>
      <div className="nw-model-picker"><label>Ollama model<select className="nw-field" value={model} disabled={busy||loading||!models.length} onChange={event=>setModel(event.target.value)}>
        {!models.length&&<option value="">{loading?'Finding models…':'Connect to choose a model'}</option>}
        {models.map(name=><option key={name}>{name}</option>)}
      </select></label><button className="nw-btn nw-tiny" disabled={busy||loading} onClick={()=>void refresh()}>{!edge?'Connect local edge':'Refresh models'}</button></div>
      <div className="nw-chat-log" ref={log} role="log" aria-label="Scene conversation" aria-live="polite">
        {!messages.length&&<div className="nw-chat-empty"><strong>Edit your reconstructed space.</strong><p>Describe the 3D feature or animation you want to add.</p><small>The model edits the added objects. Your source scene stays intact.</small></div>}
        {messages.map((entry,index)=><div className={'nw-chat-message is-'+entry.role} key={index}><span>{entry.role==='user'?'YOU':'OLLAMA'}</span><p>{entry.content}</p></div>)}
        {busy&&<p role="status" className="nw-fine">Planning scene edits… Larger models can take up to two minutes.</p>}
      </div>
      <div className="nw-prompt-examples">{['Add a blue floating sphere','Add a gold spinning torus'].map(text=><button className="nw-btn nw-tiny" disabled={busy} key={text} onClick={()=>setPrompt(text)}>{text}</button>)}</div>
      <form className="nw-prompt-form" onSubmit={event=>{event.preventDefault();void send();}}>
        <label className="nw-sr-only" htmlFor="scene-prompt">Describe a scene edit</label>
        <textarea id="scene-prompt" className="nw-field" rows={3} maxLength={2000} placeholder="Add something to this world…" value={prompt} disabled={busy} onChange={event=>setPrompt(event.target.value)}/>
        <button className="nw-btn nw-primary" disabled={busy||!sceneReady||!edge||!model||!prompt.trim()}>{busy?'Thinking…':'Send to model'}</button>
      </form>
      {issue&&<p className="nw-assistant-error" role="alert">{issue}</p>}
      <p className="nw-fine">Load a reconstruction to enable scene edits. Manual controls work without Ollama. Edits last for this session.</p>
      <fieldset disabled={busy||!sceneReady} className="nw-object-controls">
        <legend>Added objects <span>{objects.length} / 12</span></legend>
        <div className="nw-actions">{(['sphere','cube','torus','cone'] as const).map(shape=><button className="nw-btn nw-tiny" key={shape} disabled={objects.length>=12} onClick={()=>add(shape)}>+ {shape}</button>)}</div>
        {item&&<>
          <label>Selected object<select className="nw-field" value={item.id} onChange={event=>setSelected(event.target.value)}>{objects.map(value=><option key={value.id} value={value.id}>{value.name}</option>)}</select></label>
          <div className="nw-object-row"><label>Color<input type="color" value={item.color} onChange={event=>edit({color:event.target.value})}/></label>
            <label>Animation<select className="nw-field" value={item.animation} onChange={event=>edit({animation:event.target.value as ProjectionObject['animation']})}>{['none','spin','float','pulse'].map(value=><option key={value}>{value}</option>)}</select></label></div>
          {(['x','y','z'] as const).map((axis,index)=><label key={axis}>Position {axis.toUpperCase()}<span>{item.position[index].toFixed(2)}</span><input type="range" min={-1} max={1} step={.05} value={item.position[index]} onChange={event=>{const position:[number,number,number]=[...item.position];position[index]=+event.target.value;edit({position});}}/></label>)}
          <label>Object size<span>{item.size.toFixed(2)}</span><input type="range" min={.05} max={.6} step={.01} value={item.size} onChange={event=>edit({size:+event.target.value})}/></label>
        </>}
        <div className="nw-actions">
          <button className="nw-btn nw-tiny" disabled={!canUndo} onClick={undo}>Undo edit</button>
          <button className="nw-btn nw-tiny" disabled={!objects.length} aria-pressed={!playing} onClick={()=>setPlaying(!playing)}>{playing?'Pause animations':'Play animations'}</button>
          <button className="nw-btn nw-tiny" disabled={!item} onClick={()=>change(objects.filter(value=>value.id!==item?.id))}>Remove object</button>
          <button className="nw-btn nw-tiny" disabled={!objects.length} onClick={()=>change([])}>Clear objects</button>
        </div>
      </fieldset>
    </div>
  </section>;
}
