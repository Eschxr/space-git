import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
test('demo has six unique non-overlapping objects contained on a metric wall', async () => {
  const {objects, wall, frame} = JSON.parse(await readFile(new URL('../../fixtures/gallery.json',import.meta.url)));
  assert.equal(frame,'wall-world-meters'); assert.equal(objects.length,6);
  assert.equal(new Set(objects.map(o=>o.id)).size,6); assert.equal(new Set(objects.map(o=>o.marker)).size,6);
  for(const o of objects){
    assert.ok(o.x-o.w/2>0 && o.y-o.h/2>0 && o.x+o.w/2<wall[0] && o.y+o.h/2<wall[1]);
    for(const p of objects.filter(p=>p.id!==o.id))assert.ok(Math.abs(o.x-p.x)>=(o.w+p.w)/2 || Math.abs(o.y-p.y)>=(o.h+p.h)/2);
  }
});
