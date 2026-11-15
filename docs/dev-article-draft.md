---
title: "We built version control for a room. The hardest part was deciding what a change means."
published: false
description: "How SpaceGit separates camera observations, human review and approved history without losing source evidence."
tags: python, computervision, webdev, ai
---

<!-- Draft for team review. Confirm the event's DEV entry instructions and any
required tags before publishing. Replace the diagram/screenshot notes with actual
media and verify public links. No public post has been created. -->

We are **ZygomorphicMereOtter**, a Durham University team building **SpaceGit** at
DurHack 2026 for **Marshall Wace Challenge 1**, whose theme is **New Worlds**.
We approached that theme through familiar spaces: what would a useful diff look
like for a room, and how could we explore its past and possible arrangements?

A photograph records a room. It does not tell you which observations are reliable,
which changes someone agrees with, or why an earlier state should remain approved.
That gap became the core of our project.

## The workflow before the model

SpaceGit gives each saved space four fixed camera roles: three side views and an
overhead view. An operator uploads four images or imports a complete saved rig
session. We retain the original bytes, hashes and timestamps, then process working
copies with the correct image orientation.

YOLOE supplies object labels, boxes and instance masks. DINOv2 supplies appearance
features from object crops. The pipeline matches observations within a camera view
and proposes changes such as appearance, motion, disappearance from view or an
uncertain association.

The useful part comes next. A person inspects the image, crop or run overlay and
records Accept, Reject or Needs review. Accepting alone does not create a revision.
The operator selects accepted proposals and explicitly commits them.

That distinction is deliberate: a model observation is evidence to consider, while
an approved revision is a decision someone made.

## Three records that should not be confused

We needed to keep three kinds of record separate:

- **Original capture:** immutable source images and their metadata.
- **Processing run:** versioned observations, associations, proposals and model
  provenance. Failed attempts remain visible.
- **Approved revision:** an immutable snapshot created from selected accepted
  changes applied to its parent state.

Rejecting a newer observation can leave an object supported by an older approved
image. That is useful behavior: the newest image is not automatically the newest
approved evidence. The UI identifies the source capture for each object.

The same discipline applies to identity. A track belongs to a saved space and one
camera view. Two similar chairs in different views do not automatically become one
physical chair in the database. “Missing from view” does not prove physical removal.

## The local architecture

Our Next.js/React/TypeScript frontend talks to two services. A Python 3.12 camera
edge handles rig sessions and the independent metric-layout workflow in SQLite.
A Python 3.11 FastAPI backend handles reviewed image history.

The history backend uses PostgreSQL for durable records, Redis/RQ for queued work
and Silo/S3 for originals and run artifacts. The API and worker run in Linux
containers on this workstation. Model initialization stays in the worker; local
weights and the pinned DINOv2 source are verified and mounted read-only.

The browser can display source images and derivatives through short-lived signed
URLs. Review decisions retain an append-only audit, and revision commits copy the
selected events and their provenance atomically. A stale baseline must be
reprocessed instead of being silently applied to a newer approved head.

For the complete deployment and flow diagrams, see
[our architecture document](https://github.com/Eschxr/space-git/blob/main/docs/workflow-and-system-diagrams.md).
That link becomes available after these documents are committed and pushed.

<!-- Optional: insert a rendered architecture diagram here. DEV/Devpost support
for Mermaid should not be assumed; use an exported image and meaningful alt text. -->

## Integrating two histories

The independently developed frontend already had metric layouts, branches, model
viewing and projector tools. The image-history backend had linear approved
revisions with camera-local evidence. They did not share a coordinate system or
the same meaning of an object ID.

We added a separate Image history workspace rather than converting image boxes
into metres or pretending the two commit models were interchangeable. The existing
3D/projector workflow remains accessible alongside it.

The frontend also includes a WSL PointDiT generation wrapper and camera-rig viewer
for four per-view clouds when the external runtime is configured. Mapping an
approved image change onto matching 3D points still needs recorded pixel-to-point
correspondence. An unordered PLY alone cannot provide that information.

## A bug that a successful request did not catch

One integration assumption failed visual inspection. Individual object masks were
stored as COCO compressed RLE JSON, but the first UI tried to display their URLs
as images. A test also checked whether all image elements were decoded without
requiring any image elements to remain. Once the broken image disappeared, an
empty list incorrectly satisfied that check.

We corrected the check and changed the product behavior. The interface now shows
source images, object crops and run overlays, while the original mask is offered
as an RLE JSON download. We verified that a real downloaded artifact matched its
stored SHA-256.

The lesson was concrete: a successful HTTP response and a passing condition are
not enough if the condition does not describe what the person needs to see.

## What we have verified

A recorded browser smoke sent four example photos through the actual local
YOLOE/DINOv2 worker and produced 69 observations and 69 proposed changes. They were
left pending human review. That is an execution result, not 69 verified facts and
not a tracking-accuracy benchmark on a controlled camera rig.

Recorded checks also cover backend contracts, PostgreSQL/Silo/Redis integration,
the camera edge, browser review/commit behavior and the independent viewer tools.
Synthetic fixtures remain labeled separately. These checks do not establish real
WSL PointDiT quality, projector calibration accuracy or a fused reconstruction.

## Trying the review workflow

The [repository](https://github.com/Eschxr/space-git) contains
[local setup instructions](https://github.com/Eschxr/space-git/blob/main/docs/frontend-integration.md).
With the local services and model assets configured:

1. Create a saved space and upload four fixed-role images.
2. Run inference and inspect the recorded provider and run status.
3. Review a proposal using its source image, crop and overlay.
4. Record a decision, explicitly select accepted changes and commit a revision.
5. Capture the same space again with the cameras fixed, then compare approved states.

The repository-listed public demo is a simulation/read-only experience, not a
remote endpoint for your workstation's cameras or real inference. Verify its
availability before sharing it.

## What comes next

We want to evaluate repeated real captures under controlled changes and connect
accepted masks to per-view dense point maps with explicit correspondence metadata.
We also want to improve how people review larger histories without losing the
source evidence behind each decision.

Our most useful design decision so far has been to make approval a real operation.
A room history becomes more useful when it can explain both what the model saw
and what the person chose to accept.

## Credits and disclosure

SpaceGit builds on pretrained YOLOE, DINOv2 and the separate PointDiT integration,
along with the web, storage and vision libraries recorded in the repository.
See [third-party notices](https://github.com/Eschxr/space-git/blob/main/THIRD_PARTY_NOTICES.md)
and the bundled viewer license. We used OpenAI/Codex for development assistance;
we are not claiming an OpenAI inference API in the running application.

<!-- Before publication: add teammates' credited names/handles with permission,
confirm the narrative in the team's voice and identify any components developed
before the event. Check every public link and any required challenge tags. -->
