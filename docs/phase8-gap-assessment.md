# Remaining work through the original Phase 8 equivalent

This is a source/test audit after Phase 5 (`d679d7b`), not a new implementation or
real-inference validation. The original Phase 6–8 requirements remain in
[the archived plan](legacy-implementation-plan.md). The active model pipeline remains
**YOLOE prompt-free + DINOv2**, with camera-local identity and human review.

## Correction to the earlier progress mapping

The subsequent Phase 6–8 implementation has completed these gaps. Its evidence,
commands and platform limits are recorded in [implementation-status](implementation-status.md).
The audit below preserves the findings that defined that work.

R4 implemented the core Phase 7/8 mechanics and passed a two-capture fake workflow.
Describing those phases simply as "delivered" hid remaining requirements. Phase 5
completed tracking, not the full image-history product. The plan now explicitly
retains Phase 6–8 completion work. No existing history functionality was removed
from application code when the old specification was archived.

## What is already implemented

- Exactly four immutable source images, canonical masks/crops/embeddings, durable
  processing runs and camera-specific inspection artifacts.
- Stable camera-local tracks, prototypes, missing/reappearance state, scored ambiguous
  candidates and a paginated **observational** track-history endpoint.
- Coarse appeared/moved/appearance/missing/reappeared/uncertain proposals, compared
  against eligible approved snapshots when available.
- Accept/reject/needs_review decisions with a current reason field.
- Atomic, environment-serialized commits of selected accepted proposals from one
  succeeded capture/run, parent-linked linear revisions and idempotency/content checks.
- Immutable copied event payloads and materialized approved track snapshots. Rejected
  or unselected proposals do not change the approved state. Committed proposals cannot
  be rewritten; reprocessing preserves old artifacts/revisions.
- Revision listing/detail, ancestor event diffs, signed before/after image/mask/crop
  evidence and per-source-capture/camera highlight manifests.
- Fake service tests for baseline→move/add→commit, rejection, idempotency, immutable
  old state, some concurrent calls, and failure/reprocessing preservation.

The last completed Phase 5 gate was 87 offline and 19 service tests. This assessment
reads the implementation/tests; it does not rerun them or certify pretrained quality.

## Concrete gaps

### 1. Complete the observable capture/run/review workflow

Capture listing and individual run retrieval exist, but a client cannot currently
list all processing attempts for a capture. Add discoverable run history, chosen
baseline/provenance summaries and a clear distinction between observed state, pending
review and the current approved revision. Preserve current endpoint behavior.

Fix and test reference-selection edge cases before building on them: no prior approved
baseline, an approved baseline after intervening unapproved captures, retries/reprocessing
of an already-committed capture, explicit debug references, backdated captures and a
head that advances while a run is processing. Existing stale-baseline rejection is a
useful safeguard, but these cases do not yet have a complete workflow/test matrix.
Approved-reference selection currently excludes the same capture ID, so reprocessing
that capture needs an explicit documented policy rather than an implicit fallback.

A small CLI or documented HTTP walkthrough can make this usable without implementing
a frontend. A processable capture with no semantic changes needs a clear no-commit
outcome. Empty-baseline approval is an optional extension, not an original Phase 8
requirement; the current nonempty baseline restriction must remain explicit unless added.

### 2. Make review decisions auditable

`application/revisions.py:decide` updates the proposal's current status/reason in place.
It does not retain the previous decisions, decision times or reviewer identity.
Add an append-only review-decision trail while preserving immutable detection evidence
and committed payloads. Identical decision retries should not create conflicting audit
records. Distinguish decision history from the current review status.

Define the review behavior for uncertain identity, repeated missing observations and
reappeared tracks. Today accepting a proposal applies that run's complete track state;
accepting `uncertain` needs a clear documented meaning. If reviewer corrections or
same-camera reassociation are supported, represent them as explicit reviewed records,
not edits to original detections. Corrections are additional functionality; the existing
accept/reject flow must stay usable without cross-camera identity merging.

### 3. Finish revision snapshots as an image-history API

`GET /revisions/{id}` currently returns metadata plus raw stored track states. It does
not assemble the complete four-camera image/evidence response with signed original,
mask/crop and revision-relevant annotated overlay URLs. The diff route does sign
image/mask/crop evidence for changed tracks, but does not attach overlay URLs.
Add typed, versioned responses that make a historical revision inspectable directly.

Expose source capture/run/model/config and immutable artifact/hash provenance directly
in that response or a linked manifest. Some provenance is already recoverable through
run IDs and immutable debug artifacts; it should not be described as absent, but is
not yet a complete revision-level contract.

Keep approved semantic state distinct from source images: when a move is rejected,
the latest capture image still shows the observation while the approved track state
retains earlier evidence. Do not present that mixed approved state as if every region
came from the revision's latest source image. Include unchanged cameras/tracks too.

### 4. Separate event logs from state comparisons

The current `/revisions/{id}/diff?from_revision_id=...` walks the ancestor chain and
returns committed events. It does **not** compare the two materialized endpoint states.
For example, moving an object out and back generates two events; a net comparison
should also be able to say its endpoint position is unchanged.

Preserve the current event-diff API and add an explicit approved-state comparison
contract: added/missing/restored/changed tracks, endpoint before/after observations,
per-camera evidence and deterministic ordering. Support identical-revision and
nonadjacent ancestor comparisons; document reverse/unrelated comparison behavior.
This is useful completion of the Git-like image-history workflow, beyond the minimal
two-revision event-diff gate already passed.

### 5. Add accepted per-track history

The Phase 5 track history lists processing-run snapshots, including explicitly tagged
failed/running runs. It is not a log of accepted revisions for that track. The original
Phase 8 requires per-object history; under the new identity contract this becomes
**per-view-track accepted history** unless the operator optionally supplies a physical link.

Add a query showing which revisions changed a track, accepted before/after states,
reviewed events and image evidence. Observed-but-rejected changes must remain visible
as observations without appearing as accepted history. Preserve legacy revision payloads.

### 6. Complete the Phase 7/8 acceptance tests

Existing happy-path tests are substantial, but do not yet establish the full contract:

- Baseline→unchanged→moved/new→partly rejected→missing→reappeared across several revisions.
- Correct parent chain and deterministic complete approved snapshots at every revision.
- Per-track accepted history distinct from observations/rejected proposals.
- Repeated/reversed review decisions with immutable audit history and retry semantics.
- Two competing **new** commits against the same head (existing concurrent E2E calls
  repeat an already-created revision); stale-head behavior and transaction rollback.
- Existing-other-environment proposals/captures and invalid review states rejected
  atomically, without partial revisions/snapshots.
- Changed model/run versions and failed retries leave every historical revision intact.
- State comparison across intermediate changes, stable response-schema contracts,
  correct signed four-camera/overlay evidence and missing storage evidence behavior.

A snapshot re-materialization consistency check is useful. A general event-replay
engine, branches, merges, image-delta chains and 3D are not prerequisites: the original
plan explicitly kept replay a future path and branching/merging out of scope.

## Restored implementation sequence

| Phase | Remaining scope | Completion gate |
|---|---|---|
| 6 | Capture/run/review workflow and reference-policy completion | A client can discover runs and inspect four-view observed/pending/approved state; edge references behave deterministically |
| 7 | Append-only review audit, explicit uncertain/missing/reappearance decisions, complete proposal evidence | Repeated decisions are auditable; accepted/rejected/uncertain semantics are tested without mutating originals |
| 8 | Complete revision image/provenance responses, approved per-track history, state comparisons and transaction/schema gates | Multi-revision fake image-history workflow round-trips with correct snapshots, evidence and accepted history |

Implement one phase at a time and stop at its gate. Reuse R4/R6 and Phase 5 code;
these are completion/hardening phases, not replacement implementations.

## Deliberate scope changes and independent gates

The old Phase 6 automatic multi-camera candidate/physical-object engine is not needed
under the refactor. Manual cross-camera links remain optional and would need a separate
scoped implementation if desired. cam_04 remains an independent camera, not a spatial map.
The image-history system can be complete using view-track IDs.

Real YOLOE/DINOv2 setup and image-quality validation remain outstanding operational
work, via [the runbook](codex-real-inference-runbook.md). They are separate from proving
history/transaction contracts with fake adapters. PointDiT real reconstruction belongs
to Phase 9 and is not required to complete the original Phase 8 image-history scope.
