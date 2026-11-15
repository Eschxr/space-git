'use client';

import {useCallback, useState, useSyncExternalStore, type RefObject} from 'react';
import type {Projection} from './domain';
import type {Agent, Engine} from './engine';
import {RenderScene} from './render-scene';
import type {ProjectionObject} from './projection-objects';

const motionPreference = '(prefers-reduced-motion: reduce)';
const serverReducedMotion = () => false;

export function PortalOffice({engine, agents, angle, lowPower, visible, reveal, outputWindow,additions,animationPlaying}:{
  engine: RefObject<Engine|null>;
  agents: Agent[];
  angle: Projection['angle'];
  lowPower: boolean;
  visible: boolean;
  reveal: number;
  outputWindow?: Window;
  additions?:ProjectionObject[];
  animationPlaying?:boolean;
}) {
  const subscribe = useCallback((listener: () => void) => {
    const query = (outputWindow ?? window).matchMedia(motionPreference);
    query.addEventListener('change', listener);
    return () => query.removeEventListener('change', listener);
  }, [outputWindow]);
  const getPreference = () => (outputWindow ?? window).matchMedia(motionPreference).matches;
  const reduceMotion = useSyncExternalStore(subscribe, getPreference, serverReducedMotion);
  const [ready, setReady] = useState<number|null>(null);
  return <div className="nw-portal">
    <RenderScene office {...{engine, agents, angle, lowPower, visible,additions,animationPlaying}}
      reveal={reveal} reducedMotion={reduceMotion} onReveal={setReady}/>
    {!reduceMotion && <div key={reveal} className="nw-portal-reveal" data-open={ready===reveal} aria-hidden="true">
      <div className="nw-portal-leaf nw-portal-leaf-left"/>
      <div className="nw-portal-leaf nw-portal-leaf-right"/>
      <div className="nw-portal-seam"/>
    </div>}
    <div className="nw-portal-frame" aria-hidden="true"/>
  </div>;
}
