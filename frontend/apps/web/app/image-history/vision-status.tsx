'use client';
import {useEffect, useState} from 'react';
import type {Tracker, VisionStatus} from './client';

export function VisionStatusPanel({api}: {api: Tracker}) {
  const [status, setStatus] = useState<VisionStatus | null>(null);
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(true);
  const [epoch, setEpoch] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setChecking(true);
      setError('');
      try {
        const result = await api.visionStatus(controller.signal);
        if (!controller.signal.aborted) setStatus(result);
      } catch (error) {
        if (!controller.signal.aborted) {
          setStatus(null);
          setError((error as Error).message);
        }
      } finally {
        if (!controller.signal.aborted) setChecking(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [api, epoch]);

  return <section className="nw-panel ih-vision-status" aria-label="AI detector status">
    <div className="nw-panel-head">
      <div>
        <h2>AI object detection</h2>
        <p>{checking ? 'CHECKING CONFIGURATION' : status?.provider === 'fake' ? 'SIMULATED PROCESSING' : status?.assets_verified ? 'REAL DETECTION CONFIGURED' : 'CONFIGURATION UNAVAILABLE'}</p>
      </div>
      <button className="nw-btn nw-tiny" disabled={checking} onClick={() => setEpoch(value => value + 1)}>Check configuration</button>
    </div>
    {status && <div className="ih-pad">
      <p>{status.detector} · {status.embedder} · {status.device.toUpperCase()}</p>
      {status.provider === 'real' && status.assets_verified && <p>Model files verified. Commit and push starts detection on the four saved images.</p>}
      {status.provider === 'fake' && <p>Analysis uses synthetic fixture instructions. Real camera detection requires the real provider.</p>}
      {status.reason && <p role="alert">{status.reason}</p>}
    </div>}
    {error && <p className="nw-notice" role="alert">{error}</p>}
  </section>;
}
