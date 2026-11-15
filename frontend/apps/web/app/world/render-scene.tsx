'use client';
import dynamic from 'next/dynamic';
import {useEffect,useState} from 'react';
import {type Asset} from './domain';
import {type Edge} from './edge';
import type {loadAsset} from './viewport';

export const RenderScene = dynamic(()=>import('./viewport'),{ssr:false,loading:()=><div className="nw-render-note" role="status">Loading 3D viewport…</div>});
type Data = Awaited<ReturnType<typeof loadAsset>>;
type State = {data:Data|null;message:string;error:boolean};
const EMPTY: State = {data:null,message:'',error:false};
export function useSceneAsset(edge: Edge|null, asset: Asset|null, file: File|null, camera?:number, refresh=0) {
  const [result,setResult]=useState<State>(EMPTY);
  useEffect(()=>{
    const controller=new AbortController();
    let release:(()=>void)|undefined;
    queueMicrotask(async()=>{
      if(controller.signal.aborted)return;
      if(!file&&(!edge||(!asset&&camera===undefined))){setResult(EMPTY);return;}
      setResult({data:null,message:'Loading geometry…',error:false});
      try{
        const io=await import('./viewport');
        const payload=file??await (camera===undefined?edge!.asset(asset!,controller.signal):edge!.pointcloud(camera,controller.signal));
        const data=await io.loadAsset(payload,file?.name??(camera===undefined?asset!.name:`cam_0${camera}.ply`));
        if(controller.signal.aborted){io.disposeAsset(data);return;}
        release=()=>io.disposeAsset(data);
        setResult({data,message:'Geometry loaded.',error:false});
      }catch(err){
        if(!controller.signal.aborted)setResult({data:null,message:err instanceof Error?err.message:'Unable to load geometry.',error:true});
      }
    });
    return ()=>{controller.abort();release?.();};
  },[edge,asset,file,camera,refresh]);
  return file||asset||camera!==undefined?result:EMPTY;
}
