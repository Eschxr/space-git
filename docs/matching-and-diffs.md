# Camera-local matching and reviewed diffs

Each environment/camera has independent durable view tracks. cam_04 is overhead and
uses its own tracks. `physical_objects` and manual link tables remain compatible but
are never populated automatically. A cross-camera move is missing/appeared evidence,
not a proven physical relocation.

Reference selection prefers the latest eligible accepted revision's **approved track
snapshots**, then a succeeded processed capture with tracking evidence. Future captures,
same-capture references and other environments are excluded. An explicit
`reference_capture_id` on process requests selects processed evidence for debugging.
Chosen run/capture/revision references persist in tracking JSON and each snapshot.
Explicit debug references cannot be committed on top of an unrelated accepted baseline.

Candidate scores combine compatible DINOv2 cosine appearance (0.45), normalized centre
position (0.25), canonical mask IoU or box IoU (0.20), and soft class consistency (0.10).
Label case/plurals and a small explicit synonym map are normalized only for scoring;
raw model labels remain stored. Different classes are a soft penalty. Area-ratio and
appearance/spatial gates reject implausible candidates while allowing movement.
Hungarian assignment includes unmatched options. Small top-two margins on either side
block forced assignment; candidate terms and unresolved alternatives remain inspectable.
Ties and output ordering are deterministic. Missing embeddings use geometry/category
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
