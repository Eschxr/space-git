import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser', testMatch: ['image-history.spec.ts', 'image-history.real.spec.ts'], workers: 1, timeout: 60000,
  use: {baseURL: process.env.SPACEGIT_TEST_URL ?? 'http://127.0.0.1:3101', viewport: {width: 1440, height: 1000},
    actionTimeout: 20000, navigationTimeout: 30000,
    launchOptions: {executablePath: process.env.SPACEGIT_BROWSER}},
  webServer: process.env.SPACEGIT_TEST_URL ? undefined : {command: 'pnpm start --port 3101', url: 'http://127.0.0.1:3101', timeout: 60000},
  outputDir: 'test-results/image-history',
});
