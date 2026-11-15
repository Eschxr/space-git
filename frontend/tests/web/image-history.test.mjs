import {test} from 'node:test';
import assert from 'node:assert/strict';
import {CAMERAS, completeSession, intentKey, trackerClient, TrackerError} from '../../apps/web/app/image-history/client.ts';

test('upload preserves bytes and fixed camera roles with canonical filenames and timestamps', async () => {
  let sent;
  const api = trackerClient('http://127.0.0.1:8001/', async (url, options) => {
    sent = {url, options}; return Response.json({id: 'capture'});
  });
  const images = Object.fromEntries(CAMERAS.map((camera, index) => [camera, new Blob([new Uint8Array([index, 8, 7])], {type: 'image/png'})]));
  const stamp = '2026-11-15T10:00:00Z';
  await api.upload('space', {images, capturedAt: stamp, frameTimes: {cam_04: stamp}});
  assert.equal(sent.url, 'http://127.0.0.1:8001/api/v1/environments/space/captures');
  assert.equal(sent.options.headers, undefined); // Browser supplies the multipart boundary.
  for (const [index, camera] of CAMERAS.entries()) {
    const file = sent.options.body.get(camera);
    assert.equal(file.name, camera + '.png');
    assert.deepEqual([...new Uint8Array(await file.arrayBuffer())], [index, 8, 7]);
  }
  assert.equal(sent.options.body.get('captured_at'), stamp);
  assert.equal(sent.options.body.get('cam_04_captured_at'), stamp);
  assert.throws(() => api.upload('space', {images: {...images, cam_04: undefined}}), /cam_04/);
});

test('API conflicts retain actionable codes and never fall back to demo data', async () => {
  const api = trackerClient('http://127.0.0.1:8001', async () => Response.json({error: {code: 'stale_reference', message: 'Head advanced', capture_id: 'failed-id'}}, {status: 409}));
  await assert.rejects(api.commit('s', 'c', ['p'], 'Reviewed', 'key'), error => error instanceof TrackerError && error.code === 'stale_reference' && error.status === 409 && error.details.capture_id === 'failed-id');
});

test('review and revision retry keys persist for the same intent, selected IDs remain explicit', async () => {
  const bodies = [];
  const api = trackerClient('http://127.0.0.1:8001', async (_, options) => {bodies.push(JSON.parse(options.body)); return Response.json({id: 'revision'});});
  const first = intentKey(null, {ids: ['p1'], message: 'Reviewed'});
  assert.equal(intentKey(first, {ids: ['p1'], message: 'Reviewed'}).key, first.key);
  assert.notEqual(intentKey(first, {ids: ['p2'], message: 'Reviewed'}).key, first.key);
  await api.decide('p1', 'accepted', 'Confirmed', 'Reviewer', 'decision-key');
  await api.commit('space', 'capture', ['p1'], 'Reviewed', first.key);
  assert.deepEqual(bodies[0], {status: 'accepted', reason: 'Confirmed', reviewer: 'Reviewer', idempotency_key: 'decision-key'});
  assert.deepEqual(bodies[1].proposal_ids, ['p1']);
  assert.equal(bodies[1].idempotency_key, first.key);
});

test('saved rig sessions require physical slots 1 through 4 regardless of display order', () => {
  assert.equal(completeSession({mode: 'live', feeds: [4, 2, 1, 3]}), true);
  for (const session of [{mode: 'live', feeds: [1, 2, 4]}, {mode: 'demo', feeds: [1, 2, 3, 4]}, {mode: 'live', feeds: [1, 2, 3, 3]}]) assert.equal(completeSession(session), false);
});

test('change proposals are loaded across pages', async () => {
  const offsets = [];
  const api = trackerClient('http://127.0.0.1:8001', async url => {
    const offset = Number(new URL(url).searchParams.get('offset')); offsets.push(offset);
    return Response.json({items: Array.from({length: offset ? 1 : 100}, (_, i) => ({id: String(offset + i)})), offset, limit: 100});
  });
  assert.equal((await api.changes('run')).length, 101);
  assert.deepEqual(offsets, [0, 100]);
});
