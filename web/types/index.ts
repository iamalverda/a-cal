/** A-Cal shared types — mirror the Python backend models. */

export type SyncMode = "mirror_filter" | "intelligent_merge" | "layered_federation" | "per_sub_agent";

export type SubAccountKind = "calendar" | "email" | "unified";

export type ProviderType =
  | "google_calendar"
  | "outlook_calendar"
  | "caldav"
  | "gmail"
  | "imap_smtp";

export type ConnectionStatus = "pending" | "connected" | "error" | "revoked";

export interface SubAccount {
  id: string;
  name: string;
  kind: SubAccountKind;
  is_main: boolean;
  sync_mode: SyncMode;
  agent_enabled: boolean;
  settings: Record<string, unknown>;
}

export interface ProviderConnection {
  id: string;
  sub_account_id: string;
  provider_type: ProviderType;
  provider_account_id: string;
  display_name: string | null;
  status: ConnectionStatus;
  last_sync_at: string | null;
}

export interface UnifiedEvent {
  provider_event_id: string;
  provider_type: ProviderType;
  title: string;
  start: string;
  end: string;
  description: string | null;
  location: string | null;
  source_sub_account_id: string | null;
  metadata: Record<string, unknown>;
}

export interface EmailMessage {
  provider_message_id: string;
  provider_type: string;
  provider_connection_id: string;
  subject: string;
  from_address: string;
  to_addresses: string[];
  received_at: string | null;
  snippet: string | null;
  has_calendar_invite: boolean;
  labels: string[];
}

export type SkillMode = "simple" | "pro" | "developer";

export interface ModeConfig {
  mode: SkillMode;
  display_name: string;
  description: string;
  visible_panels: string[];
  visible_settings: string[];
  default_sync_mode: SyncMode;
  per_task_model_routing: boolean;
  developer_studio: boolean;
  config_as_code: boolean;
  visual_builder: boolean;
  plugin_system: boolean;
  api_sdk: boolean;
  marketplace: boolean;
  default_self_model_depth: string;
  default_proactive: boolean;
}

export type ModelProvider =
  | "ollama" | "llama_cpp" | "lm_studio"
  | "openai" | "anthropic" | "google" | "azure"
  | "deepseek" | "together" | "groq" | "openrouter" | "mistral";

export interface ModelRoutingConfig {
  global_provider: ModelProvider;
  global_model: string;
  per_task_overrides: Record<string, string>;
  privacy_force_local: boolean;
}

/** Agent autonomy level — controls how much freedom agents have to act. */
export type AutonomyLevel = "suggest_only" | "confirm" | "full_auto";

/** Agent autonomy configuration — global default + per-sub-account overrides. */
export interface AutonomyConfig {
  default_level: AutonomyLevel;
  per_sub_account: Record<string, AutonomyLevel>;
}

/** Email integration depth — how deeply agents integrate with email (charter §5). */
export type EmailDepth = "sync_notify" | "agent_mediated" | "full_two_way";

/** Community profile / showcase — the user's authored items, remixes, and stats. */
export interface CommunityProfile {
  user_id: string;
  stats: {
    total_authored: number;
    total_originals: number;
    total_remixes: number;
    total_installed: number;
    total_installs_of_authored: number;
    total_remixes_of_authored: number;
    avg_rating: number;
  };
  authored: MarketplaceItem[];
  originals: MarketplaceItem[];
  remixes: MarketplaceItem[];
  installed: { item_id: string; installed_at: string }[];
}

export interface EmailIntegrationConfig {
  depth: EmailDepth;
  per_provider: Record<string, EmailDepth>;
  auto_scan_enabled: boolean;
}

export interface SelfModelDepth {
  depth: string;
  enabled_categories: Record<string, boolean>;
  cloud_sync_enabled: boolean;
  proactive_suggestions_enabled: boolean;
  feed_into_calendar_view: boolean;
  feed_into_agents: boolean;
  feed_into_proactive: boolean;
}

/** A single fact the self-model has learned about the user. */
export interface SelfModelFact {
  id: string;
  category: string;
  content: string;
  depth: string;
  privacy_tier: string;
  confidence: number;
  provenance: string;
  source_event_ids: string[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
  superseded_by: string | null;
  status: string;
}

/** Exported self-model facts bundle (backup / transfer). */
export interface SelfModelExport {
  user_id: string;
  fact_count: number;
  facts: SelfModelFact[];
}

export interface AgentSpec {
  name: string;
  display_name: string;
  description: string;
  system_prompt: string;
  tools: string[];
  default_tier: string;
  can_negotiate: boolean;
  privacy_force_local: boolean;
  capabilities: string[];
}

export interface RoutingDecision {
  intent: string;
  specialist: string | null;
  tier: string;
  force_local: boolean;
  self_model_context: string;
  reasoning: string;
}

export interface AgentAction {
  type: string;
  [key: string]: unknown;
}

export interface ConductorResponse {
  user_id: string;
  message: string;
  routing: RoutingDecision;
  response: string | null;
  actions?: AgentAction[];
  routing_trace?: RoutingTrace | null;
  cas_modules_engaged?: string[];
  timestamp: string;
  standalone: boolean;
}

// --- Swarm negotiation types ------------------------------------------------

export type SubAccountPriority = "critical" | "high" | "normal" | "low" | "deferred";
export type NegotiationState = "initiated" | "probing" | "proposing" | "accepted" | "rejected" | "conceded" | "resolved" | "escalated";
export type NegotiationStatus = "resolved" | "escalated" | "timeout" | "cancelled";

export interface ConflictClaim {
  sub_account_id: string;
  event_id: string;
  event_title: string;
  slot_start: string;
  slot_end: string;
  priority: SubAccountPriority;
  can_move: boolean;
  reasoning: string;
}

export interface SlotProposal {
  sub_account_id: string;
  proposed_start: string;
  proposed_end: string;
  reason: string;
}

export interface NegotiationMessage {
  id: string;
  negotiation_id: string;
  from_sub_account_id: string;
  to_sub_account_id: string;
  message_type: "probe" | "claim" | "propose" | "accept" | "reject" | "concede" | "escalate" | "resolve";
  timestamp: string;
  priority: SubAccountPriority | null;
  proposal: SlotProposal | null;
  reasoning: string;
}

export interface SwarmNegotiation {
  id: string;
  conflict_start: string;
  state: NegotiationState;
  status: NegotiationStatus | null;
  claims: ConflictClaim[];
  messages: NegotiationMessage[];
  winner_sub_account_id: string | null;
  resolution_reason: string;
  resolved_at: string | null;
  max_rounds: number;
  current_round: number;
}

export interface NegotiationResult {
  resolved: boolean;
  escalated: boolean;
  winner_sub_account_id: string | null;
  loser_sub_account_id: string | null;
  alternative_slot: SlotProposal | null;
  resolution_reason: string;
  rounds: number;
  negotiation_id: string;
  audit_trail: NegotiationMessage[];
}

// --- Marketplace types ------------------------------------------------------

export type MarketplaceItemType = "agent_spec" | "sync_rule_pack" | "negotiation_strategy" | "ui_theme" | "plugin_config";

export interface Provenance {
  summary: string;
  what_it_does: string;
  gaps_and_limits: string;
  integration_notes: string;
  version: string;
  license: string;
}

export interface MarketplaceItem {
  id: string;
  name: string;
  item_type: MarketplaceItemType;
  author: string;
  description: string;
  provenance: Provenance;
  config: Record<string, unknown>;
  tags: string[];
  remixed_from: string | null;
  install_count: number;
  rating: number;
  rating_count: number;
  created_at: string;
  updated_at: string | null;
}

export interface InstallRecord {
  id: string;
  user_id: string;
  item_id: string;
  installed_at: string;
  installed_config: Record<string, unknown>;
}

// --- Developer types --------------------------------------------------------

export type PluginType = "agent" | "provider" | "sync_rule" | "ui_component";

export interface Plugin {
  id: string;
  name: string;
  plugin_type: PluginType;
  version: string;
  author: string;
  description: string;
  config_schema: Record<string, unknown>;
  default_config: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
}

export interface ConfigExport {
  schema_version: string;
  mode: Record<string, unknown>;
  model_routing: Record<string, unknown>;
  self_model: Record<string, unknown>;
  custom_agent_specs: Record<string, unknown>[];
  plugins: Record<string, unknown>[];
  sub_accounts: Record<string, unknown>[];
  built_in_agent_count: number;
}

export interface ConfigImportResult {
  imported: {
    mode: string;
    model_routing: Record<string, unknown>;
    self_model: Record<string, unknown>;
    custom_agent_count: number;
    plugin_count: number;
    sub_account_count: number;
  };
  errors: string[];
  warnings: string[];
}

// --- CAS / Nervous System types ---------------------------------------------

export interface CASModule {
  brain_region: string;
  nervous_system_layer: string;
  augments: string;
  cas_source: string;
  signal_type: string;
}

export interface CASAgentSpec extends AgentSpec {
  cas: CASModule;
  is_bio_mimetic: boolean;
}

export type ActivationState = "awake" | "light_sleep" | "deep_sleep" | "wake_up_transition";
export type GateState = "open" | "throttled" | "closed" | "priority";
export type AutonomicMode = "sympathetic" | "balanced" | "parasympathetic";

export interface SystemState {
  activation: ActivationState;
  autonomic_mode: AutonomicMode;
  sympathetic_score: number;
  spotlight_target: string | null;
  spotlight_priority: number;
  meeting_load_hours: number;
  break_adequacy: number;
  focus_block_hours: number;
  last_user_interaction: string | null;
  binding_quality: number;
  overload_risk: boolean;
  burnout_risk: boolean;
}

export interface SignalEvaluation {
  gate_state: GateState;
  urgency: number;
  relevance: number;
  recommended_specialist: string | null;
  reasoning: string;
}

export interface RoutingTrace {
  signal: string;
  timestamp: string;
  thalamus_gate: SignalEvaluation;
  activation_state: ActivationState;
  autonomic_mode: AutonomicMode;
  basal_ganglia_ranking: Array<{
    name: string;
    display_name: string;
    confidence: number;
    reason: string;
  }>;
  conductor_decision: {
    chosen_specialist: string;
    chosen_display_name: string;
    confidence: number;
    gate_state: string;
    activation: string;
  };
  cas_modules_engaged: string[];
  hippocampus_encoding: {
    id: string;
    timestamp: string;
    signal: string;
    specialist: string;
    outcome: string;
    decisions: string[];
    tags: string[];
  } | null;
  binding_check: {
    binding_quality: number;
    verified: boolean;
  } | null;
  total_latency_ms: number;
}

export interface NervousSystemOverview {
  state: SystemState;
  cas_agents: CASAgentSpec[];
  augmentation_map: Record<string, string[]>;
  memory_count: number;
  habit_count: number;
  recent_memories: Array<Record<string, unknown>>;
  active_habits: Array<Record<string, unknown>>;
}

export interface RuntimePlugin {
  id: string;
  name: string;
  plugin_type: string;
  file_path: string;
  hooks: string[];
  enabled: boolean;
  load_error: string | null;
  loaded_at: string;
}

// --- Workflows --------------------------------------------------------------

export interface WorkflowNodeDef {
  id: string;
  agent: string;
  label: string;
  config: Record<string, unknown>;
  conditional?: string | null;
}

export interface WorkflowDef {
  id: string;
  name: string;
  description: string;
  nodes: WorkflowNodeDef[];
  trigger: "manual" | "schedule_change" | "email_received" | "conflict_detected";
  version: string;
  created_at: string;
  updated_at: string;
}

export interface WorkflowStepResult {
  node_id: string;
  node_index: number;
  agent: string;
  label: string;
  skipped: boolean;
  output?: string;
  actions?: Array<Record<string, unknown>>;
  routing?: Record<string, unknown> | null;
  error?: string;
}

export interface WorkflowRunResult {
  workflow_id: string;
  success: boolean;
  steps: WorkflowStepResult[];
  final_output: string;
  error: string | null;
  started_at: string;
  finished_at: string;
}

// --- Atom integration types -------------------------------------------------

export interface AtomStatus {
  available: boolean;
  backend_path: string | null;
  adapters: {
    token_storage: boolean;
    llm: boolean;
    intent: boolean;
  };
}

export type BackendMode = "standalone" | "atom";

// --- Sync Rules ------------------------------------------------------------

export type RuleType = "include" | "exclude" | "transform" | "agent";
export type RuleField = "title" | "calendar_id" | "category" | "attendee" | "keyword";

export interface SyncRule {
  id: string;
  sub_account_id: string;
  rule_type: RuleType;
  field: RuleField;
  pattern: string;
  action: Record<string, unknown>;
  priority: number;
  is_active: boolean;
}

// --- Analytics (zero-calendar integration) ---------------------------------

export interface BusyTimesAnalysis {
  total_events: number;
  busy_by_day_of_week: number[];
  events_by_day_of_week: number[];
  busy_by_hour: number[];
  busiest_day: string;
  busiest_day_hours: number;
  busiest_hour: number;
  busiest_hour_count: number;
}

export interface MeetingStats {
  total_meeting_minutes: number;
  total_meeting_hours: number;
  meeting_count: number;
  average_meeting_length: number;
  average_daily_meeting_minutes: number;
  average_daily_meeting_hours: number;
  category_counts: Record<string, number>;
  busiest_day: string;
  busiest_day_minutes: number;
  busiest_day_hours: number;
  daily_meeting_minutes: Record<string, number>;
}

export interface AnalyticsSummary {
  busy_times: BusyTimesAnalysis;
  meeting_stats: MeetingStats;
  period_days: number;
}

export interface FreeSlot {
  start: string;
  end: string;
  duration: number;
}

// --- Event Types (cal.com integration) -------------------------------------

export type SchedulingType = "round_robin" | "collective" | "managed";

export interface AvailabilitySchedule {
  days: Record<string, string>[][];
  timezone: string;
}

export interface EventType {
  id: string;
  title: string;
  slug: string;
  duration_minutes: number;
  description: string;
  scheduling_type: SchedulingType;
  availability: AvailabilitySchedule;
  status: string;
  color: string;
  metadata: Record<string, unknown>;
}

// --- Calendar Tools (zero-calendar integration) ----------------------------

export interface CalendarTool {
  name: string;
  description: string;
  parameters: Record<string, Record<string, unknown>>;
}

// --- API Explorer (Developer Studio) ---------------------------------------

/** A single API route for the API Explorer. */
export interface ApiRouteInfo {
  method: string;
  path: string;
  summary: string;
  description: string;
  tag: string;
  path_params: Array<{ name: string; in: string; required: boolean }>;
  query_params: Array<{ name: string; in: string; required: boolean; default: string | null }>;
  body_schema: {
    name: string;
    fields: Record<string, {
      type: string;
      default: string | null;
      required: boolean;
    }>;
  } | null;
}
