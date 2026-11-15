# SpaceGit workflow and system diagrams

These diagrams describe the merged implementation as of 15 November 2026.
Solid arrows describe implemented interfaces. Dashed arrows mark future Scene
Tracker Phase 9 work. The WSL PointDiT integration is a separate frontend/edge
workflow; its availability depends on that workstation's WSL installation.

## System layout and settings

```mermaid
flowchart TB
    CAM["Four fixed camera roles<br/>cam_01–03: side views about 120 degrees apart<br/>cam_04: overhead, looking down"]
    FILES["Manual JPEG / PNG / WebP files"]
    subgraph WIN["Windows workstation"]
        WEB["Next.js frontend · Node.js 24<br/>127.0.0.1:3101"]
        UI["Browser UI<br/>Image history · Capture · Hardware Studio<br/>Reconstruct · Project"]
        EDGE["Camera edge · FastAPI · Python 3.12<br/>127.0.0.1:8002"]
        LOCAL[("Edge SQLite and local files<br/>Saved JPEGs · settings<br/>Metric layouts · branches · assets")]
        MODELS[("Local pretrained assets<br/>YOLOE checkpoint<br/>DINOv2 checkpoint and pinned source")]
        subgraph DOCKER["Docker Desktop — Linux application profile"]
            API["Scene Tracker API · Python 3.11<br/>Host 8001 to container 8000"]
            REDIS[("Redis · 6379<br/>RQ queue of job/run IDs")]
            WORKER["Linux RQ vision worker<br/>YOLOE and DINOv2 · CPU"]
            PG[("PostgreSQL · 5432<br/>Spaces · captures · runs · tracks<br/>Proposals · decision audit · revisions")]
            SILO[("Private Silo/S3 storage<br/>Objects 9000 · console 9001<br/>Originals · masks · embeddings<br/>Crops · overlays · reports")]
            CACHE[("Writable model-cache volume")]
        end
        WEB -->|Serves application| UI
        UI <-->|Authenticated HTTP and WebSocket| EDGE
        EDGE <--> LOCAL
        UI -->|JSON and four-image multipart upload| API
        API --> PG
        API --> SILO
        API -->|Schedules processing| REDIS
        REDIS --> WORKER
        WORKER -->|Durable results and status| PG
        WORKER -->|Immutable run artifacts| SILO
        SILO -->|Short-lived signed URLs| UI
        MODELS -->|Read-only verification mount| API
        MODELS -->|Read-only model loading| WORKER
        WORKER <--> CACHE
    end
    CAM -->|Camera devices| EDGE
    FILES --> UI
    UI -->|Fullscreen browser output| DISPLAY["Second display or physical projector"]
```

| Setting | Local configuration |
| --- | --- |
| Frontend | `http://127.0.0.1:3101` |
| Scene Tracker API | `NEXT_PUBLIC_SCENE_TRACKER_URL=http://127.0.0.1:8001` |
| Camera edge | `NEXT_PUBLIC_SPACEGIT_EDGE_URL=http://127.0.0.1:8002` |
| Inference | `VISION_PROVIDER=real`, `YOLOE_DEVICE=cpu`, `VISION_DEVICE=cpu` |
| Models | Host `models/real-inference` mounted read-only at `/models` |
| Storage URLs | API uses `silo:9000`; browser uses signed `localhost:9000` URLs |
| Persistence | Separate PostgreSQL, Redis, Silo and model-cache volumes; edge SQLite/local files |
| Access | Loopback workstation; exact CORS origins; edge operator/local-session authentication |

Scene Tracker authentication remains outside the local MVP. The public frontend
demo does not call workstation services. The older checkout on 3000/3100/8000
remains separate. Settings are documented here without credentials.

## Image history: capture to approved revision

```mermaid
flowchart TB
    SPACE["Choose or create a saved space<br/>Environment UUID"] --> INPUT{Image source}
    INPUT -->|Manual| FOUR["Choose cam_01, cam_02, cam_03, cam_04"]
    INPUT -->|Saved rig session| RIG["Browser retrieves edge JPEGs<br/>Complete live 4/4 session only<br/>Preserve physical slots and timestamps"]
    FOUR --> UPLOAD["Upload four images to Scene Tracker"]
    RIG --> UPLOAD
    UPLOAD --> VALIDATE["Validate roles, MIME, dimensions,<br/>EXIF, timestamps and SHA-256"]
    VALIDATE --> ORIGINALS[("Immutable original bytes<br/>Ready capture with four frames")]
    ORIGINALS --> START["User clicks Run inference"]
    START --> REF["Verify models and freeze reference<br/>Approved head, eligible processed capture,<br/>or initial state"]
    REF --> QUEUE["Durable run and RQ job"]
    QUEUE --> RGB["EXIF-corrected RGB working copies"]
    RGB --> YOLOE["YOLOE prompt-free segmentation<br/>Labels, boxes and instance masks"]
    YOLOE --> DINO["DINOv2 appearance embeddings<br/>Masked, padded object crops"]
    DINO --> TRACK["Same-camera association<br/>Stable view tracks; uncertainty retained"]
    TRACK --> RESULTS["Persist observations and proposed changes<br/>Appear · move · appearance change<br/>Missing from view · reappear · uncertain"]
    QUEUE -->|Processing failure| FAILED["Record failure; fix cause and retry"]
    FAILED --> START
    RESULTS --> ANY{Any proposals?}
    ANY -->|No| NOCHANGE["No-change result; no empty revision"]
    ANY -->|Yes| REVIEW["Human reviews before/after evidence<br/>Source, crop and run overlay<br/>Download original mask RLE JSON"]
    REVIEW --> AUDIT[("Append-only decision audit<br/>Reviewer, reason and time")]
    REVIEW -->|Reject or Needs review| HOLD["Keep evidence and decision<br/>Approved state stays unchanged"]
    REVIEW -->|Accept| SELECT["Explicitly select accepted changes<br/>Enter revision message"]
    SELECT --> GUARD{Commit checks}
    GUARD -->|Stale baseline| START
    GUARD -->|Inspection only| INSPECT["Inspect; cannot commit"]
    GUARD -->|Valid| REV[("Atomic immutable revision<br/>Parent state plus selected accepted changes<br/>Source and model provenance")]
    REV --> HISTORY["Linear approved history<br/>Revision 1 to Revision 2 to Revision 3<br/>State comparisons and accepted track history"]
    REV -->|Baseline for later captures| REF
```

Accept and commit are separate actions. Rejected/unselected observations can leave
approved evidence on an older capture. Tracks are scoped to a space and camera;
missing from view does not establish physical removal. There is no automatic
cross-camera identity merge or metric movement estimate.

## Capture, reconstruction and projection

```mermaid
flowchart TB
    CAPTURE["Capture screen<br/>Configure slots; start previews; save session"]
    SAVED[("Edge SQLite<br/>Retained JPEGs and frame timestamps")]
    CAPTURE --> SAVED
    subgraph WSL["Optional WSL PointDiT workflow"]
        EXPORT["Four role-named JPEGs<br/>/home/wilson/test_images<br/>Latest export folder is replaced"]
        PD["Ubuntu user wilson<br/>PointDiT .venv<br/>scripts/demo_l_512.sh"]
        PLY[("Four latest per-view PLY files<br/>WSL generation output folder")]
        EXPORT --> PD --> PLY
    end
    SAVED -->|When generation is enabled| EXPORT
    SAVED -->|Browser imports complete session| IH["Scene Tracker Image history<br/>Human review and approved revisions"]
    PLY --> CLOUDAPI["Edge GET /rig/pointclouds/slot"]
    CLOUDAPI --> RIGVIEW["Reconstruct: Camera rig<br/>Embedded multi-camera viewer"]
    POSES["Bundled camera-poses.json<br/>Supplied transforms"] --> RIGVIEW
    METRIC[("Independent metric history<br/>SQLite layout commits and branches")]
    DEMO["Optional browser-local simulation"]
    LOCALPLY["Manually opened PLY / GLB / glTF"]
    subgraph COLMAP["Optional existing photo reconstruction"]
        PHOTOS["Overlapping photo session<br/>At least six images"]
        CW["Separate COLMAP worker"]
        ASSETS[("Registered local PLY / mesh assets")]
        PHOTOS --> CW --> ASSETS
    end
    METRIC --> SCENE["Reconstruct: Scene revision<br/>Layout or independently loaded model"]
    DEMO --> SCENE
    LOCALPLY --> SCENE
    ASSETS --> SCENE
    PLY -->|Manual file loading| LOCALPLY
    SCENE --> PROJECT["Project screen<br/>Physical scene/model or simulated office"]
    PROJECT --> WINDOW["Fullscreen window on extended display"]
    WINDOW --> HARDWARE["Physical projector or second monitor"]
    subgraph FUTURE["Pending Scene Tracker Phase 9"]
        MAP["Per-capture dense point maps<br/>Recorded pixel-to-point correspondence"]
        HIGHLIGHT["Accepted source masks mapped<br/>to matching per-view points"]
        MAP -.-> HIGHLIGHT
    end
    PD -.->|Future dense point-map export| MAP
    IH -.->|Accepted masks and source IDs| HIGHLIGHT
```

The camera-rig view has no automatic transfer of its combined display into Project.
Scene revision/model loading supplies the Project screen. An unordered PLY alone
cannot supply source-pixel correspondence. Supplied viewer poses do not establish
backend calibration, registration or a verified fused scene.

See [startup and operation](frontend-integration.md) and the
[frontend README](../frontend/README.md) for the WSL path requirements.
