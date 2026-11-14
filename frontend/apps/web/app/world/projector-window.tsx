'use client';

import {useEffect, useRef, useState, type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {requestDisplayFullscreen, type DisplayScreen} from '../components/projector-displays';

type ProjectorWindow = {window: Window; root: HTMLDivElement};

export function useProjectorWindow() {
  const opened = useRef<ProjectorWindow|null>(null);
  const [output, setOutput] = useState<ProjectorWindow|null>(null);
  const [error, setError] = useState('');

  useEffect(() => () => opened.current?.window.close(), []);
  useEffect(() => {
    if (!output) return;
    const timer = window.setInterval(() => {
      if (output.window.closed) {
        opened.current = null;
        setOutput(null);
      }
    }, 300);
    return () => window.clearInterval(timer);
  }, [output]);

  function close() {
    opened.current?.window.close();
    opened.current = null;
    setOutput(null);
    setError('');
  }

  function open(screen?: DisplayScreen) {
    if (opened.current && !opened.current.window.closed) {
      opened.current.window.focus();
      return;
    }
    const bounds = screen
      ? `left=${screen.availLeft},top=${screen.availTop},width=${screen.availWidth},height=${screen.availHeight}`
      : 'width=960,height=640';
    const popup = window.open('', '_blank', 'popup,' + bounds);
    if (!popup) {
      setError('Allow pop-ups for SpaceGit, or move this window to the projector and use Fullscreen.');
      return;
    }

    try {
      popup.document.title = 'SpaceGit Projector';
      popup.document.documentElement.lang = 'en';
      popup.document.body.style.background = 'black';
      popup.document.body.style.margin = '0';
      for (const style of document.querySelectorAll('link[rel="stylesheet"], style')) {
        const copy = style.cloneNode(true);
        if (copy instanceof HTMLLinkElement && style instanceof HTMLLinkElement) copy.href = style.href;
        popup.document.head.append(copy);
      }
      const root = popup.document.createElement('div');
      popup.document.body.append(root);
      const connection = {window:popup, root};
      opened.current = connection;
      setOutput(connection);
      setError('');
      popup.focus();
    } catch {
      popup.close();
      setError('The projector window could not open. Use Fullscreen on the extended display.');
    }
  }

  return {output, error, open, close};
}

export function ProjectorOutput({output, children, close, replay}:{
  output: ProjectorWindow;
  children: ReactNode;
  close: () => void;
  replay: () => void;
}) {
  const display = useRef<HTMLElement>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const document = output.window.document;
    const update = () => setFullscreen(document.fullscreenElement === display.current);
    document.addEventListener('fullscreenchange', update);
    return () => document.removeEventListener('fullscreenchange', update);
  }, [output]);

  async function enterFullscreen() {
    if (!display.current) return;
    try {
      await requestDisplayFullscreen(display.current);
      replay();
      setError('');
    } catch {
      setError('Fullscreen was blocked. Open SpaceGit in Chrome or Edge, or use the browser’s fullscreen shortcut.');
    }
  }

  return createPortal(
    <main ref={display} className="nw nw-projector-window" aria-label="Projector output">
      <div className="nw-projector-frame">{children}</div>
      {!fullscreen && <div className="nw-projector-toolbar">
        <button className="nw-btn nw-primary" onClick={enterFullscreen}>Enter fullscreen</button>
        <button className="nw-btn" onClick={close}>Close</button>
        {error && <p role="status">{error}</p>}
      </div>}
    </main>,
    output.root,
  );
}
