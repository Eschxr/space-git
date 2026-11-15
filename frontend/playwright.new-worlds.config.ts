import {defineConfig} from '@playwright/test';

const baseURL=process.env.SPACEGIT_TEST_URL ?? 'http://127.0.0.1:3100';
export default defineConfig({
  testDir:'./tests/browser',testMatch:['new-worlds.spec.ts','projection-mvp.spec.ts'],workers:1,timeout:55000,
  use:{baseURL,viewport:{width:1440,height:1000},
    launchOptions:{executablePath:process.env.SPACEGIT_BROWSER,args:['--enable-unsafe-swiftshader']}},
  webServer:process.env.SPACEGIT_TEST_URL?undefined:{command:'pnpm start --port 3100',url:baseURL,timeout:60000,env:{NEXT_TELEMETRY_DISABLED:'1'}},
  outputDir:'test-results/new-worlds',
});
