import {expect,test} from '@playwright/test';
import {testToken} from '../../playwright.config';

test.skip(process.env.SPACEGIT_TEST_LIVE!=='1','Opt-in: opens a physical camera, with no saved frame.');
test('live wizard opens the physical camera but gates uncalibrated projection',async({page,request})=>{
 await page.goto('/setup');
 await page.getByLabel('Operator key').fill(testToken);
 await page.getByRole('button',{name:'Connect',exact:true}).click();
 await expect(page.getByText('Edge connected',{exact:true})).toBeVisible();
 if(process.env.SPACEGIT_TEST_CAMERA_INDEX){
  await page.getByLabel('Camera',{exact:true}).selectOption('manual');
  await page.getByLabel('Camera index',{exact:true}).fill(process.env.SPACEGIT_TEST_CAMERA_INDEX);
 }
 await page.getByRole('button',{name:'Open camera'}).click();
 const image=page.getByAltText('Live camera preview');
 await expect(image).toBeVisible({timeout:12000});
 await expect.poll(()=>image.evaluate((e:HTMLImageElement)=>e.naturalWidth)).toBeGreaterThan(0);
 await expect(page.getByLabel('Camera diagnostics')).toBeVisible();
 await expect(page.getByRole('button',{name:'Automatic calibration',exact:true})).toBeDisabled();
 const status=async()=>(await request.get('http://127.0.0.1:8000/api/v1/status',{headers:{Authorization:'Bearer '+testToken}})).json();
 await expect.poll(async()=>(await status()).live.state,{timeout:10000,intervals:[150,250,350]}).toBe('SETUP_REQUIRED');
 const {camera_signature,live,camera_metrics}=await status();
 expect(live.mode).toBe('live');expect(live.camera).toBe(true);
 expect(live.projection_ready).toBe(false);
 expect(camera_metrics.brightness).toBeGreaterThanOrEqual(0);
 console.log(JSON.stringify({camera:camera_signature,diagnostics:camera_metrics,projectionReady:live.projection_ready,preview:true}));
 await page.getByRole('button',{name:'Stop camera'}).click();
 await expect(page.getByText('Camera preview unavailable')).toBeVisible();
});
