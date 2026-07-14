/** Mock data for development without a running Python backend.

This lets the A-Cal UI be fully explorable standalone. When the backend is
running, the API client uses real data instead.

Mock data is gated behind a dev-only condition. In production builds
(``NODE_ENV === "production"`` without ``NEXT_PUBLIC_A_CAL_USE_MOCKS``),
the UI surfaces real error states instead of fake data.
 */

/** Whether mock data should be used as a fallback.

Returns true when:
  - ``NODE_ENV === "development"`` (Next.js dev server), or
  - ``NEXT_PUBLIC_A_CAL_USE_MOCKS`` is explicitly set to "1" or "true".

In production, this returns false so the UI never shows fake data.
*/
export function shouldUseMocks(): boolean {
  if (process.env.NODE_ENV === "development") return true;
  return process.env.NEXT_PUBLIC_A_CAL_USE_MOCKS === "1"
    || process.env.NEXT_PUBLIC_A_CAL_USE_MOCKS === "true";
}


import type {
  SubAccount,
  ProviderConnection,
  UnifiedEvent,
  ModeConfig,
  ModelRoutingConfig,
  AgentSpec,
  ConductorResponse,
} from "@/types";

function isoOffset(days: number, hours = 0, minutes = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  d.setHours(hours, minutes, 0, 0);
  return d.toISOString();
}

export const mockSubAccounts: SubAccount[] = [
  {
    id: "sa-main",
    name: "Main Calendar",
    kind: "unified",
    is_main: true,
    sync_mode: "mirror_filter",
    agent_enabled: true,
    settings: { color: "#6366f1", visible: true },
  },
  {
    id: "sa-work-google",
    name: "Work Google",
    kind: "calendar",
    is_main: false,
    sync_mode: "mirror_filter",
    agent_enabled: false,
    settings: { color: "#3b82f6", visible: true },
  },
  {
    id: "sa-personal",
    name: "Personal",
    kind: "calendar",
    is_main: false,
    sync_mode: "intelligent_merge",
    agent_enabled: true,
    settings: { color: "#10b981", visible: true },
  },
  {
    id: "sa-email",
    name: "Email Inbox",
    kind: "email",
    is_main: false,
    sync_mode: "mirror_filter",
    agent_enabled: false,
    settings: { color: "#f59e0b", visible: true },
  },
];

export const mockProviders: Record<string, ProviderConnection[]> = {
  "sa-work-google": [
    {
      id: "pc-1",
      sub_account_id: "sa-work-google",
      provider_type: "google_calendar",
      provider_account_id: "christopher@work.com",
      display_name: "Work Calendar",
      status: "connected",
      last_sync_at: isoOffset(0, 9, 0),
    },
  ],
  "sa-personal": [
    {
      id: "pc-2",
      sub_account_id: "sa-personal",
      provider_type: "caldav",
      provider_account_id: "chris@fastmail.com",
      display_name: "Fastmail Calendar",
      status: "connected",
      last_sync_at: isoOffset(0, 8, 30),
    },
  ],
  "sa-email": [
    {
      id: "pc-3",
      sub_account_id: "sa-email",
      provider_type: "gmail",
      provider_account_id: "christopher@gmail.com",
      display_name: "Gmail",
      status: "connected",
      last_sync_at: isoOffset(0, 7, 0),
    },
    {
      id: "pc-4",
      sub_account_id: "sa-email",
      provider_type: "imap_smtp",
      provider_account_id: "chris@personal.net",
      display_name: "Personal IMAP",
      status: "pending",
      last_sync_at: null,
    },
  ],
};

export const mockEvents: UnifiedEvent[] = [
  {
    provider_event_id: "evt-1",
    provider_type: "google_calendar",
    title: "Team Standup",
    start: isoOffset(0, 9, 0),
    end: isoOffset(0, 9, 30),
    description: "Daily sync with engineering team",
    location: "Zoom",
    source_sub_account_id: "sa-work-google",
    metadata: { tags: ["work", "recurring"] },
  },
  {
    provider_event_id: "evt-2",
    provider_type: "google_calendar",
    title: "Sprint Planning",
    start: isoOffset(0, 11, 0),
    end: isoOffset(0, 12, 30),
    description: "Plan sprint 24",
    location: "Conference Room A",
    source_sub_account_id: "sa-work-google",
    metadata: { tags: ["work"] },
  },
  {
    provider_event_id: "evt-3",
    provider_type: "caldav",
    title: "Lunch with Sarah",
    start: isoOffset(0, 12, 30),
    end: isoOffset(0, 13, 30),
    description: null,
    location: "Cafe Noir",
    source_sub_account_id: "sa-personal",
    metadata: {},
  },
  {
    provider_event_id: "evt-4",
    provider_type: "google_calendar",
    title: "1:1 with Manager",
    start: isoOffset(1, 14, 0),
    end: isoOffset(1, 14, 30),
    description: "Weekly check-in",
    location: null,
    source_sub_account_id: "sa-work-google",
    metadata: { tags: ["work", "recurring"] },
  },
  {
    provider_event_id: "evt-5",
    provider_type: "caldav",
    title: "Dentist Appointment",
    start: isoOffset(2, 10, 0),
    end: isoOffset(2, 11, 0),
    description: "6-month checkup",
    location: "Dr. Patel's Office",
    source_sub_account_id: "sa-personal",
    metadata: {},
  },
  {
    provider_event_id: "evt-6",
    provider_type: "google_calendar",
    title: "Product Review",
    start: isoOffset(2, 15, 0),
    end: isoOffset(2, 16, 0),
    description: "Q3 product roadmap review",
    location: "Zoom",
    source_sub_account_id: "sa-work-google",
    metadata: { tags: ["work"], conflict: true },
  },
  {
    provider_event_id: "evt-7",
    provider_type: "google_calendar",
    title: "Design Sync",
    start: isoOffset(2, 15, 30),
    end: isoOffset(2, 16, 30),
    description: "Review new mockups",
    location: "Figma",
    source_sub_account_id: "sa-work-google",
    metadata: { tags: ["work"], conflict: true },
  },
  {
    provider_event_id: "evt-8",
    provider_type: "caldav",
    title: "Gym Session",
    start: isoOffset(3, 6, 0),
    end: isoOffset(3, 7, 0),
    description: null,
    location: "Fitness Center",
    source_sub_account_id: "sa-personal",
    metadata: {},
  },
  {
    provider_event_id: "evt-9",
    provider_type: "google_calendar",
    title: "Client Call",
    start: isoOffset(3, 13, 0),
    end: isoOffset(3, 14, 0),
    description: "Acme Corp quarterly review",
    location: "Phone",
    source_sub_account_id: "sa-work-google",
    metadata: { tags: ["work", "client"] },
  },
  {
    provider_event_id: "evt-10",
    provider_type: "caldav",
    title: "Family Dinner",
    start: isoOffset(4, 18, 0),
    end: isoOffset(4, 20, 0),
    description: null,
    location: "Home",
    source_sub_account_id: "sa-personal",
    metadata: {},
  },
];

export const mockAgents: AgentSpec[] = [
  {
    name: "a_cal_conductor",
    display_name: "A-Cal Conductor",
    description: "Central orchestrator. Routes requests to specialists, maintains unified view.",
    system_prompt: "",
    tools: ["route_to_specialist", "unified_calendar_view", "list_sub_accounts"],
    default_tier: "versatile",
    can_negotiate: true,
    privacy_force_local: false,
    capabilities: ["orchestration", "routing", "unified_view", "swarm_coordination"],
  },
  {
    name: "a_cal_sync_agent",
    display_name: "Sync Agent",
    description: "Manages sub-account sync, provider health, rule evaluation.",
    system_prompt: "",
    tools: ["pull_provider_events", "evaluate_sync_rules"],
    default_tier: "micro",
    can_negotiate: false,
    privacy_force_local: false,
    capabilities: ["sync", "provider_health", "rule_evaluation"],
  },
  {
    name: "a_cal_schedule_agent",
    display_name: "Schedule Agent",
    description: "Scheduling intelligence: conflict resolution, finding slots, optimization.",
    system_prompt: "",
    tools: ["find_open_slots", "detect_conflicts", "propose_reschedule"],
    default_tier: "versatile",
    can_negotiate: true,
    privacy_force_local: false,
    capabilities: ["scheduling", "conflict_resolution", "optimization"],
  },
  {
    name: "a_cal_email_agent",
    display_name: "Email Agent",
    description: "Inbox triage, invite parsing, draft replies. Privacy-forced local.",
    system_prompt: "",
    tools: ["list_messages", "parse_invitation", "draft_reply"],
    default_tier: "standard",
    can_negotiate: false,
    privacy_force_local: true,
    capabilities: ["email_triage", "invite_parsing", "draft_replies"],
  },
  {
    name: "a_cal_negotiate_agent",
    display_name: "Negotiate Agent",
    description: "Negotiates meeting changes with other attendees' agents.",
    system_prompt: "",
    tools: ["propose_alternatives", "send_negotiation_email"],
    default_tier: "heavy",
    can_negotiate: true,
    privacy_force_local: false,
    capabilities: ["negotiation", "rescheduling", "p2p_protocol"],
  },
  {
    name: "a_cal_self_model_agent",
    display_name: "Self-Model Agent",
    description: "Maintains the user's self-model. Depth-gated, privacy-first.",
    system_prompt: "",
    tools: ["observe_events", "get_context", "search_facts"],
    default_tier: "complex",
    can_negotiate: false,
    privacy_force_local: true,
    capabilities: ["self_model", "fact_extraction", "context_injection"],
  },
];

export const mockConductorResponse = (message: string): ConductorResponse => {
  const lower = message.toLowerCase();
  let intent = "chat";
  let specialist = "a_cal_conductor";
  if (lower.includes("sync") || lower.includes("refresh")) {
    intent = "sync";
    specialist = "a_cal_sync_agent";
  } else if (lower.includes("schedule") || lower.includes("slot") || lower.includes("free")) {
    intent = "schedule";
    specialist = "a_cal_schedule_agent";
  } else if (lower.includes("email") || lower.includes("inbox")) {
    intent = "email";
    specialist = "a_cal_email_agent";
  } else if (lower.includes("negotiate") || lower.includes("reschedule")) {
    intent = "negotiate";
    specialist = "a_cal_negotiate_agent";
  }

  return {
    user_id: "local-dev-user",
    message,
    routing: {
      intent,
      specialist,
      tier: intent === "sync" ? "micro" : "versatile",
      force_local: intent === "email" || intent === "self_model",
      self_model_context: "",
      reasoning: `Mock routing: keyword match → ${intent}`,
    },
    response: `[Mock] I'd route this to the ${specialist.replace("a_cal_", "").replace("_agent", "")} agent. Connect the Python backend to get real agent responses.`,
    timestamp: new Date().toISOString(),
    standalone: true,
  };
};

export const mockModeConfig: ModeConfig = {
  mode: "pro",
  display_name: "Pro",
  description: "For power users. Plugins, advanced settings, per-task model overrides.",
  visible_panels: ["calendar", "command_bar", "chat_panel", "advanced_settings", "sub_accounts", "sync_rules", "self_model_settings"],
  visible_settings: ["model", "per_task_models", "theme", "notifications", "sub_account_visibility", "sync_mode", "self_model_depth", "proactive_suggestions"],
  default_sync_mode: "mirror_filter",
  per_task_model_routing: true,
  developer_studio: false,
  config_as_code: true,
  visual_builder: true,
  plugin_system: true,
  api_sdk: false,
  marketplace: true,
  default_self_model_depth: "attention_intent",
  default_proactive: true,
};

export const mockModelRouting: ModelRoutingConfig = {
  global_provider: "ollama",
  global_model: "llama3.2",
  per_task_overrides: {},
  privacy_force_local: true,
};
