'use client';
import {useState} from 'react';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import type {Change,Commit,Conflict,Scene} from '../../../../packages/protocol/types';
import {api} from './connection';
import {Icon} from './icons';
import {WallPlan,ChangeList} from './wall-plan';

export type HistoryData={branches:Record<string,string>;commits:Commit[]};
export type Run=(fn:()=>Promise<void>)=>void;
export function History({data,token,run,refresh,open}:{data:HistoryData;token:string;run:Run;refresh:()=>Promise<void>;open:(id:string)=>void}){
 const router=useRouter();
 const [revision,pick]=useState(''),[base,setBase]=useState(''),[name,setName]=useState(''),[diff,setDiff]=useState<Change[]|null>(null);
 const selected=data.commits.find(c=>c.id===revision)??data.commits[0];
 if(!selected)return <div className="panel blank">Connect the edge to view revision history.</div>;
 const comparison=data.commits.find(c=>c.id===base)?.id??selected.parents[0]??selected.id;
 return <div className="split-view"><section className="panel form-panel"><div className="panel-heading"><Icon name="history"/><div><h2>Scene timeline</h2><p>Saved layouts and their parent revisions.</p></div></div>
 <div className="timeline">{data.commits.map(c=><button className={'revision '+(selected.id===c.id?'selected':'')} onClick={()=>{pick(c.id);setDiff(null);}} key={c.id}><span className="revision-dot"/><span><strong>{c.message}</strong><small>{c.id.slice(0,8)} · {c.evidence?.mode==='live'?'Camera observation':'Layout'}{c.parents.length?' · from '+c.parents.map(x=>x.slice(0,8)).join(' + '):''}</small></span><span className="pill">{Object.entries(data.branches).filter(([,v])=>v===c.id).map(([k])=>k).join(', ')||'revision'}</span></button>)}</div>
 </section><section className="panel form-panel"><div className="panel-heading"><Icon name="branch"/><div><h2>{selected.message}</h2><p>{selected.scene.objects.length} objects · {new Date(selected.time*1000).toLocaleString()}</p></div></div>
 <label>Compare with<select value={comparison} onChange={e=>{setBase(e.target.value);setDiff(null);}}>{data.commits.map(c=><option key={c.id} value={c.id}>{c.message} · {c.id.slice(0,8)}</option>)}</select></label>
 <div className="inline"><button className="btn" onClick={()=>run(async()=>setDiff(await api<Change[]>(token,'/diff',{before:comparison,after:selected.id})))}>Show object diff</button><button className="btn" onClick={()=>open(selected.id)}>View in 3D</button></div>
 {diff&&<ChangeList changes={diff}/>}
 <WallPlan scene={selected.scene} label="Restore preview" changed={diff?.map(d=>d.id)}/>
 {selected.evidence?.plan&&<p className="mono green-text">Verified deployment · {selected.evidence.plan.slice(0,8)} · {selected.evidence.tolerance_mm} mm tolerance</p>}
 <form className="inline" onSubmit={e=>{e.preventDefault();run(async()=>{await api(token,'/branches',{name,commit:selected.id});setName('');await refresh();});}}><input aria-label="Branch name" pattern="[A-Za-z0-9_-]{1,64}" placeholder="New branch name" value={name} onChange={e=>setName(e.target.value)} required/><button className="btn"><Icon name="branch"/> Create branch</button></form>
 <button className="btn primary" disabled={!selected.scene.objects.length} onClick={()=>router.push('/studio/live?revision='+selected.id)}><Icon name="target"/> Review restore settings</button>
 </section></div>;
}

type Choice='target'|'source';
type MergeData={target:string;source:string;base:string;candidate:Scene|null;candidate_id:string|null;conflicts:Conflict[];commit?:Commit;target_changes:Change[];source_changes:Change[];placement_changed:boolean};
export function MergeFlow({data,token,run,refresh}:{data:HistoryData;token:string;run:Run;refresh:()=>Promise<void>}){
 const [target,setTarget]=useState('main'),[source,setSource]=useState(''),[preview,setPreview]=useState<MergeData|null>(null),[accepted,accept]=useState(false),[saved,setSaved]=useState('');
 const [objectChoices,chooseObjects]=useState<Record<string,Choice>>({}),[ruleChoice,chooseRules]=useState<Choice|undefined>(),[dirty,setDirty]=useState(false);
 const branches=Object.keys(data.branches), current=source||branches.find(b=>b!==target)||'';
 const l=data.commits.find(c=>c.id===data.branches[target]),r=data.commits.find(c=>c.id===data.branches[current]);
 const involved=preview?.conflicts.flatMap(c=>c.ids)??[];
 function reset(){setPreview(null);accept(false);chooseObjects({});chooseRules(undefined);setDirty(false);}
 const inputs={target,source:current,object_choices:objectChoices,rule_choice:ruleChoice};
 return <div className="stack">
 <section className="panel form-panel"><div className="panel-heading"><Icon name="branch"/><div><h2>Spatial Merge</h2><p>Review object changes and placement rules from a shared ancestor before approving a new revision.</p></div></div>
 <div className="fields"><label>Target<select value={target} onChange={e=>{setTarget(e.target.value);setSource('');reset();}}>{branches.map(b=><option key={b}>{b}</option>)}</select></label><label>Source<select value={current} onChange={e=>{setSource(e.target.value);reset();}}><option value="">Choose branch</option>{branches.filter(b=>b!==target).map(b=><option key={b}>{b}</option>)}</select></label></div>
 <button className="btn primary" disabled={!current} onClick={()=>run(async()=>{setPreview(await api<MergeData>(token,'/merge',inputs));accept(false);setDirty(false);setSaved('');})}>{dirty?'Recalculate candidate':'Preview merge'} <Icon name="arrow"/></button>
 {branches.length<2&&<p className="muted">Create a branch from <Link href="/studio/history">Revision history</Link>, then commit a change in 3D.</p>}
 <div className="merge-board">{l&&<WallPlan scene={l.scene} label={'Target · '+target} changed={preview?.target_changes.map(d=>d.id)} conflicts={involved}/>}
 {r&&<WallPlan scene={r.scene} label={'Source · '+current} changed={preview?.source_changes.map(d=>d.id)} conflicts={involved}/>}
 {preview?.candidate&&<WallPlan scene={preview.candidate} label="Candidate layout" changed={preview.source_changes.map(d=>d.id)}/>}</div>
 </section><div className="split-view"><section className="panel form-panel"><h2>Changes by branch</h2>
 {preview?<><span className="pill">COMMON ANCESTOR {preview.base.slice(0,8)}</span>
 {preview.placement_changed&&<span className="pill warning">PLACEMENT RULES CHANGED</span>}
 <h3>Target changes</h3><ChangeList changes={preview.target_changes}/>
 <h3>Source changes</h3><ChangeList changes={preview.source_changes}/></>:<p className="muted">Preview a merge to compare object identity, positions, rotation, sizes, and additions or removals.</p>}
 </section><section className="panel form-panel"><h2>Resolve and approve</h2>
 {preview?<>{preview.conflicts.length?<ul className="diff-list">{preview.conflicts.map((c,i)=><li className="warning" key={i}>{c.message}</li>)}</ul>:<p>No conflicts found.</p>}
 {preview.conflicts.some(c=>c.kind==='placement-rules')&&<label>Placement rules<select value={ruleChoice??''} onChange={e=>{chooseRules((e.target.value||undefined) as Choice|undefined);setDirty(true);accept(false);}}><option value="">Choose rule set</option><option value="target">Use target rules</option><option value="source">Use source rules</option></select></label>}
 {preview.conflicts.filter(c=>c.kind==='same-object').map(c=><label key={c.ids[0]}>Conflict · {c.ids[0]}<select value={objectChoices[c.ids[0]]??'target'} onChange={e=>{chooseObjects({...objectChoices,[c.ids[0]]:e.target.value as Choice});setDirty(true);accept(false);}}><option value="target">Prefer target</option><option value="source">Prefer source</option></select></label>)}
 {dirty&&<p className="warning">Recalculate before approving the updated choices.</p>}
 {preview.candidate?<><label className="checkline"><input type="checkbox" checked={accepted} disabled={dirty} onChange={e=>accept(e.target.checked)}/> I approve the candidate placement.</label>
 <button className="btn primary" disabled={!accepted||dirty} onClick={()=>run(async()=>{const m=await api<MergeData>(token,'/merge',{...inputs,approve:true,accept_candidate:true,base_target:preview.target,base_source:preview.source,candidate_id:preview.candidate_id});setSaved(m.commit?.id??'');reset();await refresh();})}>Create merge revision</button></>:<p className="warning">No candidate under the current placement rules.</p>}</>:<p className="muted">{saved?'Created merge revision '+saved.slice(0,8)+'. Restore it from History when ready.':'No candidate yet. Preview a merge to see the results.'}</p>}
 </section></div></div>;
}
