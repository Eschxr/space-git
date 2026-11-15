import {expect,test} from '@playwright/test';

const tracker='http://127.0.0.1:8001';
const edge=process.env.SPACEGIT_TEST_EDGE_URL??'http://127.0.0.1:8000';
const stamp='2026-11-15T10:00:00Z';
const image='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+WZkAAAAASUVORK5CYII=';

test('commit and push imports the saved session automatically and restores its timeline',async({page})=>{
  let pushes=0, analyses=0;
  let uploaded=false;
  const slots:number[]=[];
  const capture={id:'capture-one',environment_id:'rig-space',captured_at:stamp,status:'ready',warnings:[],error:null};
  const run={id:'run-one',capture_id:capture.id,status:'succeeded',provider:'fake',inference_performed:false,error:null,attempt:1,scheduled_at:stamp,config_hash:'config',reference:{kind:'initial',capture_id:null,revision_id:null,inspection_reason:null},model_provenance:{},review_counts:{proposed:1},committed_revision_ids:[]};
  const commit={id:'commit-one',environment_id:'rig-space',capture_id:capture.id,source_session_id:'saved-session',message:'Record the workspace',parent_id:null,created_at:stamp,run,processing_error:null};
  const asset={url:image,storage_key:'image',sha256:'a'.repeat(64),content_type:'image/png',unavailable_reason:null};
  let releaseImage:()=>void=()=>{};
  const pendingImage=new Promise<void>(resolve=>{releaseImage=resolve;});
  await page.route('http://evidence.spacegit.test/**',async route=>{
    await pendingImage;
    return route.fulfill({body:Buffer.from(image.split(',')[1],'base64'),contentType:'image/png'});
  });
  const observation={capture_id:capture.id,frame_id:'frame-one',camera_id:'cam_01',detection_id:'det',run_id:run.id,label:'mug',box_xyxy:[0,0,1,1],width:1,height:1,image:asset,mask:null,crop:asset,overlays:[]};
  const proposal={id:'proposal-one',run_id:run.id,camera_id:'cam_01',view_track_id:'track-one',type:'moved_in_view',status:'proposed',reason:null,evidence:{},before_ref:{label:'mug',visualization:observation},after_ref:{label:'mug',visualization:observation}};
  const frames=[1,2,3,4].map(slot=>({id:'frame-'+slot,capture_id:capture.id,camera_id:'cam_0'+slot,role:slot===4?'overhead':'side',width:1,height:1,sha256:'a'.repeat(64),captured_at:stamp,image:asset}));
  await page.route('**/api/v1/**',async route=>{
    const request=route.request();const url=new URL(request.url());
    const headers={'Access-Control-Allow-Origin':new URL(page.url()).origin,'Access-Control-Allow-Methods':'GET,POST,OPTIONS','Access-Control-Allow-Headers':'content-type,authorization,x-spacegit-local'};
    const json=(value:unknown)=>route.fulfill({json:value,headers});
    const pageOf=(items:unknown[])=>json({items,limit:50,offset:0});
    if(request.method()==='OPTIONS')return route.fulfill({status:204,headers});
    if(url.origin===edge) {
      if(url.pathname==='/api/v1/local-session')return json({token:'browser-only-token'});
      if(url.pathname==='/api/v1/rig')return json({mode:'live',enabled:false,feeds:[],settings:{sources:[0,1,2,3],order:[4,3,2,1]}});
      if(url.pathname==='/api/v1/rig/captures')return json([{id:'saved-session',created:1763200800,mode:'live',feeds:[4,2,1,3],frame_times:{'1':1763200800,'2':1763200801,'3':1763200802,'4':1763200803}}]);
      const slot=/\/captures\/saved-session\/frames\/(\d)$/.exec(url.pathname);
      if(slot){slots.push(Number(slot[1]));return route.fulfill({body:Buffer.from([Number(slot[1]),99]),contentType:'image/jpeg',headers});}
      if(url.pathname==='/api/v1/commits')return json({branches:{},commits:[]});
      if(url.pathname==='/api/v1/reconstructions')return json({jobs:[],colmap:false});
    }
    if(url.origin===tracker) {
      if(url.pathname==='/api/v1/vision/status')return json({provider:'real',detector:'YOLOE 11s prompt-free',embedder:'DINOv2 ViT-S/14',device:'cpu',assets_verified:true,reason:null});
      if(url.pathname==='/api/v1/processing-runs/run-one/detections')return pageOf([
        {id:'det',run_id:run.id,frame_id:'frame-1',camera_id:'cam_01',label:'mug',det_score:0.92,box_xyxy:[0,0,1,1],embedding_key:'features/one',embedding_metadata:{dimension:384}},
        {id:'det-floor',run_id:run.id,frame_id:'frame-4',camera_id:'cam_04',label:'chair',det_score:0.75,box_xyxy:[0,0,1,1],embedding_key:null,embedding_metadata:null},
      ]);
      if(url.pathname==='/api/v1/captures/capture-one/process'){analyses++;return json(run);}
      if(url.pathname==='/api/v1/camera-commits'&&request.method()==='POST') {
        pushes++;
        const body=request.postDataBuffer()!.toString('latin1');
        for(let slot=1;slot<=4;slot++)expect(body).toContain(`filename="cam_0${slot}.jpg"`);
        expect(body).toContain('saved-session');expect(body).toContain('Record the workspace');
        uploaded=true;return json(commit);
      }
      if(url.pathname==='/api/v1/camera-commits')return pageOf(uploaded?[commit]:[]);
      if(url.pathname==='/api/v1/captures/capture-one/workflow')return json({capture,source_images:frames,latest_run:run,observed_tracks:[],approved_revision_id:null,outcome:'pending_review'});
      if(url.pathname==='/api/v1/captures/capture-one/processing-runs')return pageOf([run]);
      if(url.pathname==='/api/v1/processing-runs/run-one/changes')return pageOf([proposal]);
    }
    return route.fulfill({status:404,json:{error:{message:'Unhandled '+url.pathname}},headers});
  });
  await page.goto('/world');
  await page.getByRole('button',{name:'Connect cameras',exact:true}).click();
  await expect(page.getByLabel('Capture source')).toHaveValue('live');
  await page.getByRole('button',{name:/Version control/}).click();
  await expect(page.getByRole('button',{name:'Commit and push',exact:true})).toBeEnabled();
  await expect(page.locator('input[type=file]')).toHaveCount(0);
  await page.getByLabel('Commit message',{exact:true}).fill('Record the workspace');
  await page.getByRole('button',{name:'Commit and push',exact:true}).click();
  await expect(page.getByRole('button',{name:'Session committed and pushed'})).toBeDisabled();
  await expect(page.getByText('Record the workspace',{exact:true})).toBeVisible();
  await expect(page.locator('.ih-sources img')).toHaveCount(4);
  await expect(page.getByText('REAL DETECTION CONFIGURED',{exact:true})).toBeVisible();
  const detector=page.getByRole('region',{name:'Detected objects',exact:true});
  await expect(detector.getByRole('heading',{name:'Detected objects (2)',exact:true})).toBeVisible();
  await expect(detector.getByText('mug92.0%',{exact:true})).toBeVisible();
  await expect(detector.getByText(/384 dimensions/)).toBeVisible();
  const preview=detector.locator('.ih-image');
  const before=await preview.boundingBox();
  expect(before!.height).toBeGreaterThan(100);
  asset.url='http://evidence.spacegit.test/refreshed.png';
  const imageRequested=page.waitForRequest(asset.url);
  await page.getByRole('button',{name:'Refresh evidence',exact:true}).click();
  await preview.scrollIntoViewIfNeeded();
  await imageRequested;
  // Reserve the same viewport while a refreshed signed image is still loading.
  const pending=await preview.boundingBox();
  expect(pending!.width).toBeCloseTo(before!.width,0);
  expect(pending!.height).toBeCloseTo(before!.height,0);
  releaseImage();
  await expect.poll(()=>preview.locator('img').evaluate(img=>(img as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  const after=await preview.boundingBox();
  expect(after!.height).toBeCloseTo(before!.height,0);
  await detector.getByLabel('Detection camera',{exact:true}).selectOption('cam_04');
  await expect(detector.getByRole('button',{name:/chair/})).toBeVisible();
  await expect(detector.getByRole('button',{name:/mug/})).toHaveCount(0);
  await expect(detector.getByText('Appearance features are unavailable for this object.')).toBeVisible();
  await page.getByRole('button',{name:'Run object detection',exact:true}).click();
  await expect(page.getByText('Showing the completed analysis for these images and settings.')).toBeVisible();
  expect(analyses).toBe(1);
  await expect(page.getByText('moved in view · track track-on',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Commit selected changes',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Accept',exact:true})).toHaveCount(0);
  expect(pushes).toBe(1);expect(slots.sort()).toEqual([1,2,3,4]);
  await page.reload();
  await page.getByRole('button',{name:/Version control/}).click();
  await expect(page.getByText('Record the workspace',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Session committed and pushed'})).toBeDisabled();
  expect(pushes).toBe(1);
});
