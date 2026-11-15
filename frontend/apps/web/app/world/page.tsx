import type {Metadata} from 'next';
import World from './workbench';
export const metadata: Metadata = {title:'SpaceGit / New Worlds',description:'Capture a room, compare spatial revisions, and project reconstructed geometry.'};
export default function Page(){return <World/>;}
