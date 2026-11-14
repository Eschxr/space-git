import {expect,test} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import http from 'node:http';
import https from 'node:https';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {testToken} from '../../playwright.config';

const origin='https://[::1]:3443';
test.use({ignoreHTTPSErrors:true,viewport:{width:390,height:844}});
test.skip(process.env.SPACEGIT_TEST_HTTPS!=='1','Opt-in: requires openssl and free loopback port 3443.');

test('paired HTTPS upload reaches one revision without exposing operator routes',async({page,request})=>{
 const dir=await mkdtemp(join(tmpdir(),'spacegit-tls-')),key=join(dir,'key.pem'),cert=join(dir,'cert.pem');
 execFileSync(process.env.SPACEGIT_OPENSSL??'openssl',['req','-x509','-newkey','rsa:2048','-nodes','-days','1',
   '-subj','/CN=localhost','-addext','subjectAltName=IP:::1','-keyout',key,'-out',cert],{stdio:'ignore'});
 const gateway=https.createServer({key:await readFile(key),cert:await readFile(cert)},(incoming,outgoing)=>{
  const path=incoming.url??'/';
  const allowed=(incoming.method==='POST'&&['/api/v1/capture/photos','/api/v1/capture/paired/request'].includes(path))
    ||(incoming.method==='GET'&&path==='/api/v1/capture/paired');
  if(!allowed&&(path.startsWith('/api/')||path.startsWith('/ws/'))){outgoing.writeHead(404).end();return;}
  const target=allowed?8000:3000;
  const proxy=http.request({host:'127.0.0.1',port:target,path,method:incoming.method,headers:{...incoming.headers,
    host:'127.0.0.1:'+target,...(allowed?{origin}:{})}},r=>{outgoing.writeHead(r.statusCode??502,r.headers);r.pipe(outgoing);});
  proxy.on('error',()=>{outgoing.writeHead(502).end();});incoming.pipe(proxy);
 });
 await new Promise<void>((resolve,reject)=>{gateway.once('error',reject);gateway.listen(3443,'::1',resolve);});
 try{
  const headers={Authorization:'Bearer '+testToken};
  const history=await request.get('http://127.0.0.1:8000/api/v1/commits',{headers});
  const commit=(await history.json()).branches.main;
  const pairing=await request.post('http://127.0.0.1:8000/api/v1/capture/pair/'+commit,{headers});
  const {url}=await pairing.json();
  await page.goto(url);
  await expect(page.getByText('Paired capture · upload only')).toBeVisible();
  expect(await page.evaluate(()=>window.isSecureContext)).toBe(true);
  const photoset=await page.evaluate(()=>Array.from({length:6},(_,i)=>{
   const c=document.createElement('canvas');c.width=640;c.height=480;
   c.getContext('2d')!.fillRect(20,20,600-i*5,440);return c.toDataURL('image/png').split(',')[1];
  }));
  let first=true;
  await page.route('**/api/v1/capture/photos',route=>{if(first){first=false;return route.abort();}return route.continue();});
  await page.getByLabel('Choose photos').setInputFiles(photoset.map((b64,i)=>({name:'phone-'+i+'.png',mimeType:'image/png',buffer:Buffer.from(b64,'base64')})));
  await page.getByRole('button',{name:'Upload 6 photos'}).click();
  await expect(page.getByText('5 attached · 1 need a retry.')).toBeVisible();
  await page.getByRole('button',{name:'Retry 1 photo'}).click();
  await expect(page.getByText('1 photo(s) attached to the revision.')).toBeVisible();
  await page.getByLabel('Reconstruction output').selectOption('mesh');
  await page.getByRole('button',{name:'Request reconstruction'}).click();
  await expect(page.getByRole('button',{name:'Request sent'})).toBeDisabled();
  const photos=await request.get('http://127.0.0.1:8000/api/v1/capture/photos',{headers});
  const uploaded=await photos.json();
  expect(uploaded).toHaveLength(6);
  expect(uploaded.every((p:{commit:string})=>p.commit===commit)).toBe(true);
  const sessions=await request.get('http://127.0.0.1:8000/api/v1/capture/sessions',{headers});
  expect((await sessions.json())[0].request_quality).toBe('mesh');
  const denied=await page.request.get(origin+'/api/v1/commits');
  expect(denied.status()).toBe(404);
 }finally{
  gateway.closeAllConnections();await new Promise<void>(resolve=>gateway.close(()=>resolve()));
  await rm(dir,{recursive:true,force:true});
 }
});
