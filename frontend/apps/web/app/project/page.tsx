import type {Metadata} from 'next';
import World from '../world/workbench';
export const metadata: Metadata = {title:'SpaceGit / Project',description:'Project reconstructed geometry and add 3D features with Ollama.'};
export default function Page(){return <World projector/>;}
