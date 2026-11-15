'use client';
import {useEffect, useState} from 'react';
import type {Comparison, Proposal, Revision, RevisionEvidence, Tracker, TrackHistory} from './client';
import {date, ObservationImage, short, Sources, TrackCard, words} from './evidence';

function AcceptedHistory({api, track}: {api: Tracker; track: string}) {
  const [history, setHistory] = useState<TrackHistory | null>(null), [error, setError] = useState(''), [loading, setLoading] = useState(false);
  const [more, setMore] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void api.trackHistory(track, 0, controller.signal).then(page => {
      if (!controller.signal.aborted) {setHistory(page); setMore(page.items.length === page.limit);}
    }).catch(e => {if (!controller.signal.aborted) setError(e.message);});
    return () => controller.abort();
  }, [api, track]);
  return <div className="ih-track-history"><h3>Accepted track {short(track)}</h3>{error && <p role="alert">{error}</p>}
    {history?.items.map(item => <div className="ih-run" key={item.revision.id}><p>{date(item.revision.created_at)} · {short(item.revision.id)} · {item.revision.message}</p><TrackCard track={item.state}/></div>)}
    {history && more && <button className="nw-btn" disabled={loading} onClick={async () => {
      setLoading(true);
      try {const next = await api.trackHistory(track, history.items.length); setHistory({...next, items: [...history.items, ...next.items]}); setMore(next.items.length === next.limit); setError('');}
      catch (e) {setError((e as Error).message);} finally {setLoading(false);}
    }}>More accepted history</button>}
  </div>;
}

export default function RevisionPanel({api, revision, revisions}: {api: Tracker; revision: string; revisions: Revision[]}) {
  const [evidence, setEvidence] = useState<RevisionEvidence | null>(null), [events, setEvents] = useState<Proposal[]>([]), [error, setError] = useState('');
  const [epoch, setEpoch] = useState(0), [before, setBefore] = useState(''), [comparison, setComparison] = useState<Comparison | null>(null), [compareError, setCompareError] = useState('');
  const [track, setTrack] = useState(''), [camera, setCamera] = useState('all');
  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([api.evidence(revision, controller.signal), api.diff(revision, controller.signal)]).then(([next, diff]) => {
      if (controller.signal.aborted) return;
      setEvidence(next); setEvents(diff.changes); setError('');
    }).catch(e => {if (!controller.signal.aborted) setError(e.message);});
    return () => controller.abort();
  }, [api, revision, epoch]);
  useEffect(() => {
    if (!before) return;
    const controller = new AbortController();
    void api.compare(before, revision, controller.signal).then(next => {if (!controller.signal.aborted) {setComparison(next); setCompareError('');}}).catch(e => {if (!controller.signal.aborted) setCompareError(e.message);});
    return () => controller.abort();
  }, [api, before, revision, epoch]);
  return <section className="nw-panel ih-detail">
    <div className="nw-panel-head"><div><h2>Revision {short(revision)}</h2><p>IMMUTABLE APPROVED HISTORY</p></div><button className="nw-btn nw-tiny" onClick={() => setEpoch(x => x + 1)}>Refresh evidence</button></div>
    {error && <p className="nw-notice" role="alert">{error}</p>}
    {!evidence && !error && <p className="ih-pad">Loading revision…</p>}
    {evidence && <div className="ih-pad ih-stack">
      <div><h3>{evidence.revision.message || 'Untitled revision'}</h3><p>{date(evidence.revision.created_at)} · parent {short(evidence.revision.parent_id)} · capture {short(evidence.revision.capture_id)}</p></div>
      <h3>Source images for this capture</h3><Sources images={evidence.source_images}/>
      <p>Approved objects can retain evidence from earlier captures when a newer observation was rejected. Each object identifies its source capture.</p>
      <details><summary>Run, model and source provenance</summary><pre>{JSON.stringify(evidence.provenance, null, 2)}</pre></details>
      <div className="ih-toolbar"><h3>Approved objects ({evidence.approved_tracks.length})</h3><label>Approved camera<select className="nw-field" value={camera} onChange={e => setCamera(e.target.value)}><option value="all">All cameras</option>{['cam_01','cam_02','cam_03','cam_04'].map(id => <option key={id}>{id}</option>)}</select></label></div>
      <div className="ih-track-grid">{evidence.approved_tracks.filter(item => camera === 'all' || item.camera_id === camera).map(item => <TrackCard key={item.view_track_id} track={item} history={() => setTrack(item.view_track_id)}/>)}</div>
      {track && <div><button className="nw-btn nw-tiny" onClick={() => setTrack('')}>Close track history</button><AcceptedHistory key={track} api={api} track={track}/></div>}
      <section className="ih-stack"><h3>Compare approved states</h3><label>Compare from<select className="nw-field" value={before} onChange={e => {setBefore(e.target.value); setComparison(null); setCompareError('');}}><option value="">Choose a revision</option>{revisions.map(item => <option key={item.id} value={item.id}>{short(item.id)} · {item.message || date(item.created_at)}</option>)}</select></label>
        {compareError && <p role="alert">{compareError}</p>}
        {comparison && <><p>{words(comparison.direction)} comparison · {comparison.items.filter(item => item.kind !== 'unchanged').length} changed tracks</p>{comparison.items.filter(item => item.kind !== 'unchanged').map(item => <article className="ih-proposal" key={item.view_track_id}><h3>{item.camera_id} · {words(item.kind)} · {short(item.view_track_id)}</h3><p>Fields: {item.fields.join(', ') || 'lifecycle'}</p><div className="ih-pair"><ObservationImage label="Before" observation={item.before?.observation}/><ObservationImage label="After" observation={item.after?.observation}/></div></article>)}</>}
      </section>
      <details><summary>Applied events since parent ({events.length})</summary><p>This is the committed event sequence. Compare approved states above to see net changes.</p><pre>{JSON.stringify(events, null, 2)}</pre></details>
      {!!evidence.highlight_paths.length && <details><summary>Image / future point-map highlight manifests</summary><p>Existing local cloud viewers and projector tools remain available in the 3D workspace. Real PointDiT generation is still a later phase.</p>{evidence.highlight_paths.map(path => <a className="ih-manifest" href={api.base + path} target="_blank" rel="noopener noreferrer" key={path}>{path}</a>)}</details>}
    </div>}
  </section>;
}
