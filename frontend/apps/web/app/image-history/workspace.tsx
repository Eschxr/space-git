'use client';
import Link from 'next/link';
import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {localHost} from '../components/connection';
import {Icon} from '../components/icons';
import {trackerClient, TrackerError, type Capture, type Revision, type Space, type Tracker} from './client';
import CaptureReview from './capture-review';
import RevisionPanel from './revision-panel';
import UploadPanel from './upload-panel';
import {date, short} from './evidence';
import '../world/world.css';
import './history.css';

const BASE = process.env.NEXT_PUBLIC_SCENE_TRACKER_URL || 'http://127.0.0.1:8001';
type Selection = {kind: 'capture' | 'revision'; id: string};
type RunAction = (label: string, action: () => Promise<void>) => void;
const merge = <T extends {id: string}>(before: T[], after: T[]) => [...new Map([...before, ...after].map(item => [item.id, item])).values()];

function SpaceWorkspace({api, space, busy, run}: {api: Tracker; space: Space; busy: boolean; run: RunAction}) {
  const [captures, setCaptures] = useState<Capture[]>([]), [revisions, setRevisions] = useState<Revision[]>([]);
  const [captureMore, setCaptureMore] = useState(false), [revisionMore, setRevisionMore] = useState(false);
  const [selection, setSelection] = useState<Selection | null>(null), [error, setError] = useState(''), [loaded, setLoaded] = useState(false);
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const [images, history] = await Promise.all([api.captures(space.id, 0, signal), api.revisions(space.id, 0, signal)]);
    if (signal?.aborted) return;
    setCaptures(images.items); setCaptureMore(images.items.length === images.limit); setRevisions(history.items); setRevisionMore(history.items.length === history.limit); setLoaded(true); setError('');
  }, [api, space.id]);
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      if (!controller.signal.aborted) void refresh(controller.signal).catch(e => {if (!controller.signal.aborted) setError(e.message);});
    });
    return () => controller.abort();
  }, [refresh]);
  return <div className="ih-layout">
    <aside className="ih-stack">
      <section className="nw-panel"><div className="nw-panel-head"><div><h2>{space.name}</h2><p>SPACE {short(space.id)}</p></div><button className="nw-btn nw-tiny" disabled={busy} onClick={() => run('Refreshing space', refresh)}>Refresh lists</button></div>
        {error && <p className="nw-notice" role="alert">{error}</p>}
        <div className="ih-pad ih-stack"><h3>Captures</h3>{!loaded && !error && <p>Loading…</p>}{loaded && !captures.length && <p>No captures yet. Add four images below.</p>}
          <div className="ih-list">{captures.map(item => <button className="ih-list-item" key={item.id} disabled={busy} aria-current={selection?.kind === 'capture' && selection.id === item.id ? 'true' : undefined} onClick={() => setSelection({kind: 'capture', id: item.id})}><strong>{short(item.id)} <span>{item.status}</span></strong><small>{date(item.captured_at)}</small></button>)}</div>
          {captureMore && <button className="nw-btn nw-tiny" disabled={busy} onClick={() => run('Loading captures', async () => {const next = await api.captures(space.id, captures.length); setCaptures(old => merge(old, next.items)); setCaptureMore(next.items.length === next.limit);})}>More captures</button>}
          <h3>Approved revisions</h3>{loaded && !revisions.length && <p>No approved revisions yet.</p>}
          <div className="ih-list">{revisions.map((item, index) => <button className="ih-list-item" key={item.id} disabled={busy} aria-current={selection?.kind === 'revision' && selection.id === item.id ? 'true' : undefined} onClick={() => setSelection({kind: 'revision', id: item.id})}><strong>{short(item.id)} {index === 0 && <span>HEAD</span>}</strong><span>{item.message || 'Untitled revision'}</span><small>{date(item.created_at)} · parent {short(item.parent_id)}</small></button>)}</div>
          {revisionMore && <button className="nw-btn nw-tiny" disabled={busy} onClick={() => run('Loading revisions', async () => {const next = await api.revisions(space.id, revisions.length); setRevisions(old => merge(old, next.items)); setRevisionMore(next.items.length === next.limit);})}>More revisions</button>}
        </div>
      </section>
      <UploadPanel api={api} space={space.id} busy={busy} run={run} uploaded={async capture => {
        setCaptures(old => merge(old, [capture])); setSelection({kind: 'capture', id: capture.id}); await refresh();
      }}/>
    </aside>
    <div className="ih-content">
      {!selection && <section className="nw-panel ih-empty"><Icon name="history" size={34}/><h2>Evidence before approval.</h2><p>Select a capture to run inference and review changes, or open a revision to inspect its approved image history.</p><p>History is linear within each saved space. Objects are tracked within their camera view; review ambiguous matches before accepting them.</p><Link href="/world" className="nw-btn">Open 3D & projection workspace <Icon name="external" size={14}/></Link></section>}
      {selection?.kind === 'capture' && <CaptureReview key={selection.id} api={api} space={space.id} capture={selection.id} busy={busy} run={run} committed={async id => {setSelection({kind: 'revision', id}); await refresh();}}/>}
      {selection?.kind === 'revision' && <RevisionPanel key={selection.id} api={api} revision={selection.id} revisions={revisions}/>}
    </div>
  </div>;
}

export default function ImageHistory() {
  const api = useMemo(() => trackerClient(BASE), []);
  const [local, setLocal] = useState<boolean | null>(null), [spaces, setSpaces] = useState<Space[]>([]), [spaceId, setSpaceId] = useState('');
  const [more, setMore] = useState(false), [name, setName] = useState(''), [busy, setBusy] = useState(''), [error, setError] = useState(''), [connected, setConnected] = useState(false);
  const locked = useRef(false);
  const run: RunAction = useCallback((label, action) => {
    if (locked.current) return;
    locked.current = true; setBusy(label); setError('');
    void action().catch(e => {
      const details = e instanceof TrackerError ? ` (${e.code})${e.details.capture_id ? ' · failed capture ' + e.details.capture_id : ''}` : '';
      setError(e.message + details);
    }).finally(() => {locked.current = false; setBusy('');});
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      const enabled = localHost(); setLocal(enabled);
      if (!enabled) return;
      void api.spaces(0, controller.signal).then(page => {
        if (controller.signal.aborted) return;
        setSpaces(page.items); setMore(page.items.length === page.limit); setConnected(true);
        let saved = ''; try {saved = localStorage.getItem('spacegit.image-history.space.' + BASE) ?? '';} catch {}
        setSpaceId(page.items.some(item => item.id === saved) ? saved : page.items[0]?.id ?? '');
      }).catch(e => {if (!controller.signal.aborted) setError(e.message);});
    });
    return () => controller.abort();
  }, [api]);
  function choose(id: string) {
    setSpaceId(id); try {localStorage.setItem('spacegit.image-history.space.' + BASE, id);} catch {}
  }
  const space = spaces.find(item => item.id === spaceId);
  return <div className="nw ih">
    <header className="nw-top"><div className="nw-top-inner"><Link href="/world" className="nw-brand"><span className="nw-mark"><Icon name="cube" size={20}/></span><strong>Space<span>Git</span></strong><span className="nw-brand-divider"/><span className="nw-edition">IMAGE HISTORY</span></Link><div className="nw-top-actions"><Link href="/world" className="nw-btn nw-tiny">3D & projection <Icon name="arrow" size={14}/></Link></div></div></header>
    <main className="nw-shell nw-main"><div className="nw-titlebar"><div><div className="nw-eyebrow"><span/> OBSERVE · REVIEW · COMMIT</div><h1>Image history.</h1><p>Four camera views. Reviewed changes. An approved record for every space.</p></div></div>
      {local === null && <p role="status">Opening local workspace…</p>}
      {local === false && <section className="nw-panel ih-empty"><h2>Open on your local workstation</h2><p>Image history needs the local Scene Tracker API and worker. Start the application profile, then open http://127.0.0.1:3000/image-history with the local frontend build.</p><p>The public demo’s Capture, 3D viewer and projector workflow remain available.</p><Link className="nw-btn" href="/world">Return to the workspace</Link></section>}
      {local && <>
        <div className="ih-spacebar nw-panel"><label>Saved space<select className="nw-field" value={spaceId} disabled={!!busy || !spaces.length} onChange={e => choose(e.target.value)}><option value="">Choose a space</option>{spaces.map(item => <option key={item.id} value={item.id}>{item.name} · {short(item.id)}</option>)}</select></label>
          <button className="nw-btn nw-tiny" disabled={!!busy} onClick={() => run('Loading spaces', async () => {
            const next = await api.spaces(more ? spaces.length : 0); setSpaces(old => more ? merge(old, next.items) : next.items); setMore(next.items.length === next.limit); setConnected(true);
          })}>{more ? 'More spaces' : 'Refresh spaces'}</button>
          <form onSubmit={event => {event.preventDefault(); run('Creating space', async () => {const created = await api.createSpace(name.trim()); setSpaces(old => [created, ...old]); choose(created.id); setName(''); setConnected(true);});}}><label>New space name<input className="nw-field" placeholder="Lab or Bedroom" value={name} maxLength={200} required disabled={!!busy} onChange={e => setName(e.target.value)}/></label><button className="nw-btn nw-primary" disabled={!!busy || !name.trim()}>Create space</button></form>
        </div>
        <p className="ih-connection">Scene Tracker · {BASE} · {connected ? 'connected' : 'awaiting API'} · image evidence and linear approvals</p>
        {error && <p className="nw-notice" role="alert">{error}</p>}{busy && <p className="nw-notice" role="status">{busy}…</p>}
        {space ? <SpaceWorkspace key={space.id} api={api} space={space} busy={!!busy} run={run}/> : connected && <section className="nw-panel ih-empty"><h2>Choose or create a saved space</h2><p>Each physical room has its own captures and approved revisions. Use consistent fixed camera roles within a space.</p></section>}
      </>}
    </main><footer className="nw-shell nw-footer"><span>SPACEGIT / IMAGE HISTORY</span><Link href="/world">Capture · 3D · Project</Link><Link href="/studio">Hardware studio</Link></footer>
  </div>;
}
