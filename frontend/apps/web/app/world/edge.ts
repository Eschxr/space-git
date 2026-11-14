import type {Change, Commit, Job, Scene} from '../../../../packages/protocol/types';
import {api, apiBase, localHost} from '../components/connection';
import type {Asset, CameraDevice, Capture, History, Rig, RigSettings} from './domain';

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
    capture: () => api<Capture>(token,'/rig/captures',{}),
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
