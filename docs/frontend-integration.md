# Local frontend and Scene Tracker

The frontend has an **Image history** workspace at `/image-history`, linked from
`/world`. It works with the backend through Phase 8. Its saved spaces, captures,
review decisions and approved revisions live in PostgreSQL/Silo. The existing
metric layout branches, 3D viewers, reconstruction tools and projector workflow
remain available in `/world` and Hardware Studio.

## Start the integrated workstation

Use these ports on this system. A separate `SpaceGit-MVP` checkout already uses
3000, 3100 and 8000; leave its services running.

| Service | Address |
| --- | --- |
| This frontend | http://127.0.0.1:3101 |
| Scene Tracker API | http://127.0.0.1:8001 |
| This camera edge | http://127.0.0.1:8002 |
| PostgreSQL / Redis / Silo | Existing loopback 5432 / 6379 / 9000 |

From the repository root, keep the existing `.env`. For a new workstation, copy
`.env.example` and configure it first. Real inference requires `VISION_PROVIDER=real`
and the local weights, hashes and pinned source described in [model setup](model-setup.md).

```powershell
docker compose --env-file .env -f infra/compose.yaml --profile application up -d --build
docker compose --env-file .env -f infra/compose.yaml exec api scene-tracker model-readiness --runtime
```

The application profile runs additive migrations, the API and the durable Linux RQ
worker. Native Windows is not supported by the pinned RQ worker's POSIX process calls.
API and worker share an image and identical container paths for model verification.
Credentials and database URL options come from `.env`; the entrypoint translates
database/Redis hosts to their Compose service names. Originals and existing history
are preserved. Do not use `down -v` to restart this system.

The first build installs the locked vision dependencies and can take several minutes
and multiple gigabytes. The current lock includes CUDA libraries even though this
profile deliberately runs CPU inference. No model weights are downloaded by the build.
The default read-only model mount is `models/real-inference`, containing:

```text
checkpoints/yoloe-11s-seg-pf.pt
checkpoints/dinov2_vits14_pretrain.pth
sources/dinov2/  (clean pinned Git checkout)
```

Set `SCENE_TRACKER_MODELS_DIR` if this layout lives elsewhere. The writable
`model_cache` volume is separate. Git compares normalized line endings in the Linux
image so unchanged Windows CRLF checkouts pass the same pinned-source check.

The frontend's Python 3.12 camera environment is independent of the backend's Python
3.11 vision environment. From `frontend/`, install and configure once:

```powershell
pnpm install --frozen-lockfile
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r apps/edge/requirements.txt
Copy-Item apps/web/.env.local.example apps/web/.env.local
```

Then start the edge and web UI together:

```powershell
.\scripts\start.ps1 -Mode live -Port 3101 -EdgePort 8002
```

On Linux, use `SPACEGIT_WEB_PORT=3101 SPACEGIT_EDGE_PORT=8002 bash scripts/start.sh live`.
The start scripts keep their original 3000/8000 defaults when no port options are supplied.
Starting the edge does not configure or start the four physical camera feeds; use
Capture to map the slots and explicitly start live previews.

For image files alone, no edge is required: from `frontend/`, run
`pnpm dev --port 3101`, or `pnpm build` followed by `pnpm start --port 3101`.
`apps/web/.env.local` sets `NEXT_PUBLIC_SCENE_TRACKER_URL` and
`NEXT_PUBLIC_SPACEGIT_EDGE_URL`. These are public build-time URLs; rebuild a production
frontend after changing them. HTTP requests, camera previews and live WebSockets use
the configured edge URL. Public/remote frontend builds make no workstation requests
from Image history and show local startup instructions.

Both APIs allow the exact localhost/127.0.0.1 origins on ports 3000 and 3101.
Scene Tracker can override these through the JSON `CORS_ORIGINS` setting. Its private
bucket uses short-lived signed browser image URLs via `PUBLIC_OBJECTSTORE_ENDPOINT`;
the server uses `S3_ENDPOINT` internally. `S3_REGION` defaults to `us-east-1`, avoiding
region discovery through the browser's localhost from inside Docker. This is a local
MVP, with Scene Tracker authentication still outside its current scope.

## Review an image capture

1. Open Image history and choose or create a space such as Lab or Bedroom. Keep camera
   roles and positions fixed within that physical space.
2. Upload JPEG, PNG or WebP files for all four roles. The browser assigns canonical
   filenames without changing their bytes; the API validates the decoded format,
   orientation, dimensions and hashes. Each file is limited to 20 MiB by the UI.
3. Alternatively, connect the edge and choose a saved **complete live** rig session.
   Physical slots 1–4 map to cam_01–cam_04 independently of capture/display order.
   The bridge copies the saved JPEG bytes and original session/frame timestamps.
   Partial and simulated sessions are disabled. It does not start cameras or create
   a new hardware capture for you.
4. Click **Run inference**. Upload does not start inference automatically. The API's
   configured provider controls inference; the run explicitly identifies real or
   synthetic output. The UI polls queued/running work and exposes attempts, failures,
   reference IDs and model provenance. Refresh restores current server state.
5. Review before/after evidence for each camera-local proposal. Select source,
   crop or run overlay; inspect uncertainty. Individual masks are stored as COCO
   compressed RLE JSON. Use **Download mask RLE JSON** for the unchanged original;
   there is no individual mask image preview. JSON artifact links are signed with
   an attachment disposition. Record Accept, Reject or Needs review,
   with a reviewer label and optional reason. Decision audit is append-only.
6. Explicitly select accepted proposals, enter a message and commit. Selection is
   never automatic. Only the selected accepted changes advance approved history.
   Empty revisions are unavailable. Stale baselines need reprocessing; inspection
   runs cannot be committed. Once a run contributes a revision, reprocess remaining
   observations against the new head instead of appending from that old baseline.
7. Open an approved revision to inspect four source images, approved object evidence,
   provenance, accepted track history and endpoint-state comparisons in either direction.
   Rejected newer observations can leave an object's approved image on an older capture;
   the source capture is shown explicitly. The parent event sequence remains inspectable.

Review and commit requests retain idempotency keys across failed retries of the same
intent. Uploads have no backend idempotency key: after a timeout, refresh the capture
list before repeating an upload. Signed URLs expire; **Refresh evidence** requests new
ones. A missing asset stays explicitly unavailable. No fallback to simulated results
occurs when the API or real models fail.

## Boundaries and endpoint mapping

| UI action | Scene Tracker API under `/api/v1` |
| --- | --- |
| Saved-space picker / creation | `GET /environments`, `POST /environments` |
| Capture list / immutable upload | `GET/POST /environments/{id}/captures` |
| Run state and evidence | `GET /captures/{id}/workflow`, `/processing-runs` |
| Start or retry | `POST /captures/{id}/process` |
| Proposed changes | `GET /processing-runs/{id}/changes` |
| Review / audit | `POST /change-proposals/{id}/decision`, `GET .../decisions` |
| Commit / revision list | `POST/GET /environments/{id}/revisions` |
| Approved evidence / provenance | `GET /revisions/{id}/evidence` |
| Net state comparison / parent event log | `GET /revisions/{id}/compare`, `/diff` |
| Accepted object history | `GET /view-tracks/{id}/revisions` |
| Projection boundary | Signed image layers and capture/camera highlight manifests |

Image evidence is in canonical image coordinates. It is never converted to metric
scene positions or cross-camera physical identities. Image history is linear, while
the independent layout workflow retains its branches. Existing PLY/GLB viewing and
projector tools are accessible alongside image history; there is no automatic mapping
from image masks to an independently opened cloud. The pulled frontend also has an
independent WSL PointDiT export/generation flow and Camera rig viewer, described in
the frontend README. Its Windows startup script enables that flow using its WSL
paths; it is separate from Scene Tracker's reconstruction jobs and immutable
per-capture point-map history, which remain Phase 9. No aligned/fused cloud is implied.

## Verification and manual real smoke

```powershell
# From frontend/ after building:
pnpm lint
pnpm test
$env:SPACEGIT_BROWSER='C:\Program Files\Google\Chrome\Application\chrome.exe'
$env:SPACEGIT_TEST_EDGE_URL='http://127.0.0.1:8002'
pnpm exec playwright test --config playwright.image-history.config.ts
```

The browser contract suite intercepts API/rig responses. It checks explicit review and
commit selection, slot/timestamp/byte preservation, API errors, public-host guards and
desktop/mobile rendering. It does not validate pretrained quality or physical cameras.
`SPACEGIT_TEST_URL` reuses an already running frontend instead of starting one.

The real smoke is opt-in and uses the actual running API, Linux worker and installed
models. Provide four existing JPEGs named cam_01.jpg through cam_04.jpg:

```powershell
$env:SPACEGIT_TEST_URL='http://127.0.0.1:3101'
$env:SPACEGIT_RUN_REAL_SMOKE='1'
$env:SPACEGIT_REAL_IMAGES='D:\path\to\four-images'
pnpm exec playwright test --config playwright.image-history.config.ts --grep 'real images traverse'
```

It creates a clearly named real-smoke space, uploads/processes the photos, verifies real
provenance and signed browser images, saves screenshots and leaves all proposals for
human review. It never downloads weights, accepts changes or commits a revision.
Example photos exercise execution and contracts, not calibrated identity/movement
accuracy for a fixed real rig. Outputs are under ignored `frontend/test-results/`.
