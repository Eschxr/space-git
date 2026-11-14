import type {Metadata} from 'next';
import World from '../world/workbench';
export const metadata: Metadata = {title:'SpaceGit / Project',description:'An office beyond the wall. Made for a second screen.'};
export default function Page(){return <World projector/>;}
