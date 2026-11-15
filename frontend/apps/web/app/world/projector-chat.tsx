'use client';
import {useRef,useState} from 'react';
import type {Edge} from './edge';

export type ChatMessage = {role:'user'|'assistant';content:string};
export type ProjectorCommand = 'reconstruction'|'blackout'|'resume';

const COMMANDS:Record<string,ProjectorCommand> = {
  'show current reconstruction':'reconstruction', 'show reconstruction':'reconstruction',
  'blackout':'blackout', 'black out':'blackout', 'show output':'resume', 'resume output':'resume',
};

export function ProjectorChat({edge,local,connect,command,outputLabel,blackedOut,objects,sceneId,generateObject}:{
  edge:Edge|null; local:boolean; connect:()=>Promise<string>; command:(action:ProjectorCommand)=>string;
  outputLabel:string; blackedOut:boolean; objects?:string[];
  sceneId?:string; generateObject:(prompt:string,requestId:string)=>Promise<string>;
}) {
  const [messages,setMessages]=useState<ChatMessage[]>([]);
  const [input,setInput]=useState('');
  const [busy,setBusy]=useState('');
  const [error,setError]=useState('');
  const log=useRef<HTMLDivElement>(null);
  const retry=useRef<{scene:string|undefined;prompt:string;id:string}|null>(null);

  function append(message:ChatMessage) {
    setMessages(previous=>[...previous.slice(-39),message]);
    requestAnimationFrame(()=>{if(log.current)log.current.scrollTop=log.current.scrollHeight;});
  }

  async function send(forceGeneration=false) {
    const question=input.trim();
    if(!question||busy)return;
    const user:ChatMessage={role:'user',content:question};
    setInput('');setError('');append(user);
    const phrase=question.toLowerCase().replace(/[.!?]+$/,'').replace(/\s+/g,' ').replace(/^show the /,'show ');
    const action=Object.hasOwn(COMMANDS,phrase)?COMMANDS[phrase]:undefined;
    let answer:string;
    if(forceGeneration||/^(?:please\s+)?(?:add|create|generate|place|put|insert)\s+\S/i.test(question)) {
      const request=retry.current?.prompt===question&&retry.current.scene===sceneId?retry.current:{scene:sceneId,prompt:question,id:crypto.randomUUID()};
      retry.current=request;
      setBusy('Generating a 3D object…');
      try {
        const name=await generateObject(question,request.id);
        answer='Generated and saved '+name+' in '+outputLabel+'.';
        retry.current=null;
      } catch(cause) {
        setError(cause instanceof Error?cause.message:'The local model could not generate an object.');
        setInput(question);
        return;
      } finally {setBusy('');}
    } else if(action)answer=command(action);
    else if(['what is showing',"what's showing",'what is on the projector'].includes(phrase)) {
      answer=blackedOut?'The projector is blacked out. The selected output is '+outputLabel+'.':'Selected output: '+outputLabel+'.';
    } else if(['help','how do i add a model','how do i add models'].includes(phrase)) {
      answer='Describe an object, such as “add a red chair on the left”. You can also open a PLY, GLB or self-contained glTF with Add 3D models.';
    } else if(edge) {
      setBusy('Waiting for the local model…');
      try {
        const result=await edge.projectorChat([...messages.slice(-7),user].map(message=>({...message,content:message.content.slice(0,1200)})),outputLabel.slice(0,240),objects?.map(name=>name.slice(0,120))??[]);
        answer=result.reply;
      } catch(cause) {
        setError(cause instanceof Error?cause.message:'Local chat could not respond.');
        setInput(question);
        return;
      } finally {setBusy('');}
    } else {
      answer=local?'Connect this workstation to use Ollama chat and load saved 3D models. Type “help” for projector commands.':'Type “help” for the available projector commands.';
    }
    append({role:'assistant',content:answer});
  }

  return <section className="nw-panel" aria-label="Projector chat">
    <div className="nw-panel-head"><h2>Projector chat</h2></div>
    <div className="nw-chat">
      <div className="nw-chat-log" role="log" aria-label="Conversation" ref={log}>
        {!messages.length&&<p>Try “add a red chair on the left”.</p>}
        {messages.map((message,index)=><p key={index} className={message.role==='user'?'nw-chat-user':undefined}>
          <strong>{message.role==='user'?'You':'SpaceGit'}</strong>{message.content}
        </p>)}
      </div>
      {busy&&<p role="status">{busy}</p>}
      {error&&<p role="alert">{error}</p>}
      {local&&!edge&&<button className="nw-btn nw-tiny" disabled={!!busy} onClick={async()=>{
        setBusy('Connecting to this workstation…');setError('');
        try{await connect();}catch(cause){setError((cause as Error).message);}finally{setBusy('');}
      }}>Connect this workstation</button>}
      <form onSubmit={event=>{event.preventDefault();void send();}}>
        <label htmlFor="projector-chat-message">Message</label>
        <div className="nw-chat-compose">
          <input id="projector-chat-message" className="nw-field" value={input} onChange={event=>setInput(event.target.value)} maxLength={1200} disabled={!!busy}/>
          <button className="nw-btn nw-primary" disabled={!!busy||!input.trim()}>Send</button>
        </div>
        <button className="nw-btn nw-tiny" type="button" disabled={!!busy||input.trim().length<3} onClick={()=>void send(true)}>Generate 3D object</button>
      </form>
    </div>
  </section>;
}
