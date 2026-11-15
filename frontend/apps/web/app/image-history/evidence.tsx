'use client';
/* Signed immutable evidence is served directly by the local object store. */
/* eslint-disable @next/next/no-img-element */
import {useState} from 'react';
import type {Asset, Observation, SourceImage, Track} from './client';

export const short = (id: string | null | undefined) => id?.slice(0, 8) ?? 'none';
export const words = (text: string) => text.replaceAll('_', ' ');
export const date = (value: string) => new Date(value).toLocaleString();

export function AssetImage({asset, alt}: {asset: Asset; alt: string}) {
  const [failed, setFailed] = useState(false);
  if (!asset.url || failed) return <div className="ih-unavailable">{asset.unavailable_reason ?? 'Image unavailable or link expired. Refresh evidence to request a new link.'}</div>;
  return <a href={asset.url} target="_blank" rel="noopener noreferrer"><img src={asset.url} alt={alt} loading="lazy" onError={() => setFailed(true)}/></a>;
}

export function Sources({images}: {images: SourceImage[]}) {
  return <div className="ih-sources">{images.map(frame => <figure key={frame.id}>
    <AssetImage key={frame.image.url} asset={frame.image} alt={frame.camera_id + ' source image'}/>
    <figcaption><strong>{frame.camera_id}</strong> · {frame.role} · {frame.width} × {frame.height}<br/>
      <span>Capture {short(frame.capture_id)} · SHA {short(frame.sha256)}</span></figcaption>
  </figure>)}</div>;
}

export function ObservationImage({observation, label}: {observation: Observation | null | undefined; label: string}) {
  const [mode, setMode] = useState<'image' | 'crop' | 'overlay'>('image');
  if (!observation) return <figure className="ih-observation"><figcaption>{label}</figcaption><div className="ih-unavailable">No observation on this side.</div></figure>;
  const asset = mode === 'overlay' ? observation.overlays[0] : observation[mode];
  return <figure className="ih-observation">
    <figcaption><strong>{label}</strong> · {observation.label} · {observation.camera_id}</figcaption>
    <select className="nw-field" aria-label={label + ' evidence layer'} value={mode} onChange={e => setMode(e.target.value as typeof mode)}>
      <option value="image">Source image</option><option value="crop">Object crop</option><option value="overlay">Run overlay</option>
    </select>
    {observation.mask?.url && <a className="ih-mask-download" href={observation.mask.url} download>Download mask RLE JSON</a>}
    <div className="ih-image">{asset ? <AssetImage key={asset.url} asset={asset} alt={label + ' ' + observation.label}/> : <div className="ih-unavailable">This layer is unavailable.</div>}
      {mode === 'image' && <svg viewBox={`0 0 ${observation.width} ${observation.height}`} aria-hidden="true"><rect x={observation.box_xyxy[0]} y={observation.box_xyxy[1]} width={observation.box_xyxy[2] - observation.box_xyxy[0]} height={observation.box_xyxy[3] - observation.box_xyxy[1]} fill="none" stroke="#f3cc62" strokeWidth={Math.max(observation.width / 220, 2)}/></svg>}
    </div>
    <figcaption>Source capture {short(observation.capture_id)} · run {short(observation.run_id)}</figcaption>
  </figure>;
}

export function TrackCard({track, history}: {track: Track; history?: () => void}) {
  return <article className="ih-track"><ObservationImage observation={track.observation} label={String(track.state.label ?? track.observation.label)}/>
    <p>{track.camera_id} · track {short(track.view_track_id)} · {String(track.state.status ?? 'observed')}</p>
    {history && <button className="nw-btn nw-tiny" onClick={history}>Accepted track history</button>}
  </article>;
}
