import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compareScenes,explainDiff,sameSceneReference,realHistory,EMPTY_RIG} from '../../apps/web/app/world/domain.ts';

const scene={version:1,id:'recorded-wall',name:'Recorded wall',frame:'wall-world-meters',wall:[5,3],objects:[{id:'chair',name:'Chair',marker:10,x:1,y:1,angle:0,w:.5,h:1,d:.5}]};
test('recorded changes use authoritative edge differences and compatible references',()=>{
 const moved={...scene,objects:[{...scene.objects[0],x:2}]};
 assert.equal(compareScenes(scene,moved,[]).every(row=>row.kind==='unchanged'),true);
 assert.equal(sameSceneReference(scene,{...moved,wall:[9,3]}),false);
 assert.equal(sameSceneReference(scene,{...moved,workspace_id:'other'}),false);
 const rows=compareScenes(scene,moved);
 assert.match(explainDiff(rows,'wall-world-meters'),/Chair moved 1.00 m right/);
 assert.doesNotMatch(explainDiff(rows,null),/1.00 m/);
});
test('synthetic history is excluded without modifying retained records and disconnected feeds are offline',()=>{
 const fake={id:'old-fixture',scene,evidence:{mode:'demo'}};
 const real={id:'actual',scene,evidence:{mode:'live'}};
 const original={commits:[fake,real],branches:{main:'actual',old:'old-fixture'}};
 assert.deepEqual(realHistory(original),{commits:[real],branches:{main:'actual'}});
 assert.equal(original.commits.length,2);
 assert.equal(EMPTY_RIG.mode,'live');
 assert.ok(EMPTY_RIG.feeds.every(feed=>feed.status==='offline'));
});
