import type {Change, Commit, Job, Scene} from '../../../../packages/protocol/types';
import {api, apiBase, localHost} from '../components/connection';
import type {Asset, CameraDevice, Capture, History, ProjectedObject, Rig, RigModel, RigSettings} from './domain';
import type {ChatMessage} from './projector-chat';
import type {Representation,SurfaceAction,SurfaceJob,SurfaceSettings} from './surface-types';

const segment = encodeURIComponent;
const MAX_ASSET = 64 * 1024 * 1024;

export function edgeAdapter(token: string) {
  const getFile = async (path: string, signal?: AbortSignal, limit = MAX_ASSET, timeoutMs = 12000): Promise<Blob> => {
    if (!token || !localHost()) throw Error('Connect to the local edge first.');
    const timeout = AbortSignal.timeout(timeoutMs);
    const response = await fetch(apiBase() + '/api/v1' + path,{signal:signal ? AbortSignal.any([timeout,signal]) : timeout,
      headers:{Authorization:'Bearer ' + token},cache:'no-store'});
    if (!response.ok) throw Error('The edge could not deliver this file (' + response.status + ').');
    if (Number(response.headers.get('content-length')) > limit) {
      await response.body?.cancel();
      throw Error('The asset exceeds the viewer size limit.');
    }
    const blob = await response.blob();
    if (blob.size > limit) throw Error('The asset exceeds the viewer size limit.');
    return blob;
  };
  return {
    rig: () => api<Rig>(token,'/rig'),
    devices: () => api<{cameras: CameraDevice[]}>(token,'/devices'),
    saveRig: (settings: RigSettings) => api<Rig>(token,'/rig/settings',settings),
    start: () => api<Rig>(token,'/rig/start',{}),
    stop: () => api<Rig>(token,'/rig/stop',{}),
    sessions: () => api<Capture[]>(token,'/rig/captures'),
    capture: () => api<Capture>(token,'/rig/captures',{},'POST',1850000),
    pointcloud: (slot: number, signal: AbortSignal, version?:string) => getFile((version?'/rig/models/'+segment(version):'/rig')+'/pointclouds/'+slot,signal),
    rigModels: () => api<RigModel[]>(token,'/rig/models'),
    saveCurrentRig: () => api<RigModel>(token,'/rig/models/import-current',{},'POST',30000),
    uploadCloud: async (file:File,signal:AbortSignal):Promise<{source:string}> => {
      const response=await fetch(apiBase()+'/api/v1/surfaces/inputs',{method:'POST',body:file,signal,
        headers:{Authorization:'Bearer '+token,'Content-Type':'application/octet-stream'}});
      if(!response.ok){
        const data=await response.json().catch(()=>({}));
        throw Error(typeof data.detail==='string'?data.detail:'Could not send the PLY to the local worker.');
      }
      return response.json();
    },
    startSurface: (source:string,action:SurfaceAction,settings:SurfaceSettings,base?:string) =>
      api<SurfaceJob>(token,'/surfaces/jobs',{source,action,settings,base}),
    surfaceJob: (id:string) => api<SurfaceJob>(token,'/surfaces/jobs/'+segment(id)),
    latestSurface: (source:string) => api<SurfaceJob|null>(token,'/surfaces/sources/'+segment(source)+'/latest'),
    cancelSurface: (id:string) => api<{ok:boolean}>(token,'/surfaces/jobs/'+segment(id),undefined,'DELETE'),
    applySurface: (id:string) => api<SurfaceJob>(token,'/surfaces/jobs/'+segment(id)+'/apply',{}),
    surfaceFile: (id:string,slot:number,representation:Representation|'report',signal?:AbortSignal) =>
      getFile('/surfaces/jobs/'+segment(id)+'/views/'+slot+'/'+representation,signal,192*1024*1024,60000),
    projectorChat: (messages:ChatMessage[],output:string,objects:string[]) => api<{reply:string}>(token,'/projector/chat',{messages,output,objects},'POST',65000),
    projectorObjects: (scene:string) => api<ProjectedObject[]>(token,'/projector/scenes/'+segment(scene)+'/objects'),
    generateProjectorObject: (scene:string,prompt:string,requestId:string) => api<ProjectedObject>(token,'/projector/scenes/'+segment(scene)+'/objects',{prompt,request_id:requestId},'POST',125000),
    regenerateProjectorObject: (scene:string,id:string) => api<ProjectedObject>(token,'/projector/scenes/'+segment(scene)+'/objects/'+segment(id)+'/regenerate',{},'POST',125000),
    positionProjectorObject: (scene:string,id:string,offset:[number,number,number]) => api<ProjectedObject>(token,'/projector/scenes/'+segment(scene)+'/objects/'+segment(id)+'/position',{offset}),
    preview: (id: number, signal: AbortSignal, capture?: string) => getFile(
      capture ? '/rig/captures/'+segment(capture)+'/frames/'+id : '/rig/frames/'+id,signal,2 * 1024 * 1024,2000),
    history: () => api<History>(token,'/commits'),
    compare: (before: string, after: string) => api<Change[]>(token,'/diff',{before,after}),
    branch: (name: string, commit: string) => api<History>(token,'/branches',{name,commit}),
    commit: (branch: string, expected: string, message: string, scene?: Scene) => scene
      ? api<Commit>(token,'/commits',{scene,branch,expected,message})
      : api<Commit>(token,'/tracking/commit',{branch,expected,message}),
    jobs: () => api<{jobs: Job[]; colmap: boolean}>(token,'/reconstructions'),
    asset: (asset: Asset, signal: AbortSignal) => getFile('/assets/' + segment(asset.id) + '/' + segment(asset.name),signal),
  };
}
export type Edge = ReturnType<typeof edgeAdapter>;
