import {expect, test} from '@playwright/test';

const api = 'http://127.0.0.1:8001';
const edgeURL = process.env.SPACEGIT_TEST_EDGE_URL ?? 'http://127.0.0.1:8000';
const stamp = '2026-11-15T10:00:00Z';
const image = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+WZkAAAAASUVORK5CYII=';
const asset = {url: image, storage_key: 'original.png', sha256: 'a'.repeat(64), content_type: 'image/png', unavailable_reason: null};
const observation = {capture_id: 'capture-one', frame_id: 'frame', detection_id: 'detection', run_id: 'run-one', camera_id: 'cam_01', label: 'chair', width: 320, height: 240, box_xyxy: [35, 60, 125, 170], image: asset, mask: {...asset, content_type: 'application/json', url: 'data:application/json,%7B%22counts%22%3A%22x%22%7D'}, crop: asset, overlays: [asset]};

test('upload, human review, selected commit and approved evidence stay in image history', async ({page}, info) => {
  const errors: string[] = []; page.on('pageerror', e => errors.push(e.message));
  let uploaded = false, processed = false, status = 'proposed', committed = false;
  let reviewBody: Record<string, unknown> = {}, commitBody: Record<string, unknown> = {};
  const capture = {id: 'capture-one', environment_id: 'space-one', captured_at: stamp, status: 'ready', warnings: [], error: null};
  const source_images = [1,2,3,4].map(i => ({id: 'frame-' + i, capture_id: capture.id, camera_id: 'cam_0' + i, role: i === 4 ? 'overhead' : 'side', width: 320, height: 240, sha256: 'a'.repeat(64), captured_at: stamp, image: asset}));
  const revision = {id: 'revision-one', environment_id: 'space-one', capture_id: capture.id, parent_id: null, created_at: stamp, message: 'Confirmed chair'};
  const proposal = () => ({id: 'proposal-one', run_id: 'run-one', camera_id: 'cam_01', view_track_id: 'track-one', type: 'appeared_in_view', status, reason: null, evidence: {uncertainty: null}, before_ref: null, after_ref: {label: 'chair', visualization: observation}});
  const run = () => ({id: 'run-one', capture_id: capture.id, status: 'succeeded', provider: 'fake', inference_performed: false, attempt: 1, error: null, scheduled_at: stamp, config_hash: 'config', reference: {kind: 'initial', capture_id: null, revision_id: null, inspection_reason: null}, model_provenance: {}, review_counts: {[status]: 1}, committed_revision_ids: committed ? [revision.id] : []});
  await page.route(api + '/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname.slice('/api/v1'.length);
    const headers = {'Access-Control-Allow-Origin': new URL(page.url()).origin, 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS', 'Access-Control-Allow-Headers': 'content-type'};
    const json = (value: unknown) => route.fulfill({json: value, headers});
    const pageOf = (items: unknown[]) => json({items, limit: 50, offset: 0});
    if (request.method() === 'OPTIONS') return route.fulfill({status: 204, headers});
    if (path === '/vision/status') return json({provider:'fake',detector:'Synthetic fixture detector',embedder:'Synthetic appearance features',device:'cpu',assets_verified:false,reason:null});
    if (path === '/processing-runs/run-one/detections') return pageOf([]);
    if (path === '/environments') return pageOf([{id: 'space-one', name: 'Lab', prompts: null, created_at: stamp}]);
    if (path === '/environments/space-one/captures' && request.method() === 'POST') {
      expect(request.postDataBuffer()?.toString()).toContain('filename="cam_04.png"'); uploaded = true; return json(capture);
    }
    if (path === '/environments/space-one/captures') return pageOf(uploaded ? [capture] : []);
    if (path === '/environments/space-one/revisions' && request.method() === 'POST') {commitBody = request.postDataJSON(); committed = true; return json(revision);}
    if (path === '/environments/space-one/revisions') return pageOf(committed ? [revision] : []);
    if (path === '/captures/capture-one/process') {processed = true; return json(run());}
    if (path === '/captures/capture-one/workflow') return json({capture, source_images, latest_run: processed ? run() : null, observed_tracks: [], approved_revision_id: committed ? revision.id : null, outcome: committed ? 'committed' : processed ? status === 'accepted' ? 'ready_to_commit' : 'pending_review' : 'unprocessed'});
    if (path === '/captures/capture-one/processing-runs') return pageOf(processed ? [run()] : []);
    if (path === '/processing-runs/run-one/changes') return pageOf([proposal()]);
    if (path === '/change-proposals/proposal-one/decision') {reviewBody = request.postDataJSON(); status = String(reviewBody.status); return json(proposal());}
    if (path === '/change-proposals/proposal-one/decisions') return pageOf(status === 'accepted' ? [{id: 'decision', previous_status: 'proposed', new_status: status, reason: reviewBody.reason, reviewer: reviewBody.reviewer, decided_at: stamp}] : []);
    if (path === '/revisions/revision-one/evidence') return json({revision, source_images, approved_tracks: [{view_track_id: 'track-one', camera_id: 'cam_01', state: {label: 'chair'}, observation}], changes: [proposal()], provenance: {origin: 'commit_snapshot'}, highlight_paths: []});
    if (path === '/revisions/revision-one/diff') return json({changes: [proposal()]});
    throw new Error('Unexpected Scene Tracker path: ' + path);
  });
  await page.goto('/world'); await page.getByRole('link', {name: 'Image history', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Lab', exact: true})).toBeVisible();
  for (let i = 0; i < 4; i++) await page.locator('input[type=file]').nth(i).setInputFiles({name: 'photo.png', mimeType: 'image/png', buffer: Buffer.from('fixture')});
  await page.getByRole('button', {name: 'Upload four images', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Run inference', exact: true})).toBeVisible();
  expect(processed).toBe(false);
  await page.getByRole('button', {name: 'Run inference', exact: true}).click();
  const card = page.getByRole('article', {name: 'chair change proposal'});
  await expect(card).toBeVisible();
  await expect(card.getByRole('link', {name: 'Download mask RLE JSON', exact: true})).toBeVisible();
  await expect(card.locator('option[value="mask"]')).toHaveCount(0);
  await expect(page.getByRole('button', {name: 'Commit selected changes', exact: true})).toBeDisabled();
  await card.getByLabel('Decision reason').fill('Confirmed in the image');
  await card.getByRole('button', {name: 'Accept', exact: true}).click();
  await expect(card.getByRole('button', {name: 'Accept', exact: true})).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', {name: 'Commit selected changes', exact: true})).toBeDisabled();
  await card.getByLabel('Include in revision').check();
  await card.getByRole('button', {name: 'Decision audit', exact: true}).click();
  await expect(card.getByText(/local-operator: proposed → accepted/)).toBeVisible();
  await page.getByLabel('Revision message').fill('Confirmed chair');
  await page.getByRole('button', {name: 'Commit selected changes', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Revision revision'})).toBeVisible();
  expect(commitBody.proposal_ids).toEqual(['proposal-one']); expect(commitBody.idempotency_key).toBeTruthy();
  expect(reviewBody.reason).toBe('Confirmed in the image');
  await expect(page.getByRole('heading', {name: 'Approved objects (1)'})).toBeVisible();
  await expect(page.getByRole('link', {name: /3D & projection/})).toBeVisible();
  await page.screenshot({path: info.outputPath('approved-history-desktop.png'), fullPage: true});
  await page.setViewportSize({width: 390, height: 844});
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({path: info.outputPath('approved-history-mobile.png'), fullPage: true});
  expect(errors).toEqual([]);
});

test('an unavailable API stays an explicit error with no simulation fallback', async ({page}) => {
  await page.route(api + '/**', route => route.abort());
  await page.goto('/image-history');
  await expect(page.locator('p[role=alert]').first()).toContainText('Scene Tracker is unreachable');
  await expect(page.getByRole('button', {name: 'Refresh spaces', exact: true})).toBeVisible();
  await expect(page.getByText('No approved revisions yet.')).toHaveCount(0);
});

test('remote/public UI never contacts workstation services', async ({page, baseURL}) => {
  let calls = 0;
  await page.route('http://127.0.0.1:8001/**', async route => {calls++; await route.abort();});
  await page.route(edgeURL + '/**', async route => {calls++; await route.abort();});
  const html = await (await page.request.get('/image-history')).text();
  await page.route('http://public.spacegit.test/**', async route => {
    if (route.request().resourceType() === 'document') return route.fulfill({body: html, contentType: 'text/html'});
    const response = await route.fetch({url: route.request().url().replace('http://public.spacegit.test', new URL(baseURL!).origin)});
    return route.fulfill({response});
  });
  calls = 0;
  await page.goto('http://public.spacegit.test/image-history');
  await expect(page.getByRole('heading', {name: 'Open on your local workstation'})).toBeVisible();
  await page.waitForLoadState('networkidle');
  expect(calls).toBe(0);
  await page.unrouteAll({behavior: 'wait'});
});

test('complete saved rig sessions keep slot identity, original bytes and frame times', async ({page}) => {
  const slots: number[] = []; let body = '', uploaded = false;
  const capture = {id: 'rig-capture', environment_id: 'rig-space', captured_at: stamp, status: 'ready', warnings: [], error: null};
  const cors = () => ({'Access-Control-Allow-Origin': new URL(page.url()).origin, 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS', 'Access-Control-Allow-Headers': 'content-type,authorization,x-spacegit-local'});
  await page.route(edgeURL + '/**', route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    const headers = cors();
    if (request.method() === 'OPTIONS') return route.fulfill({status: 204, headers});
    if (path.endsWith('/local-session')) return route.fulfill({json: {token: 'loopback-session'}, headers});
    if (path.endsWith('/rig/captures')) return route.fulfill({json: [
      {id: 'partial', created: 1700000000, mode: 'live', feeds: [1,2,3]},
      {id: 'complete', created: 1700000000, mode: 'live', feeds: [4,1,3,2], order: [4,1,3,2], frame_times: {'1': 1700000000.001, '2': 1700000000.002, '3': 1700000000.003, '4': 1700000000.004}},
    ], headers});
    const slot = Number(path.split('/').at(-1)); slots.push(slot);
    return route.fulfill({body: Buffer.from('original-slot-' + slot), contentType: 'image/jpeg', headers});
  });
  await page.route(api + '/**', route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    const headers = cors(), json = (value: unknown) => route.fulfill({json: value, headers});
    const pageOf = (items: unknown[]) => json({items, limit: 50, offset: 0});
    if (request.method() === 'OPTIONS') return route.fulfill({status: 204, headers});
    if (path.endsWith('/vision/status')) return json({provider:'fake',detector:'Synthetic fixture detector',embedder:'Synthetic appearance features',device:'cpu',assets_verified:false,reason:null});
    if (path.endsWith('/environments')) return pageOf([{id: 'rig-space', name: 'Rig lab', created_at: stamp}]);
    if (path.endsWith('/captures') && request.method() === 'POST') {body = request.postDataBuffer()!.toString(); uploaded = true; return json(capture);}
    if (path.endsWith('/captures')) return pageOf(uploaded ? [capture] : []);
    if (path.endsWith('/revisions') || path.endsWith('/processing-runs')) return pageOf([]);
    if (path.endsWith('/workflow')) return json({capture, source_images: [], latest_run: null, observed_tracks: [], approved_revision_id: null, outcome: 'unprocessed'});
    throw new Error('Unexpected API path: ' + path);
  });
  await page.goto('/image-history');
  await page.getByText('Import a saved camera rig session', {exact: true}).click();
  await page.getByRole('button', {name: 'Connect edge & load sessions', exact: true}).click();
  const picker = page.getByRole('combobox', {name: 'Saved session', exact: true});
  await expect(picker.locator('option[value="partial"]')).toBeDisabled();
  await picker.selectOption('complete');
  await page.getByRole('button', {name: 'Import selected session', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Run inference', exact: true})).toBeVisible();
  expect(slots.sort()).toEqual([1,2,3,4]);
  for (const slot of [1,2,3,4]) expect(body).toMatch(new RegExp(`name="cam_0${slot}"; filename="cam_0${slot}.jpg"[\\s\\S]*?original-slot-${slot}`));
  expect(body).toContain('name="cam_04_captured_at"'); expect(body).toContain('2023-11-14T22:13:20.004Z');
  expect(body).toContain('name="captured_at"'); expect(body).toContain('2023-11-14T22:13:20.000Z');
});
