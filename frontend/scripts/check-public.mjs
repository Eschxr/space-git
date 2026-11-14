/** Check the published demo through a real browser, without any operator key. */
import {chromium} from '@playwright/test';
import fs from 'node:fs';
const url=new URL(process.argv[2]);
if(url.protocol!=='https:'&&!(url.protocol==='http:'&&url.hostname==='127.0.0.1'))throw Error('Use the HTTPS deployment hostname or a loopback release candidate.');
const browser=await chromium.launch({headless:true,executablePath:process.env.SPACEGIT_BROWSER,
 args:['--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const unexpected=[],failures=[];
 page.on('request',r=>{if(new URL(r.url()).hostname!==url.hostname)unexpected.push(r.url());});
 page.on('websocket',s=>unexpected.push(s.url()));
 page.on('pageerror',e=>failures.push(e.message));
 for(const route of ['/','/studio','/studio/live','/studio/3d','/studio/history','/studio/merge','/setup','/studio/capture','/projector']){
  const response=await page.goto(new URL(route,url).href,{waitUntil:'networkidle'});
  if(response?.status()!==200)throw Error(route+' returned '+response?.status());
  if(route==='/')await page.getByRole('heading',{name:'Version control for physical space.'}).waitFor();
  if(route==='/studio'){
    await page.getByText('DEMO / READ ONLY').waitFor();
    await page.locator('canvas').waitFor();
    await page.getByRole('button',{name:/Exhibit D/}).click();
    await page.getByText(/OBJECT \/ d|ARUCO \/ 20/).waitFor();
  }
  if(route==='/setup')await page.getByText('Hardware setup runs locally').waitFor();
  if(route==='/studio/live'){
   await page.getByRole('button',{name:'Play simulated move'}).click();
   await page.getByText('Replay verified · simulated only').waitFor();
  }
  console.log(route+' HTTP 200');
 }
 if(unexpected.length||failures.length)throw Error(JSON.stringify({unexpected,failures}));
 fs.mkdirSync('test-results/public',{recursive:true});
 await page.goto(new URL('/',url).href,{waitUntil:'networkidle'});
 await page.screenshot({path:'test-results/public/landing.png',fullPage:true,animations:'disabled'});
 console.log('Demo is read-only. No off-origin requests, WebSockets, or page errors.');
}finally{await browser.close();}
