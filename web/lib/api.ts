/** A-Cal API client — bridges the frontend to the Python backend.

All calls go through Next.js rewrites (/api/* → backend). In development
without a running backend, the client falls back to mock data so the UI is
fully explorable standalone.
 */

import type {
  SubAccount,
  ProviderConnection,
  UnifiedEvent,
  EmailMessage,
  ModeConfig,
  ModelRoutingConfig,
  AgentSpec,
  ConductorResponse,
  SelfModelDepth,
  SelfModelFact,
  SelfModelExport,
  NegotiationResult,
  SwarmNegotiation,
  MarketplaceItem,
  InstallRecord,
  Plugin,
  ConfigExport,
  ConfigImportResult,
  RuntimePlugin,
  CASModule,
  CASAgentSpec,
  SystemState,
  RoutingTrace,
  NervousSystemOverview,
  WorkflowDef,
  WorkflowRunResult,
  AtomStatus,
  BackendMode,
  SyncRule,
  RuleType,
  RuleField,
  AutonomyConfig,
  EmailIntegrationConfig,
  CommunityProfile,
  AnalyticsSummary,
  BusyTimesAnalysis,
  MeetingStats,
  FreeSlot,
  EventType,
  CalendarTool,
  ApiRouteInfo,
  AuthUser,
  FlagRecord,
  VerificationStatus,
} from "@/types";

const API_BASE = "/api/a-cal";

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json() as Promise<T>;
}

// --- Sub-accounts ----------------------------------------------------------

export const api = {
  async listSubAccounts(): Promise<SubAccount[]> {
    return fetchJson(`${API_BASE}/sub-accounts`);
  },

  async createSubAccount(data: {
    name: string;
    kind?: string;
    sync_mode?: string;
    is_main?: boolean;
    agent_enabled?: boolean;
  }): Promise<SubAccount> {
    return fetchJson(`${API_BASE}/sub-accounts`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /** Update a sub-account's settings (sync mode, agent enabled, visibility, etc.). */
  async updateSubAccount(subId: string, patch: {
    name?: string;
    sync_mode?: string;
    agent_enabled?: boolean;
    settings?: Record<string, unknown>;
  }): Promise<SubAccount> {
    return fetchJson(`${API_BASE}/sub-accounts/${subId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },

  /** Delete a sub-account and all its provider connections. */
  async deleteSubAccount(subId: string): Promise<{ status: string }> {
    return fetchJson(`${API_BASE}/sub-accounts/${subId}`, {
      method: "DELETE",
    });
  },

  // --- Provider connections -----------------------------------------------

  async listProviders(subAccountId: string): Promise<ProviderConnection[]> {
    return fetchJson(`${API_BASE}/providers?sub_account_id=${subAccountId}`);
  },

  async createProvider(data: {
    sub_account_id: string;
    provider_type: string;
    provider_account_id: string;
    display_name?: string;
    config?: Record<string, unknown>;
  }): Promise<ProviderConnection> {
    return fetchJson(`${API_BASE}/providers`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async listAllProviders(): Promise<ProviderConnection[]> {
    return fetchJson(`${API_BASE}/providers/all`);
  },

  async deleteProvider(providerId: string): Promise<{ status: string }> {
    return fetchJson(`${API_BASE}/providers/${providerId}`, {
      method: "DELETE",
    });
  },

  async triggerSync(subAccountId: string): Promise<Record<string, unknown>> {
    return fetchJson(`${API_BASE}/sync/trigger`, {
      method: "POST",
      body: JSON.stringify({ sub_account_id: subAccountId }),
    });
  },

  // --- Sync rules ----------------------------------------------------------

  async listSyncRules(subAccountId: string): Promise<SyncRule[]> {
    return fetchJson(`${API_BASE}/sync-rules?sub_account_id=${encodeURIComponent(subAccountId)}`);
  },

  async createSyncRule(data: {
    sub_account_id: string;
    rule_type: RuleType;
    field: RuleField;
    pattern: string;
    action?: Record<string, unknown>;
    priority?: number;
  }): Promise<{ id: string; sub_account_id: string }> {
    return fetchJson(`${API_BASE}/sync-rules`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  },

  async deleteSyncRule(ruleId: string): Promise<{ status: string; id: string }> {
    return fetchJson(`${API_BASE}/sync-rules/${ruleId}`, { method: "DELETE" });
  },

  // --- Unified calendar ----------------------------------------------------

  async getUnifiedCalendar(days = 7): Promise<UnifiedEvent[]> {
    return fetchJson(`${API_BASE}/calendar/unified?days=${days}`);
  },

  async createEvent(data: {
    title: string;
    start: string;
    end: string;
    description?: string;
    location?: string;
    source_sub_account_id?: string;
  }): Promise<UnifiedEvent> {
    return fetchJson(`${API_BASE}/calendar/events`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updateEvent(eventId: string, patch: Record<string, unknown>): Promise<UnifiedEvent> {
    return fetchJson(`${API_BASE}/calendar/events/${eventId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },

  async deleteEvent(eventId: string): Promise<{ status: string }> {
    return fetchJson(`${API_BASE}/calendar/events/${eventId}`, {
      method: "DELETE",
    });
  },

  async listEvents(days = 30): Promise<UnifiedEvent[]> {
    return fetchJson(`${API_BASE}/calendar/events?days=${days}`);
  },

  // --- Email ---------------------------------------------------------------

  async listEmailMessages(opts?: {
    subAccountId?: string;
    limit?: number;
  }): Promise<EmailMessage[]> {
    const params = new URLSearchParams();
    if (opts?.subAccountId) params.set("sub_account_id", opts.subAccountId);
    if (opts?.limit) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return fetchJson(`${API_BASE}/email/messages${qs ? `?${qs}` : ""}`);
  },

  async sendEmail(data: {
    provider_connection_id: string;
    to: string[];
    subject: string;
    body_text: string;
  }): Promise<{ status: string; provider_message_id: string }> {
    return fetchJson(`${API_BASE}/email/send`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /** Scan emails for scheduling-related content and return suggestions.
   *  The depth field reflects the user's email integration depth setting,
   *  which gates whether draft replies and auto-actions are included. */
  async scanEmailForSchedule(): Promise<{
    detections: Array<Record<string, unknown>>;
    suggestions: Array<Record<string, unknown>>;
    summary: string;
    stats: Record<string, number>;
    depth: string;
    agent_actions_enabled: boolean;
    autonomous_enabled: boolean;
  }> {
    return fetchJson(`${API_BASE}/email/scan-schedule`, {
      method: "POST",
    });
  },

  // --- Conductor chat ------------------------------------------------------

  async sendToConductor(message: string): Promise<ConductorResponse> {
    return fetchJson(`${API_BASE}/conductor/chat`, {
      method: "POST",
      body: JSON.stringify({ message }),
    });
  },

  // --- Agents --------------------------------------------------------------

  async listAgents(): Promise<AgentSpec[]> {
    return fetchJson(`${API_BASE}/agents`);
  },

  // --- Settings ------------------------------------------------------------

  async getMode(): Promise<ModeConfig> {
    return fetchJson(`${API_BASE}/settings/mode`);
  },

  async setMode(mode: string): Promise<ModeConfig> {
    return fetchJson(`${API_BASE}/settings/mode`, {
      method: "POST",
      body: JSON.stringify({ mode }),
    });
  },

  async getModelRouting(): Promise<ModelRoutingConfig> {
    return fetchJson(`${API_BASE}/settings/model-routing`);
  },

  async setModelRouting(config: ModelRoutingConfig): Promise<ModelRoutingConfig> {
    return fetchJson(`${API_BASE}/settings/model-routing`, {
      method: "POST",
      body: JSON.stringify(config),
    });
  },

  async getAutonomy(): Promise<AutonomyConfig> {
    return fetchJson(`${API_BASE}/settings/autonomy`);
  },

  async setAutonomy(config: AutonomyConfig): Promise<AutonomyConfig> {
    return fetchJson(`${API_BASE}/settings/autonomy`, {
      method: "POST",
      body: JSON.stringify(config),
    });
  },

  async getEmailSettings(): Promise<EmailIntegrationConfig> {
    return fetchJson(`${API_BASE}/settings/email`);
  },

  async setEmailSettings(config: Partial<EmailIntegrationConfig>): Promise<EmailIntegrationConfig> {
    return fetchJson(`${API_BASE}/settings/email`, {
      method: "POST",
      body: JSON.stringify(config),
    });
  },

  async getCommunityProfile(): Promise<CommunityProfile> {
    return fetchJson(`${API_BASE}/marketplace/community/profile`);
  },

  async getSelfModelSettings(): Promise<SelfModelDepth> {
    return fetchJson(`${API_BASE}/settings/self-model`);
  },

  async setSelfModelSettings(settings: SelfModelDepth): Promise<SelfModelDepth> {
    return fetchJson(`${API_BASE}/settings/self-model`, {
      method: "POST",
      body: JSON.stringify(settings),
    });
  },

  /** Get the user's IANA timezone (e.g. America/Chicago). */
  async getTimezone(): Promise<string> {
    const data = await fetchJson(`${API_BASE}/settings/timezone`) as { timezone: string };
    return data.timezone;
  },

  /** Set the user's IANA timezone. */
  async setTimezone(timezone: string): Promise<string> {
    const data = await fetchJson(`${API_BASE}/settings/timezone`, {
      method: "POST",
      body: JSON.stringify({ timezone }),
    }) as { timezone: string };
    return data.timezone;
  },

  // --- Self-model facts (transparency view) ---------------------------------

  async listSelfModelFacts(category?: string): Promise<SelfModelFact[]> {
    const params = category ? `?category=${encodeURIComponent(category)}` : "";
    return fetchJson(`${API_BASE}/self-model/facts${params}`);
  },

  async searchSelfModelFacts(query: string, limit?: number): Promise<SelfModelFact[]> {
    const params = new URLSearchParams({ q: query });
    if (limit) params.set("limit", String(limit));
    return fetchJson(`${API_BASE}/self-model/facts/search?${params}`);
  },

  async deleteSelfModelFact(factId: string): Promise<{ status: string; fact_id: string }> {
    return fetchJson(`${API_BASE}/self-model/facts/${encodeURIComponent(factId)}`, {
      method: "DELETE",
    });
  },

  async clearAllSelfModelFacts(): Promise<{ facts_removed: number }> {
    return fetchJson(`${API_BASE}/self-model/facts`, {
      method: "DELETE",
    });
  },

  async editSelfModelFact(factId: string, content: string): Promise<SelfModelFact> {
    return fetchJson(`${API_BASE}/self-model/facts/${encodeURIComponent(factId)}`, {
      method: "PATCH",
      body: JSON.stringify({ content }),
    });
  },

  async exportSelfModelFacts(): Promise<SelfModelExport> {
    return fetchJson(`${API_BASE}/self-model/export`);
  },

  async getProactiveSuggestions(limit?: number): Promise<Array<{
    fact_id: string;
    content: string;
    category: string;
    priority: number;
    confidence: number;
  }>> {
    const qs = limit ? `?limit=${limit}` : "";
    return fetchJson(`${API_BASE}/self-model/suggestions${qs}`);
  },

  // --- LLM settings -------------------------------------------------------

  async getLLMEnabled(): Promise<{ enabled: boolean }> {
    return fetchJson(`${API_BASE}/settings/llm-enabled`);
  },

  async setLLMEnabled(enabled: boolean): Promise<{ enabled: boolean }> {
    return fetchJson(`${API_BASE}/settings/llm-enabled`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    });
  },

  async getOllamaStatus(): Promise<{ available: boolean; models: string[] }> {
    return fetchJson(`${API_BASE}/settings/ollama-status`);
  },

  async getBackendMode(): Promise<{ mode: string }> {
    return fetchJson(`${API_BASE}/settings/backend-mode`);
  },

  async setBackendMode(mode: BackendMode): Promise<{ mode: string }> {
    return fetchJson(`${API_BASE}/settings/backend-mode`, {
      method: "POST",
      body: JSON.stringify({ mode }),
    });
  },

  async getAtomStatus(): Promise<AtomStatus> {
    return fetchJson(`${API_BASE}/settings/atom-status`);
  },

  async getApiKeys(): Promise<Record<string, string>> {
    return fetchJson(`${API_BASE}/settings/api-keys`);
  },

  async setApiKeys(keys: Record<string, string>): Promise<Record<string, string>> {
    return fetchJson(`${API_BASE}/settings/api-keys`, {
      method: "POST",
      body: JSON.stringify({ keys }),
    });
  },

  // --- Nervous System / CAS ---

  async getNervousSystemOverview(): Promise<NervousSystemOverview> {
    return fetchJson(`${API_BASE}/nervous-system/overview`);
  },

  async getNervousSystemAgents(): Promise<Array<AgentSpec & { cas?: CASModule; is_bio_mimetic?: boolean }>> {
    return fetchJson(`${API_BASE}/nervous-system/agents`);
  },

  async getNervousSystemState(): Promise<SystemState> {
    return fetchJson(`${API_BASE}/nervous-system/state`);
  },

  async routeThroughNervousSystem(signal: string): Promise<RoutingTrace> {
    return fetchJson(`${API_BASE}/nervous-system/route`, {
      method: "POST",
      body: JSON.stringify({ signal }),
    });
  },

  // --- Analytics (zero-calendar integration) ---------------------------------

  async getAnalyticsSummary(days = 30): Promise<AnalyticsSummary> {
    return fetchJson(`${API_BASE}/analytics/summary?days=${days}`);
  },

  async getBusyTimes(days = 30): Promise<BusyTimesAnalysis> {
    return fetchJson(`${API_BASE}/analytics/busy-times?days=${days}`);
  },

  async getMeetingStats(days = 30): Promise<MeetingStats> {
    return fetchJson(`${API_BASE}/analytics/meeting-stats?days=${days}`);
  },

  async getFreeSlots(startDate: string, endDate: string, minDuration = 30): Promise<{ free_slots: FreeSlot[]; total: number }> {
    const params = new URLSearchParams({ start_date: startDate, end_date: endDate, min_duration: String(minDuration) });
    return fetchJson(`${API_BASE}/analytics/free-slots?${params}`);
  },

  async suggestReschedule(eventId: string, lookAheadDays = 14): Promise<Record<string, unknown>> {
    return fetchJson(`${API_BASE}/analytics/suggest-reschedule`, {
      method: "POST",
      body: JSON.stringify({ event_id: eventId, look_ahead_days: lookAheadDays }),
    });
  },

  // --- Event Types (cal.com integration) ------------------------------------

  async listEventTypes(): Promise<EventType[]> {
    return fetchJson(`${API_BASE}/event-types`);
  },

  async createEventType(data: Partial<EventType>): Promise<EventType> {
    return fetchJson(`${API_BASE}/event-types`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async deleteEventType(id: string): Promise<{ deleted: string }> {
    return fetchJson(`${API_BASE}/event-types/${id}`, { method: "DELETE" });
  },

  async getAvailabilitySchedule(): Promise<Record<string, unknown>> {
    return fetchJson(`${API_BASE}/availability/schedule`);
  },

  async getCalendarTools(): Promise<{ tools: CalendarTool[]; count: number }> {
    return fetchJson(`${API_BASE}/calendar-tools`);
  },

  async getNervousSystemMemories(limit: number = 10): Promise<Array<Record<string, unknown>>> {
    return fetchJson(`${API_BASE}/nervous-system/memories?limit=${limit}`);
  },

  async assessUserState(events: Array<Record<string, unknown>>): Promise<Record<string, unknown>> {
    return fetchJson(`${API_BASE}/nervous-system/assess-user-state`, {
      method: "POST",
      body: JSON.stringify({ events }),
    });
  },

  async verifyBinding(events: Array<Record<string, unknown>>, subAccounts: Array<Record<string, unknown>>): Promise<Record<string, unknown>> {
    return fetchJson(`${API_BASE}/nervous-system/verify-binding`, {
      method: "POST",
      body: JSON.stringify({ events, sub_accounts: subAccounts }),
    });
  },

  async getCASAgents(): Promise<CASAgentSpec[]> {
    return fetchJson(`${API_BASE}/nervous-system/cas-agents`);
  },

};

// --- Swarm negotiation -----------------------------------------------------

export const swarmApi = {
  async negotiate(claimA: Record<string, unknown>, claimB: Record<string, unknown>): Promise<NegotiationResult> {
    return fetchJson(`${API_BASE}/swarm/negotiate`, {
      method: "POST",
      body: JSON.stringify({ claim_a: claimA, claim_b: claimB }),
    });
  },

  async listNegotiations(): Promise<SwarmNegotiation[]> {
    return fetchJson(`${API_BASE}/swarm/negotiations`);
  },

  async getNegotiation(id: string): Promise<SwarmNegotiation> {
    return fetchJson(`${API_BASE}/swarm/negotiations/${id}`);
  },

  async detectConflicts(events: Array<{ title: string; source_sub_account_id: string; start: string; end: string }>): Promise<{ conflict_count: number; conflicts: Array<{ event_a: Record<string, string>; event_b: Record<string, string> }> }> {
    return fetchJson(`${API_BASE}/swarm/detect-conflicts`, {
      method: "POST",
      body: JSON.stringify({ events }),
    });
  },
};

// --- Marketplace ------------------------------------------------------------

export const marketplaceApi = {
  async listItems(itemType?: string, tag?: string): Promise<MarketplaceItem[]> {
    const params = new URLSearchParams();
    if (itemType) params.set("item_type", itemType);
    if (tag) params.set("tag", tag);
    const qs = params.toString();
    return fetchJson(`${API_BASE}/marketplace/items${qs ? `?${qs}` : ""}`);
  },

  async getItem(id: string): Promise<MarketplaceItem> {
    return fetchJson(`${API_BASE}/marketplace/items/${id}`);
  },

  async search(q: string): Promise<MarketplaceItem[]> {
    return fetchJson(`${API_BASE}/marketplace/search?q=${encodeURIComponent(q)}`);
  },

  async publish(body: Record<string, unknown>): Promise<MarketplaceItem> {
    return fetchJson(`${API_BASE}/marketplace/items`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async install(itemId: string): Promise<InstallRecord> {
    return fetchJson(`${API_BASE}/marketplace/items/${itemId}/install`, { method: "POST" });
  },

  async getInstalls(): Promise<InstallRecord[]> {
    return fetchJson(`${API_BASE}/marketplace/installs`);
  },

  async remix(itemId: string, body: Record<string, unknown>): Promise<MarketplaceItem> {
    return fetchJson(`${API_BASE}/marketplace/items/${itemId}/remix`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async getRemixes(itemId: string): Promise<MarketplaceItem[]> {
    return fetchJson(`${API_BASE}/marketplace/items/${itemId}/remixes`);
  },

  async getRemixChain(itemId: string): Promise<Array<{ item_id: string; name: string; author: string }>> {
    return fetchJson(`${API_BASE}/marketplace/items/${itemId}/remix-chain`);
  },

  async rate(itemId: string, stars: number): Promise<MarketplaceItem> {
    return fetchJson(`${API_BASE}/marketplace/items/${itemId}/rate`, {
      method: "POST",
      body: JSON.stringify({ stars }),
    });
  },

  // --- Registry: portable export/import + remote browsing -------------------

  /** Get the local registry manifest (catalog of all items, no full configs). */
  async getRegistryManifest(): Promise<Record<string, unknown>> {
    return fetchJson(`${API_BASE}/marketplace/registry/manifest`);
  },

  /** Export marketplace items as a portable JSON bundle. Empty ids = all items. */
  async exportBundle(itemIds?: string[]): Promise<Record<string, unknown>> {
    return fetchJson(`${API_BASE}/marketplace/export`, {
      method: "POST",
      body: JSON.stringify({ item_ids: itemIds ?? [] }),
    });
  },

  /** Import items from a JSON bundle string. Returns import summary. */
  async importBundle(bundleJson: string): Promise<{
    imported: number;
    skipped: number;
    errors: string[];
    exported_by: string;
    exported_at: string;
  }> {
    return fetchJson(`${API_BASE}/marketplace/import`, {
      method: "POST",
      body: JSON.stringify({ bundle_json: bundleJson }),
    });
  },

  /** Fetch a remote registry's manifest for browsing. */
  async browseRemoteRegistry(registryUrl: string): Promise<Record<string, unknown>> {
    return fetchJson(`${API_BASE}/marketplace/registry/browse`, {
      method: "POST",
      body: JSON.stringify({ registry_url: registryUrl }),
    });
  },

  /** Pull a specific item from a remote registry and publish it locally. */
  async pullFromRemoteRegistry(
    registryUrl: string,
    itemId: string,
  ): Promise<{ published: boolean; item: MarketplaceItem; message?: string }> {
    return fetchJson(`${API_BASE}/marketplace/registry/pull`, {
      method: "POST",
      body: JSON.stringify({ registry_url: registryUrl, item_id: itemId }),
    });
  },

  // --- Trust & Moderation ---------------------------------------------------

  /** Flag a marketplace item for moderation. */
  async flagItem(itemId: string, reason: string): Promise<FlagRecord> {
    return fetchJson(`${API_BASE}/marketplace/items/${itemId}/flag`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  },

  /** Get all flags for a marketplace item. */
  async getFlags(itemId: string): Promise<FlagRecord[]> {
    return fetchJson(`${API_BASE}/marketplace/items/${itemId}/flags`);
  },

  /** Resolve a flag (moderator action). */
  async resolveFlag(flagId: string): Promise<FlagRecord> {
    return fetchJson(`${API_BASE}/marketplace/flags/${flagId}/resolve`, {
      method: "POST",
    });
  },

  /** Verify a marketplace item (moderator/admin action). */
  async verifyItem(itemId: string): Promise<MarketplaceItem> {
    return fetchJson(`${API_BASE}/marketplace/items/${itemId}/verify`, {
      method: "POST",
    });
  },

  /** Get trust info (score, verification status, flag count) for an item. */
  async getTrustInfo(itemId: string): Promise<{
    item_id: string;
    trust_score: number;
    verification_status: VerificationStatus;
    flag_count: number;
    content_hash: string;
  }> {
    return fetchJson(`${API_BASE}/marketplace/items/${itemId}/trust`);
  },
};

// --- Developer --------------------------------------------------------------

export const developerApi = {
  // Plugins
  async listPlugins(pluginType?: string): Promise<Plugin[]> {
    const qs = pluginType ? `?plugin_type=${pluginType}` : "";
    return fetchJson(`${API_BASE}/developer/plugins${qs}`);
  },

  async registerPlugin(body: Record<string, unknown>): Promise<Plugin> {
    return fetchJson(`${API_BASE}/developer/plugins`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async deletePlugin(id: string): Promise<{ deleted: boolean }> {
    return fetchJson(`${API_BASE}/developer/plugins/${id}`, { method: "DELETE" });
  },

  async enablePlugin(id: string): Promise<Plugin> {
    return fetchJson(`${API_BASE}/developer/plugins/${id}/enable`, { method: "POST" });
  },

  async disablePlugin(id: string): Promise<Plugin> {
    return fetchJson(`${API_BASE}/developer/plugins/${id}/disable`, { method: "POST" });
  },

  async updatePluginConfig(id: string, config: Record<string, unknown>): Promise<Plugin> {
    return fetchJson(`${API_BASE}/developer/plugins/${id}/config`, {
      method: "PATCH",
      body: JSON.stringify({ config }),
    });
  },

  // Agent specs
  async listAgentSpecs(): Promise<AgentSpec[]> {
    return fetchJson(`${API_BASE}/developer/agents`);
  },

  async createAgentSpec(body: Record<string, unknown>): Promise<AgentSpec> {
    return fetchJson(`${API_BASE}/developer/agents`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async updateAgentSpec(name: string, body: Record<string, unknown>): Promise<AgentSpec> {
    return fetchJson(`${API_BASE}/developer/agents/${name}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },

  async deleteAgentSpec(name: string): Promise<{ deleted: boolean }> {
    return fetchJson(`${API_BASE}/developer/agents/${name}`, { method: "DELETE" });
  },

  // Config-as-code
  async exportConfig(): Promise<ConfigExport> {
    return fetchJson(`${API_BASE}/developer/config/export`, {
      method: "POST",
      body: JSON.stringify({ include_sub_accounts: true, include_plugins: true, include_custom_agents: true }),
    });
  },

  async importConfig(config: Record<string, unknown>): Promise<ConfigImportResult> {
    return fetchJson(`${API_BASE}/developer/config/import`, {
      method: "POST",
      body: JSON.stringify({ config }),
    });
  },

  // Plugin runtime (loaded code, not just specs)
  async listRuntimePlugins(): Promise<RuntimePlugin[]> {
    return fetchJson(`${API_BASE}/developer/plugins/runtime/list`);
  },

  async scanRuntimePlugins(): Promise<{
    scanned: number;
    loaded: number;
    failed: number;
    plugins: RuntimePlugin[];
  }> {
    return fetchJson(`${API_BASE}/developer/plugins/runtime/scan`, { method: "POST" });
  },

  async reloadRuntimePlugin(pluginId: string): Promise<RuntimePlugin> {
    return fetchJson(`${API_BASE}/developer/plugins/runtime/${pluginId}/reload`, { method: "POST" });
  },

  async enableRuntimePlugin(pluginId: string): Promise<{ status: string }> {
    return fetchJson(`${API_BASE}/developer/plugins/runtime/${pluginId}/enable`, { method: "POST" });
  },

  async disableRuntimePlugin(pluginId: string): Promise<{ status: string }> {
    return fetchJson(`${API_BASE}/developer/plugins/runtime/${pluginId}/disable`, { method: "POST" });
  },

  async listRuntimeHooks(): Promise<{ hooks: string[] }> {
    return fetchJson(`${API_BASE}/developer/plugins/runtime/hooks`);
  },

  // Workflows — save, load, run
  async listWorkflows(): Promise<WorkflowDef[]> {
    return fetchJson(`${API_BASE}/developer/workflows`);
  },

  async saveWorkflow(workflow: Omit<WorkflowDef, "created_at" | "updated_at">): Promise<WorkflowDef> {
    return fetchJson(`${API_BASE}/developer/workflows`, {
      method: "POST",
      body: JSON.stringify(workflow),
    });
  },

  async getWorkflow(id: string): Promise<WorkflowDef> {
    return fetchJson(`${API_BASE}/developer/workflows/${id}`);
  },

  async deleteWorkflow(id: string): Promise<{ status: string; id: string }> {
    return fetchJson(`${API_BASE}/developer/workflows/${id}`, { method: "DELETE" });
  },

  async runWorkflow(
    workflow: { name: string; description: string; nodes: WorkflowDef["nodes"]; trigger: string; version: string },
    initialMessage?: string,
  ): Promise<WorkflowRunResult> {
    return fetchJson(`${API_BASE}/developer/workflows/run`, {
      method: "POST",
      body: JSON.stringify({ ...workflow, initial_message: initialMessage || "" }),
    });
  },

  async runSavedWorkflow(id: string, initialMessage?: string): Promise<WorkflowRunResult> {
    return fetchJson(`${API_BASE}/developer/workflows/${id}/run`, {
      method: "POST",
      body: JSON.stringify({ initial_message: initialMessage || "" }),
    });
  },

  // API Explorer — list all registered routes
  async getApiRoutes(): Promise<ApiRouteInfo[]> {
    return fetchJson(`${API_BASE}/developer/api-routes`);
  },
};

// --- OAuth ----------------------------------------------------------------

export interface OAuthStartResponse {
  authorization_url: string;
  provider_id: string;
  provider_type: string;
  redirect_uri: string;
}

export const oauthApi = {
  /** Initiate an OAuth flow for a provider connection.

  Returns the provider's authorization URL. The caller should redirect
  the user to it (window.location.href = url) so they can authorize.
  */
  async start(providerId: string): Promise<OAuthStartResponse> {
    return fetchJson(`${API_BASE}/providers/${providerId}/oauth/start`);
  },
};

// --- Health ----------------------------------------------------------------

export interface HealthResponse {
  status: string;
  mode: string;
  version: string;
  database: string;
}

export const healthApi = {
  /** Check backend health, including database backend type. */
  async check(): Promise<HealthResponse> {
    const res = await fetch("/api/health");
    if (!res.ok) throw new Error(`health check failed: ${res.status}`);
    return res.json() as Promise<HealthResponse>;
  },
};

// --- Auth ------------------------------------------------------------------

export const authApi = {
  /** Check if the user has an active session.
   *
   * Returns an object with either `user` (authenticated), `user: null`
   * (backend reachable but no session), or `backendDown: true` (backend
   * unreachable — fall through to demo mode).
   */
  async me(): Promise<{ user: AuthUser | null; backendDown?: boolean }> {
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        credentials: "include",
      });
      if (!res.ok) return { user: null };
      const data = await res.json();
      return { user: data ?? null };
    } catch {
      return { user: null, backendDown: true };
    }
  },

  async login(email: string, password: string): Promise<AuthUser> {
    return fetchJson(`${API_BASE}/auth/login`, {
      method: "POST",
      body: JSON.stringify({ email, password }),
      credentials: "include",
    });
  },

  async register(
    email: string,
    password: string,
    displayName?: string,
  ): Promise<AuthUser> {
    return fetchJson(`${API_BASE}/auth/register`, {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        display_name: displayName ?? undefined,
      }),
      credentials: "include",
    });
  },

  async logout(): Promise<void> {
    await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
  },

  /** Auto-login as the demo user (standalone/dev mode only). */
  async demoLogin(): Promise<AuthUser> {
    return fetchJson(`${API_BASE}/auth/demo-login`, {
      method: "POST",
      credentials: "include",
    });
  },
};
