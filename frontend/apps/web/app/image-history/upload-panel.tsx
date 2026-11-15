'use client';
import {useMemo, useState} from 'react';
import {useToken} from '../components/connection';
import {edgeAdapter} from '../world/edge';
import type {Capture as RigCapture} from '../world/domain';
import {CAMERAS, completeSession, type Camera, type Capture, type Tracker} from './client';
import {date, short} from './evidence';

export default function UploadPanel({api, space, busy, run, uploaded}: {api: Tracker; space: string; busy: boolean; run: (label: string, action: () => Promise<void>) => void; uploaded: (capture: Capture) => Promise<void>}) {
  const [files, setFiles] = useState<Partial<Record<Camera, File>>>({});
  const [sessions, setSessions] = useState<RigCapture[]>([]), [sessionId, setSessionId] = useState('');
  const [sessionsLoaded, setSessionsLoaded] = useState(false);
  const [token,,connectLocal] = useToken();
  const edge = useMemo(() => token ? edgeAdapter(token) : null, [token]);
  const session = sessions.find(s => s.id === sessionId);
  return <section className="nw-panel">
    <div className="nw-panel-head"><div><h2>Add image evidence</h2><p>FOUR FIXED CAMERA ROLES</p></div></div>
    <form className="ih-form" onSubmit={event => {event.preventDefault(); const form = event.currentTarget; run('Uploading four images', async () => {
      const capture = await api.upload(space, {images: files as Record<Camera, File>});
      setFiles({}); form.reset(); await uploaded(capture);
    });}}>
      <p>Choose three fixed side views and the overhead view. Original bytes are retained. Upload and inference are separate steps.</p>
      <div className="ih-file-grid">{CAMERAS.map((camera, i) => <label key={camera}>{camera} · {i === 3 ? 'overhead' : 'side ' + (i + 1)}
        <input type="file" accept="image/jpeg,image/png,image/webp" required disabled={busy} onChange={event => setFiles(old => ({...old, [camera]: event.target.files?.[0]}))}/>
      </label>)}</div>
      <button className="nw-btn nw-primary" disabled={busy || !CAMERAS.every(camera => files[camera])}>Upload four images</button>
    </form>
    <details className="ih-form ih-divider"><summary>Import a saved camera rig session</summary>
      <p>Slots 1–4 map to cam_01–cam_04, regardless of preview order. Only complete live sessions are eligible. Set up cameras in <a href="/world">Capture</a>.</p>
      <button className="nw-btn" disabled={busy} onClick={() => run('Loading rig sessions', async () => {
        const connected = edge ?? edgeAdapter(await connectLocal());
        const items = await connected.sessions();
        setSessions(items); setSessionsLoaded(true);
        setSessionId(old => items.some(item => item.id === old) ? old : '');
      })}>Connect edge & load sessions</button>
      {sessionsLoaded && !sessions.length && <p role="status">No saved rig sessions yet. Save a complete four-camera session in Capture, or upload four files above.</p>}
      {!!sessions.length && <label>Saved session<select className="nw-field" value={sessionId} disabled={busy} onChange={e => setSessionId(e.target.value)}>
        <option value="">Choose a session</option>{sessions.map(item => <option key={item.id} value={item.id} disabled={!completeSession(item)}>{date(new Date(item.created * 1000).toISOString())} · {short(item.id)} · {item.feeds.length}/4 {completeSession(item) ? '' : '(incomplete or simulated)'}</option>)}
      </select></label>}
      <button className="nw-btn" disabled={busy || !edge || !session || !completeSession(session)} onClick={() => run('Importing rig images', async () => {
        if (!session || !edge || !completeSession(session)) return;
        const controller = new AbortController();
        try {
          const blobs = await Promise.all(CAMERAS.map((_, index) => edge.preview(index + 1, controller.signal, session.id)));
          const frameTimes = Object.fromEntries(CAMERAS.flatMap((camera, index) => session.frame_times?.[String(index + 1)] ? [[camera, new Date(session.frame_times[String(index + 1)] * 1000).toISOString()]] : []));
          await uploaded(await api.upload(space, {images: Object.fromEntries(CAMERAS.map((camera, index) => [camera, blobs[index]])) as Record<Camera, Blob>, capturedAt: new Date(session.created * 1000).toISOString(), frameTimes}));
        } finally {controller.abort();}
      })}>Import selected session</button>
    </details>
  </section>;
}
