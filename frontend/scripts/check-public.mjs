/** Verify the public build does not contain fabricated scenes or hardware actions. */
import {chromium,expect} from '@playwright/test';
const url=new URL(process.argv[2]);
if(url.protocol!=='https:'&&!(url.protocol==='http:'&&url.hostname==='127.0.0.1'))throw Error('Use HTTPS or a loopback release candidate.');
const browser=await chromium.launch({headless:true,executablePath:process.env.SPACEGIT_BROWSER,args:['--enable-unsafe-swiftshader']});
try {
 const page=await browser.newPage();
 await page.goto(new URL('/project',url).href);
 await expect(page.getByRole('heading',{name:'Project',exact:true})).toBeVisible();
 await expect(page.locator('canvas')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Start Demo'})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'+ sphere',exact:true})).toBeDisabled();
 console.log('Public workspace has no generated source scene.');
} finally {await browser.close();}
