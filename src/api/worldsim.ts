/**
 * Typed worldsim operations over the generated contract (C1).
 *
 * DTOs come from `content/clients/worldsim.ts` (regenerate: run the export
 * plus `backend/scripts/gen_ts_client.py`; see README). Every call takes an
 * explicit story/world id where applicable — never the single-world
 * convenience path — plus the caller's role. First-story creation is never
 * gated on the world-count readiness check (see `seedStatus` in client.ts).
 */

import type {
  ActivityListResponse,
  ActivityView,
  DraftValidationView,
  EditorDraftCompleteRequest,
  EditorDraftOpenRequest,
  EditorDraftPublishRequest,
  EditorDraftSaveRequest,
  EditorDraftView,
  InterventionCancelRequest,
  InterventionEditRequest,
  InterventionRequest,
  InterventionView,
  MapResponse,
  PresetDetail,
  PresetPublishView,
  PresetSummary,
  RoleGrantView,
  RoleSelectRequest,
  Stage1AdvanceRequest,
  Stage1AdvanceResponse,
  StoryCreateResponse,
  StoryDetail,
  StoryDraftCreateRequest,
  StoryDraftPatchRequest,
  StoryDraftView,
  StoryListResponse,
  StorySetupView,
  TimelineResponse
} from '../../content/clients/worldsim'
import { apiFetch, type Role } from './http'

export type { Role }

export interface CallOptions {
  role?: Role
  characterId?: string
  signal?: AbortSignal
  timeoutMs?: number
}

/* Presets --------------------------------------------------------------- */

export function listPresets(
  kind: string | undefined,
  opts: CallOptions = {}
): Promise<PresetSummary[]> {
  const query = kind ? `?kind=${encodeURIComponent(kind)}` : ''
  return apiFetch<PresetSummary[]>(`/library/presets${query}`, { ...opts, method: 'GET' })
}

export function getPreset(
  id: string,
  revision: number | undefined,
  opts: CallOptions = {}
): Promise<PresetDetail> {
  const query = revision !== undefined ? `?revision=${revision}` : ''
  return apiFetch<PresetDetail>(`/library/presets/${id}${query}`, { ...opts, method: 'GET' })
}

export function createPreset(
  kind: string,
  name: string,
  payload: Record<string, unknown>,
  idempotencyKey: string,
  opts: CallOptions = {}
): Promise<PresetDetail> {
  // Durable creation identity: the caller mints one stable key per local
  // draft and reuses it across retries, so a lost response replays instead
  // of minting a second preset. The server receipt is still pending — new
  // presets stay local-until-publish and this wrapper is not yet wired to
  // any publish path.
  return apiFetch<PresetDetail>('/library/presets', {
    ...opts,
    method: 'POST',
    body: { kind, name, payload },
    idempotencyKey
  })
}

/* Preset editor drafts (E3) ------------------------------------------------ */

export function openEditorDraft(
  presetId: string,
  baseRevision: number,
  opts: CallOptions = {}
): Promise<EditorDraftView> {
  const body: EditorDraftOpenRequest = { base_revision: baseRevision }
  return apiFetch<EditorDraftView>(`/library/presets/${presetId}/editor-drafts`, {
    ...opts,
    method: 'POST',
    body
  })
}

export function readEditorDraft(
  presetId: string,
  opts: CallOptions = {}
): Promise<EditorDraftView> {
  return apiFetch<EditorDraftView>(`/library/presets/${presetId}/editor-drafts/current`, {
    ...opts,
    method: 'GET'
  })
}

export function saveEditorDraft(
  presetId: string,
  draftId: string,
  fields: EditorDraftSaveRequest['fields'],
  version: number,
  opts: CallOptions = {}
): Promise<EditorDraftView> {
  const body: EditorDraftSaveRequest = { fields, expected_version: version }
  return apiFetch<EditorDraftView>(`/library/presets/${presetId}/editor-drafts/${draftId}`, {
    ...opts,
    method: 'PATCH',
    body
  })
}

export function discardEditorDraft(
  presetId: string,
  draftId: string,
  version: number,
  opts: CallOptions = {}
): Promise<{ draft_id: string }> {
  return apiFetch<{ draft_id: string }>(
    `/library/presets/${presetId}/editor-drafts/${draftId}?expected_version=${version}`,
    { ...opts, method: 'DELETE' }
  )
}

export function completeEditorDraft(
  presetId: string,
  draftId: string,
  version: number,
  opts: CallOptions = {}
): Promise<{ draft_id: string }> {
  const body: EditorDraftCompleteRequest = { expected_version: version }
  return apiFetch<{ draft_id: string }>(
    `/library/presets/${presetId}/editor-drafts/${draftId}/complete`,
    { ...opts, method: 'POST', body }
  )
}

export function publishEditorDraft(
  presetId: string,
  draftId: string,
  version: number,
  presetVersion: number,
  opts: CallOptions = {}
): Promise<PresetPublishView> {
  const body: EditorDraftPublishRequest = {
    expected_version: version,
    preset_expected_version: presetVersion
  }
  return apiFetch<PresetPublishView>(
    `/library/presets/${presetId}/editor-drafts/${draftId}/publish`,
    {
      ...opts,
      method: 'POST',
      body
    }
  )
}

/* Story drafts ----------------------------------------------------------- */

export function createDraft(
  payload: StoryDraftCreateRequest['payload'],
  step: string,
  opts: CallOptions = {}
): Promise<StoryDraftView> {
  // payload is optional-but-not-nullable server-side: omit, never null.
  const body: StoryDraftCreateRequest = { payload, current_step: step }
  return apiFetch<StoryDraftView>('/story-drafts', { ...opts, method: 'POST', body })
}

export function getDraft(id: string, opts: CallOptions = {}): Promise<StoryDraftView> {
  return apiFetch<StoryDraftView>(`/story-drafts/${id}`, { ...opts, method: 'GET' })
}

export function patchDraft(
  id: string,
  payload: StoryDraftPatchRequest['payload'],
  step: string,
  version: number,
  opts: CallOptions = {}
): Promise<StoryDraftView> {
  const body: StoryDraftPatchRequest = {
    payload,
    current_step: step,
    expected_version: version
  }
  return apiFetch<StoryDraftView>(`/story-drafts/${id}`, { ...opts, method: 'PATCH', body })
}

export function validateDraft(id: string, opts: CallOptions = {}): Promise<DraftValidationView> {
  return apiFetch(`/story-drafts/${id}/validate`, { ...opts, method: 'POST' })
}

/** The authoritative persisted grant (role + controlled runtime id), if any. */
export function getRole(worldId: string, opts: CallOptions = {}): Promise<RoleGrantView | null> {
  return apiFetch<RoleGrantView | null>(`/stage2/roles?world_id=${worldId}`, {
    ...opts,
    method: 'GET'
  })
}

/* Stories ----------------------------------------------------------------- */

export function listStories(
  status: 'in_progress' | 'archived' | 'all' = 'in_progress',
  opts: CallOptions = {}
): Promise<StoryListResponse> {
  return apiFetch<StoryListResponse>(`/stories?status=${status}`, { ...opts, method: 'GET' })
}

export function getStory(id: string, opts: CallOptions = {}): Promise<StoryDetail> {
  return apiFetch<StoryDetail>(`/stories/${id}`, { ...opts, method: 'GET' })
}

export function getSetup(id: string, opts: CallOptions = {}): Promise<StorySetupView> {
  return apiFetch<StorySetupView>(`/stories/${id}/setup`, { ...opts, method: 'GET' })
}

export function openStory(id: string, opts: CallOptions = {}): Promise<StoryDetail> {
  return apiFetch<StoryDetail>(`/stories/${id}/open`, { ...opts, method: 'POST' })
}

export function archiveStory(
  id: string,
  version: number,
  opts: CallOptions = {}
): Promise<StoryDetail> {
  return apiFetch<StoryDetail>(`/stories/${id}/archive`, {
    ...opts,
    method: 'POST',
    body: { expected_version: version }
  })
}

export function unarchiveStory(
  id: string,
  version: number,
  opts: CallOptions = {}
): Promise<StoryDetail> {
  return apiFetch<StoryDetail>(`/stories/${id}/unarchive`, {
    ...opts,
    method: 'POST',
    body: { expected_version: version }
  })
}

export function createStory(
  draftId: string,
  version: number,
  idempotencyKey: string,
  opts: CallOptions = {}
): Promise<StoryCreateResponse> {
  return apiFetch<StoryCreateResponse>('/stories', {
    ...opts,
    method: 'POST',
    body: { draft_id: draftId, expected_draft_version: version },
    idempotencyKey
  })
}

/* Gameplay ------------------------------------------------------------------ */

export function startTravel(
  worldId: string,
  characterId: string,
  toLocationId: string,
  opts: CallOptions = {}
): Promise<ActivityView> {
  // No server idempotency key on this route: a repeated start while the
  // first is active returns 409 PRECONDITION (no duplicate). Callers must
  // reconcile by listing activities instead of treating 409 as failure.
  return apiFetch<ActivityView>('/stage2/activities', {
    ...opts,
    method: 'POST',
    body: {
      world_id: worldId,
      character_id: characterId,
      kind: 'travel',
      to_location_id: toLocationId
    }
  })
}

export function listActivities(
  worldId: string,
  opts: CallOptions = {}
): Promise<ActivityListResponse> {
  return apiFetch<ActivityListResponse>(`/stage2/activities?world_id=${worldId}`, {
    ...opts,
    method: 'GET'
  })
}

export function advanceStory(
  worldId: string,
  absoluteIndex: number,
  intents?: Stage1AdvanceRequest['player_intents'],
  opts: CallOptions = {}
): Promise<Stage1AdvanceResponse> {
  // One atomic beat per absolute_index; the server replays repeats
  // (`duplicate: true`). Never issue an extra Stage 0 tick alongside this:
  // the Stage 1 orchestrator advances its own clock.
  // player_intents is optional-but-not-nullable: omit when there are none.
  const body: Stage1AdvanceRequest =
    intents === undefined
      ? { world_id: worldId, absolute_index: absoluteIndex }
      : { world_id: worldId, absolute_index: absoluteIndex, player_intents: intents }
  return apiFetch<Stage1AdvanceResponse>('/stage1/advance', { ...opts, method: 'POST', body })
}

export function getTimeline(
  worldId: string,
  after: number,
  opts: CallOptions = {},
  limit = 50
): Promise<TimelineResponse> {
  return apiFetch<TimelineResponse>(
    `/stage2/timeline?world_id=${worldId}&after=${after}&limit=${limit}`,
    { ...opts, method: 'GET' }
  )
}

export function getMap(worldId: string, opts: CallOptions = {}): Promise<MapResponse> {
  return apiFetch<MapResponse>(`/stage2/map?world_id=${worldId}`, { ...opts, method: 'GET' })
}

/* Operating seats -------------------------------------------------------- */

export function selectSeat(
  worldId: string,
  role: 'watcher' | 'director' | 'deity',
  opts: CallOptions = {}
): Promise<RoleGrantView> {
  // Taking a seat replaces the world's grant at a safe boundary; the
  // server rejects mid-run switches with PRECONDITION_FAILED.
  const body: RoleSelectRequest = { world_id: worldId, role }
  return apiFetch<RoleGrantView>('/stage2/roles/select', { ...opts, method: 'POST', body })
}

/* Director/God interventions ---------------------------------------------- */

export function submitIntervention(
  worldId: string,
  mode: 'influence' | 'force' | 'attempt',
  text: string,
  clientRequestId: string,
  opts: CallOptions = {}
): Promise<InterventionView> {
  // The client request id makes submission idempotent: resubmitting the
  // same key replays the same queue item instead of duplicating it.
  const body: InterventionRequest = {
    world_id: worldId,
    client_request_id: clientRequestId,
    mode,
    text
  }
  return apiFetch<InterventionView>('/interventions', { ...opts, method: 'POST', body })
}

export function listInterventions(
  worldId: string,
  opts: CallOptions = {}
): Promise<InterventionView[]> {
  // The queue is an operator surface: watcher, director and deity only.
  return apiFetch<InterventionView[]>(`/interventions?world_id=${worldId}`, {
    ...opts,
    method: 'GET'
  })
}

export function readIntervention(id: string, opts: CallOptions = {}): Promise<InterventionView> {
  return apiFetch<InterventionView>(`/interventions/${id}`, { ...opts, method: 'GET' })
}

export function editIntervention(
  id: string,
  expectedVersion: number,
  text: string,
  opts: CallOptions = {}
): Promise<InterventionView> {
  // Reinterprets before claim with restarted history; a stale version
  // conflicts instead of overwriting a newer interpretation.
  const body: InterventionEditRequest = { text, expected_version: expectedVersion }
  return apiFetch<InterventionView>(`/interventions/${id}`, { ...opts, method: 'PATCH', body })
}

export function cancelIntervention(
  id: string,
  expectedVersion: number,
  opts: CallOptions = {}
): Promise<InterventionView> {
  // Cancels before application; executing work cannot stop. Completed
  // history is preserved, not rewritten.
  const body: InterventionCancelRequest = { expected_version: expectedVersion }
  return apiFetch<InterventionView>(`/interventions/${id}/cancel`, {
    ...opts,
    method: 'POST',
    body
  })
}
