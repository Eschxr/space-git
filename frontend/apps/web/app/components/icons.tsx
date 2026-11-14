import Link from 'next/link';
const paths:Record<string,string>={
cube:'M12 2 21 7v10l-9 5-9-5V7l9-5ZM3 7l9 5 9-5m-9 5v10m-5-12V5m10 10 4-2',
grid:'M3 3h7v7H3zm11 0h7v7h-7zM3 14h7v7H3zm11 0h7v7h-7z',
live:'M2 12h5l3-7 4 14 3-7h5',history:'M3 12a9 9 0 1 1 3 6.7M3 5v7h7m2-5v5l3 2',
branch:'M6 6v12m0-2c0-6 12-3 12-10M4 4a2 2 0 1 0 4 0 2 2 0 0 0-4 0Zm12 0a2 2 0 1 0 4 0 2 2 0 0 0-4 0ZM4 20a2 2 0 1 0 4 0 2 2 0 0 0-4 0Z',
camera:'M4 6h4l2-3h4l2 3h4v14H4zm12 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
target:'M12 2v5m0 10v5M2 12h5m10 0h5M5 5h14v14H5z',arrow:'M4 12h15m-6-6 6 6-6 6',
external:'M13 4h7v7m0-7L9 15m9-2v7H4V6h7',
screen:'M3 4h18v13H3zm9 13v4m-4 0h8',check:'m5 12 4 4L19 6',chevron:'m9 5 7 7-7 7',
plus:'M12 5v14M5 12h14',download:'M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5',
bolt:'M13 2 4 14h7l-1 8 10-13h-7l1-7Z',lock:'M5 10h14v11H5zm3 0V6a4 4 0 0 1 8 0v4',
rotate:'M4 11a8 8 0 1 1 4 8m-4-8V5m0 6h6',menu:'M4 6h16M4 12h16M4 18h16',
};
export function Icon({name,size=18}:{name:string;size?:number}){return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]??paths.cube}/></svg>;}
export function Brand(){return <Link className="brand" href="/" aria-label="SpaceGit home"><span className="brand-glyph"><Icon name="cube" size={23}/></span><span>SPACE<span>GIT</span><small>VISUAL OPERATIONS</small></span></Link>;}
