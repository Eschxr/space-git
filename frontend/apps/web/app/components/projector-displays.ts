'use client';

import {useEffect, useRef, useState} from 'react';

export type DisplayScreen = Screen & {
  left: number;
  top: number;
  availLeft: number;
  availTop: number;
  label: string;
  isPrimary: boolean;
  devicePixelRatio: number;
};
export type ScreenDetails = EventTarget & {currentScreen: DisplayScreen; screens: DisplayScreen[]};
type DisplayWindow = Window & {getScreenDetails?: () => Promise<ScreenDetails>};

export function screenKey(screen: DisplayScreen) {
  return [screen.left, screen.top, screen.width, screen.height, screen.devicePixelRatio, screen.label].join(':').slice(0,160);
}

export function requestDisplayFullscreen(element: HTMLElement, screen?: DisplayScreen) {
  return element.requestFullscreen(screen ? {screen} as FullscreenOptions : undefined);
}

export function useProjectorDisplays() {
  const [details, setDetails] = useState<ScreenDetails|null>(null);
  const detailsRef = useRef<ScreenDetails|null>(null);
  const [screens, setScreens] = useState<DisplayScreen[]>([]);
  const [selected, select] = useState('');
  const [issue, setIssue] = useState('');

  useEffect(() => {
    if (!details) return;
    function refresh() {
      const available = [...details!.screens];
      setScreens(available);
      select(current => available.some(screen => screenKey(screen) === current) ? current : '');
    }
    details.addEventListener('screenschange', refresh);
    return () => details.removeEventListener('screenschange', refresh);
  }, [details]);

  async function detect() {
    try {
      const browser = window as DisplayWindow;
      if (!browser.getScreenDetails) throw Error('This browser cannot list displays.');
      const next = await browser.getScreenDetails();
      const external = next.screens.find(screen => !screen.isPrimary);
      detailsRef.current = next;
      setDetails(next);
      setScreens([...next.screens]);
      select(current => next.screens.some(screen => screenKey(screen) === current) ? current : external ? screenKey(external) : '');
      setIssue(next.screens.length > 1 ? '' : 'Only one display detected. Connect the projector, choose Extend in your display settings, and detect displays again.');
    } catch {
      setIssue('Display detection is unavailable. Move the projector window to the extended display manually.');
    }
  }

  function selectedScreen() {
    const screen = detailsRef.current?.screens.find(screen => screenKey(screen) === selected);
    if (selected && !screen) throw Error('The selected display was disconnected. Detect displays again.');
    return screen;
  }

  return {detailsRef, screens, selected, select, selectedScreen, detect, issue};
}
