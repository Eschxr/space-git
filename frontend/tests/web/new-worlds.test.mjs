import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compareScenes,commitDemo,demoCapture,EMPTY_HISTORY,explainDiff,sampleScene,sameSceneReference} from '../../apps/web/app/world/domain.ts';
import {AGENTS,Engine,navigation,validateCommand} from '../../apps/web/app/world/engine.ts';

test('fixture captures make linked immutable revisions with one moved object',()=>{
 const original=demoCapture(0,100,'initial'), later=demoCapture(1,105,'later');
 const first=commitDemo(EMPTY_HISTORY,original,'main','Baseline');
 const history=commitDemo(first,later,'main','Move mug');
 assert.deepEqual(history.commits[0].parents,['initial']);
 assert.equal(first.branches.main,'initial');
 assert.equal(history.branches.main,'later');
 assert.equal(history.commits[0].evidence.mode,'demo');
 assert.equal(commitDemo(history,later,'main','Repeated'),history);
 const rows=compareScenes(history.commits[1].scene,history.commits[0].scene);
 assert.equal(rows.filter(c=>c.kind==='moved').length,1);
 assert.match(explainDiff(rows,'wall-world-meters'),/Ceramic mug moved 1.10 m right.*3 objects are unchanged/);
 assert.doesNotMatch(explainDiff(rows,null),/1.10 m/);
});

test('edge differences are authoritative, and frames from different workspaces are incompatible',()=>{
 const before=sampleScene(0),after=sampleScene(1);
 assert.equal(compareScenes(before,after,[]).every(row=>row.kind==='unchanged'),true);
 assert.equal(sameSceneReference(before,{...after,wall:[9,3.1]}),false);
 assert.equal(sameSceneReference(before,{...after,workspace_id:'other'}),false);
 const change={kind:'removed',id:'mug',before:before.objects[2],after:null,fields:[]};
 assert.match(explainDiff(compareScenes(before,{...after,objects:after.objects.filter(x=>x.id!=='mug')},[change]),null),/Ceramic mug is absent from the later revision/);
});

test('scheduler validates actions, routes via the aisle, interpolates, sits and pauses',()=>{
 const engine=new Engine();
 const [ada]=AGENTS, actor=engine.actors.get(ada.id);
 assert.deepEqual(navigation({x:-2.8,z:-1.45},{x:2.8,z:-1.45}),[{x:-2.8,z:-.1},{x:2.8,z:-.1},{x:2.8,z:-1.45}]);
 assert.throws(()=>validateCommand({agent_id:ada.id,action:'work',target:'__proto__',duration_ms:1000},AGENTS));
 assert.throws(()=>validateCommand({agent_id:ada.id,action:'sit',target:'door',duration_ms:1000},AGENTS));
 assert.throws(()=>validateCommand({agent_id:ada.id,action:'walk',target:'door',duration_ms:0},AGENTS));
 engine.command({agent_id:ada.id,action:'sit',target:'desk_01',duration_ms:7000});
 engine.tick(.05);
 assert.deepEqual([actor.pose.z,actor.pose.sit],[-.35,0]);
 engine.running=true;
 engine.tick(.05);
 assert.ok(actor.pose.z<-.35&&actor.pose.z>-1.45);
 for(let i=0;i<50;i++)engine.tick(.05);
 assert.equal(actor.pose.action,'sit');
 assert.ok(actor.pose.sit>.95);
 engine.running=false;
 const paused={...actor.pose};
 engine.tick(1);
 assert.deepEqual(actor.pose,paused);
});
