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
  is_all_day?: boolean;
  recurrence_rule?: string | null;
  attendees?: EventAttendee[] | null;
  color?: string | null;
}

/** An attendee on a calendar event. */
export interface EventAttendee {
  email: string;
  name?: string;
  status?: string;
}

// --- Phase 4: Advanced Email types ----------------------------------------

/** A custom, color-coded email label. */
export interface EmailLabel {
  id: string;
  name: string;
  color: string;
}

/** An auto-apply email filter rule. */
export interface EmailFilter {
  id: string;
  name: string;
  field: string;
  pattern: string;
  action: string;
  action_value: string | null;
  is_active: boolean;
}

/** A snoozed email. */
export interface EmailSnooze {
  id: string;
  provider_connection_id: string;
  provider_message_id: string;
  snooze_until: string;
}

/** A scheduled email pending delivery. */
export interface ScheduledEmail {
  id: string;
  provider_connection_id: string;
  to_addresses: string[];
  subject: string;
  body_text: string;
  scheduled_for: string;
  status: string;
}

/** A reusable email template. */
export interface EmailTemplate {
  id: string;
  name: string;
  subject: string | null;
  body_text: string;
}

/** Vacation auto-responder configuration. */
export interface VacationConfig {
  enabled: boolean;
  subject: string;
  body_text: string;
  start_date: string | null;
  end_date: string | null;
}

/** AI email summarization result. */
export interface EmailSummary {
  summary: string;
  method: string;
}

export interface EmailAttachment {
  filename: string;
  content_type: string;
  size: number;
  content_id?: string | null;
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
  account_display_name?: string | null;
  account_email?: string | null;
  sub_account_id?: string | null;
  sub_account_name?: string | null;
  is_unread?: boolean;
  is_starred?: boolean;
  body_text?: string | null;
  thread_id?: string | null;
  attachments?: EmailAttachment[];
}

/** A connected email account shown in the unified inbox sidebar. */
export interface EmailAccount {
  provider_connection_id: string;
  provider_type: string;
  display_name: string;
  email: string | null;
  sub_account_id: string;
  sub_account_name: string;
  status: string;
  unread_count: number;
  total_count: number;
}

/** Email folder/label type for the folder navigation bar. */
export type EmailFolder = "INBOX" | "STARRED" | "SENT" | "DRAFT" | "TRASH" | "ALL";

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

/** Verification status for a marketplace item (trust & moderation). */
export type VerificationStatus = "unverified" | "verified" | "flagged";

/** A moderation flag record on a marketplace item. */
export interface FlagRecord {
  id: string;
  item_id: string;
  flagged_by: string;
  reason: string;
  created_at: string;
  resolved: boolean;
  resolved_by: string | null;
  resolved_at: string | null;
}

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
  // Trust & moderation fields
  content_hash: string;
  verification_status: VerificationStatus;
  flag_count: number;
  trust_score: number;
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

export interface CustomQuestion {
  id: string;
  label: string;
  type: "text" | "textarea" | "select" | "phone" | "checkbox";
  required: boolean;
  options: string[];
  placeholder: string;
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
  buffer_before_minutes: number;
  buffer_after_minutes: number;
  min_notice_hours: number;
  max_booking_days: number;
  recurring_pattern: string;
  recurring_interval: number;
  custom_questions: CustomQuestion[];
  video_provider: string;
  reminder_enabled: boolean;
  reminder_minutes_before: number;
  confirmation_email_enabled: boolean;
  confirmation_template: string | null;
  // Phase 5: Team & Payments
  team_id: string | null;
  assignment_strategy: AssignmentStrategy;
  routing_form_id: string | null;
  is_paid: boolean;
  price_cents: number;
  currency: string;
  stripe_product_id: string | null;
}

export interface BookingSlot {
  start: string;
  end: string;
}

export interface Booking {
  id: string;
  event_type_id: string;
  user_id: string;
  attendee_name: string;
  attendee_email: string;
  attendee_timezone: string;
  start_time: string;
  end_time: string;
  status: string;
  answers: Record<string, unknown>;
  video_link: string | null;
  notes: string | null;
  metadata: Record<string, unknown>;
  // Phase 5: Payment and team assignment
  payment_status: string;
  payment_intent_id: string | null;
  assigned_member_id: string | null;
  created_at: string | null;
}

export interface BookingResult {
  status: string;
  booking_id: string;
  start_time: string;
  end_time: string;
  video_link: string | null;
  event_type_title: string;
  // Phase 5
  assigned_member_id: string | null;
  payment_status: string;
  price_cents: number;
  currency: string;
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

// --- Auth ------------------------------------------------------------------

/** Authenticated user info from GET /api/a-cal/auth/me */
export interface AuthUser {
  id: string;
  email: string;
  display_name: string | null;
  is_active: boolean;
}

// --- Phase 5: Team & Payments types ----------------------------------------

/** Assignment strategy for team event types. */
export type AssignmentStrategy = "collective" | "round_robin";

/** A scheduling team. */
export interface Team {
  id: string;
  name: string;
  slug: string;
  description: string;
  logo_url: string | null;
  branding: Record<string, unknown>;
  members?: TeamMember[];
  created_at: string | null;
}

/** A member of a scheduling team. */
export interface TeamMember {
  id: string;
  team_id: string;
  email: string;
  display_name: string;
  role: string;
  provider_connection_id: string | null;
  is_active: boolean;
}

/** A routing form question. */
export interface RoutingQuestion {
  id: string;
  label: string;
  type: "text" | "textarea" | "select" | "phone" | "checkbox";
  required: boolean;
  options: string[];
}

/** A routing rule mapping answers to event types or members. */
export interface RoutingRule {
  condition: string;
  event_type_id: string | null;
  member_id: string | null;
}

/** A routing form. */
export interface RoutingForm {
  id: string;
  name: string;
  description: string;
  questions: RoutingQuestion[];
  routing_rules: RoutingRule[];
  is_active: boolean;
  created_at: string | null;
}

/** A webhook endpoint configuration. */
export interface WebhookConfig {
  id: string;
  url: string;
  events: string[];
  secret: string | null;
  is_active: boolean;
  last_delivery_at: string | null;
  last_status: number | null;
  created_at: string | null;
}

/** A webhook delivery record. */
export interface WebhookDelivery {
  id: string;
  webhook_id: string;
  event_type: string;
  status_code: number | null;
  response_body: string | null;
  delivered_at: string | null;
}

/** Payment service configuration. */
export interface PaymentConfig {
  is_configured: boolean;
  is_mock: boolean;
  publishable_key: string | null;
}

/** A Stripe payment intent. */
export interface PaymentIntent {
  id: string;
  client_secret: string | null;
  amount: number;
  currency: string;
  status: string;
}

/** Custom domain configuration for booking pages. */
export interface CustomDomainConfig {
  domain: string;
  is_active: boolean;
  ssl_verified: boolean;
}

/** Workflow trigger configuration. */
export interface WorkflowTriggerConfig {
  booking_created: boolean;
  booking_cancelled: boolean;
  booking_rescheduled: boolean;
}

/** GraphQL query response. */
export interface GraphQLResponse {
  data: Record<string, unknown>;
  errors?: Array<{ message: string }>;
}

/** GraphQL schema introspection. */
export interface GraphQLSchema {
  types: Record<string, Record<string, unknown>>;
}
