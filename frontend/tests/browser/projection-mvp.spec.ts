import {expect,test,type Page} from '@playwright/test';

const edgeURL=process.env.SPACEGIT_TEST_EDGE_URL??'http://127.0.0.1:8002';
const orb={id:'blue-orb',name:'Blue orb',shape:'sphere',color:'#72d5ef',animation:'float',position:[0,0,0],size:.18};
const ply='ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 0\n1 0 0\n0 1 0\n';

async function mockOllama(page:Page,baseURL:string,chat:(body:Record<string,unknown>)=>unknown){
  await page.addInitScript(()=>localStorage.setItem('spacegit.operator.v1','projection-browser-test-token'));
  const headers={'Access-Control-Allow-Origin':new URL(baseURL).origin,'Access-Control-Allow-Headers':'authorization,content-type','Access-Control-Allow-Methods':'GET,POST,OPTIONS'};
  await page.route(edgeURL+'/api/v1/**',async route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    if(request.method()==='OPTIONS')return route.fulfill({status:204,headers});
    if(path.includes('/rig/pointclouds/'))return route.fulfill({body:ply,contentType:'application/octet-stream',headers});
    if(path.endsWith('/projection/models'))return route.fulfill({json:{models:['local-chat:latest'],provider:'ollama'},headers});
    if(path.endsWith('/projection/chat'))return route.fulfill({json:chat(request.postDataJSON()),headers});
    if(path.endsWith('/rig'))return route.fulfill({json:{mode:'live',enabled:false,feeds:[]},headers});
    if(path.endsWith('/commits'))return route.fulfill({json:{branches:{},commits:[]},headers});
    if(path.endsWith('/reconstructions'))return route.fulfill({json:{jobs:[],colmap:false},headers});
    return route.fulfill({json:[],headers});
  });
}

test('Ollama chat adds and refines objects, manual edits and undo supply authoritative context',async({page,baseURL},info)=>{
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  const requests:Record<string,unknown>[]=[];
  await mockOllama(page,baseURL!,body=>{
    requests.push(body);
    return {reply:requests.length===1?'Added a blue floating sphere.':'Made it spin.',objects:[{...orb,animation:requests.length===1?'float':'spin'}],provider:'ollama',model:'local-chat:latest'};
  });
  await page.goto('/project');
  await expect(page.getByLabel('Ollama model')).toHaveValue('local-chat:latest');
  await page.getByLabel('Describe a scene edit').fill('Add a blue floating sphere');
  await page.getByRole('button',{name:'Send to model'}).click();
  await expect(page.getByText('Added a blue floating sphere.',{exact:true})).toBeVisible();
  await expect(page.getByLabel('Selected object')).toHaveValue('blue-orb');
  await expect(page.getByRole('combobox',{name:'Animation',exact:true})).toHaveValue('float');
  expect(requests[0].objects).toEqual([]);
  await page.getByRole('slider',{name:/Position X/}).focus();
  for(let step=0;step<10;step++)await page.keyboard.press('ArrowRight');
  await page.getByLabel('Describe a scene edit').fill('Make it spin');
  await page.getByRole('button',{name:'Send to model'}).click();
  await expect(page.getByRole('combobox',{name:'Animation',exact:true})).toHaveValue('spin');
  expect(requests[1].objects).toEqual([{...orb,position:[.5,0,0]}]);
  expect(requests[1].messages).toHaveLength(2);
  await page.getByRole('button',{name:'Undo edit'}).click();
  await expect(page.getByRole('combobox',{name:'Animation',exact:true})).toHaveValue('float');
  await expect(page.getByLabel('Position X')).toHaveValue('0.5');
  await page.getByRole('button',{name:'Pause animations'}).click();
  await expect(page.getByRole('button',{name:'Play animations'})).toBeVisible();
  await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
  await page.screenshot({path:info.outputPath('project-assistant.png'),fullPage:true});
  expect(errors).toEqual([]);
});

test('invalid model plan preserves the scene and prompt, quick adds work offline on mobile',async({page,baseURL},info)=>{
  await page.setViewportSize({width:390,height:844});
  await mockOllama(page,baseURL!,()=>({reply:'Unsafe',objects:[{...orb,shape:'script'}]}));
  await page.goto('/project');
  await page.getByRole('button',{name:'+ cube',exact:true}).click();
  await expect(page.getByLabel('Selected object').locator('option')).toHaveText(['Cube']);
  await page.getByLabel('Describe a scene edit').fill('Change this');
  await page.getByRole('button',{name:'Send to model'}).click();
  await expect(page.getByRole('region',{name:'Scene assistant'}).getByRole('alert')).toContainText('Invalid scene plan');
  await expect(page.getByLabel('Selected object').locator('option')).toHaveText(['Cube']);
  await expect(page.getByLabel('Describe a scene edit')).toHaveValue('Change this');
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth)).toBe(390);
  await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
  await page.screenshot({path:info.outputPath('project-mobile.png'),fullPage:true});
  await page.getByRole('button',{name:'Clear objects'}).click();
  await expect(page.getByLabel('Selected object')).toHaveCount(0);
  await page.getByRole('button',{name:'Undo edit'}).click();
  await expect(page.getByLabel('Selected object').locator('option')).toHaveText(['Cube']);
});

test('projector renders once and the page mirrors live pixels, scene edits, blackout and source changes',async({page},info)=>{
  await page.goto('/project');
  await page.getByRole('button',{name:'+ sphere',exact:true}).click();
  const [output]=await Promise.all([page.waitForEvent('popup'),page.getByRole('button',{name:'Open projector window',exact:true}).click()]);
  const surface=page.getByTestId('projector-surface');
  await expect(output.locator('canvas')).toBeVisible();
  await expect(surface.locator('canvas')).toHaveCount(0);
  const video=surface.getByLabel('Live projector preview');
  await expect(video).toBeVisible();
  await expect.poll(()=>video.evaluate((node:HTMLVideoElement)=>node.readyState)).toBeGreaterThanOrEqual(2);
  await expect.poll(()=>video.evaluate((node:HTMLVideoElement)=>{
    const sample=document.createElement('canvas');sample.width=160;sample.height=90;
    const context=sample.getContext('2d')!;context.drawImage(node,0,0,160,90);
    const data=context.getImageData(0,0,160,90).data;
    let colored=0;
    for(let i=0;i<data.length;i+=4)if(data[i+2]>data[i]+25&&data[i+1]>data[i]+25)colored++;
    return colored;
  })).toBeGreaterThan(10);
  await page.getByRole('button',{name:'Blackout',exact:true}).click();
  await expect(surface.getByLabel('Output blacked out')).toBeVisible();
  await expect(output.getByLabel('Output blacked out')).toBeVisible();
  await page.getByRole('button',{name:'Show output'}).click();
  await page.getByRole('button',{name:'Test pattern'}).click();
  await expect(surface.getByRole('img',{name:/Projection alignment grid/})).toBeVisible();
  await expect(output.getByRole('img',{name:/Projection alignment grid/})).toBeVisible();
  await page.getByLabel('Open reconstructed scene').setInputFiles({name:'view.ply',mimeType:'application/octet-stream',buffer:Buffer.from('ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 0\n1 0 0\n0 1 0\n')});
  await expect(output.getByLabel('Physical scene 3D viewport')).toBeVisible();
  await expect.poll(()=>video.evaluate((node:HTMLVideoElement)=>node.readyState)).toBeGreaterThanOrEqual(2);
  await page.getByRole('button',{name:'+ torus',exact:true}).click();
  await expect(page.getByLabel('Selected object').locator('option')).toHaveCount(2);
  await page.screenshot({path:info.outputPath('project-live-preview.png'),fullPage:true});
  await output.close();
  await expect(surface.locator('canvas')).toBeVisible();
  await expect(surface.locator('video')).toHaveCount(0);
});

test('unavailable Ollama reports the error and keeps manual controls usable',async({page,baseURL})=>{
  await mockOllama(page,baseURL!,()=>({}));
  await page.route(edgeURL+'/api/v1/projection/models',route=>route.fulfill({status:503,json:{detail:'Ollama is unavailable.'},headers:{'Access-Control-Allow-Origin':new URL(baseURL!).origin}}));
  await page.goto('/project');
  await expect(page.getByRole('region',{name:'Scene assistant'}).getByRole('alert')).toHaveText('Ollama is unavailable.');
  await expect(page.getByRole('button',{name:'Send to model'})).toBeDisabled();
  await page.getByRole('button',{name:'+ cone',exact:true}).click();
  await expect(page.getByLabel('Selected object').locator('option')).toHaveText(['Cone']);
});

test('current reconstruction loads by camera, receives chat additions and retries without simulation fallback',async({page,baseURL})=>{
  let unavailable=false;
  const views:number[]=[];
  await mockOllama(page,baseURL!,()=>({reply:'Added a floating blue orb to this view.',objects:[orb],provider:'ollama',model:'local-chat:latest'}));
  await page.route(edgeURL+'/api/v1/rig/pointclouds/*',async route=>{
    const headers={'Access-Control-Allow-Origin':new URL(baseURL!).origin,'Access-Control-Allow-Headers':'authorization,content-type'};
    if(route.request().method()==='OPTIONS')return route.fulfill({status:204,headers});
    views.push(Number(route.request().url().split('/').at(-1)));
    return unavailable?route.fulfill({status:404,json:{detail:'No generated PLY'},headers}):route.fulfill({body:ply,contentType:'application/octet-stream',headers});
  });
  await page.goto('/project');
  await expect(page.getByText('Latest reconstruction · cam_01 · Radial A',{exact:false})).toBeVisible();
  await expect(page.getByTestId('projector-surface').locator('canvas')).toBeVisible();
  expect(views).toEqual([1]);
  await page.getByRole('combobox',{name:'Reconstruction view',exact:true}).selectOption('4');
  await expect(page.getByText('Latest reconstruction · cam_04 · Floor',{exact:false})).toBeVisible();
  await expect.poll(()=>views).toEqual([1,4]);
  const [output]=await Promise.all([page.waitForEvent('popup'),page.getByRole('button',{name:'Open projector window',exact:true}).click()]);
  await expect(output.getByLabel('Physical scene 3D viewport')).toBeVisible();
  await page.getByLabel('Describe a scene edit').fill('Add a floating blue sphere to the current reconstruction');
  await page.getByRole('button',{name:'Send to model'}).click();
  await expect(page.getByText('Added a floating blue orb to this view.',{exact:true})).toBeVisible();
  await expect(page.getByLabel('Selected object')).toHaveValue(orb.id);
  unavailable=true;
  await page.getByRole('button',{name:'Load current reconstruction',exact:true}).click();
  await expect(output.getByRole('alert')).toContainText('404');
  await expect(output.locator('canvas')).toHaveCount(0);
  await expect(page.getByText('VIRTUAL ENVIRONMENT · LOCAL SIMULATION',{exact:true})).toHaveCount(0);
  unavailable=false;
  await page.getByRole('button',{name:'Load current reconstruction',exact:true}).click();
  await expect(output.getByLabel('Physical scene 3D viewport')).toBeVisible();
  await expect(page.getByLabel('Selected object')).toHaveValue(orb.id);
  await output.close();
  await expect(page.getByTestId('projector-surface').locator('canvas')).toBeVisible();
});
