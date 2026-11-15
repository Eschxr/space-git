import {defineConfig} from '@playwright/test';
import {randomUUID} from 'node:crypto';
const windows=process.platform==='win32';
const python=windows?'.venv\\Scripts\\python.exe':'.venv/bin/python';
export const testToken='spacegit-browser-test-operator-1234';
export default defineConfig({
 testDir:'./tests/browser',fullyParallel:false,workers:1,timeout:35000,
 use:{baseURL:'http://127.0.0.1:3000',viewport:{width:1440,height:1000},
  launchOptions:{...(process.env.SPACEGIT_BROWSER?{executablePath:process.env.SPACEGIT_BROWSER}:{}),
   args:['--enable-unsafe-swiftshader']}},
 webServer:[
  {command:'pnpm start',url:'http://127.0.0.1:3000',timeout:60000,env:{NEXT_TELEMETRY_DISABLED:'1'}},
  {command:python+' -m uvicorn spacegit_edge.main:app --app-dir apps/edge --host 127.0.0.1 --port 8000 --no-access-log',url:'http://127.0.0.1:8000/health',timeout:15000,
   env:{SPACEGIT_TOKEN:testToken,SPACEGIT_MODE:'live',SPACEGIT_DATA:'test-results/edge-'+randomUUID(),
    ...(process.env.SPACEGIT_TEST_HTTPS==='1'?{SPACEGIT_MOBILE_ORIGIN:'https://[::1]:3443'}:{})}}
 ],
 outputDir:'test-results/artifacts',
});
