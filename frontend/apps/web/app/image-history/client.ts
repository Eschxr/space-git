/** Scene Tracker's camera-local image history. Independent of metric edge scenes. */
export const CAMERAS = ['cam_01', 'cam_02', 'cam_03', 'cam_04'] as const;
export type Camera = typeof CAMERAS[number];
export type Page<T> = {items: T[]; limit: number; offset: number};
export type Space = {id: string; name: string; created_at: string; prompts: string[] | null};
export type Capture = {id: string; environment_id: string; captured_at: string; status: string; warnings: string[]; error: string | null};
export type Asset = {storage_key: string; sha256: string | null; content_type: string | null; url: string | null; unavailable_reason: string | null};
export type SourceImage = {id: string; capture_id: string; camera_id: Camera; role: string; width: number; height: number; sha256: string; captured_at: string | null; image: Asset};
export type Observation = {capture_id: string; frame_id: string; camera_id: Camera; detection_id: string; run_id: string | null; label: string; box_xyxy: number[]; width: number; height: number; image: Asset; mask: Asset | null; crop: Asset | null; overlays: Asset[]};
export type Track = {view_track_id: string; camera_id: Camera; state: Record<string, unknown>; observation: Observation};
export type Run = {id: string; capture_id: string; status: string; provider: string | null; inference_performed: boolean; error: string | null; attempt: number | null; scheduled_at: string | null; config_hash: string; reference: {kind: string; capture_id: string | null; revision_id: string | null; inspection_reason: string | null} | null; model_provenance: Record<string, unknown>; review_counts: Record<string, number>; committed_revision_ids: string[]};
export type Workflow = {capture: Capture; source_images: SourceImage[]; latest_run: Run | null; observed_tracks: Track[]; approved_revision_id: string | null; outcome: string};
export type DecisionStatus = 'accepted' | 'rejected' | 'needs_review';
export type Proposal = {id: string; run_id: string; camera_id: Camera; view_track_id: string; type: string; status: string; reason: string | null; evidence: Record<string, unknown>; before_ref: {label: string; visualization: Observation | null} | null; after_ref: {label: string; visualization: Observation | null} | null};
export type Decision = {id: string; previous_status: string; new_status: DecisionStatus; reason: string | null; reviewer: string; decided_at: string};
export type Revision = {id: string; environment_id: string; capture_id: string; parent_id: string | null; message: string; created_at: string};
export type RevisionEvidence = {revision: Revision; source_images: SourceImage[]; approved_tracks: Track[]; changes: Proposal[]; highlight_paths: string[]; provenance: Record<string, unknown>};
export type Comparison = {direction: string; items: {view_track_id: string; camera_id: Camera; kind: string; fields: string[]; before: Track | null; after: Track | null}[]};
export type TrackHistory = Page<{revision: Revision; state: Track; before: Track | null; changes: Proposal[]}>;
export type Upload = {images: Record<Camera, Blob>; capturedAt?: string; frameTimes?: Partial<Record<Camera, string>>};

export class TrackerError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;
  constructor(message: string, status: number, code: string, details: Record<string, unknown>) {
    super(message); this.status = status; this.code = code; this.details = details;
  }
}

export function trackerClient(base: string, fetcher: typeof fetch = fetch) {
  const origin = base.replace(/\/$/, '');
  async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    const multipart = body instanceof FormData;
    const timeout = AbortSignal.timeout(multipart ? 120000 : 20000);
    let response: Response;
    try {
      response = await fetcher(origin + '/api/v1' + path, {
        method: body === undefined ? 'GET' : 'POST', cache: 'no-store',
        signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
        headers: body !== undefined && !multipart ? {'Content-Type': 'application/json'} : undefined,
        body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
      });
    } catch (error) {
      if (signal?.aborted) throw error;
      throw new Error('Scene Tracker is unreachable at ' + origin + '. Check the API, Docker services and browser origin. A timed-out write may have succeeded; refresh before retrying an upload.');
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new TrackerError(data.error?.message ?? (typeof data.detail === 'string' ? data.detail : 'Request failed (' + response.status + ').'), response.status, data.error?.code ?? 'request_failed', data.error ?? {detail: data.detail});
    return data as T;
  }
  const id = encodeURIComponent;
  const page = (offset = 0) => '?limit=50&offset=' + offset;
  return {
    base: origin,
    spaces: (offset = 0, signal?: AbortSignal) => request<Page<Space>>('/environments' + page(offset), undefined, signal),
    createSpace: (name: string) => request<Space>('/environments', {name}),
    captures: (space: string, offset = 0, signal?: AbortSignal) => request<Page<Capture>>('/environments/' + id(space) + '/captures' + page(offset), undefined, signal),
    revisions: (space: string, offset = 0, signal?: AbortSignal) => request<Page<Revision>>('/environments/' + id(space) + '/revisions' + page(offset), undefined, signal),
    upload: (space: string, upload: Upload) => {
      const form = new FormData();
      for (const camera of CAMERAS) {
        const blob = upload.images[camera];
        const extension = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}[blob?.type];
        if (!blob || !extension) throw new Error(camera + ': choose a JPEG, PNG or WebP image.');
        if (!blob.size || blob.size > 20 * 1024 * 1024) throw new Error(camera + ': image must be between 1 byte and 20 MiB.');
        form.append(camera, blob, camera + '.' + extension);
        if (upload.frameTimes?.[camera]) form.append(camera + '_captured_at', upload.frameTimes[camera]!);
      }
      if (upload.capturedAt) form.append('captured_at', upload.capturedAt);
      return request<Capture>('/environments/' + id(space) + '/captures', form);
    },
    workflow: (capture: string, signal?: AbortSignal) => request<Workflow>('/captures/' + id(capture) + '/workflow', undefined, signal),
    runs: (capture: string, offset = 0, signal?: AbortSignal) => request<Page<Run>>('/captures/' + id(capture) + '/processing-runs' + page(offset), undefined, signal),
    process: (capture: string, retry = false) => request('/captures/' + id(capture) + '/process', {preset: 'default', retry}),
    changes: async (run: string, signal?: AbortSignal) => {
      const items: Proposal[] = [];
      for (let offset = 0; ; offset += 100) {
        const next = await request<Page<Proposal>>('/processing-runs/' + id(run) + '/changes?limit=100&offset=' + offset, undefined, signal);
        items.push(...next.items);
        if (next.items.length < 100) return items;
      }
    },
    decide: (proposal: string, status: DecisionStatus, reason: string, reviewer: string, key: string) => request('/change-proposals/' + id(proposal) + '/decision', {status, reason: reason || null, reviewer, idempotency_key: key}),
    decisions: (proposal: string, offset = 0, signal?: AbortSignal) => request<Page<Decision>>('/change-proposals/' + id(proposal) + '/decisions' + page(offset), undefined, signal),
    commit: (space: string, capture: string, proposalIds: string[], message: string, key: string) => request<Revision>('/environments/' + id(space) + '/revisions', {capture_id: capture, proposal_ids: proposalIds, message, idempotency_key: key}),
    evidence: (revision: string, signal?: AbortSignal) => request<RevisionEvidence>('/revisions/' + id(revision) + '/evidence', undefined, signal),
    compare: (before: string, after: string, signal?: AbortSignal) => request<Comparison>('/revisions/' + id(after) + '/compare?from_revision_id=' + id(before), undefined, signal),
    diff: (revision: string, signal?: AbortSignal) => request<{changes: Proposal[]}>('/revisions/' + id(revision) + '/diff', undefined, signal),
    trackHistory: (track: string, offset = 0, signal?: AbortSignal) => request<TrackHistory>('/view-tracks/' + id(track) + '/revisions' + page(offset), undefined, signal),
  };
}
export type Tracker = ReturnType<typeof trackerClient>;

/** Slot identity is fixed, regardless of the edge's presentation/capture order. */
export function completeSession(session: {mode: string; feeds: number[]}) {
  return session.mode === 'live' && session.feeds.length === 4 && [1, 2, 3, 4].every(slot => session.feeds.includes(slot));
}

export function intentKey(previous: {payload: string; key: string} | null, payload: unknown) {
  const serialized = JSON.stringify(payload);
  return previous?.payload === serialized ? previous : {payload: serialized, key: crypto.randomUUID()};
}
