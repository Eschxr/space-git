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
 await expect(page.getByRole('link',{name:'Hardware studio'})).toHaveCount(0);
 await page.getByRole('button',{name:/^Start Demo/}).click();
 const guide=page.getByRole('region',{name:'Guided demo'});
 await expect(guide.getByText('Inspect the four feeds')).toBeVisible();
 await guide.getByRole('button',{name:'Pause demo'}).click();
 await expect(page.locator('.nw-feed')).toHaveCount(4);
 const advance=async (stage:string)=>{
  await guide.getByRole('button',{name:'Next stage'}).click();
  if(stage!=='Activate projector view') await expect(guide.getByText(stage,{exact:true})).toBeVisible();
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
 await advance('Open the reconstructed study');
 await expect(page.getByTestId('projector-surface').locator('canvas')).toBeVisible();

 await advance('Activate projector view');
 await expect.poll(()=>page.evaluate(()=>document.fullscreenElement?.getAttribute('data-testid'))).toBe('projector-surface');
 await expect(page.getByTestId('projector-surface')).toHaveClass(/is-presenting/);
 await page.evaluate(()=>document.exitFullscreen());
 await expect(page.getByTestId('projector-surface').locator('canvas')).toBeVisible();
 expect(errors).toEqual([]);
});

test('projector controls and chat operate on the standalone route',async({page})=>{
 await page.goto('/project');
 await expect(page.getByRole('heading',{name:'Project',exact:true})).toBeVisible();
 await expect(page.getByRole('heading',{name:'World engine',exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:/Virtual office|Test pattern/})).toHaveCount(0);
 const chat=page.getByRole('region',{name:'Projector chat'});
 await chat.getByLabel('Message').fill('blackout');
 await chat.getByRole('button',{name:'Send',exact:true}).click();
 await expect(chat.getByRole('log')).toContainText('Output blacked out.');
 await page.getByRole('button',{name:'Fullscreen',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>!!document.fullscreenElement)).toBe(true);
 await expect(page.getByLabel('Output blacked out')).toBeVisible();
 await page.evaluate(()=>document.exitFullscreen());
 await page.reload();
 await expect(chat.getByRole('button',{name:'Generate 3D object'})).toBeVisible();
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
 await expect(surface.getByText(/Open a reconstruction/)).toBeVisible();
 await output.getByRole('button',{name:'Enter fullscreen'}).click();
 await expect.poll(()=>output.evaluate(()=>document.fullscreenElement?.getAttribute('aria-label'))).toBe('Projector output');
 await expect(page.getByRole('heading',{name:'Project',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Blackout'}).click();
 await expect(surface.locator('[aria-label="Output blacked out"]')).toBeVisible();
 await page.getByRole('button',{name:'Show output'}).click();
 await expect(surface.locator('[aria-label="Output blacked out"]')).toHaveCount(0);
 await output.close();
 await expect(page.getByTestId('projector-surface').getByText(/Open a reconstruction/)).toBeVisible();
});

test('Project switches between saved versions in its existing projector window',async({page,baseURL})=>{
 const origin=new URL(baseURL!).origin;
 test.skip(!['127.0.0.1','localhost'].includes(new URL(origin).hostname),'The saved models live on the local edge.');
 const headers={'Access-Control-Allow-Origin':origin,'Access-Control-Allow-Headers':'authorization,content-type,x-spacegit-local','Access-Control-Allow-Methods':'GET,POST,OPTIONS'};
 const versions=['recent-capture','earlier-capture'].map((id,index)=>({id,capture_id:id,created:1720000000-index,files:[]}));
 const ply=(count:number)=>'ply\nformat ascii 1.0\nelement vertex '+count+'\nproperty float x\nproperty float y\nproperty float z\nend_header\n'+Array.from({length:count},(_,i)=>i+' '+i+' 0').join('\n')+'\n';
 const saved=new Map<string,Record<string,unknown>[]>();
 let moves=0;
 let lampRequested=false;
 let finishLamp=()=>{};
 const lampPending=new Promise<void>(resolve=>{finishLamp=resolve;});
 await page.route(edgeURL+'/api/v1/**',async route=>{
  const request=route.request(),path=new URL(request.url()).pathname;
  const json=(value:unknown)=>route.fulfill({json:value,headers});
  if(request.method()==='OPTIONS')return route.fulfill({status:204,headers});
  if(path.endsWith('/local-session'))return json({token:'local-browser-test'});
  if(path.endsWith('/rig'))return json({mode:'live',enabled:false,feeds:[]});
  if(path.endsWith('/commits'))return json({branches:{},commits:[]});
  if(path.endsWith('/reconstructions'))return json({jobs:[],colmap:false});
  if(path.endsWith('/rig/models'))return json(versions);
  if(path.endsWith('/position')) {
   const key=path.split('/objects/')[0]+'/objects';
   const items=saved.get(key)!;
   const id=path.split('/').at(-2);
   const object=items.find(item=>item.id===id)!;
   expect(request.postDataJSON()).toEqual({offset:[1.25,.2,-.1]});
   const updated={...object,offset:request.postDataJSON().offset};
   saved.set(key,items.map(item=>item.id===id?updated:item));moves++;
   return json(updated);
  }
  if(path.endsWith('/objects')) {
   if(request.method()==='POST') {
    expect(path).toContain('rig-earlier-capture');
    const {prompt,request_id}=request.postDataJSON();
    const chair=prompt==='add a red chair on the left';
    const lamp=prompt==='add a green lamp';
    expect(chair||lamp||prompt==='add a blue table').toBe(true);
    if(lamp){lampRequested=true;await lampPending;}
    const object={id:request_id,name:chair?'Red chair':lamp?'Green lamp':'Blue table',prompt,placement:'left',height:.9,
     parts:[{shape:'box',color:chair?'#dd1122':lamp?'#397333':'#1233ee',position:[0,.5,0],size:[.5,.1,.5],rotation:[0,0,0]}]};
    saved.set(path,[...(saved.get(path)??[]),object]);
    return json(object);
   }
   return json(saved.get(path)??[]);
  }
  if(path.includes('/pointclouds/'))return route.fulfill({body:ply(path.includes('earlier-capture')?5:3),contentType:'application/octet-stream',headers});
  return json([]);
 });
 await page.goto('/world');
 await page.getByRole('button',{name:'Connect cameras'}).click();
 const nav=page.getByRole('navigation',{name:'New Worlds workflow'});
 await nav.getByRole('button',{name:/Reconstruct/}).click();
 await expect(page.getByText(/Loaded Floor, Radial A, Radial B and Radial C/)).toBeVisible();
 await expect(page.getByRole('button',{name:'Scene revision',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Open projector view'}).click();
 const picker=page.getByLabel('Model version');
 await expect(picker.locator('option[value="rig:recent-capture"]')).toHaveCount(1);
 const [output]=await Promise.all([page.waitForEvent('popup'),page.getByRole('button',{name:'Open projector window'}).click()]);
 const frame=output.frameLocator('iframe[title="Projected camera reconstruction"]');
 await expect(frame.locator('#info')).toContainText('3 points');
 await picker.selectOption('rig:earlier-capture');
 await expect(frame.locator('#info')).toContainText('5 points');
 await expect(frame.locator('#panel')).toBeHidden();
 const chat=page.getByRole('region',{name:'Projector chat'});
 const generated=page.getByRole('region',{name:'Generated objects'});
 await chat.getByLabel('Message').fill('what is showing?');
 await chat.getByRole('button',{name:'Send',exact:true}).click();
 await expect(chat.getByRole('log')).toContainText('Camera rig reconstruction');
 await chat.getByLabel('Message').fill('add a red chair on the left');
 await chat.getByRole('button',{name:'Send',exact:true}).click();
 await expect(chat.getByRole('log')).toContainText('Generated and saved Red chair');
 await expect(frame.locator('body')).toHaveAttribute('data-projected-objects','1');
 await page.getByRole('button',{name:'Edit position',exact:true}).click();
 const position=page.getByRole('form',{name:'Object position'});
 const setSlider=async (name:string,value:string)=>position.getByRole('slider',{name}).evaluate((element,next)=>{
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(element,next);
  element.dispatchEvent(new Event('input',{bubbles:true}));
 },value);
 await setSlider('X position','1.2');
 await setSlider('Y position','0.2');
 await setSlider('Z position','-0.1');
 const x=position.getByRole('slider',{name:'X position'});
 await x.focus();
 await x.dispatchEvent('wheel',{deltaY:-120});
 await expect(x).toHaveValue('1.25');
 expect(moves).toBe(0);
 await position.getByRole('button',{name:'Save position'}).click();
 await expect(position).toHaveCount(0);
 expect(moves).toBe(1);
 await page.getByRole('button',{name:'Restore original model',exact:true}).click();
 await expect(frame.locator('body')).toHaveAttribute('data-projected-objects','0');
 await expect(frame.locator('#info')).toContainText('5 points');
 await expect(generated.getByRole('listitem')).toHaveCount(0);
 await page.getByRole('button',{name:'Show generated objects',exact:true}).click();
 await expect(frame.locator('body')).toHaveAttribute('data-projected-objects','1');
 await expect(generated.getByRole('listitem')).toHaveCount(1);
 expect(moves).toBe(1);
 await picker.selectOption('rig:recent-capture');
 await expect(frame.locator('body')).toHaveAttribute('data-projected-objects','0');
 await picker.selectOption('rig:earlier-capture');
 await expect(frame.locator('body')).toHaveAttribute('data-projected-objects','1');
 await page.getByRole('button',{name:'Edit position',exact:true}).click();
 await expect(position.getByRole('slider',{name:'X position'})).toHaveValue('1.25');
 await expect(position.getByRole('slider',{name:'Y position'})).toHaveValue('0.2');
 await position.getByRole('button',{name:'Cancel',exact:true}).click();
 await chat.getByLabel('Message').fill('add a blue table');
 await chat.getByRole('button',{name:'Send',exact:true}).click();
 await expect(chat.getByRole('log')).toContainText('Generated and saved Blue table');
 await expect(page.getByRole('region',{name:'Generated objects'})).toContainText('Showing Blue table.');
 await expect(frame.locator('body')).toHaveAttribute('data-projected-objects','1');
 await page.getByRole('button',{name:'Show Red chair',exact:true}).click();
 await expect(page.getByRole('region',{name:'Generated objects'})).toContainText('Showing Red chair.');
 await expect(frame.locator('body')).toHaveAttribute('data-projected-objects','1');
 await chat.getByLabel('Message').fill('add a green lamp');
 await chat.getByRole('button',{name:'Send',exact:true}).click();
 try {
  await expect.poll(()=>lampRequested).toBe(true);
  await generated.getByRole('button',{name:'Restore original model',exact:true}).click();
  await expect(generated.getByRole('listitem')).toHaveCount(0);
  await expect(frame.locator('body')).toHaveAttribute('data-projected-objects','0');
 } finally {finishLamp();}
 await expect(chat.getByRole('log')).toContainText('Generated and saved Green lamp');
 await expect(generated.getByRole('listitem')).toHaveCount(0);
 await expect(frame.locator('body')).toHaveAttribute('data-projected-objects','0');
 await generated.getByRole('button',{name:'Show generated objects',exact:true}).click();
 await expect(generated.getByRole('listitem')).toHaveCount(3);
 await expect(generated.getByRole('status')).toHaveText('Showing Red chair.');
 await expect(frame.locator('body')).toHaveAttribute('data-projected-objects','1');
 await expect(output.getByRole('region',{name:'Projector chat'})).toHaveCount(0);
 await output.close();
});

test('PLY loading, parse failure and recovery on a narrow viewport',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto('/project');
 const upload=page.getByLabel('Add 3D models');
 await upload.setInputFiles({name:'one.ply',mimeType:'application/octet-stream',buffer:Buffer.from('ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 0\n1 0 0\n0 1 0\n')});
 await expect(page.getByRole('heading',{name:'one.ply',exact:true})).toBeVisible();
 await expect(page.getByTestId('projector-surface').locator('canvas')).toBeVisible();
 await upload.setInputFiles({name:'bad.ply',mimeType:'application/octet-stream',buffer:Buffer.from('invalid')});
 await expect(page.getByRole('alert').filter({hasText:'Provide a PLY'})).toBeVisible();
 await page.getByRole('button',{name:'Remove selected model'}).click();
 await page.getByLabel('Model version').selectOption({label:'one.ply'});
 await expect(page.getByTestId('projector-surface').locator('canvas')).toBeVisible();
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth)).toBe(390);
});
