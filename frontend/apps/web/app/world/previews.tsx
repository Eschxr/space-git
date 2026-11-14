import {CAMERAS} from './domain';

export function FeedIllustration({id,sample=0}:{id:number;sample?:number}) {
  const mug = sample % 2 ? 244 : 188;
  return <svg viewBox="0 0 420 250" preserveAspectRatio="xMidYMid slice" className="nw-feed-art" aria-hidden="true">
    <rect width="420" height="250" fill="#222"/>
    {id===1 ? <>
      <path d="M0 16 103 28H383L420 3V195L384 160H103L0 199Z" fill="#646464"/>
      <path d="M0 199 103 160H384L420 195V250H0Z" fill="#474747"/>
      <path d="M0 16 103 28v132L0 199ZM383 28 420 3v192l-37-35Z" fill="#414141"/>
      <path d="M113 124h251l37 30H95Z" fill="#a4a4a4"/><path d="M95 154h306v6H95Zm14 6h7v60h-7Zm267 0h7v58h-7Z" fill="#303030"/>
      <path d="M140 127v-17l15-31h23l6 6h-24l-13 26v16ZM129 131h29v4h-29Z" fill="#262626"/>
      <path d="M220 135h27l11 7h-39Z" fill="#393939"/>
      <path d="M319 125h20l-3 12h-14Z" fill="#292929"/><path d="M329 126q-2-38-15-34 0 14 15 20 9-24 19-18-2 11-17 23" fill="#303030"/>
      <path d={`M${mug} 126h11v10h-11Zm11 2q9-3 4 6h-4`} fill="#e0e0e0" stroke="#bbb"/>
      <path d="M195 44h73v50h-73z" fill="#333"/><path d="M200 49h63v40h-63z" fill="#858585"/><path d="m201 84 19-21 10 10 8-7 23 18" stroke="#444" fill="none"/>
    </> : id===2 ? <>
      <path d="M0 18 278 36 420 0v197l-142-29L0 208Z" fill="#5b5b5b"/><path d="M278 36 420 0v197l-142-29Z" fill="#3b3b3b"/>
      <path d="M0 208 278 168 420 197v53H0Z" fill="#777"/>
      <path d="M37 49 191 54v108l-154 21Z" fill="#282828"/><path d="M46 58 182 62v92l-136 18Z" fill="#454545"/>
      {[80,107,134,161].map((y,i)=><path key={y} d={`M47 ${y}l134 ${i* -6+2}v5l-134 ${i*6-2}Z`} fill="#252525"/>)}
      {[56,69,89,112,127,138,153,164].map((x,i)=><path key={x} d={`M${x} ${89+i%3*2}v14h${7+i%3*2}V${89+i%3*2}`} fill={['#888','#aaa','#666'][i%3]}/>)}
      <path d="m322 52 54-13v134l-54-10Z" fill="#272727"/><path d="m330 60 39-9v112l-39-5Z" fill="#777"/><circle cx="359" cy="115" r="3" fill="#252525"/>
    </> : id===3 ? <>
      <path d="M0 0 171 35h249v156l-249-26L0 202Z" fill="#595959"/><path d="M0 0 171 35v130L0 202Z" fill="#3b3b3b"/>
      <path d="M0 202 171 165l249 26v59H0Z" fill="#797979"/>
      <path d="M224 48h141v79H224Z" fill="#292929"/><path d="M231 55h127v65H231Z" fill="#aeaeae"/><path d="m282 55 26 65m9-65 28 65" stroke="#ccc" strokeWidth="9"/><path d="M291 55v65m-60-33h127" stroke="#444" strokeWidth="4"/>
      <path d="m48 137 80-12 44 29-86 17Z" fill="#9b9b9b"/><path d="M86 171v37m76-58v37m-105-45v31" stroke="#333" strokeWidth="6"/>
      <path d="m285 176 46-4 26 20-55 8Z" fill="#474747"/><path d="M301 199v25m50-32v22" stroke="#303030" strokeWidth="5"/>
    </> : <>
      <path d="M0 0h420v250H0Z" fill="#767676"/>
      <path d="M0 45h420M0 100h420M0 155h420M0 210h420M70 0v45m0 55v55m0 55v40M210 0v45m0 55v55m0 55v40M350 0v45m0 55v55m0 55v40M135 45v55m0 55v55m140-165v55m0 55v55" stroke="#505050" fill="none"/>
      <path d="M-18 68 124 30l36 153L12 218Z" fill="#3c3c3c" stroke="#aaa" strokeWidth="3"/>
      <path d="m11 80 101-27 27 119L26 200Z" fill="none" stroke="#666" strokeWidth="3"/>
      <circle cx="241" cy="140" r="33" fill="#505050"/><circle cx="237" cy="135" r="26" fill="#262626"/>
      <circle cx="237" cy="135" r="11" fill="#9d9d9d"/>
    </>}
    <path d="M20 38V20h18m344 0h18v18M20 212v18h18m344 0h18v-18M202 125h16m-8-8v16" stroke="#eee" strokeOpacity=".53" fill="none"/>
  </svg>;
}

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
