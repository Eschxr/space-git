/** Package only public web build inputs for the authenticated Vercel API. */
import fs from 'node:fs';
import path from 'node:path';
const files=['package.json','pnpm-workspace.yaml','pnpm-lock.yaml','vercel.json',
 'apps/web/package.json','apps/web/next.config.ts','apps/web/tsconfig.json','apps/web/eslint.config.mjs',
 'packages/design/tokens.css','packages/protocol/types.ts','fixtures/gallery.json','fixtures/replay.json'];
for(const prefix of ['apps/web/app','apps/web/public']){
 for(const relative of fs.readdirSync(prefix,{recursive:true,withFileTypes:true})){
  if(relative.isFile())files.push(path.join(relative.parentPath,relative.name).replaceAll(path.sep,'/'));
 }
}
const enc=files.map(file=>({file,encoding:'base64',data:fs.readFileSync(file).toString('base64')}));
fs.mkdirSync('.cache',{recursive:true});
fs.writeFileSync('.cache/public-deploy.json',JSON.stringify(enc));
console.log(JSON.stringify({count:files.length, bytes:fs.statSync('.cache/public-deploy.json').size,files}));
