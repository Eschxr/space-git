# SpaceGit — Devpost submission copy

Prepared 15 November 2026 from the repository and recorded validation. This is a
copy-ready draft, not a submitted entry. Replace `[TEAM INPUT: ...]` before submitting.
The first-person inspiration/learning narrative is proposed wording for team review.

## Project overview

Team: **ZygomorphicMereOtter**. Institution: **Durham University**.
Guild: **Skyline**. Table: **203-N5** (room **TLC203**, row **N**, column **5**).
Primary sponsor category: **Marshall Wace Challenge 1 — New Worlds**.

### Project name — paste this

SpaceGit

### Elevator pitch — paste this

Version control for new worlds: capture physical spaces, review AI-proposed changes, and explore their approved image history alongside 3D and projection tools.

### Short introduction

SpaceGit brings a familiar software habit into the physical world: record a state,
inspect what changed, and approve the changes worth keeping. Four camera views
become a reviewable history, with the source images always attached.

## Project Story — paste the section below into About the project

## Inspiration

Software teams can inspect a diff before accepting a change. Shared physical
spaces rarely have that convenience. After someone rearranges a desk, changes a
workshop or moves equipment in a lab, a photograph can show the scene, but finding
what changed and explaining which version matters is still manual work.

We built SpaceGit around a question: what would a review-and-commit workflow look
like for a room? We wanted the useful parts of version control—evidence, explicit
decisions and a history people can revisit—without pretending a camera understands
everything it sees.

## Exploring New Worlds

We interpret “New Worlds” as discovering new ways to understand and interact with
the spaces we already inhabit. A room has a past, a present and possible future
arrangements. SpaceGit makes its observed changes reviewable, while the independent
layout, 3D and projector tools let people explore representations and possibilities.
The connection starts with evidence and human decisions; automatic mask-to-cloud
correspondence remains a future integration step.

## What it does

SpaceGit lets you create a saved space and add four fixed camera views: three side
views and one overhead view. You can upload files or import a complete saved
four-camera session from the local camera edge.

YOLOE identifies objects and instance masks. DINOv2 supplies appearance features
for matching observations within the same camera view. The system proposes changes
such as an object appearing, moving, changing appearance or becoming missing from
view. Ambiguous matches stay visible for human review.

You inspect the source images, object crops and run overlays, then accept, reject
or flag each proposal. Accepting a proposal does not silently rewrite history:
you explicitly select accepted changes and commit them. Approved revisions retain
their source evidence and model provenance, so you can compare states and follow
an object's accepted history later.

Alongside image history, SpaceGit includes an independent metric layout workflow
with branches, a 3D scene/model viewer and projector output. The frontend also has
a WSL PointDiT integration for generating four per-view point clouds and inspecting
them in a camera-rig viewer when that external environment is configured.

## How we built it

The interface uses Next.js, React, TypeScript and Three.js. A local Python camera
edge handles saved rig frames, hardware controls and its own SQLite layout history.

The image-history backend uses FastAPI, PostgreSQL, Redis/RQ and Silo object
storage. PostgreSQL owns durable run status, review decisions and approved
revisions. Object storage retains the original image bytes and versioned run
artifacts. Vision runs in a Linux worker using PyTorch, pretrained YOLOE and DINOv2;
the API stays independent of model initialization. Docker Compose makes the
backend services reproducible while the frontend and camera edge run locally.

We connected the independently developed frontend and backend through explicit
API contracts. Image evidence and metric layouts keep their own histories rather
than forcing incompatible coordinate systems and IDs together.

## Challenges we ran into

An AI observation is not automatically a fact. Similar-looking objects, occlusion
and missing observations make tracking uncertain, so we designed review into the
workflow and kept evidence attached to decisions.

The frontend's branched metric layouts and the backend's linear image history
also represented different things. A separate Image history workspace let both
remain useful. Immutable originals, stale-baseline checks and explicit commits
help keep later processing from changing an earlier approved result.

Runtime integration was another challenge: the camera edge and vision backend
use separate Python environments, and the durable worker needs Linux. We used
Docker for the API and worker, separate local ports, verified model assets and
browser tests across the service boundaries.

## Accomplishments we're proud of

We connected real pretrained inference to a complete browser upload and review
flow. One recorded four-image smoke run produced 69 observations and 69 proposals,
all left pending for human review. That demonstrates execution of the pipeline;
it is not an accuracy benchmark or proof of tracking quality on a fixed rig.

We also retained a clear boundary between observations and approved history,
including decision audit, selected commits, source hashes and revision provenance.
Automated checks cover backend contracts, real infrastructure, the camera edge
and browser workflows, with synthetic fixtures identified separately from real
model execution.

## What we learned

The valuable output is more than a detection or a point cloud. It is a change
someone can inspect, explain and choose to accept. Preserving uncertainty and
source evidence made the product easier to reason about than treating every model
prediction as ground truth.

We also learned that integration depends on agreeing what a record means: a
camera-local track, a metric object and a point in a cloud are not interchangeable.

## What's next for SpaceGit

Next is connecting approved image changes to matching per-view point maps, with
recorded pixel-to-point correspondence and immutable reconstruction provenance.
We also want to evaluate tracking on controlled, repeated captures of real spaces
and improve the review experience as histories grow.

Automatic cross-camera identity, metric motion from these images and a verified
fused reconstruction are outside the current image-history implementation.

## Built with — suggested tags, maximum 25

Use the following 20 tags, selecting the closest existing Devpost spelling:

`Python`, `TypeScript`, `Next.js`, `React`, `Three.js`, `FastAPI`, `PyTorch`,
`YOLOE`, `DINOv2`, `PointDiT`, `OpenCV`, `PostgreSQL`, `Redis`, `RQ`, `SQLite`,
`Docker`, `Silo`, `uv`, `Git`, `Playwright`.

OpenAI/Codex was used as development assistance in this collaboration. Do not
describe an OpenAI API integration in the running application unless the team
confirms one. Add COLMAP as a tag only if presenting that optional feature.

## Try it out links

| Label | URL | Description |
| --- | --- | --- |
| Source code | https://github.com/Eschxr/space-git | Main repository; confirm judges can access it. |
| Public demo | https://spacegit-3d.vercel.app | Repository-listed simulation/read-only demo; check availability before submitting. It does not expose local image inference or hardware. |
| Local demo instructions | https://github.com/Eschxr/space-git/blob/main/docs/frontend-integration.md | Local services, models and operator workflow. |
| Workflow diagrams | https://github.com/Eschxr/space-git/blob/main/docs/workflow-and-system-diagrams.md | Visible after this document is committed and pushed. |

The public URLs could not be verified by the browsing tool during preparation.
Do not put localhost links in the public Try it out fields. The local workstation
entry point is http://127.0.0.1:3101/image-history for an in-person demonstration.

## Additional info — organizer fields

| Field | Answer / action |
| --- | --- |
| Sponsor / Special Prizes | **Marshall Wace Challenge 1** — team-confirmed brief: “Make a project that explores the idea of New Worlds.” Additional recommended entry: **[MLH] DEV Writing Challenge**, pending publication. See [prize assessment](devpost-prize-assessment.md). |
| Guild | Skyline |
| Room | TLC203 |
| Row | N — the supplied form options omit N; confirm the live dropdown/organizer correction rather than selecting a different row. |
| Column | 5 |
| Table number in plaintext | 203-N5 |
| Universities or schools | Durham University |
| AI tools used this weekend | Select **OpenAI** only. The team confirmed no other AI tools beyond the already discussed model stack. YOLOE, DINOv2 and PointDiT remain in Built with; do not infer Hugging Face or other checkbox selections from model use. |
| GoDaddy Registry domains | `[TEAM INPUT: registered domain names, or N/A if none]` |
| Gemini Project Number | N/A — no Gemini API integration reported. |
| Video demo URL | `[TEAM INPUT: uploaded video URL]` |

### Technology feedback — suggested wording for team review

Docker Compose helped us separate the vision runtime from the Windows camera
workflow and reproduce the API, database, queue and object store together.
Making service ports, model mounts and host-versus-container URLs explicit was
essential when joining independently developed components.

YOLOE and DINOv2 gave us pretrained object and appearance features to build on.
Their predictions still needed source evidence and human review, especially for
similar objects and occlusion. OpenAI/Codex assisted with engineering and
integration; tests and visual inspection remained necessary to catch incorrect
assumptions at component boundaries.

### Generative AI model or API — suggested answer

Yes. We implemented an integration with pretrained PointDiT for image-to-3D
generation through a separate WSL runtime. It produces per-view point clouds for
visual inspection when that environment is configured; we did not train the model
from scratch. YOLOE and DINOv2 support object perception and appearance matching,
rather than text generation. OpenAI/Codex was used for development assistance.
The current application does not claim an OpenAI or Gemini inference API
integration. Automatic projection of approved image changes onto generated point
maps remains future backend integration work.

Team confirmation: distinguish the implemented PointDiT wrapper from any actual
PointDiT runs the team demonstrated this weekend. The recorded local verification
in this chat covers real YOLOE/DINOv2 execution, not a real WSL PointDiT run.

## Submission notes — do not paste into the public story

- Review the proposed inspiration, achievements and learning in the team's own voice.
  Confirm which components were built during this event, which predated it, and each
  member's contributions against the event rules; that provenance is not established
  by this write-up. Credit all collaborators and reused components.
- Keep real-model execution, synthetic fixtures, public simulation and optional WSL
  generation clearly labeled. Do not claim 69 correct detections, measured tracking
  accuracy, four aligned clouds, a completed restoration test or end-to-end Phase 9.
- Keep the original model/library attribution and license notices. See
  [third-party notices](../THIRD_PARTY_NOTICES.md) and bundled viewer license.
- Use media you made or have permission to publish. Attribute any reused example
  photos from the corresponding `sources.json`; do not upload private room imagery
  or personal details without permission.
- Gallery requirements supplied by the form: JPG/PNG/GIF, each at most 5 MB,
  preferably 3:2, at most 15 images. See [media and demo copy](devpost-media-and-demo.md).
- Devpost does not document Mermaid support in its Markdown guide. Use rendered
  diagram images in the gallery; do not assume a Mermaid fence will render there.
- Verify public links, replace every team placeholder, and confirm the video's
  access settings before submitting. No submission or external publication was made.

## Preparation references

- [Prize assessment and recommended additional entry](devpost-prize-assessment.md).
- [DEV article draft](dev-article-draft.md), prepared for team review and publication.

- [Devpost Community Guidelines](https://info.devpost.com/legal/devpost/community-guidelines): accurate representation, credit, rights and privacy.
- [Devpost Markdown and LaTeX guide](https://help.devpost.com/article/193-markdown-tips): story formatting.
- [Devpost video guide](https://help.devpost.com/article/85-uploading-a-demo-video): upload to a supported host and supply an accessible share link; check event-specific rules.
- [Implementation and validation record](implementation-status.md).
- [System diagrams](workflow-and-system-diagrams.md).
