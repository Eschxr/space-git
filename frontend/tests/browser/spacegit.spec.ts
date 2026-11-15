import {expect,test} from '@playwright/test';

test('landing and disconnected Studio show no bundled scene or rehearsal',async({page})=>{
 await page.goto('/');
 await expect(page.getByRole('link',{name:'Open workspace',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Preview next object'})).toHaveCount(0);
 await page.goto('/studio');
 await expect(page.getByRole('heading',{name:'No recorded scene'})).toBeVisible();
 await expect(page.locator('canvas')).toHaveCount(0);
 await page.goto('/studio/live');
 await expect(page.getByText('Connect the live edge in Hardware setup',{exact:false})).toBeVisible();
 await expect(page.getByRole('button',{name:'Play simulated move'})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Replay one move'})).toHaveCount(0);
});

test('the physical projector shows setup requirements instead of fixture guidance',async({page})=>{
 await page.goto('/projector');
 await expect(page.getByRole('button',{name:'Enter fullscreen'})).toBeDisabled();
 await expect(page.getByText('Connect the local edge in Setup first.')).toBeVisible();
 await expect(page.getByText('DEMO / SIMULATED')).toHaveCount(0);
});

test('operator-provided GLB loads in the real Project workspace',async({page})=>{
 const file=process.env.SPACEGIT_TEST_GLB;
 test.skip(!file,'Provide the locally reconstructed GLB for the manual operator gate.');
 await page.goto('/project');
 await page.getByLabel('Open reconstructed scene').setInputFiles(file!);
 await expect(page.getByLabel('Physical scene 3D viewport')).toBeVisible();
 await expect(page.getByRole('button',{name:'+ sphere',exact:true})).toBeEnabled();
});
