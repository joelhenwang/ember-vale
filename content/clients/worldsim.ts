// Generated TypeScript client for the worldsim HTTP boundary.
//
// Regenerate with `make contracts` (runs scripts/gen_ts_client.py).
// Checked in so the Vue surface shares one typed contract.

export interface CharacterSummary {
  id: string;
  life_status: string;
  location_id: string;
  name: string;
}

export interface CharacterDetail {
  card?: Record<string, unknown> | null;
  id: string;
  life_status: string;
  location_id: string;
  name: string;
  state?: Record<string, unknown> | null;
}

export interface ParticipantView {
  character_id: string;
  role: string;
}

export interface IntentView {
  author_character_id: string;
  detail?: Record<string, unknown> | null;
  family: string;
  id: string;
}

export interface AttemptView {
  actor_character_id: string;
  id: string;
  observable_summary: string;
  status: string;
}

export interface ReactionView {
  detail?: Record<string, unknown> | null;
  family: string;
  id: string;
  reactor_character_id: string;
}

export interface ResolutionView {
  outcome: string;
  rationale: string;
  resolver: string;
}

export interface SceneDetail {
  attempts?: AttemptView[];
  beat_budget: number;
  event_id?: string | null;
  id: string;
  intents?: IntentView[];
  participants?: ParticipantView[];
  phase_run_id: string;
  reactions?: ReactionView[];
  resolution?: ResolutionView | null;
  status: string;
  world_id: string;
}

export interface SceneSummary {
  event_id?: string | null;
  id: string;
  participant_ids?: string[];
  status: string;
}

export interface BeatView {
  id: string;
  kind: string;
  source_event_id: string;
  speaker_id?: string | null;
  text: string;
}

export interface ModelRunView {
  actor_id?: string | null;
  attempts?: Record<string, unknown>[];
  budgets?: Record<string, number>;
  call_id: string;
  completion_tokens?: number;
  error_code?: string | null;
  latency_ms?: number;
  manifest_id?: string | null;
  max_tokens?: number | null;
  pin_profile_id?: string | null;
  pin_profile_revision?: number | null;
  profile: string;
  prompt_tokens?: number;
  rendered_hash?: string | null;
  role: string;
  status: string;
  task_run_id?: string | null;
}

export interface Stage1AdvanceRequest {
  absolute_index: number;
  player_intents?: Record<string, Record<string, unknown>>;
  world_id: string;
}

export interface Stage1SceneOutcome {
  event_id: string;
  narration: string;
  resolution_outcome: string;
  scene_id: string;
}

export interface Stage1AdvanceResponse {
  absolute_index: number;
  duplicate?: boolean;
  quiet?: boolean;
  run_id: string;
  scenes?: Stage1SceneOutcome[];
  snapshot_id: string;
  world_id: string;
}

export interface PartyBeginRequest {
  character_class?: string;
  character_id?: string | null;
  level?: number;
  name: string;
  race?: string;
  stats?: Record<string, number> | null;
  world_id: string;
}

export interface PartyMemberView {
  character_class: string;
  character_id?: string | null;
  conditions?: string[];
  hp_current?: number | null;
  hp_max?: number | null;
  id: string;
  level: number;
  name: string;
  version: number;
  world_id: string;
}

export interface PartyRosterResponse {
  members?: PartyMemberView[];
  world_id: string;
}

export interface ActivityStartRequest {
  character_id: string;
  duration_phases?: number | null;
  kind: string;
  skill?: string | null;
  to_location_id?: string | null;
  world_id: string;
}

export interface ActivityView {
  character_id: string;
  duration_phases: number;
  effective_progress_phases?: number | null;
  from_location_id?: string | null;
  id: string;
  kind: string;
  progress_phases: number;
  route_id?: string | null;
  start_absolute: number;
  status: string;
  to_location_id?: string | null;
  version: number;
  world_id: string;
}

export interface ActivityListResponse {
  members?: ActivityView[];
  world_id: string;
}

export interface RelationshipEvidenceRequest {
  delta: number;
  dimension: string;
  note?: string;
  source_id: string;
  target_id: string;
  world_id: string;
}

export interface RelationshipView {
  affection: number;
  direction: string;
  id: string;
  respect: number;
  source_id: string;
  summary: string;
  target_id: string;
  trust: number;
  version: number;
  world_id: string;
}

export interface RelationshipListResponse {
  character_id: string;
  members?: RelationshipView[];
  world_id: string;
}

export interface ClaimRequest {
  audience_location_id?: string | null;
  proposition: string;
  refutes_claim_id?: string | null;
  speaker_id: string;
  world_id: string;
}

export interface ClaimView {
  audience_location_id: string | null;
  id: string;
  proposition: string;
  refutes_claim_id: string | null;
  speaker_id: string;
  version: number;
  world_id: string;
}

export interface ClaimListResponse {
  members?: ClaimView[];
  viewer_id: string;
  world_id: string;
}

export interface BeliefView {
  confidence: unknown;
  holder_id: string;
  id: string;
  last_touched_absolute: number;
  proposition: string;
  version: number;
  world_id: string;
}

export interface BeliefListResponse {
  holder_id: string;
  members?: BeliefView[];
  world_id: string;
}

export interface ItemGiveRequest {
  item_key: string;
  owner_id?: string | null;
  quantity?: number;
  world_id: string;
}

export interface ItemTransferRequest {
  to_owner_id?: string | null;
}

export interface ItemView {
  id: string;
  item_key: string;
  owner_id: string | null;
  quantity: number;
  version: number;
  world_id: string;
}

export interface ItemListResponse {
  members?: ItemView[];
  owner_id: string | null;
  world_id: string;
}

export interface SkillView {
  progress: number;
  sessions: number;
  skill_key: string;
  version: number;
}

export interface SkillListResponse {
  character_id: string;
  members?: SkillView[];
  world_id: string;
}

export interface RoleSelectRequest {
  character_id?: string | null;
  role: string;
  world_id: string;
}

export interface RoleGrantView {
  character_id: string | null;
  granted_absolute: number;
  id: string;
  role: string;
  version: number;
  world_id: string;
}

export interface DirectorProposalRequest {
  kind: string;
  participant_ids?: string[];
  purpose?: string;
  requested_powers?: string[];
  title: string;
  world_id: string;
}

export interface DirectorProposalView {
  id: string;
  kind: string;
  reason: string;
  title: string;
  world_id: string;
}

export interface DeityOverrideRequest {
  character_id: string;
  conditions?: string[] | null;
  life_status?: string | null;
  mana?: number | null;
  retcon?: boolean;
  stamina?: number | null;
  world_id: string;
}

export interface DeityOverrideView {
  character_id: string;
  event_id: string;
  retcon: boolean;
  world_id: string;
}

export interface TimelineEntry {
  absolute_index: number;
  event_id: string;
  event_type: string;
  sequence: number;
  snippet?: string | null;
}

export interface TimelineResponse {
  entries?: TimelineEntry[];
  has_more: boolean;
  next_after: number;
  total: number;
  world_id: string;
}

export interface MapRoute {
  duration_phases: number;
  to_location_id: string;
}

export interface MapPlace {
  discovered: boolean;
  id: string;
  name: string;
  occupant_ids?: string[];
  occupants?: string[];
  region: string;
  routes?: MapRoute[];
}

export interface MapResponse {
  places?: MapPlace[];
  world_id: string;
}

export interface DiaryEntry {
  kind: string;
  phase: number;
  text: string;
}

export interface DiaryResponse {
  character_id: string;
  digests?: DiaryEntry[];
  memories?: DiaryEntry[];
  observations?: DiaryEntry[];
  summaries?: DiaryEntry[];
}

export interface HookView {
  id: string;
  status: string;
  title: string;
}

export interface ArcView {
  id: string;
  status: string;
  title: string;
}

export interface HookListResponse {
  arcs?: ArcView[];
  hooks?: HookView[];
  world_id: string;
}

export interface OperationsStatus {
  open_run_id: string | null;
  open_run_state: string | null;
  pending_outbox: number;
  total_events: number;
  world_id: string;
}

export interface MacroEffectView {
  detail: string;
  event_id?: string | null;
  kind: string;
  target_ids?: string[];
}

export interface MacroInterruptionView {
  at_absolute: number;
  detail: string;
  reason: string;
}

export interface MacroRunView {
  effects?: MacroEffectView[];
  end_absolute: number;
  interruptions?: MacroInterruptionView[];
  resolution: string;
  run_id: string;
  start_absolute: number;
  state: string;
}

export interface MacroRunsResponse {
  runs?: MacroRunView[];
  world_id: string;
}

export interface LineageLinkView {
  birth_absolute: number;
  child_id: string;
  child_name: string;
  parent_id: string;
  parent_name: string;
}

export interface LineageRecordView {
  birth_absolute: number;
  character_id: string;
  death_absolute?: number | null;
  life_status: string;
  name: string;
  succession_eligible: boolean;
}

export interface LineageResponse {
  links?: LineageLinkView[];
  records?: LineageRecordView[];
  world_id: string;
}

export interface FocusAssignmentView {
  effective_absolute: number;
  from_character_id?: string | null;
  from_name?: string | null;
  reason: string;
  slot: string;
  to_character_id: string;
  to_name: string;
  version: number;
}

export interface FocusResponse {
  assignments?: FocusAssignmentView[];
  world_id: string;
}

export interface EraView {
  end_absolute: number;
  era_id: string;
  owner_id: string;
  source_ids?: string[];
  start_absolute: number;
  text: string;
  version: number;
}

export interface ErasResponse {
  eras?: EraView[];
  world_id: string;
}

export interface EndingView {
  detail: string;
  evaluated_absolute: number;
  evidence_event_ids?: string[];
  kind: string;
  satisfied: boolean;
  window_start_absolute: number;
}

export interface EndingsResponse {
  endings?: EndingView[];
  world_id: string;
}

export interface MacroAdvanceRequest {
  day: number;
  resolution: string;
  world_id: string;
}

export interface MacroAdvanceResponse {
  duplicate: boolean;
  end_absolute: number;
  event_ids?: string[];
  run_id: string;
  start_absolute: number;
  state: string;
}

export interface EraComposeRequest {
  end_absolute: number;
  owner_id: string;
  start_absolute: number;
  world_id: string;
}

export interface EndingsEvaluateRequest {
  at_absolute: number;
  world_id: string;
}

export interface FocusAssignRequest {
  effective_absolute: number;
  from_character_id?: string | null;
  reason: string;
  slot: string;
  to_character_id: string;
  world_id: string;
}

export interface ScheduleCancelResponse {
  schedule_id: string;
  status: string;
}

export interface CharacterCreateRequest {
  appearance?: string;
  background?: string;
  location_id: string;
  name: string;
  personality?: string;
  world_id: string;
}

export interface PartyLinkRequest {
  character_id: string;
  expected_version: number;
  world_id: string;
}

export interface ChronicleEntry {
  absolute_index: number;
  event_id: string;
  event_type: string;
  location_id?: string | null;
  participant_ids?: string[];
  revision?: number;
  scene_id?: string | null;
  sequence: number;
  text?: string | null;
  title: string;
}

export interface ChronicleResponse {
  entries?: ChronicleEntry[];
  has_more: boolean;
  next_after: number;
  watermark: number;
  world_id: string;
}

export interface SimulationStatus {
  absolute_index: number;
  latest_run_id?: string | null;
  latest_run_state?: string | null;
  open_run_id?: string | null;
  open_run_state?: string | null;
  world_id: string;
}

export interface PresentationCapabilities {
  capabilities?: string[];
  character_id?: string | null;
  role: string;
}

export interface MapAnchorView {
  location_id: string;
  x: unknown;
  y: unknown;
}

export interface MapManifestView {
  anchors?: MapAnchorView[];
  asset_id?: string | null;
  id: string;
  schematic: boolean;
  version: number;
}

export interface CastEntry {
  character_id: string;
  life_status: string;
  location_id: string;
  name: string;
  portrait_asset_id?: string | null;
}

export interface PresentationResponse {
  absolute_index: number;
  activities?: ActivityView[];
  capabilities: PresentationCapabilities;
  cast?: CastEntry[];
  day: number;
  latest_run_id?: string | null;
  manifest: MapManifestView;
  open_run_id?: string | null;
  phase: string;
  recent_event_id?: string | null;
  revision: number;
  run_state?: string | null;
  threads?: string[];
  world_id: string;
}

export interface AssetView {
  content_ref: string;
  height: number;
  id: string;
  kind: string;
  mime: string;
  status: string;
  style_pack_version: string;
  subject_id?: string | null;
  subject_visual_version: number;
  version: number;
  width: number;
  world_id?: string | null;
}

export interface EnsureStarterRequest {
  world_id: string;
}

export interface InterventionScope {
  character_ids?: string[];
  kind?: string;
  location_ids?: string[];
}

export interface InterventionRequest {
  client_request_id: string;
  effective_at?: string;
  mode: string;
  scope?: InterventionScope;
  text: string;
  world_id: string;
}

export interface InterventionStepView {
  explanation?: string;
  failure_reason?: string;
  id: string;
  kind: string;
  result_activity_id?: string | null;
  result_event_id?: string | null;
  result_hook_id?: string | null;
  seq: number;
  status: string;
  version: number;
}

export interface InterventionView {
  client_request_id: string;
  failure_reason?: string;
  id: string;
  mode: string;
  role: string;
  status: string;
  steps?: InterventionStepView[];
  text: string;
  version: number;
  world_id: string;
}

export interface InterventionEditRequest {
  expected_version: number;
  scope?: InterventionScope;
  text: string;
}

export interface InterventionCancelRequest {
  expected_version: number;
}

export interface SuggestionView {
  destination_location_id?: string | null;
  family: string;
  id: string;
  needs_topic?: boolean;
  subtitle?: string;
  target_character_id?: string | null;
  title: string;
}

export interface ConditionView {
  detail?: string;
  ends_absolute: number;
  id: string;
  kind: string;
  public_label: string;
  scope_location_ids?: string[];
  severity: number;
  started_absolute: number;
  status: string;
  version: number;
  world_id: string;
}

export interface ConditionsResponse {
  conditions?: ConditionView[];
  world_id: string;
}

export interface StorySummary {
  absolute_index: number;
  archived?: boolean;
  day: number;
  last_played_at?: string | null;
  mode: string;
  phase: string;
  status: string;
  story_id: string;
  title: string;
  world_id: string;
  world_name: string;
}

export interface StoryDetail {
  absolute_index: number;
  archived_at?: string | null;
  day: number;
  last_played_at?: string | null;
  metadata_version: number;
  mode: string;
  phase: string;
  status: string;
  story_id: string;
  title: string;
  world_id: string;
  world_name: string;
}

export interface StoryListResponse {
  items?: StorySummary[];
  next_cursor?: string | null;
}

export interface StorySetupView {
  content_hash: string;
  created_at: string;
  payload?: Record<string, unknown>;
  provenance: string;
  schema_version: number;
  story_id: string;
  world_id: string;
}

export interface StoryPatchRequest {
  cover_asset_id?: string | null;
  expected_version: number;
  title?: string | null;
}

export interface StoryArchiveRequest {
  expected_version: number;
}

export interface StoryDraftPayload {
  ai?: Record<string, unknown> | null;
  cast?: Record<string, unknown>[] | null;
  mode?: Record<string, unknown> | null;
  story?: Record<string, unknown> | null;
  world?: Record<string, unknown> | null;
}

export interface StoryDraftCreateRequest {
  current_step?: string;
  payload?: StoryDraftPayload;
}

export interface StoryDraftPatchRequest {
  current_step: string;
  expected_version: number;
  payload: StoryDraftPayload;
}

export interface StoryDraftView {
  created_at: string;
  created_world_id?: string | null;
  current_step: string;
  id: string;
  payload: StoryDraftPayload;
  updated_at: string;
  version: number;
}

export interface DraftValidationView {
  issues?: string[];
  resolved?: Record<string, unknown>;
  valid: boolean;
}

export interface StoryCreateRequest {
  draft_id: string;
  expected_draft_version: number;
}

export interface StoryCreateResponse {
  art_registered?: number;
  character_id?: string | null;
  replayed?: boolean;
  role: string;
  story_id: string;
  world_id: string;
}

export interface PresetSummary {
  archived: boolean;
  builtin: boolean;
  current_revision: number;
  id: string;
  kind: string;
  name: string;
  readonly: boolean;
  version: number;
}

export interface PresetDetail {
  archived_at?: string | null;
  builtin: boolean;
  current_revision: number;
  id: string;
  kind: string;
  name: string;
  readonly: boolean;
  revision?: Record<string, unknown>;
  version: number;
}

export interface PresetPublishView {
  detail: PresetDetail;
  published_revision: number;
}

export interface PresetCreateRequest {
  kind: string;
  name: string;
  payload: Record<string, unknown>;
}

export interface PresetArchiveRequest {
  expected_version: number;
}

export interface PresetRevisionRequest {
  expected_version: number;
  payload: Record<string, unknown>;
}

export interface EditorDraftView {
  base_revision: number;
  fields?: Record<string, unknown>;
  id: string;
  preset_id: string;
  published_hash?: string | null;
  published_revision?: number | null;
  published_version?: number | null;
  replayed?: boolean;
  updated_at: string;
  version: number;
}

export interface EditorDraftOpenRequest {
  base_revision: number;
}

export interface EditorDraftSaveRequest {
  expected_version: number;
  fields?: Record<string, unknown>;
}

export interface EditorDraftPublishRequest {
  expected_version: number;
  preset_expected_version: number;
}

export interface EditorDraftCompleteRequest {
  expected_version: number;
}

export interface PreferencesView {
  accessibility?: Record<string, unknown>;
  gameplay?: Record<string, unknown>;
  operator: string;
  profile?: Record<string, unknown>;
  version: number;
}

export interface PreferencesPatchRequest {
  accessibility?: Record<string, unknown> | null;
  expected_version: number;
  gameplay?: Record<string, unknown> | null;
  profile?: Record<string, unknown> | null;
}

export interface ProviderConnectionView {
  adapter: string;
  allow_local_endpoint?: boolean;
  config_version: number;
  created_at: string;
  credential_env?: string | null;
  endpoint: string;
  has_credential?: boolean;
  id: string;
  name: string;
}

export interface ProviderConnectionCreate {
  adapter: string;
  allow_local_endpoint?: boolean;
  credential_env?: string | null;
  endpoint: string;
  name: string;
}

export interface ProviderConnectionPatch {
  allow_local_endpoint?: boolean | null;
  credential_env?: string | null;
  endpoint?: string | null;
  expected_version: number;
  name?: string | null;
}

export interface ProviderProfileView {
  capabilities?: string[];
  connection_id: string;
  created_at: string;
  id: string;
  max_tokens: number;
  model_id: string;
  revision: number;
  temperature?: unknown | null;
  top_k?: number | null;
  top_p?: unknown | null;
}

export interface ProviderProfileCreate {
  max_tokens?: number;
  model_id: string;
  temperature?: unknown | null;
  top_k?: number | null;
  top_p?: unknown | null;
}

export interface ProviderCapabilitiesView {
  adapter: string;
  connection_id: string;
  models?: string[];
  probe?: Record<string, unknown>;
  supported_parameters?: string[];
}

export interface ProviderTestRequest {
  live?: boolean;
}

export interface ProviderTestView {
  detail?: string;
  reachable?: boolean;
  state: string;
  tested_at?: string;
  tested_config_revision?: number;
  text_ready?: string;
}

export interface StoryProviderPinView {
  adapter: string;
  connection_name: string;
  model_id: string;
  profile_id: string;
  revision: number;
}

export interface StoryProviderEnvironmentView {
  active_profile: string;
  adapter: string;
  model_id?: string | null;
}

export interface StoryProviderView {
  effective_adapter?: string | null;
  effective_model_id?: string | null;
  effective_revision?: number | null;
  effective_source: string;
  environment: StoryProviderEnvironmentView;
  pin?: StoryProviderPinView | null;
  pin_error?: string | null;
  pin_state: string;
  story_id: string;
  world_id: string;
}

export interface CacheScopeView {
  description: string;
  files: number;
  scope: string;
}

export interface CacheClearRequest {
  scope: string;
}

export type WatcherHeaders = {
  "X-Worldsim-Role": "watcher";
};

export type PlayerHeaders = {
  "X-Worldsim-Role": "player";
  "X-Worldsim-Character": string;
};

export const ROUTES = {
  listCharacters: "GET /api/v1/stage1/characters",
  getCharacter: "GET /api/v1/stage1/characters/{character_id}",
  listScenes: "GET /api/v1/stage1/scenes",
  getScene: "GET /api/v1/stage1/scenes/{scene_id}",
  getNarration: "GET /api/v1/stage1/scenes/{scene_id}/narration",
  listModelRuns: "GET /api/v1/stage1/model-runs",
  beginPartyMember: "POST /api/v1/stage1/party/begin",
  readSimulationStatus: "GET /api/v1/simulation/status",
  resume: "POST /api/v1/stage1/resume",
  listParty: "GET /api/v1/stage1/party",
  createCharacter: "POST /api/v1/stage1/characters",
  linkPartyMember: "POST /api/v1/stage1/party/{member_id}/link",
  startActivity: "POST /api/v1/stage2/activities",
  interruptActivity: "POST /api/v1/stage2/activities/{activity_id}/interrupt",
  resumeActivity: "POST /api/v1/stage2/activities/{activity_id}/resume",
  cancelActivity: "POST /api/v1/stage2/activities/{activity_id}/cancel",
  listActivities: "GET /api/v1/stage2/activities",
  recordRelationshipEvidence: "POST /api/v1/stage2/relationships/evidence",
  listRelationships: "GET /api/v1/stage2/relationships",
  assertClaim: "POST /api/v1/stage2/claims",
  listClaims: "GET /api/v1/stage2/claims",
  listBeliefs: "GET /api/v1/stage2/beliefs",
  giveItem: "POST /api/v1/stage2/items/give",
  transferItem: "POST /api/v1/stage2/items/{item_id}/transfer",
  listItems: "GET /api/v1/stage2/items",
  listSkills: "GET /api/v1/stage2/skills",
  selectRole: "POST /api/v1/stage2/roles/select",
  readRole: "GET /api/v1/stage2/roles",
  readConditions: "GET /api/v1/world/conditions",
  listTimeline: "GET /api/v1/stage2/timeline",
  readMap: "GET /api/v1/stage2/map",
  readDiary: "GET /api/v1/stage2/characters/{character_id}/diary",
  listCharacterActivities: "GET /api/v1/stage2/characters/{character_id}/activities",
  listDirectorHooks: "GET /api/v1/stage2/director/hooks",
  readOperationsStatus: "GET /api/v1/stage2/operations/status",
  listEvents: "GET /api/v1/world/events",
  readPresentation: "GET /api/v1/world/presentation",
  readChronicle: "GET /api/v1/world/chronicle",
  listMacroRuns: "GET /api/v1/macro/runs",
  readLineage: "GET /api/v1/macro/lineage",
  listFocus: "GET /api/v1/macro/focus",
  requestImageJob: "POST /api/v1/assets/jobs",
  readImageJob: "GET /api/v1/assets/jobs/{job_id}",
  ensureStarterAssets: "POST /api/v1/assets/ensure-starter",
  submitIntervention: "POST /api/v1/interventions",
  listInterventions: "GET /api/v1/interventions",
  readIntervention: "GET /api/v1/interventions/{intervention_id}",
  editIntervention: "PATCH /api/v1/interventions/{intervention_id}",
  cancelIntervention: "POST /api/v1/interventions/{intervention_id}/cancel",
  evaluateEndings: "POST /api/v1/macro/endings/evaluate",
  assignFocus: "POST /api/v1/macro/focus/assign",
  cancelSchedule: "POST /api/v1/macro/schedules/{schedule_id}/cancel",
  listStories: "GET /api/v1/stories",
  createStory: "POST /api/v1/stories",
  readStory: "GET /api/v1/stories/{story_id}",
  renameStory: "PATCH /api/v1/stories/{story_id}",
  readStorySetup: "GET /api/v1/stories/{story_id}/setup",
  exportStorySetup: "GET /api/v1/stories/{story_id}/setup/export",
  readStoryProvider: "GET /api/v1/stories/{story_id}/provider",
  openStory: "POST /api/v1/stories/{story_id}/open",
  archiveStory: "POST /api/v1/stories/{story_id}/archive",
  unarchiveStory: "POST /api/v1/stories/{story_id}/unarchive",
  listDrafts: "GET /api/v1/story-drafts",
  createDraft: "POST /api/v1/story-drafts",
  readDraft: "GET /api/v1/story-drafts/{draft_id}",
  saveDraft: "PATCH /api/v1/story-drafts/{draft_id}",
  deleteDraft: "DELETE /api/v1/story-drafts/{draft_id}",
  validateDraft: "POST /api/v1/story-drafts/{draft_id}/validate",
  listPresets: "GET /api/v1/library/presets",
  createPreset: "POST /api/v1/library/presets",
  readPreset: "GET /api/v1/library/presets/{preset_id}",
  addPresetRevision: "POST /api/v1/library/presets/{preset_id}/revisions",
  openEditorDraft: "POST /api/v1/library/presets/{preset_id}/editor-drafts",
  readEditorDraft: "GET /api/v1/library/presets/{preset_id}/editor-drafts/current",
  saveEditorDraft: "PATCH /api/v1/library/presets/{preset_id}/editor-drafts/{draft_id}",
  discardEditorDraft: "DELETE /api/v1/library/presets/{preset_id}/editor-drafts/{draft_id}",
  publishEditorDraft: "POST /api/v1/library/presets/{preset_id}/editor-drafts/{draft_id}/publish",
  completeEditorDraft: "POST /api/v1/library/presets/{preset_id}/editor-drafts/{draft_id}/complete",
  duplicatePreset: "POST /api/v1/library/presets/{preset_id}/duplicate",
  archivePreset: "POST /api/v1/library/presets/{preset_id}/archive",
  unarchivePreset: "POST /api/v1/library/presets/{preset_id}/unarchive",
  exportPreset: "GET /api/v1/library/presets/{preset_id}/export",
  listLibraryAssets: "GET /api/v1/library/assets",
  readPreferences: "GET /api/v1/settings/preferences",
  savePreferences: "PATCH /api/v1/settings/preferences",
  listProviders: "GET /api/v1/settings/providers",
  createProvider: "POST /api/v1/settings/providers",
  readProvider: "GET /api/v1/settings/providers/{connection_id}",
  saveProvider: "PATCH /api/v1/settings/providers/{connection_id}",
  listProfiles: "GET /api/v1/settings/providers/{connection_id}/profiles",
  addProfile: "POST /api/v1/settings/providers/{connection_id}/profiles",
  readCapabilities: "GET /api/v1/settings/providers/{connection_id}/capabilities",
  testProvider: "POST /api/v1/settings/providers/{connection_id}/test",
  listCaches: "GET /api/v1/settings/cache",
  clearCache: "POST /api/v1/settings/cache/clear",
} as const;
