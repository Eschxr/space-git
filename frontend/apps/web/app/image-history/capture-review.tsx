'use client';
import {useEffect, useRef, useState} from 'react';
import {intentKey, type Decision, type DecisionStatus, type Proposal, type Run, type Tracker, type Workflow} from './client';
import {date, ObservationImage, short, Sources, TrackCard, words} from './evidence';
import {DetectedObjects} from './detected-objects';

const OUTCOMES: Record<string, string> = {
  unprocessed: 'Images saved. Start inference to find camera-local objects and proposed changes.',
  processing: 'The durable worker is queued or running. This page refreshes automatically.',
  failed: 'Processing failed. Read the run error, correct the cause and retry.',
  no_changes: 'Analysis found no proposed object changes. The camera images remain saved in history.',
  pending_review: 'Review the evidence, record decisions, then select accepted changes to commit.',
  ready_to_commit: 'Accepted changes are ready. Choose which ones to include in the revision.',
  review_complete: 'All changes were rejected. Approved history is unchanged.',
  committed: 'This run contributed to an approved revision. Remaining changes need a new run against the current head.',
  inspection_only: 'This run is for inspection. It cannot be committed.',
  stale_baseline: 'Approved history advanced after this run was scheduled. Reprocess against the current head before committing.',
};

function Audit({api, proposal}: {api: Tracker; proposal: string}) {
  const [items, setItems] = useState<Decision[]>([]), [opened, setOpened] = useState(false), [more, setMore] = useState(false), [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  async function load() {
    setLoading(true); setError('');
    try {const page = await api.decisions(proposal, items.length); setItems(old => [...old, ...page.items]); setMore(page.items.length === page.limit); setOpened(true);}
    catch (e) {setError((e as Error).message);} finally {setLoading(false);}
  }
  return <div className="ih-audit">
    {!opened && <button className="nw-btn nw-tiny" disabled={loading} onClick={() => void load()}>Decision audit</button>}
    {opened && <><strong>Decision audit</strong>{!items.length && <p>No human decisions yet.</p>}{items.map(item => <p key={item.id}>{date(item.decided_at)} · {item.reviewer}: {words(item.previous_status)} → {words(item.new_status)}{item.reason && ' · ' + item.reason}</p>)}
      {more && <button className="nw-btn nw-tiny" disabled={loading} onClick={() => void load()}>More decisions</button>}</>}
    {error && <p role="alert">{error}</p>}
  </div>;
}

function ProposalCard({api, proposal, busy, editable, reviewer, selected, toggle, decide, readOnly=false}: {api: Tracker; proposal: Proposal; busy: boolean; editable: boolean; reviewer: string; selected: boolean; toggle: () => void; decide: (status: DecisionStatus, reason: string) => void; readOnly?:boolean}) {
  const [reason, setReason] = useState(proposal.reason ?? '');
  const label = proposal.after_ref?.label ?? proposal.before_ref?.label ?? 'Object';
  return <article className="ih-proposal" aria-label={label + ' change ' + short(proposal.id)}>
    <header><div><h3>{label} <span>· {proposal.camera_id}</span></h3><p>{words(proposal.type)} · track {short(proposal.view_track_id)}</p></div><span className="nw-chip">{words(proposal.status)}</span></header>
    <div className="ih-pair"><ObservationImage observation={proposal.before_ref?.visualization} label="Before"/><ObservationImage observation={proposal.after_ref?.visualization} label="After"/></div>
    <details><summary>Match evidence & uncertainty</summary><pre>{JSON.stringify(proposal.evidence, null, 2)}</pre></details>
    {!readOnly&&<><label>Decision reason<textarea className="nw-field" value={reason} maxLength={2000} disabled={busy || !editable} onChange={e => setReason(e.target.value)} placeholder="Explain a decision or flag ambiguity"/></label>
    <div className="nw-actions">
      {(['accepted', 'rejected', 'needs_review'] as const).map(status => <button key={status} className="nw-btn nw-tiny" disabled={busy || !editable || !reviewer.trim()} aria-pressed={proposal.status === status} onClick={() => decide(status, reason)}>{status === 'accepted' ? 'Accept' : status === 'rejected' ? 'Reject' : 'Needs review'}</button>)}
      <label className="ih-check"><input type="checkbox" checked={selected} disabled={busy || !editable || proposal.status !== 'accepted'} onChange={toggle}/> Include in revision</label>
    </div>
    <Audit key={proposal.status + (proposal.reason ?? '')} api={api} proposal={proposal.id}/></>}
  </article>;
}

export default function CaptureReview({api, space, capture, busy, run, committed, readOnly=false}: {api: Tracker; space: string; capture: string; busy: boolean; run: (label: string, action: () => Promise<void>) => void; committed: (id: string) => Promise<void>; readOnly?:boolean}) {
  const [workflow, setWorkflow] = useState<Workflow | null>(null), [changes, setChanges] = useState<Proposal[]>([]), [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState(''), [epoch, setEpoch] = useState(0), [camera, setCamera] = useState('all');
  const [selected, setSelected] = useState<string[]>([]), [message, setMessage] = useState(''), [reviewer, setReviewer] = useState('local-operator');
  const [hasMoreRuns, setHasMoreRuns] = useState(false);
  const [analysisNotice,setAnalysisNotice] = useState('');
  const decisionIntents = useRef<Record<string, {payload: string; key: string}>>({});
  const commitIntent = useRef<{payload: string; key: string} | null>(null);
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const [next, attempts] = await Promise.all([api.workflow(capture, controller.signal), api.runs(capture, 0, controller.signal)]);
        const proposals = next.latest_run?.status === 'succeeded' ? await api.changes(next.latest_run.id, controller.signal) : [];
        if (controller.signal.aborted) return;
        setWorkflow(next); setRuns(attempts.items); setHasMoreRuns(attempts.items.length === attempts.limit); setChanges(proposals); setError('');
        setSelected(old => old.filter(id => proposals.some(item => item.id === id && item.status === 'accepted')));
        if (next.outcome === 'processing') timer = setTimeout(() => void load(), 2000);
      } catch (e) {if (!controller.signal.aborted) setError((e as Error).message);}
    }
    void load();
    return () => {controller.abort(); clearTimeout(timer);};
  }, [api, capture, epoch]);
  const latest = workflow?.latest_run;
  const editable = latest?.status === 'succeeded' && !['committed', 'inspection_only', 'stale_baseline'].includes(workflow?.outcome ?? '');
  const chosen = changes.filter(item => selected.includes(item.id) && item.status === 'accepted').map(item => item.id).sort();
  const visible = changes.filter(item => camera === 'all' || item.camera_id === camera);
  return <section className="nw-panel ih-detail">
    <div className="nw-panel-head"><div><h2>Capture {short(capture)}</h2><p>OBSERVED IMAGE EVIDENCE</p></div><button className="nw-btn nw-tiny" disabled={busy} onClick={() => setEpoch(x => x + 1)}>Refresh evidence</button></div>
    {error && <p className="nw-notice" role="alert">{error}</p>}
    {!workflow && !error && <p className="ih-pad" role="status">Loading capture…</p>}
    {workflow && <div className="ih-stack ih-pad">
      <div><span className="nw-chip">{words(readOnly?(latest?.status??'images saved'):workflow.outcome)}</span>
        <p className="ih-lead" role="status">{readOnly?'Images committed. '+(latest?.status==='succeeded'?(changes.length?'Detected changes are shown below.':'Analysis found no proposed object changes.'):latest?'Analysis is '+words(latest.status)+'.':'Analysis is waiting to start.'):OUTCOMES[workflow.outcome]}</p>
        <p>{date(workflow.capture.captured_at)}{!readOnly&&' · approved head '+short(workflow.approved_revision_id)}</p></div>
      {workflow.capture.error && <p role="alert">Upload failed: {workflow.capture.error}. Upload a complete new capture.</p>}
      {workflow.capture.warnings.map(warning => <p key={warning} className="nw-notice">{warning}</p>)}
      <Sources images={workflow.source_images}/>
      {latest && <div className="ih-run"><strong>{latest.provider === 'real' ? 'Real model run' : 'Synthetic fixture run'} · {latest.status}</strong>
        <p>Inference performed: {latest.inference_performed ? 'yes' : 'no'} · run {short(latest.id)} · reference {words(latest.reference?.kind ?? 'none')} {short(latest.reference?.revision_id ?? latest.reference?.capture_id)}</p>
        {latest.reference?.inspection_reason && <p>{words(latest.reference.inspection_reason)}</p>}
        {latest.error && <p role="alert">{latest.error}</p>}
      </div>}
      <div className="nw-actions"><button className="nw-btn nw-primary" disabled={busy || workflow.capture.status !== 'ready' || workflow.outcome === 'processing'} onClick={() => run('Scheduling object detection', async () => {
        setAnalysisNotice('');
        const result=await api.process(capture, latest?.status === 'failed');
        setAnalysisNotice(result.status==='succeeded'?'Showing the completed analysis for these images and settings.':'Object detection scheduled. Results refresh automatically.');
        setEpoch(x => x + 1);
      })}>
        {readOnly?(latest?.status==='failed'?'Retry object detection':'Run object detection'):latest?.status === 'failed' ? 'Retry failed inference' : latest ? 'Reprocess capture' : 'Run inference'}
      </button>{!readOnly&&<span>Uses the API’s configured provider. No automatic approval.</span>}</div>
      {analysisNotice&&<p role="status">{analysisNotice}</p>}
      <DetectedObjects api={api} workflow={workflow}/>
      {!!runs.length && <details><summary>Processing attempts ({runs.length}{hasMoreRuns ? '+' : ''})</summary>{runs.map(attempt => <div className="ih-run" key={attempt.id}><p>{short(attempt.id)} · {attempt.status} · {attempt.provider} · {attempt.scheduled_at && date(attempt.scheduled_at)}</p><details><summary>Model and reference provenance</summary><pre>{JSON.stringify(attempt, null, 2)}</pre></details></div>)}
        {hasMoreRuns && <button className="nw-btn nw-tiny" disabled={busy} onClick={() => run('Loading attempts', async () => {const page = await api.runs(capture, runs.length); setRuns(old => [...old, ...page.items]); setHasMoreRuns(page.items.length === page.limit);})}>More attempts</button>}
      </details>}
      {!!changes.length && <>
        <div className="ih-toolbar"><h3>{readOnly?'Detected changes':'Review proposed changes'} ({changes.length})</h3><label>Camera<select className="nw-field" value={camera} onChange={e => setCamera(e.target.value)}><option value="all">All cameras</option>{['cam_01','cam_02','cam_03','cam_04'].map(id => <option key={id}>{id}</option>)}</select></label>
          {!readOnly&&<label>Reviewer label<input className="nw-field" value={reviewer} maxLength={200} disabled={busy} onChange={e => setReviewer(e.target.value)}/></label>}</div>
        {visible.map(proposal => <ProposalCard key={proposal.id} api={api} proposal={proposal} busy={busy} editable={!!editable} reviewer={reviewer} readOnly={readOnly} selected={chosen.includes(proposal.id)} toggle={() => setSelected(old => old.includes(proposal.id) ? old.filter(id => id !== proposal.id) : [...old, proposal.id])} decide={(status, reason) => run('Recording decision', async () => {
          const intent = intentKey(decisionIntents.current[proposal.id] ?? null, {status, reason, reviewer: reviewer.trim()});
          decisionIntents.current[proposal.id] = intent;
          await api.decide(proposal.id, status, reason, reviewer.trim(), intent.key);
          // A completed intent is distinct from a later deliberate reversal to the same values.
          delete decisionIntents.current[proposal.id]; setEpoch(x => x + 1);
        })}/>)}
        {!readOnly&&<form className="ih-commit" onSubmit={event => {event.preventDefault(); run('Committing selected changes', async () => {
          const intent = intentKey(commitIntent.current, {capture, chosen, message}); commitIntent.current = intent;
          const revision = await api.commit(space, capture, chosen, message, intent.key);
          await committed(revision.id);
        });}}>
          <h3>Commit {chosen.length} selected accepted changes</h3><p>Only these changes advance approved history. Rejected and unselected observations stay out of this revision. Empty revisions are unavailable.</p>
          <label>Revision message<textarea className="nw-field" maxLength={2000} value={message} disabled={busy} onChange={e => setMessage(e.target.value)}/></label>
          <button className="nw-btn nw-primary" disabled={busy || !editable || !chosen.length || chosen.length > 1000}>Commit selected changes</button>
        </form>}
      </>}
      {!!workflow.observed_tracks.length && <details><summary>All observed tracks ({workflow.observed_tracks.length})</summary><div className="ih-track-grid">{workflow.observed_tracks.map(track => <TrackCard key={track.view_track_id} track={track}/>)}</div></details>}
    </div>}
  </section>;
}
