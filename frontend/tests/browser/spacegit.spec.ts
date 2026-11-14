import {expect,test} from '@playwright/test';
import {testToken} from '../../playwright.config';
import {readFile} from 'node:fs/promises';

test('landing preview and interactive studio render with honest provenance',async({page},info)=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'Version control for physical space.'})).toBeVisible();
 await page.getByRole('button',{name:'Preview next object'}).click();
 await expect(page.getByText('Exhibit B',{exact:false})).toBeVisible();
 await page.screenshot({path:info.outputPath('landing.png'),fullPage:true,animations:'disabled'});
 await page.getByRole('link',{name:'Launch Studio'}).last().click();
 await expect(page.getByRole('heading',{name:'Scene overview'})).toBeVisible();
 await expect(page.getByText('DEMO / READ ONLY')).toBeVisible();
 await expect(page.locator('canvas')).toBeVisible();
 await page.getByRole('button',{name:/Exhibit C/}).click();
 await expect(page.getByText('OBJECT / c')).toBeVisible();
 await page.screenshot({path:info.outputPath('studio.png'),fullPage:true,animations:'disabled'});
 expect(errors).toEqual([]);
});

test('local pairing, restore replay, commit/diff, GLB round trip and phone-sized upload',async({page,request},info)=>{
 await page.goto('/setup');
 await page.getByLabel('Operator key').fill(testToken);
 await page.getByRole('button',{name:'Connect',exact:true}).click();
 await expect(page.getByText('DEMO / SIMULATED')).toBeVisible();
 await page.getByRole('link',{name:'Live tracking',exact:true}).click();
 await page.getByLabel('Position tolerance (mm)').fill('18');
 await page.getByLabel('Stable dwell (s)').fill('0.8');
 await page.getByRole('button',{name:'Replay one move'}).click();
 await expect(page.getByText('Move to target',{exact:false})).toBeVisible();
 const timestamp=await page.locator('.projection-preview svg').getAttribute('aria-label');
 expect(timestamp).toBe('Projection guidance');
 await expect(page.getByText('Revision deployed',{exact:true})).toBeVisible();
 await expect(page.getByText(/0\.\d+ s dwell · simulated/)).toBeVisible();
 await page.screenshot({path:info.outputPath('verified-demo.png'),fullPage:true,animations:'disabled'});

 await page.getByRole('link',{name:'3D workspace'}).click();
 await expect(page.locator('canvas')).toBeVisible();
 const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Export GLB'}).click()]);
 const path=info.outputPath('round-trip.glb');
 await download.saveAs(path);
 const buf=await readFile(path);
 expect(buf.subarray(0,4).toString()).toBe('glTF');
 const meta=JSON.parse(buf.subarray(20,20+buf.readUInt32LE(12)).toString());
 expect(meta.nodes.some((n:{extras?:{stable_id?:string}})=>n.extras?.stable_id==='a')).toBe(true);
 const [screenshot]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Export screenshot'}).click()]);
 const screenshotPath=info.outputPath('viewport-export.png');
 await screenshot.saveAs(screenshotPath);
 expect((await readFile(screenshotPath)).subarray(1,4).toString()).toBe('PNG');
 await page.getByLabel('Import model').setInputFiles(path);
 await expect(page.getByText('Imported scene with 6 stable object IDs.')).toBeVisible();
 await page.getByLabel('X (m)',{exact:true}).fill('0.52');
 await page.getByLabel('Commit message').fill('Browser layout edit');
 await page.getByRole('button',{name:'Commit layout',exact:true}).click();
 await expect(page.getByText(/Saved revision/)).toBeVisible();
 await page.getByRole('link',{name:'History',exact:true}).click();
 await page.getByRole('button',{name:'Show object diff'}).click();
 await expect(page.getByText('changed x')).toBeVisible();

 await page.setViewportSize({width:390,height:844});
 await page.goto('/studio/capture');
 await expect(page.getByRole('heading',{name:'Phone capture'})).toBeVisible();
 const pixels=await page.evaluate(()=>{
  const canvas=document.createElement('canvas');canvas.width=640;canvas.height=480;
  const ctx=canvas.getContext('2d')!;ctx.fillStyle='#55ff95';ctx.fillRect(0,0,640,480);
  return canvas.toDataURL('image/png').split(',')[1];
 });
 await page.getByLabel('Choose photos').setInputFiles({name:'capture.png',mimeType:'image/png',buffer:Buffer.from(pixels,'base64')});
 await page.getByRole('button',{name:'Upload 1 photo'}).click();
 await expect(page.getByText('1 photo(s) attached to the revision.')).toBeVisible();
 const r=await request.get('http://127.0.0.1:8000/api/v1/capture/photos',{headers:{Authorization:'Bearer '+testToken}});
 expect((await r.json()).length).toBeGreaterThan(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
 await page.screenshot({path:info.outputPath('capture-mobile.png'),fullPage:true,animations:'disabled'});
});

test('Spatial Merge previews three layouts and requires approval of the current candidate',async({page,request},info)=>{
 const base='http://127.0.0.1:8000/api/v1',headers={Authorization:'Bearer '+testToken};
 const history=await (await request.get(base+'/commits',{headers})).json(),seed=history.commits.at(-1);
 for(const [name,x] of [['review-target',.55],['review-source',.59]] as const){
  expect((await request.post(base+'/branches',{headers,data:{name,commit:seed.id}})).ok()).toBe(true);
  const scene=structuredClone(seed.scene);scene.objects[0].x=x;
  expect((await request.post(base+'/commits',{headers,data:{branch:name,expected:seed.id,message:name,scene}})).ok()).toBe(true);
 }
 await page.goto('/setup');await page.getByLabel('Operator key').fill(testToken);await page.getByRole('button',{name:'Connect',exact:true}).click();
 await expect(page.getByText('DEMO / SIMULATED',{exact:true})).toBeVisible();
 await page.getByRole('link',{name:'Branch & merge'}).click();
 await page.getByRole('combobox',{name:'Target',exact:true}).selectOption('review-target');
 await page.getByRole('combobox',{name:'Source',exact:true}).selectOption('review-source');
 await page.getByRole('button',{name:'Preview merge'}).click();
 await expect(page.getByRole('img',{name:/Candidate layout/})).toBeVisible();
 await expect(page.getByText(/Both branches changed Exhibit A/)).toBeVisible();
 await page.getByRole('combobox',{name:'Conflict · a',exact:true}).selectOption('source');
 await expect(page.getByRole('button',{name:'Create merge revision'})).toBeDisabled();
 await page.getByRole('button',{name:'Recalculate candidate'}).click();
 await expect(page.getByText(/Using source for conflicting fields/)).toBeVisible();
 await page.screenshot({path:info.outputPath('spatial-merge.png'),fullPage:true,animations:'disabled'});
 await page.getByText('I approve the candidate placement.').click();
 await page.getByRole('button',{name:'Create merge revision'}).click();
 await expect(page.getByText(/Created merge revision/)).toBeVisible();
 const after=await (await request.get(base+'/commits',{headers})).json();
 const merged=after.commits.find((c:{id:string})=>c.id===after.branches['review-target']);
 expect(merged.parents).toHaveLength(2);
 expect(merged.scene.objects[0].x).toBe(.59);
});

test('bundled guidance rehearsal works without operator access',async({page},info)=>{
 const privateRequests:string[]=[];
 page.on('request',r=>{if(new URL(r.url()).port==='8000')privateRequests.push(r.url());});
 page.on('websocket',s=>privateRequests.push(s.url()));
 await page.goto('/studio/live');
 await page.getByRole('button',{name:'Play simulated move'}).click();
 await expect(page.getByText('Replay verified · simulated only')).toBeVisible();
 expect(privateRequests).toEqual([]);
 await page.screenshot({path:info.outputPath('public-rehearsal.png'),fullPage:true,animations:'disabled'});
});

test('real reconstructed GLB opens as an independent visual layer',async({page},info)=>{
 const file=process.env.SPACEGIT_TEST_GLB;
 test.skip(!file,'Set SPACEGIT_TEST_GLB to the locally reconstructed GLB.');
 await page.goto('/studio/3d');
 await page.getByLabel('Import model').setInputFiles(file!);
 await expect(page.getByRole('heading',{name:'Visual geometry layer'})).toBeVisible();
 await expect(page.getByText('VISUAL GEOMETRY / RAW FRAME',{exact:false})).toBeVisible();
 await expect(page.locator('canvas')).toBeVisible();
 await page.screenshot({path:info.outputPath('reconstructed-mesh.png'),fullPage:true,animations:'disabled'});
 await page.getByLabel('Known reference (m)').fill('0.5');
 await page.getByLabel('Same span in model units').fill('2');
 await page.getByRole('button',{name:'Apply reference scale'}).click();
 await expect(page.getByLabel('Scale factor')).toHaveValue('0.25');
 await expect(page.getByText('OBJECT / a')).toBeVisible();
});
