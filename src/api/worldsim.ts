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
  AutoplayPlayRequest,
  AutoplayView,
  BeatView,
  CharacterDetail,
  ChronicleResponse,
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
  ItemListResponse,
  MapResponse,
  PresentationResponse,
  PresetDetail,
  PresetPublishView,
  PresetSummary,
  ProviderConnectionCreate,
  ProviderConnectionPatch,
  ProviderConnectionView,
  ProviderProfileCreate,
  ProviderProfileView,
  ProviderTestRequest,
  ProviderTestView,
  PreferencesPatchRequest,
  PaintSceneRequest,
  PictureSuggestion,
  SceneArtView,
  StoryPromptsUpdate,
  StoryPromptsView,
  PreferencesView,
  RoleGrantView,
  RoleSelectRequest,
  SceneDetail,
  SimulationStatus,
  Stage1AdvanceRequest,
  Stage1AdvanceResponse,
  StoryBranchPoints,
  StoryBranchResponse,
  StoryRewindResponse,
  StoryCreateResponse,
  StoryDetail,
  StoryDraftCreateRequest,
  StoryDraftPatchRequest,
  StoryDraftView,
  StoryListResponse,
  StoryProviderView,
  StorySetupView,
  SuggestionView,
  TimelineResponse,
  MapImageView,
  MapPlacesView,
  MapRoadsView,
  WorldMapRequest,
  PlaceMapRequest,
  FaceView,
  WritingEnhanceView,
  WritingFillRequest,
  WritingFillView,
  WritingSampleRequest,
  PortraitPromptView,
  PicturePromptView,
  JobView,
  WritingSampleView,
  TerrainView,
  PartyRosterResponse,
  PartyMemberView,
  LevelChoiceRequest,
  PartyCallingRequest
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
  // of minting a second preset. First creation is wired through this
  // wrapper: the frozen request creates revision 1 and the studios hand
  // off to the real preset on the receipt.
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

export function getStoryProvider(id: string, opts: CallOptions = {}): Promise<StoryProviderView> {
  return apiFetch<StoryProviderView>(`/stories/${id}/provider`, { ...opts, method: 'GET' })
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

/** Turns this story can branch from (their end state was kept). */
export function branchPoints(storyId: string, opts: CallOptions = {}): Promise<StoryBranchPoints> {
  return apiFetch<StoryBranchPoints>(`/stories/${storyId}/branch-points`, opts)
}

/** A new story continuing from the end of one turn; the original is untouched. */
export function branchStory(
  storyId: string,
  absoluteIndex: number,
  idempotencyKey: string,
  opts: CallOptions = {}
): Promise<StoryBranchResponse> {
  return apiFetch<StoryBranchResponse>(`/stories/${storyId}/branch`, {
    ...opts,
    method: 'POST',
    body: { absolute_index: absoluteIndex },
    idempotencyKey
  })
}

/**
 * Go back to a kept turn of this story. The later turns are removed from it
 * and kept as a story of their own ("the path not taken").
 */
export function rewindStory(
  storyId: string,
  absoluteIndex: number,
  idempotencyKey: string,
  opts: CallOptions = {}
): Promise<StoryRewindResponse> {
  return apiFetch<StoryRewindResponse>(`/stories/${storyId}/rewind`, {
    ...opts,
    method: 'POST',
    body: { absolute_index: absoluteIndex },
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

export function getSimulationStatus(
  worldId: string,
  opts: CallOptions = {}
): Promise<SimulationStatus> {
  return apiFetch<SimulationStatus>(`/simulation/status?world_id=${worldId}`, {
    ...opts,
    method: 'GET'
  })
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

/* Observatory -------------------------------------------------------------- */

export function getPresentation(
  worldId: string,
  opts: CallOptions = {}
): Promise<PresentationResponse> {
  // Map manifest (art + place anchors), cast positions, clock and run state
  // in one perspective-filtered read.
  return apiFetch<PresentationResponse>(`/world/presentation?world_id=${worldId}`, {
    ...opts,
    method: 'GET'
  })
}

export function getChronicle(
  worldId: string,
  after: number,
  opts: CallOptions = {},
  limit = 50
): Promise<ChronicleResponse> {
  // Visible events after a source cursor, with title/text, participants and
  // place; `next_after` advances even when a page is empty.
  return apiFetch<ChronicleResponse>(
    `/world/chronicle?world_id=${worldId}&after=${after}&limit=${limit}`,
    { ...opts, method: 'GET' }
  )
}

/**
 * Same-origin URL for stored art (map, portraits); the dev proxy adds auth.
 * `width`: the widest it is drawn, in device pixels (about 2x its CSS size);
 * the server sends a WebP that wide (snapped to a few sizes) instead of the
 * whole painting. Leave it out where the full picture is needed.
 */
export function assetUrl(worldId: string, assetId: string, width?: number): string {
  const w = width ? `&w=${width}` : ''
  return `/api/v1/assets/${assetId}?world_id=${worldId}${w}`
}

export function getAutoplay(worldId: string, opts: CallOptions = {}): Promise<AutoplayView> {
  return apiFetch<AutoplayView>(`/stories/${worldId}/autoplay`, { ...opts, method: 'GET' })
}

export function playAutoplay(
  worldId: string,
  body: AutoplayPlayRequest,
  opts: CallOptions = {}
): Promise<AutoplayView> {
  // Server-side: beats keep running while an observer reports presence,
  // up to the beat limit, one at a time through the same gate as Step.
  return apiFetch<AutoplayView>(`/stories/${worldId}/autoplay/play`, {
    ...opts,
    method: 'POST',
    body
  })
}

export function pauseAutoplay(worldId: string, opts: CallOptions = {}): Promise<AutoplayView> {
  // Stops admitting beats; one already running finishes and commits.
  return apiFetch<AutoplayView>(`/stories/${worldId}/autoplay/pause`, {
    ...opts,
    method: 'POST'
  })
}

export function reportPresence(worldId: string, opts: CallOptions = {}): Promise<AutoplayView> {
  // Without a fresh presence report autoplay pauses itself after its grace
  // period, so a closed tab never keeps spending.
  return apiFetch<AutoplayView>(`/stories/${worldId}/autoplay/presence`, {
    ...opts,
    method: 'POST'
  })
}

/* Beat reading ------------------------------------------------------------ */

export function getSceneDetail(sceneId: string, opts: CallOptions = {}): Promise<SceneDetail> {
  // Structured beat content (intents, attempts, reactions, resolution) for
  // the room's reading view. Perspective-scoped like every other read: pass
  // the caller's role headers.
  return apiFetch<SceneDetail>(`/stage1/scenes/${sceneId}`, { ...opts, method: 'GET' })
}

export function getSceneNarration(sceneId: string, opts: CallOptions = {}): Promise<BeatView[]> {
  // Narration beats with speaker and kind (dialogue vs narration), backing
  // the same reading view.
  return apiFetch<BeatView[]>(`/stage1/scenes/${sceneId}/narration`, { ...opts, method: 'GET' })
}

/* Adventure (player seat) ---------------------------------------------- */

export function getCharacter(
  characterId: string,
  opts: CallOptions = {}
): Promise<CharacterDetail> {
  // Card and state are filled for the caller's own character (or a watcher).
  return apiFetch<CharacterDetail>(`/stage1/characters/${characterId}`, { ...opts, method: 'GET' })
}

export function getSuggestions(
  characterId: string,
  opts: CallOptions = {}
): Promise<SuggestionView[]> {
  // Actions the rules allow right now: places to go, people here, things to pick up.
  return apiFetch<SuggestionView[]>(`/stage1/suggestions?character_id=${characterId}`, {
    ...opts,
    method: 'GET'
  })
}

export function listItems(
  worldId: string,
  ownerId: string | null,
  opts: CallOptions = {}
): Promise<ItemListResponse> {
  const owner = ownerId ? `&owner_id=${ownerId}` : ''
  return apiFetch<ItemListResponse>(`/stage2/items?world_id=${worldId}${owner}`, {
    ...opts,
    method: 'GET'
  })
}

/** A combat story's party (hero and companions, 5e sheets) and the foes of
 *  its latest fight while it is on; a story without fights has no members. */
export function getParty(worldId: string, opts: CallOptions = {}): Promise<PartyRosterResponse> {
  return apiFetch<PartyRosterResponse>(`/stage1/party?world_id=${worldId}`, {
    ...opts,
    method: 'GET'
  })
}

/** Make a level-up choice for a hero: +2 to one ability or +1 to two
 *  (`abilities`), or the spells to learn (`spells`). */
export function chooseLevelOption(
  memberId: string,
  body: LevelChoiceRequest,
  opts: CallOptions = {}
): Promise<PartyMemberView> {
  return apiFetch<PartyMemberView>(`/stage1/party/${memberId}/choices`, {
    ...opts,
    method: 'POST',
    body
  })
}

/** Another people and calling for a companion who has not fought yet. */
export function changeCalling(
  memberId: string,
  body: PartyCallingRequest,
  opts: CallOptions = {}
): Promise<PartyMemberView> {
  return apiFetch<PartyMemberView>(`/stage1/party/${memberId}/calling`, {
    ...opts,
    method: 'POST',
    body
  })
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

/* Provider profiles (storyteller pins) -------------------------------------- */

export function listProviders(opts: CallOptions = {}): Promise<ProviderConnectionView[]> {
  // Reads never return secrets: connections expose a write-only
  // credential reference plus a boolean.
  return apiFetch<ProviderConnectionView[]>('/settings/providers', { ...opts, method: 'GET' })
}

export function listProfiles(
  connectionId: string,
  opts: CallOptions = {}
): Promise<ProviderProfileView[]> {
  return apiFetch<ProviderProfileView[]>(`/settings/providers/${connectionId}/profiles`, {
    ...opts,
    method: 'GET'
  })
}

export function createProvider(
  body: ProviderConnectionCreate,
  opts: CallOptions = {}
): Promise<ProviderConnectionView> {
  // The server also adds profile revision 1 with the adapter's default model.
  return apiFetch<ProviderConnectionView>('/settings/providers', { ...opts, method: 'POST', body })
}

export function updateProvider(
  connectionId: string,
  body: ProviderConnectionPatch,
  opts: CallOptions = {}
): Promise<ProviderConnectionView> {
  // expected_version guards concurrent edits (VERSION_CONFLICT on mismatch).
  return apiFetch<ProviderConnectionView>(`/settings/providers/${connectionId}`, {
    ...opts,
    method: 'PATCH',
    body
  })
}

export function addProfile(
  connectionId: string,
  body: ProviderProfileCreate,
  opts: CallOptions = {}
): Promise<ProviderProfileView> {
  // Append-only: stories keep the revision they pinned.
  return apiFetch<ProviderProfileView>(`/settings/providers/${connectionId}/profiles`, {
    ...opts,
    method: 'POST',
    body
  })
}

export function testProvider(
  connectionId: string,
  opts: CallOptions = {}
): Promise<ProviderTestView> {
  // Reachability of the SAVED connection only; never sends the credential.
  const body: ProviderTestRequest = { live: false }
  return apiFetch<ProviderTestView>(`/settings/providers/${connectionId}/test`, {
    ...opts,
    method: 'POST',
    body
  })
}

/* Operator preferences and image generation ------------------------------ */

export function getPreferences(opts: CallOptions = {}): Promise<PreferencesView> {
  return apiFetch<PreferencesView>('/settings/preferences', { ...opts, method: 'GET' })
}

export function savePreferences(
  body: PreferencesPatchRequest,
  opts: CallOptions = {}
): Promise<PreferencesView> {
  // expected_version guards concurrent edits (VERSION_CONFLICT on mismatch).
  return apiFetch<PreferencesView>('/settings/preferences', { ...opts, method: 'PATCH', body })
}

export interface ImageServiceView {
  provider: string
  configured: boolean
  reachable: boolean
  loaded: boolean
  checkpoint: string | null
  queued: number
  checkpoints: string[]
  styles: Array<{ id: string; label: string }>
  ratios: string[]
  steps: number[]
  error: string | null
}

export interface ImagePreviewItem {
  data_url: string
  seed: number | null
  width: number
  height: number
  seconds: number | null
}

export function getImageService(opts: CallOptions = {}): Promise<ImageServiceView> {
  // Reads the image service's health and catalog; never draws anything.
  return apiFetch<ImageServiceView>('/settings/images/service', { ...opts, method: 'GET' })
}

export function previewImages(
  body: { prompt: string; ratio: string; count: number; images?: Record<string, unknown> },
  opts: CallOptions = {}
): Promise<{ images: ImagePreviewItem[] }> {
  // Draws with unsaved choices; nothing is stored. ~12 s per image, more with a
  // busy queue, Turbo off or a checkpoint switch (~35 s once), so wait long.
  return apiFetch<{ images: ImagePreviewItem[] }>('/settings/images/preview', {
    ...opts,
    timeoutMs: opts.timeoutMs ?? 40_000 + body.count * 60_000,
    method: 'POST',
    body
  })
}

/* Scene pictures ------------------------------------------------------------ */

export function getPictureSuggestion(
  worldId: string,
  sceneId: string,
  opts: CallOptions = {}
): Promise<PictureSuggestion> {
  // Plain words for the scene (who, what happens, where) for the player to edit.
  const query = `?world_id=${encodeURIComponent(worldId)}`
  return apiFetch<PictureSuggestion>(`/world/scenes/${sceneId}/picture-suggestion${query}`, {
    ...opts,
    method: 'GET'
  })
}

/** The whole prompt a scene picture is painted from, as the image service gets it. */
export function getPicturePrompt(
  worldId: string,
  pictureId: string,
  opts: CallOptions = {}
): Promise<PicturePromptView> {
  const query = `?world_id=${encodeURIComponent(worldId)}`
  return apiFetch<PicturePromptView>(`/world/pictures/${pictureId}/prompt${query}`, {
    ...opts,
    method: 'GET'
  })
}

/** Paint a picture again from the player's whole prompt, sent as written. */
export function repaintPicture(
  worldId: string,
  pictureId: string,
  prompt: string,
  opts: CallOptions = {}
): Promise<PicturePromptView> {
  return apiFetch<PicturePromptView>(`/world/pictures/${pictureId}/repaint`, {
    ...opts,
    method: 'POST',
    body: { world_id: worldId, prompt }
  })
}

/** One image job, to follow a painting until it is done. */
export function getImageJob(jobId: string, opts: CallOptions = {}): Promise<JobView> {
  return apiFetch<JobView>(`/assets/jobs/${jobId}`, { ...opts, method: 'GET' })
}

export function paintScene(
  sceneId: string,
  body: PaintSceneRequest,
  opts: CallOptions = {}
): Promise<SceneArtView> {
  // Queued; the picture shows in the story once painted (~16 s on an idle machine).
  return apiFetch<SceneArtView>(`/world/scenes/${sceneId}/pictures`, {
    ...opts,
    method: 'POST',
    body
  })
}

/* Story settings: the player's words around this story's prompts --------- */

export function getStoryPrompts(
  worldId: string,
  opts: CallOptions = {}
): Promise<StoryPromptsView> {
  return apiFetch<StoryPromptsView>(`/stories/${worldId}/prompts`, { ...opts, method: 'GET' })
}

export function saveStoryPrompts(
  worldId: string,
  body: StoryPromptsUpdate,
  opts: CallOptions = {}
): Promise<StoryPromptsView> {
  // expected_version guards concurrent edits (VERSION_CONFLICT on mismatch).
  return apiFetch<StoryPromptsView>(`/stories/${worldId}/prompts`, {
    ...opts,
    method: 'PUT',
    body
  })
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

/* World maps -------------------------------------------------------------- */

/** Same-origin URL for an unscoped library picture (a world's map). */
export function libraryAssetUrl(assetId: string, width?: number): string {
  return `/api/v1/library/assets/${assetId}/bytes${width ? `?w=${width}` : ''}`
}

export function uploadMap(dataUrl: string, opts: CallOptions = {}): Promise<MapImageView> {
  return apiFetch<MapImageView>('/library/maps', {
    timeoutMs: 120000,
    ...opts,
    method: 'POST',
    body: { data_url: dataUrl }
  })
}

/** Keep a world's own picture (unscoped; the preset keeps its banner frame). */
export function uploadCover(dataUrl: string, opts: CallOptions = {}): Promise<MapImageView> {
  return apiFetch<MapImageView>('/library/covers', {
    timeoutMs: 120000,
    ...opts,
    method: 'POST',
    body: { data_url: dataUrl }
  })
}

export function uploadPortrait(dataUrl: string, opts: CallOptions = {}): Promise<MapImageView> {
  return apiFetch<MapImageView>('/library/portraits', {
    timeoutMs: 120000,
    ...opts,
    method: 'POST',
    body: { data_url: dataUrl }
  })
}

/**
 * Paint a character from how they look, in the house style (the image
 * service; free, ~15 s, longer when it first switches its model).
 */
/** Paint a character; `raw` sends the prompt exactly as written (no house style added). */
export function paintPortrait(
  prompt: string,
  raw = false,
  opts: CallOptions = {}
): Promise<MapImageView> {
  return apiFetch<MapImageView>('/library/portraits/paint', {
    timeoutMs: 240000,
    ...opts,
    method: 'POST',
    body: { prompt, raw }
  })
}

/** The whole prompt and the settings painting would send the image service. */
export function previewPortraitPrompt(
  prompt: string,
  raw = false,
  opts: CallOptions = {}
): Promise<PortraitPromptView> {
  return apiFetch<PortraitPromptView>('/library/portraits/prompt', {
    ...opts,
    method: 'POST',
    body: { prompt, raw }
  })
}

/** A fuller overview from the player's rough one (a small text model; a fraction of a cent). */
export function enhanceOverview(
  kind: 'character' | 'world',
  overview: string,
  name: string,
  opts: CallOptions = {}
): Promise<WritingEnhanceView> {
  return apiFetch<WritingEnhanceView>('/library/writing/enhance', {
    timeoutMs: 120000,
    ...opts,
    method: 'POST',
    body: { kind, overview, name }
  })
}

/** A few lines in a character's voice, in a situation the player picked. */
export function sampleVoice(
  body: WritingSampleRequest,
  opts: CallOptions = {}
): Promise<WritingSampleView> {
  return apiFetch<WritingSampleView>('/library/writing/sample', {
    timeoutMs: 120000,
    ...opts,
    method: 'POST',
    body
  })
}

/** Text for the fields the player left empty, from their overview; filled ones stay theirs. */
export function fillFields(
  body: WritingFillRequest,
  opts: CallOptions = {}
): Promise<WritingFillView> {
  return apiFetch<WritingFillView>('/library/writing/fill', {
    timeoutMs: 150000,
    ...opts,
    method: 'POST',
    body
  })
}

/** Where the map reader sees the face on an imported portrait (costs a fraction of a cent). */
export function findFace(assetId: string, opts: CallOptions = {}): Promise<FaceView> {
  return apiFetch<FaceView>(`/library/portraits/${assetId}/face`, {
    timeoutMs: 120000,
    ...opts,
    method: 'POST'
  })
}

export function paintMap(
  prompt: string,
  ratio: string,
  opts: CallOptions = {}
): Promise<MapImageView> {
  // The image service may first switch its model (~35 s), then paint.
  return apiFetch<MapImageView>('/library/maps/paint', {
    timeoutMs: 300000,
    ...opts,
    method: 'POST',
    body: { prompt, ratio }
  })
}

/** The places on a map; `known` are the world's own place names, to match unlabelled drawings. */
export function readMapPlaces(
  assetId: string,
  known: string[] = [],
  opts: CallOptions = {}
): Promise<MapPlacesView> {
  return apiFetch<MapPlacesView>(`/library/maps/${assetId}/places`, {
    timeoutMs: 420000,
    ...opts,
    method: 'POST',
    body: { known }
  })
}

/** What covers a map, as a grid of terrain letters (a draft; a cent or so). */
export function readTerrain(
  assetId: string,
  cols: number,
  rows: number,
  opts: CallOptions = {}
): Promise<TerrainView> {
  return apiFetch<TerrainView>(`/library/maps/${assetId}/terrain`, {
    timeoutMs: 420000,
    ...opts,
    method: 'POST',
    body: { cols, rows }
  })
}

export function readMapSpots(assetId: string, opts: CallOptions = {}): Promise<MapPlacesView> {
  return apiFetch<MapPlacesView>(`/library/maps/${assetId}/spots`, {
    timeoutMs: 420000,
    ...opts,
    method: 'POST'
  })
}

export function readMapRoads(
  assetId: string,
  places: Array<{ name: string; kind: string; point: [number, number] }>,
  opts: CallOptions = {}
): Promise<MapRoadsView> {
  return apiFetch<MapRoadsView>(`/library/maps/${assetId}/roads`, {
    timeoutMs: 420000,
    ...opts,
    method: 'POST',
    body: { places }
  })
}

export function saveWorldMap(
  presetId: string,
  body: WorldMapRequest,
  opts: CallOptions = {}
): Promise<PresetDetail> {
  // expected_version guards concurrent edits (VERSION_CONFLICT on mismatch).
  return apiFetch<PresetDetail>(`/library/presets/${presetId}/map`, {
    ...opts,
    method: 'PUT',
    body
  })
}

export function savePlaceMap(
  presetId: string,
  placeKey: string,
  body: PlaceMapRequest,
  opts: CallOptions = {}
): Promise<PresetDetail> {
  // A null asset_id takes the place's map away; expected_version as above.
  return apiFetch<PresetDetail>(
    `/library/presets/${presetId}/places/${encodeURIComponent(placeKey)}/map`,
    { ...opts, method: 'PUT', body }
  )
}

/** Put a preset away (or bring it back); `version` is its metadata version. */
export function setPresetArchived(
  presetId: string,
  archived: boolean,
  version: number,
  opts: CallOptions = {}
): Promise<PresetDetail> {
  return apiFetch<PresetDetail>(
    `/library/presets/${presetId}/${archived ? 'archive' : 'unarchive'}`,
    { ...opts, method: 'POST', body: { expected_version: version } }
  )
}

export function duplicatePreset(presetId: string, opts: CallOptions = {}): Promise<PresetDetail> {
  return apiFetch<PresetDetail>(`/library/presets/${presetId}/duplicate`, {
    ...opts,
    method: 'POST'
  })
}
