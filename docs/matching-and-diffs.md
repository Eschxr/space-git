# Camera-local matching and reviewed diffs

Each environment/camera has independent durable view tracks. cam_04 is overhead and
uses its own tracks. `physical_objects` and manual link tables remain compatible but
are never populated automatically. A cross-camera move is missing/appeared evidence,
not a proven physical relocation.

Scheduling records the latest eligible accepted revision's **approved track snapshots**,
or a succeeded processed capture with tracking evidence when there is no eligible
approved baseline. It locks the environment while selecting and hashes that reference
into the processing config. All four cameras consume the recorded reference, including
when the head advances before execution. Future captures, same-capture processed-run
references and other environments are excluded.

An explicit `reference_capture_id` selects processed evidence for inspection.
Reprocessing the capture already at the approved head uses that head's approved states.
These runs and backdated captures whose eligible reference predates the current head
are inspection-only. Their results preserve earlier runs and revisions. Normal commits
require the recorded accepted parent to remain current. The API workflow response
exposes inspection/stale outcomes and source references.

Candidate scores combine compatible DINOv2 cosine appearance (0.45), normalized centre
position (0.25), canonical mask IoU or box IoU (0.20), soft class consistency (0.10), and scale similarity (0.05). Raw weights are
normalized by their effective sum; unavailable appearance is excluded.
Label case/plurals and a small explicit synonym map are normalized only for scoring;
raw model labels remain stored. Different classes are a soft penalty. Area-ratio and
appearance/spatial gates reject implausible candidates while allowing movement.
Hungarian assignment includes unmatched options. Small top-two margins on either side
block forced assignment; candidate terms and unresolved alternatives remain inspectable.
Reports persist actual costs and their term contributions, gate/reject reasons, both
sides' top-two valid scores/margins and explicit unmatched decisions. Close margins
block assignment when both alternatives clear the score threshold; a score equal to
the unmatched threshold remains unmatched. Ties and output ordering are deterministic. Missing embeddings use geometry/category
with an uncertainty penalty and yield uncertain change hypotheses, not strong identity.

`TRACKING` accepts JSON overrides in `.env` or environment, for example:

```dotenv
TRACKING={"movement_threshold":0.035,"minimum_score":0.65,"margin":0.08}
```

All defaults, weights, gates and tolerances live in `core/tracking_settings.py` and
are copied into the processing config hash. They are starting heuristics, not calibrated
probabilities. Normalized coordinates accommodate different image resolutions within
one fixed camera; they imply no metric/world coordinates.

First capture proposes `appeared_in_view` initial observations, never movement. Review
and commit those to establish the approved baseline. Subsequent changes are
`moved_in_view`, `appearance_changed`, `missing_from_view`, `reappeared` or `uncertain`.
Movement requires the configured normalized centre threshold and sufficient area.
Appearance uses compatible feature/area changes; sub-threshold lighting noise is
ignored, but larger illumination shifts can still trigger review. Missing means not
observed in the image, never physically removed. Missing tracks keep their last-visible
mask and may reappear on convincing same-camera evidence. Ambiguity never silently merges
identities. The MVP requires a nonempty selection of accepted proposals for a revision;
an empty scene has processed state but no empty baseline-commit operation.

Review can accept, reject or mark needs_review. Commit selects accepted proposals from
one succeeded run and capture, serializes on the environment, and copies their events
and resulting track states. Unselected/rejected changes do not affect accepted state.
Reusing an idempotency key with identical contents returns the existing revision;
different content returns 409. A proposal cannot be committed twice. Stale accepted
references return 409 and require reprocessing. Revision diffs copy committed evidence
and support an optional ancestor `from_revision_id`; signed visualization URLs are
regenerated and naturally change/expire while the underlying evidence remains immutable.

See [API](api.md) for review/commit calls and [highlight semantics](highlights.md).

Decisions append previous/new status, reasons, reviewer label, UTC time and an optional
idempotency key. A keyed retry returns its recorded decision alongside current proposal
status. Accepting an uncertain proposal applies its exact camera-local snapshot with
uncertainty retained. Repeated accepted missing events retain the last-visible
observation and advance the counter. Accepted reappearance resets it. Approved state
advances only through a selected commit.

Revision `/diff` retains the ancestor event log. Revision `/compare` returns endpoint
content with both observations and deterministic ordering. It includes unchanged tracks
and supports identical and reverse comparisons. The per-track `/revisions` endpoint
lists accepted changes with their prior/approved states. These APIs preserve source
capture/frame/camera references for overlays and future per-view cloud mapping.


Phase 5 retains a last-confident-embedding prototype in each immutable track snapshot.
It references the original vector blob plus source capture/frame/detection/camera and
metadata, rather than averaging vectors. A confident appearance-supported match advances
it; a missing mask/vector, low appearance confidence or missed observation retains it.
Ambiguous new tracks do not overwrite another identity. Geometry/masks still come from
the most recent observation; candidate evidence identifies the appearance source. Legacy
snapshots derive a reference in memory from their observation if available, without
rewriting history. No fabricated embedding is attached to a maskless detection.

Read-only track/history endpoints are documented in [API](api.md). Snapshot schema v2
and the new pipeline configuration preserve old run IDs/artifacts/revisions. No new
relational migration or model dependency is needed for this Phase 5 consolidation.
