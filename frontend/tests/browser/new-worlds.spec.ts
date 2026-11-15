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

test('one-click demo records, versions, reconstructs and projects without the edge',async({page},info)=>{
 const errors:string[]=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route(edgeURL+'/**',route=>route.abort());
 await page.goto('/');
 await page.getByRole('link',{name:'Start Demo',exact:true}).click();
 const guide=page.getByRole('region',{name:'Guided demo'});
 await expect(guide.getByText('Inspect the four feeds')).toBeVisible();
 await guide.getByRole('button',{name:'Pause demo'}).click();
 await expect(page.locator('.nw-feed')).toHaveCount(4);
 const advance=async (stage:string)=>{
  await guide.getByRole('button',{name:'Next stage'}).click();
  if(stage!=='Activate projector view'&&stage!=='Watch the office come alive') await expect(guide.getByText(stage,{exact:true})).toBeVisible();
 };
 await page.screenshot({path:info.outputPath('capture.png'),animations:'disabled'});
 await advance('Capture the initial state');
 await expect(page.getByText('SESSION',{exact:false}).first()).toBeVisible();
 await advance('Commit the initial state');
 await expect(page.getByRole('button',{name:/Baseline desk layout/})).toBeVisible();
 await advance('Capture and commit a changed scene');
 await advance('Compare the revisions');
 await expect(page.getByText(/Ceramic mug moved 1.10 m right/)).toBeVisible();
 await expect(page.getByText(/3 objects are unchanged/)).toBeVisible();
 await page.screenshot({path:info.outputPath('versions.png'),animations:'disabled'});
 await advance('Reconstruct the study');
 const scene=page.getByTestId('reconstruction');
 await expect(scene.locator('canvas')).toBeVisible();
 await page.getByRole('button',{name:'Ceramic mug'}).click();
 await expect(page.getByText('mug',{exact:true})).toBeVisible();
 await advance('Open the virtual office');
 await expect(page.getByTestId('projector-surface').locator('canvas')).toBeVisible();

 await advance('Activate projector view');
 await expect.poll(()=>page.evaluate(()=>document.fullscreenElement?.getAttribute('data-testid'))).toBe('projector-surface');
 await expect(page.getByTestId('projector-surface')).toHaveClass(/is-presenting/);
 await page.evaluate(()=>document.exitFullscreen());
 await advance('Watch the office come alive');
 await expect(page.getByText('RUNNING',{exact:true})).toBeVisible();
 await expect(page.getByText(/At work|On the move|Inspecting details/).first()).toBeVisible();
 const canvas=page.getByTestId('projector-surface').locator('canvas');
 const first=await canvas.screenshot({path:info.outputPath('office.png')});
 await expect.poll(async()=>!(await canvas.screenshot()).equals(first)).toBe(true);
 expect(errors).toEqual([]);
});

test('projector presets, commands, fullscreen and alignment pattern operate on the standalone route',async({page},info)=>{
 await page.goto('/project');
 await expect(page.getByRole('heading',{name:'Project',exact:true})).toBeVisible();
 await page.getByLabel('Viewing angle').selectOption('Corner');
 await page.getByRole('button',{name:'Add agent'}).click();
 await expect(page.getByText('Noor',{exact:false}).first()).toBeVisible();
 await page.getByText('Command an agent',{exact:true}).click();
 await page.getByRole('button',{name:'Send command'}).click();
 await expect(page.getByText('Command queued for Noor.')).toBeVisible();
 await page.getByRole('button',{name:'Pause',exact:true}).click();
 await page.getByRole('button',{name:'Test pattern'}).click();
 await page.getByRole('button',{name:'Fullscreen',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>!!document.fullscreenElement)).toBe(true);
 await expect(page.getByRole('img',{name:/Projection alignment grid/})).toBeVisible();
 await page.screenshot({path:info.outputPath('alignment.png'),animations:'disabled'});
 await page.evaluate(()=>document.exitFullscreen());
 await page.reload();
 await expect(page.getByLabel('Viewing angle')).toHaveValue('Corner');
});

test('the selected projector receives a separate fullscreen window controlled by Project',async({page})=>{
 await page.addInitScript(()=>{
  const main={left:0,top:0,width:1440,height:1000,availLeft:0,availTop:0,availWidth:1440,availHeight:960,label:'Laptop',isPrimary:true,devicePixelRatio:1};
  const external={left:1440,top:0,width:1920,height:1080,availLeft:1440,availTop:0,availWidth:1920,availHeight:1040,label:'HDMI projector',isPrimary:false,devicePixelRatio:1};
  Object.defineProperty(window,'getScreenDetails',{value:async()=>Object.assign(new EventTarget(),{currentScreen:main,screens:[main,external]})});
  const open=window.open.bind(window);
  window.open=(url,target,features)=>{
   document.documentElement.dataset.projectorPosition=features;
   return open(url,target,features);
  };
 });
 await page.goto('/project');
 await page.getByRole('button',{name:'Detect displays'}).click();
 await expect(page.getByLabel('Output display').locator('option:checked')).toHaveText(/HDMI projector/);
 const [output]=await Promise.all([
  page.waitForEvent('popup'),
  page.getByRole('button',{name:'Open projector window',exact:true}).click(),
 ]);
 await expect(page.locator('html')).toHaveAttribute('data-projector-position',/left=1440.*width=1920/);
 const surface=output.getByRole('main',{name:'Projector output'});
 await expect(surface.locator('canvas')).toBeVisible();
 const closedWall=surface.locator('.nw-portal-reveal');
 await expect(closedWall).toHaveAttribute('data-open','true');
 const firstWall=await closedWall.elementHandle();
 await output.getByRole('button',{name:'Enter fullscreen'}).click();
 await expect.poll(()=>output.evaluate(()=>document.fullscreenElement?.getAttribute('aria-label'))).toBe('Projector output');
 await expect.poll(()=>firstWall!.evaluate(element=>element.isConnected)).toBe(false);
 await expect(closedWall).toHaveAttribute('data-open','true');
 await expect.poll(async()=>Number(await closedWall.locator('.nw-portal-leaf-left').evaluate(element=>getComputedStyle(element).opacity))).toBeLessThan(.001);
 await expect(page.getByRole('heading',{name:'Project',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Test pattern'}).click();
 await expect(surface.getByRole('img',{name:/Projection alignment grid/})).toBeVisible();
 await page.getByRole('button',{name:'Blackout'}).click();
 await expect(surface.locator('[aria-label="Output blacked out"]')).toBeVisible();
 await page.getByRole('button',{name:'Show output'}).click();
 await expect(surface.locator('[aria-label="Output blacked out"]')).toHaveCount(0);
 await output.emulateMedia({reducedMotion:'reduce'});
 await page.getByRole('button',{name:'Virtual office'}).click();
 await expect(surface.locator('.nw-portal-reveal')).toHaveCount(0);
 await expect(surface.locator('canvas')).toBeVisible();
 await page.getByRole('button',{name:'Test pattern'}).click();
 await output.close();
 await expect(page.getByTestId('projector-surface').getByRole('img',{name:/Projection alignment grid/})).toBeVisible();
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
 await page.getByRole('button',{name:'Physical world',exact:true}).click();
 await expect(page.getByTestId('projector-surface').locator('canvas')).toBeVisible();
 await page.getByRole('navigation',{name:'New Worlds workflow'}).getByRole('button',{name:'Reconstruct'}).click();
 await upload.setInputFiles({name:'bad.ply',mimeType:'application/octet-stream',buffer:Buffer.from('invalid')});
 await expect(page.getByRole('alert').filter({hasText:'Provide a PLY'})).toBeVisible();
 await page.getByRole('button',{name:'Return to layout'}).click();
 await expect(page.getByText(/Commit a snapshot or open/)).toBeVisible();
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth)).toBe(390);
});
