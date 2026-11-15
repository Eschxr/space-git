'use client';
import {useEffect, useState} from 'react';
import {CAMERAS as RIG_CAMERAS} from '../world/domain';
import {CAMERAS, type Detection, type Observation, type Tracker, type Workflow} from './client';
import {ObservationImage} from './evidence';

export function DetectedObjects({api, workflow}: {api: Tracker; workflow: Workflow}) {
  const run = workflow.latest_run;
  const runId = run?.id;
  const runStatus = run?.status;
  const [objects, setObjects] = useState<Detection[]>([]);
  const [camera, setCamera] = useState('all');
  const [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setObjects([]);
      setSelected('');
      setError('');
      setLoading(false);
      if (!runId || runStatus !== 'succeeded') return;
      setLoading(true);
      try {
        const result = await api.detections(runId, controller.signal);
        if (!controller.signal.aborted) setObjects(result.sort((a, b) => b.det_score - a.det_score));
      } catch (error) {
        if (!controller.signal.aborted) setError((error as Error).message);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [api, runId, runStatus]);

  if (!run || run.status !== 'succeeded') return null;
  const visible = objects.filter(object => camera === 'all' || object.camera_id === camera);
  const object = visible.find(item => item.id === selected) ?? visible[0];
  const frame = workflow.source_images.find(frame => frame.id === object?.frame_id);
  const tracked = workflow.observed_tracks.find(track => track.observation.detection_id === object?.id);
  const observation: Observation | null = tracked?.observation ?? (object && frame ? {
    capture_id: workflow.capture.id,
    frame_id: frame.id,
    camera_id: object.camera_id,
    detection_id: object.id,
    run_id: run.id,
    label: object.label,
    box_xyxy: object.box_xyxy,
    width: frame.width,
    height: frame.height,
    image: frame.image,
    mask: null,
    crop: null,
    overlays: [],
  } : null);
  const embeddings = objects.filter(object => object.embedding_key).length;

  return <section className="ih-detector" aria-label="Detected objects">
    <div className="ih-toolbar">
      <div>
        <h3>Detected objects ({objects.length})</h3>
        <p>{run.provider === 'real' ? 'YOLOE predictions' : 'Simulated objects'} · {embeddings} {run.provider === 'real' ? 'DINOv2' : 'simulated'} feature records</p>
      </div>
      <label>Detection camera<select aria-label="Detection camera" className="nw-field" value={camera} onChange={event => {setCamera(event.target.value); setSelected('');}}>
        <option value="all">All cameras</option>
        {CAMERAS.map((camera, index) => <option key={camera} value={camera}>{RIG_CAMERAS[index].name}</option>)}
      </select></label>
    </div>
    {loading && <p role="status">Loading detected objects…</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && !error && !objects.length && <p>No objects were detected in this run.</p>}
    {!loading && !error && !!objects.length && <div className="ih-detector-grid">
      <div className="ih-object-list" aria-label="Object list">
        {!visible.length && <p>No objects were detected by this camera.</p>}
        {visible.map(item => <button key={item.id} className="ih-list-item" aria-pressed={item.id === object?.id} onClick={() => setSelected(item.id)}>
          <strong>{item.label}<span>{(item.det_score * 100).toFixed(1)}%</span></strong>
          <small>{RIG_CAMERAS[CAMERAS.indexOf(item.camera_id)]?.name ?? item.camera_id}</small>
        </button>)}
      </div>
      {object && <div className="ih-object-preview">
        <ObservationImage key={object.id} observation={observation} label="Detected object"/>
        <p>Model confidence {(object.det_score * 100).toFixed(1)}%. Labels are predictions and can be incorrect.</p>
        <p>{object.embedding_key ? `${run.provider === 'real' ? 'DINOv2' : 'Simulated'} appearance features available · ${object.embedding_metadata?.dimension ?? 'unknown'} dimensions` : 'Appearance features are unavailable for this object.'}</p>
      </div>}
    </div>}
  </section>;
}
