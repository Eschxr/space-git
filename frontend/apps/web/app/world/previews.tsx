import {CAMERAS} from './domain';

export function RigDiagram() {
  return <svg viewBox="0 0 300 220" className="nw-rig-art" role="img" aria-label="One vertical pole with outward cameras at 0, 120 and 240 degrees, and camera 4 facing down toward the floor">
    <defs><pattern id="rig-dots" width="12" height="12" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".7" fill="#444"/></pattern></defs>
    <rect width="300" height="220" fill="url(#rig-dots)"/>
    <g fill="none" stroke="#414141"><ellipse cx="150" cy="158" rx="87" ry="37"/><ellipse cx="150" cy="158" rx="58" ry="24"/><path d="M27 158h246m-123-58v112" strokeDasharray="3 5"/></g>
    <g stroke="#a6a6a6" fill="#a6a6a6"><path fill="none" d="M150 145v-17m-20 9-56 25m6-9-6 9 12 2m84-27 56 25m-12 2 12-2-6-9m-69-42 52-24m-11-1 11 1-4 8" strokeWidth="1.4"/>
    <rect x="145" y="64" width="10" height="91" rx="3" fill="#8b8b8b"/><ellipse cx="150" cy="154" rx="13" ry="5" fill="#555"/>
    <path d="m129 122 21-9 21 9-21 10Z" fill="#c9c9c9"/><path d="m129 122 21 10 21-10v10l-21 10-21-10Z" fill="#666"/>
    <path d="M155 61h23" strokeWidth="3"/><rect x="165" y="59" width="26" height="12" rx="2" fill="#444"/><rect x="172" y="71" width="12" height="5" fill="#bbb"/>
    <path d="M178 81v25m-5-5 5 5 5-5" fill="none" strokeWidth="1.4"/></g>
    <g fontFamily="monospace" fontSize="10" fill="#bfbfbf"><text x="166" y="48">04 / FLOOR</text><text x="205" y="77">01 / 000°</text><text x="214" y="184">02 / 120°</text><text x="35" y="184">03 / 240°</text></g>
  </svg>;
}

export function RigLabels(){return <div className="nw-rig-labels">{CAMERAS.map(cam=><div key={cam.id}><span>{String(cam.id).padStart(2,'0')}</span><strong>{cam.name}</strong><span>{cam.angle}</span></div>)}</div>;}
