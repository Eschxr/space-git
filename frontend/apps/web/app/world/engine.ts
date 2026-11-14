export type Spot = {x:number; z:number; facing:number};
export const SPOTS = {
  desk_01:{x:-2.8,z:-1.45,facing:Math.PI}, desk_02:{x:0,z:-1.45,facing:Math.PI},
  desk_03:{x:2.8,z:-1.45,facing:Math.PI}, archive:{x:-4.1,z:1.35,facing:-Math.PI/2},
  door:{x:4.15,z:.95,facing:Math.PI/2}, meeting:{x:.25,z:1.75,facing:0},
} satisfies Record<string,Spot>;
export type Target = keyof typeof SPOTS;
export const ACTIONS = ['idle','walk','sit','stand','inspect','work','talk'] as const;
export type Action = typeof ACTIONS[number];
export type Command = {agent_id:string; action:Action; target:Target; duration_ms:number};
export type Agent = {id:string; name:string; role:string; home:Target; tone:string};
export const AGENTS: Agent[] = [
  {id:'researcher_01',name:'Ada',role:'Spatial researcher',home:'desk_01',tone:'#a0a0a0'},
  {id:'designer_02',name:'Lin',role:'World designer',home:'desk_02',tone:'#5b5b5b'},
  {id:'engineer_03',name:'Ivo',role:'Systems engineer',home:'desk_03',tone:'#d2d2d2'},
];
export const EXTRA_NAMES = ['Noor','Mika','Remy'];
export const STATUS: Record<Action,string> = {idle:'Taking a breath',walk:'On the move',sit:'Taking a seat',stand:'Standing up',inspect:'Inspecting details',work:'At work',talk:'In conversation'};

export function validateCommand(input: unknown, roster: Agent[]): Command {
  if (!input || typeof input !== 'object') throw Error('An action object is required.');
  const {agent_id, action, target, duration_ms} = input as Partial<Command>;
  if (!agent_id || !roster.some(agent => agent.id === agent_id) || !action || !ACTIONS.includes(action) ||
      !target || !Object.hasOwn(SPOTS,target) || !Number.isInteger(duration_ms) || duration_ms! < 500 || duration_ms! > 15000)
    throw Error('Choose a valid agent, action, target and duration (500–15000 ms).');
  if ((action === 'sit' || action === 'work') && !target.startsWith('desk_')) throw Error('Choose a desk for this action.');
  return {agent_id,action,target,duration_ms:duration_ms!};
}

export function plan(agent: Agent, index: number, turn: number): Command {
  const cycles: [Action, Target, number][][] = [
    [['work',agent.home,3600],['stand',agent.home,900],['inspect','archive',3100],['talk','meeting',4500],['sit',agent.home,1200]],
    [['inspect','desk_02',3300],['talk','meeting',4300],['walk','door',1600],['work',agent.home,5200],['idle',agent.home,1500]],
    [['walk','meeting',2100],['talk','meeting',5500],['inspect','door',2100],['sit',agent.home,1300],['work',agent.home,4000]],
  ];
  const cycle = cycles[index % cycles.length];
  const [action,target,duration_ms] = cycle[turn % cycle.length];
  return {agent_id:agent.id,action,target,duration_ms};
}

type Point = {x:number; z:number};
export type Pose = Point & {yaw:number; sit:number; step:number; action:Action; target:Target; time:number};
type Actor = {model:Agent; index:number; pose:Pose; turn:number; command:Command|null; route:Point[]; elapsed:number; lastSit:number; arrival:boolean};
const cone = (point: Point,index: number) => ({x:point.x+Math.cos(index*2.4)*.54,z:point.z+Math.sin(index*2.4)*.54});
// Desk and archive access use a clear aisle in front of the workstations.
export function navigation(from: Point, to: Point): Point[] {
  if (Math.hypot(to.x-from.x,to.z-from.z) < .04) return [];
  const route: Point[] = [];
  if (from.z < -.65 && Math.abs(from.x-to.x) > .38) route.push({x:from.x,z:-.1});
  if (to.z < -.65 && Math.abs(from.x-to.x) > .38) route.push({x:to.x,z:-.1});
  return [...route,{...to}];
}
const approach = (current:number,next:number,speed:number) => current + (next-current)*Math.min(1,speed);
const turnTo = (from:number,to:number,speed:number) => from + Math.atan2(Math.sin(to-from),Math.cos(to-from))*Math.min(1,speed);

export class Engine {
  actors = new Map<string,Actor>();
  running = false;
  constructor(roster: Agent[] = AGENTS){roster.forEach(agent=>this.add(agent));}
  add(model:Agent) {
    if (this.actors.has(model.id)) return;
    const index = this.actors.size;
    this.actors.set(model.id,{model,index,turn:0,command:null,route:[],elapsed:0,lastSit:0,arrival:false,
      pose:{x:[-2.8,.15,2.8,-2,2,-.5][index%6],z:[-.35,1.18,-.35,1.1,1.4,2.5][index%6],yaw:Math.PI,sit:0,step:0,action:'idle',target:model.home,time:0}});
  }
  command(raw: unknown) {
    const command = validateCommand(raw,[...this.actors.values()].map(actor=>actor.model));
    this.assign(this.actors.get(command.agent_id)!,command);
  }
  private assign(actor:Actor,command:Command) {
    const spot = SPOTS[command.target];
    actor.command = command;
    actor.route = navigation(actor.pose, command.target === 'meeting' ? cone(spot,actor.index) : {x:spot.x + (actor.index >= 3 && command.target.startsWith('desk_') ? .48 : 0), z:spot.z});
    actor.elapsed = 0;
    actor.arrival = false;
    actor.pose.target = command.target;
  }
  tick(dt:number) {
    if (!this.running) return;
    dt = Math.max(0, Math.min(.05,dt));
    this.actors.forEach(actor=>{
      const {pose} = actor;
      if (!actor.command) this.assign(actor,plan(actor.model,actor.index,actor.turn++));
      const command = actor.command!;
      pose.time += dt;
      const waypoint = actor.route[0];
      if (waypoint) {
        pose.action = 'walk';
        pose.sit = approach(pose.sit,0,dt*6);
        if (pose.sit > .12) return;
        const dx = waypoint.x-pose.x, dz = waypoint.z-pose.z, distance = Math.hypot(dx,dz), stride = dt*1.45;
        if (distance <= stride) { pose.x = waypoint.x;pose.z = waypoint.z;actor.route.shift(); }
        else {pose.x += stride*dx/distance;pose.z += stride*dz/distance;}
        pose.yaw = turnTo(pose.yaw,Math.atan2(dx,dz),dt*10);
        pose.step += dt*10;
        return;
      }
      if (!actor.arrival) {actor.arrival=true;actor.lastSit=pose.sit;}
      actor.elapsed += dt*1000;
      pose.action = command.action === 'walk' ? 'idle' : command.action;
      const seat = command.action === 'sit' || command.action === 'work' ? 1 : command.action === 'idle' ? actor.lastSit : 0;
      pose.sit = approach(pose.sit,seat,dt*5);
      const to = SPOTS[command.target];
      pose.yaw = turnTo(pose.yaw,command.target==='meeting' ? Math.atan2(to.x-pose.x,to.z-pose.z) : to.facing,dt*7);
      if (actor.elapsed >= command.duration_ms) actor.command = null;
    });
  }
}
