import type {Metadata,Viewport} from 'next';
import '@fontsource-variable/inter';
import './styles.css';
export const metadata:Metadata={title:'SpaceGit — Version control for physical space',description:'Record your wall, compare layouts, and project a verified route back.',icons:'/mark.svg',manifest:'/manifest.webmanifest',referrer:'no-referrer'};
export const viewport:Viewport={themeColor:'#0B111A'};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>;}
