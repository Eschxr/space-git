'use client';
import {useEffect,useState} from 'react';
import type {Live,Pair} from '../../../../packages/protocol/types';
export const localHost=()=>typeof window!=='undefined' && ['localhost','127.0.0.1'].includes(window.location.hostname) && process.env.NEXT_PUBLIC_SPACEGIT_PUBLIC!=='1';
const KEY='spacegit.operator.v1';
const LOCAL_CONNECTION='spacegit.local.connection.v1';
async function localSession(signal:AbortSignal, token=''):Promise<string>{
 if(!localHost())throw Error('Open SpaceGit on the projector workstation.');
 const response=await fetch(apiBase()+'/api/v1/local-session',{
  method:'POST',cache:'no-store',signal,
  headers:{'X-SpaceGit-Local':'1',...(token?{Authorization:'Bearer '+token}:{})},
 });
 if(!response.ok)throw Error('Start the local edge or enter its operator key.');
 return (await response.json() as {token:string}).token;
}
export function useToken(){
 const [key,setKey]=useState('');
 const [session,setSession]=useState('');
 const [automatic,setAutomatic]=useState(false);
 useEffect(()=>{
  if(!localHost())return;
  const sync=()=>{
   setKey(localStorage.getItem(KEY)??'');
   setAutomatic(localStorage.getItem(LOCAL_CONNECTION)==='on');
  };
  queueMicrotask(sync);
  function changed(event:StorageEvent){if(!event.key||[KEY,LOCAL_CONNECTION].includes(event.key))sync();}
  window.addEventListener('storage',changed);
  return ()=>window.removeEventListener('storage',changed);
 },[]);
 useEffect(()=>{
  if(!automatic||key)return;
  const controller=new AbortController();
  let credential='', timer:ReturnType<typeof setTimeout>;
  async function renew(){
   try{
    credential=await localSession(AbortSignal.any([controller.signal,AbortSignal.timeout(3000)]),credential);
    if(!controller.signal.aborted)setSession(credential);
   }catch{}
   if(!controller.signal.aborted)timer=setTimeout(renew,credential?60000:5000);
  }
  queueMicrotask(()=>{if(!controller.signal.aborted)void renew();});
  return ()=>{controller.abort();clearTimeout(timer);};
 },[automatic,key]);
 async function connectLocal(){
  let token:string;
  try{token=await localSession(AbortSignal.timeout(3500));}
  catch{throw Error('Could not connect. Start the local edge or enter its operator key in Hardware Setup.');}
  localStorage.removeItem(KEY);
  localStorage.setItem(LOCAL_CONNECTION,'on');
  setKey('');
  setSession(token);
  setAutomatic(true);
  return token;
 }
 function setToken(value:string){
  if(!localHost())return;
  localStorage.removeItem(LOCAL_CONNECTION);
  setAutomatic(false);
  setSession('');
  if(value)localStorage.setItem(KEY,value);else localStorage.removeItem(KEY);
  setKey(value);
 }
 return [key||(automatic?session:''),setToken,connectLocal] as const;
}
export const apiBase=()=>localHost()?(process.env.NEXT_PUBLIC_SPACEGIT_EDGE_URL || 'http://127.0.0.1:8000').replace(/\/$/,''):'';
export async function api<T>(token:string,path:string,body?:unknown,method?:string,timeoutMs=12000):Promise<T>{
 if(!localHost()) throw Error('Local edge controls are available on the projector workstation.');
 const r=await fetch(apiBase()+'/api/v1'+path,{headers:{Authorization:'Bearer '+token,...(body!==undefined?{'Content-Type':'application/json'}:{})},body:body===undefined?undefined:JSON.stringify(body),method:method??(body===undefined?'GET':'POST'),signal:AbortSignal.timeout(timeoutMs),cache:'no-store'});
 if(!r.ok){const data=await r.json().catch(()=>({}));throw Error(typeof data.detail==='string'?data.detail:'Request failed ('+r.status+'). Check the supplied values.');}
 const data=await r.json();
 if(path==='/status'&&data.live?.mode!=='live')throw Error('Start the edge in live mode to use real data.');
 if(path==='/commits'&&Array.isArray(data.commits)){
  data.commits=data.commits.filter((item:{evidence?:{mode?:string}})=>item.evidence?.mode!=='demo');
  const ids=new Set(data.commits.map((item:{id:string})=>item.id));
  data.branches=Object.fromEntries(Object.entries(data.branches??{}).filter(([,id])=>ids.has(id)));
 }
 return data as T;
}
export type Wizard={index:number;point:Pair;key?:string;shown?:boolean;kind?:'physical'|'auto_blank'|'auto_spot';expected?:Pair};
export function useLive(token:string,maxSilence=1000){
 const [event,set]=useState<Live|null>(null),[error,err]=useState('');
 useEffect(()=>{
  if(!token||!localHost())return;
  let done=false, last=0, device='', retry:ReturnType<typeof setTimeout>, ws:WebSocket, received=0;
  const connect=()=>{
   const endpoint=new URL('/ws/live',apiBase());
   endpoint.protocol=endpoint.protocol==='https:'?'wss:':'ws:';
   ws=new WebSocket(endpoint,'spacegit.v1');
   ws.onopen=()=>ws.send(token);
   ws.onmessage=e=>{try{const n:Live=JSON.parse(e.data);if(!n||n.version!==1)return;
    if(n.mode!=='live'){set(null);err('Start the edge in live mode to use real data.');return;}
    if(n.device!==device){device=n.device;last=0;}
    if(n.seq<=last)return;last=n.seq;received=Date.now();set(n);err('');
   }catch{}};
   ws.onclose=()=>{if(!done){set(null);err('Edge disconnected. Check the local service and operator key.');retry=setTimeout(connect,1800);}};
  };
  connect();
  const expiry=setInterval(()=>{if(received&&Date.now()-received>maxSilence){set(null);err('Waiting for fresh tracking frames.');}},Math.min(250,maxSilence/3));
  return ()=>{done=true;clearTimeout(retry);clearInterval(expiry);if(ws?.readyState<2)ws.close();};
 },[token,maxSilence]);
 return {event:token?event:null,error:token?error:''};
}
