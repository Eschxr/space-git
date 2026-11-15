export type ProjectionObject = {
  id: string;
  name: string;
  shape: 'sphere'|'cube'|'torus'|'cone';
  color: string;
  animation: 'none'|'spin'|'float'|'pulse';
  position: [number,number,number];
  size: number;
};
export type ProjectionMessage = {role:'user'|'assistant';content:string};
export type ProjectionPlan = {reply:string;objects:ProjectionObject[];provider:'ollama';model:string};

export function validateObjects(value: unknown): ProjectionObject[] {
  if (!Array.isArray(value) || value.length > 12) throw Error('Invalid scene plan.');
  const ids = new Set<string>();
  for (const item of value) {
    if (!item || typeof item !== 'object' || typeof item.id !== 'string' || !/^[a-zA-Z0-9_-]{1,40}$/.test(item.id) || ids.has(item.id)
      || typeof item.name !== 'string' || !item.name.length || item.name.length > 60
      || !['sphere','cube','torus','cone'].includes(item.shape) || !['none','spin','float','pulse'].includes(item.animation)
      || typeof item.color !== 'string' || !/^#[a-f\d]{6}$/i.test(item.color)
      || !Array.isArray(item.position) || item.position.length !== 3 || !item.position.every((n:unknown)=>typeof n==='number' && Number.isFinite(n) && Math.abs(n)<=1)
      || typeof item.size !== 'number' || !Number.isFinite(item.size) || item.size < .05 || item.size > .6) throw Error('Invalid scene plan. No edits were applied.');
    ids.add(item.id);
  }
  return value;
}
