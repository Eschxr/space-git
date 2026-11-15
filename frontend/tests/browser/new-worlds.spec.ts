import {expect,test} from '@playwright/test';
const edgeURL=process.env.SPACEGIT_TEST_EDGE_URL ?? 'http://127.0.0.1:8000';

test('Capture connects, saves the camera sequence and refreshes the floor preview',async({page,baseURL})=>{
 const origin=new URL(baseURL!).origin;
 test.skip(!['127.0.0.1','localhost'].includes(new URL(origin).hostname),'Live controls require the local web build.');
 let settings={sources:[null,null,null,null] as (number|null)[],order:[1,2,3,4]};
 let enabled=false, frames=0, connected=false;
 const cors={'Access-Control-Allow-Origin':origin,'Access-Control-Allow-Headers':'authorization,content-type,x-spacegit-local','Access-Control-Allow-Methods':'GET,POST,OPTIONS'};
 const frame=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+WZkAAAAASUVORK5CYII=','base64');
 await page.route(edgeURL+'/api/v1/**',async route=>{
  const request=route.request(), path=new URL(request.url()).pathname.slice('/api/v1'.length);
  if(request.method()==='OPTIONS')return route.fulfill({status:204,headers:cors});
  const json=(value:unknown)=>route.fulfill({json:value,headers:cors});
  const rig=()=>({mode:'live',enabled,settings,feeds:[1,2,3,4].map(id=>({
   id,status:settings.sources[id-1]!==null ? enabled?'live':'offline' : 'unmapped',age_ms:4,
  }))});
  if(path==='/local-session'){connected=request.headers()['x-spacegit-local']==='1';return json({token:'test-connection'});}
  if(path==='/rig/settings'){settings=request.postDataJSON();return json(rig());}
  if(path==='/rig/start'){enabled=true;return json(rig());}
  if(path==='/rig')return json(rig());
  if(path==='/rig/frames/4'){frames++;return route.fulfill({body:frame,contentType:'image/png',headers:cors});}
  if(path==='/devices')return json({cameras:[{index:0,label:'USB Floor Camera'}]});
  if(path==='/commits')return json({branches:{},commits:[]});
  if(path==='/reconstructions')return json({jobs:[],colmap:false});
  return json([]);
 });
 await page.goto('/world');
 const connect=page.getByRole('button',{name:'Connect cameras'});
 await expect(connect).toBeVisible();
 await connect.click();
 await page.getByText('Edit camera sequence',{exact:true}).click();
 const floor=page.getByLabel(/Camera 4.*Floor view/);
 await expect(floor.getByRole('option',{name:/USB Floor Camera/})).toHaveCount(1);
 await floor.selectOption('0');
 const move=page.getByRole('button',{name:'Move camera 4 earlier'});
 await move.click();
 await move.click();
 await move.click();
 await page.getByRole('button',{name:'Save sequence'}).click();
 await expect(page.getByText('Camera sequence saved.')).toBeVisible();
 expect(connected).toBe(true);
 expect(settings).toEqual({sources:[null,null,null,0],order:[4,1,2,3]});
 await page.getByRole('button',{name:'Start live previews'}).click();
 const first=page.locator('.nw-feed').first();
 await expect(first.getByRole('heading',{name:'Floor'})).toBeVisible();
 await expect(first.getByRole('img',{name:'Camera 4 preview'})).toBeVisible();
 await expect.poll(()=>frames).toBeGreaterThan(2);
 await page.reload();
 await expect(first.getByRole('img',{name:'Camera 4 preview'})).toBeVisible();
});

test('real workspace has no synthetic capture, saved fixture history or guided demo entry point',async({page})=>{
 const stored=JSON.stringify({captures:[{id:'fixture',mode:'demo'}],history:{commits:[{id:'fixture',message:'Fabricated history'}],branches:{main:'fixture'}}});
 await page.addInitScript(value=>localStorage.setItem('spacegit.newworlds.workspace.v1',value),stored);
 await page.goto('/world?demo=1');
 await expect(page.getByRole('button',{name:'Start Demo'})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Capture session',exact:true})).toBeDisabled();
 await expect(page.getByText('No sessions yet.',{exact:false})).toBeVisible();
 await expect(page.locator('.nw-feed-art')).toHaveCount(0);
 await page.keyboard.press('d');
 await expect(page.getByRole('region',{name:'Guided demo'})).toHaveCount(0);
 await page.getByRole('button',{name:'Version control',exact:false}).click();
 await expect(page.getByText('No revisions yet.',{exact:false})).toBeVisible();
 expect(await page.evaluate(()=>localStorage.getItem('spacegit.newworlds.workspace.v1'))).toBe(stored);
 await page.goto('/studio/3d');
 await expect(page.getByRole('heading',{name:'No recorded scene'})).toBeVisible();
 await expect(page.locator('canvas')).toHaveCount(0);
 await page.goto('/');
 await expect(page.getByRole('link',{name:'Start Demo'})).toHaveCount(0);
});

test('a simulated edge is rejected before its history or frames can enter the workspace',async({page,baseURL})=>{
 let historyReads=0;
 const cors={'Access-Control-Allow-Origin':new URL(baseURL!).origin,'Access-Control-Allow-Headers':'authorization,content-type,x-spacegit-local','Access-Control-Allow-Methods':'GET,POST,OPTIONS'};
 await page.route(edgeURL+'/api/v1/**',async route=>{
  if(route.request().method()==='OPTIONS')return route.fulfill({status:204,headers:cors});
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/local-session'))return route.fulfill({headers:cors,json:{token:'test-live-only-connection'}});
  if(path.endsWith('/rig'))return route.fulfill({headers:cors,json:{mode:'demo',enabled:true,feeds:[{id:1,status:'simulated'}]}});
  if(path.endsWith('/commits'))historyReads++;
  return route.fulfill({headers:cors,json:[]});
 });
 await page.goto('/world');
 await page.getByRole('button',{name:'Connect cameras'}).click();
 await expect(page.getByRole('alert').filter({hasText:'Start the edge in live mode'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Capture session',exact:true})).toBeDisabled();
 await expect(page.locator('.nw-feed-art')).toHaveCount(0);
 expect(historyReads).toBe(0);
});

test('projector controls, fullscreen and alignment pattern operate without fabricated geometry',async({page},info)=>{
 await page.goto('/project');
 await expect(page.getByText('Connect the local edge to load the current reconstruction.',{exact:true})).toBeVisible();
 await expect(page.locator('canvas')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'+ sphere',exact:true})).toBeDisabled();
 await page.getByRole('checkbox',{name:'Reduce quality'}).check();
 await page.getByRole('button',{name:'Test pattern'}).click();
 await page.getByRole('button',{name:'Fullscreen',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>!!document.fullscreenElement)).toBe(true);
 await expect(page.getByRole('img',{name:/Projection alignment grid/})).toBeVisible();
 await page.screenshot({path:info.outputPath('alignment.png'),animations:'disabled'});
 await page.evaluate(()=>document.exitFullscreen());
 await page.reload();
 await expect(page.getByRole('checkbox',{name:'Reduce quality'})).toBeChecked();
});

test('the connected projector receives the loaded model with a separate fullscreen output',async({page})=>{
 await page.addInitScript(()=>{
  const main={left:0,top:0,width:1440,height:1000,availLeft:0,availTop:0,availWidth:1440,availHeight:960,label:'Laptop',isPrimary:true,devicePixelRatio:1};
  const external={left:1440,top:0,width:1920,height:1080,availLeft:1440,availTop:0,availWidth:1920,availHeight:1040,label:'HDMI projector',isPrimary:false,devicePixelRatio:1};
  Object.defineProperty(window,'getScreenDetails',{value:async()=>Object.assign(new EventTarget(),{currentScreen:main,screens:[main,external]})});
  const open=window.open.bind(window);window.open=(url,target,features)=>{document.documentElement.dataset.projectorPosition=features;return open(url,target,features);};
 });
 await page.goto('/project');
 await page.getByLabel('Open reconstructed scene').setInputFiles({name:'source.ply',mimeType:'application/octet-stream',buffer:Buffer.from('ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 0\n1 0 0\n0 1 0\n')});
 await page.getByRole('button',{name:'Detect displays'}).click();
 await expect(page.getByLabel('Output display').locator('option:checked')).toHaveText(/HDMI projector/);
 const [output]=await Promise.all([page.waitForEvent('popup'),page.getByRole('button',{name:'Open projector window',exact:true}).click()]);
 await expect(page.locator('html')).toHaveAttribute('data-projector-position',/left=1440.*width=1920/);
 const surface=output.getByRole('main',{name:'Projector output'});
 await expect(surface.locator('canvas')).toBeVisible();
 await output.getByRole('button',{name:'Enter fullscreen'}).click();
 await expect.poll(()=>output.evaluate(()=>document.fullscreenElement?.getAttribute('aria-label'))).toBe('Projector output');
 await expect(page.getByLabel('Live projector preview')).toBeVisible();
 await page.getByRole('button',{name:'Test pattern'}).click();
 await expect(surface.getByRole('img',{name:/Projection alignment grid/})).toBeVisible();
 await page.getByRole('button',{name:'Blackout'}).click();
 await expect(surface.getByLabel('Output blacked out')).toBeVisible();
 await page.getByRole('button',{name:'Show output'}).click();
 await expect(surface.getByLabel('Output blacked out')).toHaveCount(0);
 await page.getByRole('button',{name:'Test pattern'}).click();
 await expect(surface.locator('canvas')).toBeVisible();
 await output.close();
 await expect(page.getByTestId('projector-surface').locator('canvas')).toBeVisible();
});

test('PLY loading, parse failure and recovery on a narrow viewport',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto('/world');
 await page.getByRole('button',{name:'Reconstruct',exact:false}).first().click();
 const upload=page.getByLabel('Open local model');
 await upload.setInputFiles({name:'one.ply',mimeType:'application/octet-stream',buffer:Buffer.from('ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 0\n1 0 0\n0 1 0\n')});
 await expect(page.getByText('Geometry loaded.')).toBeVisible();
 await expect(page.getByTestId('reconstruction').locator('canvas')).toBeVisible();
 await expect(page.getByRole('checkbox',{name:'Point cloud'})).toBeChecked();
 await page.getByRole('button',{name:'Open projector view'}).click();
 await expect(page.getByTestId('projector-surface').locator('canvas')).toBeVisible();
 await page.getByRole('navigation',{name:'Workspace workflow'}).getByRole('button',{name:'Reconstruct'}).click();
 await upload.setInputFiles({name:'bad.ply',mimeType:'application/octet-stream',buffer:Buffer.from('invalid')});
 await expect(page.getByRole('alert').filter({hasText:'Provide a PLY'})).toBeVisible();
 await page.getByRole('button',{name:'Return to layout'}).click();
 await expect(page.getByText(/Commit a snapshot or open/)).toBeVisible();
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth)).toBe(390);
});
