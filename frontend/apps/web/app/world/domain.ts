import type {Card, Change, Commit, Job, Scene} from '../../../../packages/protocol/types';

export const CAMERAS = [
  {id: 1, angle: '000°', name: 'Radial A', direction: 'Outward · 0°'},
  {id: 2, angle: '120°', name: 'Radial B', direction: 'Outward · 120°'},
  {id: 3, angle: '240°', name: 'Radial C', direction: 'Outward · 240°'},
  {id: 4, angle: '↓', name: 'Floor', direction: 'Downward · Floor view'},
] as const;

export const CAMERA_ORDER = CAMERAS.map(camera => camera.id);
export type CameraSource = number|'primary'|null;
export type CameraDevice = {index: number; label: string};
export type RigSettings = {sources: CameraSource[]; order: number[]};
export type Feed = {id: number; status: 'live'|'waiting'|'offline'|'unmapped'|'simulated'; age_ms: number|null; error?: string|null};
export type Rig = {mode: 'demo'|'live'; enabled: boolean; feeds: Feed[]; settings?: RigSettings};
export type Capture = {id: string; created: number; mode: 'demo'|'live'; feeds: number[]; order?: number[]; sample?: number; head?: string; saved?: string; frame_times?: Record<string, number>; pointdit?: {status:'succeeded'|'failed'; files?:string[]; error?:string; log:string}};
export type History = {branches: Record<string, string>; commits: Commit[]};
export type Asset = {id: string; name: string; label: string; job?: Job};
export type Delta = {id: string; label: string; kind: 'added'|'missing'|'moved'|'unchanged'|'modified'; before?: Card; after?: Card; fields: string[]};
export const EMPTY_RIG: Rig = {mode: 'live', enabled: false, feeds: CAMERAS.map(({id}) => ({id, status:'offline', age_ms: null}))};

export const EMPTY_HISTORY: History = {branches:{}, commits:[]};
export function realHistory(history:History):History {
  const commits=history.commits.filter(commit=>commit.evidence?.mode!=='demo');
  const ids=new Set(commits.map(commit=>commit.id));
  return {commits,branches:Object.fromEntries(Object.entries(history.branches).filter(([,id])=>ids.has(id)))};
}

export function sameSceneReference(before: Scene, after: Scene): boolean {
  const a: Scene & {workspace_id?:string|null} = before, b: Scene & {workspace_id?:string|null} = after;
  return a.frame===b.frame && a.id===b.id && a.workspace_id===b.workspace_id && a.wall.every((v,i)=>v===b.wall[i]);
}
export const isNormalized = (scene:Scene|undefined) => String(scene?.frame)==='wall-normalized';

export function compareScenes(before: Scene, after: Scene, supplied?: Change[]): Delta[] {
  const older = new Map(before.objects.map(card => [card.id,card]));
  const newer = new Map(after.objects.map(card => [card.id,card]));
  const changes = new Map(supplied?.map(change => [change.id,change]));
  return [...new Set([...older.keys(), ...newer.keys(), ...changes.keys()])].map(id => {
    const change = changes.get(id), from = supplied ? (change ? change.before ?? undefined : older.get(id)) : older.get(id),
      to = supplied ? (change ? change.after ?? undefined : newer.get(id)) : newer.get(id);
    const fields = supplied ? change?.fields ?? [] : from && to ? (['x','y','angle','w','h','d','name'] as const).filter(key => from[key] !== to[key]) : [];
    const kind = supplied ? change?.kind === 'added' ? 'added' : change?.kind === 'removed' ? 'missing' : !change ? 'unchanged' : fields.some(key => ['x','y','angle'].includes(key)) ? 'moved' : 'modified'
      : !from ? 'added' : !to ? 'missing' : fields.some(key => ['x','y','angle'].includes(key)) ? 'moved' : fields.length ? 'modified' : 'unchanged';
    return {id,label:to?.name ?? from?.name ?? id,kind,before:from,after:to,fields};
  });
}

export function explainDiff(rows: Delta[], frame: Scene['frame']|null): string {
  if (!rows.length) return 'The selected revisions contain no recorded objects.';
  const unchanged = rows.filter(row => row.kind === 'unchanged').length;
  const summary = rows.filter(row => row.kind !== 'unchanged').map(row => {
    if (row.kind === 'added') return row.label + ' appears in the later revision.';
    if (row.kind === 'missing') return row.label + ' is absent from the later revision.';
    if (row.kind === 'modified') return row.label + ' changed (' + row.fields.join(', ') + ').';
    if (!row.before || !row.after) return row.label + ' has a recorded pose change.';
    const dx = row.after.x - row.before.x, dy = row.after.y - row.before.y;
    const distance = Math.hypot(dx,dy);
    const turn = row.fields.includes('angle');
    if (distance < 1e-6) return row.label + (turn ? ' rotated.' : ' has a recorded pose change.');
    const direction = [dx > 1e-6 ? 'right' : dx < -1e-6 ? 'left' : '', dy > 1e-6 ? 'up' : dy < -1e-6 ? 'down' : ''].filter(Boolean).join(' and ');
    return row.label + ' moved ' + (frame === 'wall-world-meters' ? distance.toFixed(2) + ' m ' : '') + direction + (turn ? ' and rotated.' : '.');
  });
  if (unchanged) summary.push(unchanged + (unchanged === 1 ? ' object is' : ' objects are') + ' unchanged in the recorded layouts.');
  return summary.join(' ');
}

export const DEFAULT_PROJECTION = {brightness:100,contrast:100,lowPower:false};
export type Projection = typeof DEFAULT_PROJECTION;
export function readProjection(): Projection {
  try {
    const raw = JSON.parse(localStorage.getItem('spacegit.world.projection.v1') ?? '{}');
    return {
      brightness: Number.isFinite(raw.brightness) ? Math.min(160,Math.max(40,raw.brightness)) : 100,
      contrast: Number.isFinite(raw.contrast) ? Math.min(160,Math.max(60,raw.contrast)) : 100,
      lowPower: raw.lowPower === true,
    };
  } catch {return DEFAULT_PROJECTION;}
}
