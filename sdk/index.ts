/**
 * A-Cal SDK — TypeScript client for the A-Cal REST API.
 *
 * @example
 * ```typescript
 * import { ACalClient } from "@a-cal/sdk";
 *
 * const client = new ACalClient({ baseUrl: "http://localhost:8000/api/a-cal" });
 *
 * // Talk to the conductor
 * const result = await client.conductor.chat("Schedule lunch tomorrow at noon");
 *
 * // Manage sub-accounts
 * const subs = await client.subAccounts.list();
 * await client.subAccounts.create({ name: "Work Google", kind: "calendar" });
 *
 * // Configure LLM
 * await client.settings.setLLMEnabled(true);
 * await client.settings.setApiKeys({ openai: "sk-..." });
 *
 * // Manage calendar events
 * const events = await client.calendar.listEvents(30);
 * await client.calendar.createEvent({ title: "Team sync", start: "2026-07-13T10:00:00Z" });
 *
 * // Scan emails for scheduling suggestions
 * const scan = await client.email.scanForSchedule();
 *
 * // Trigger a sync
 * await client.sync.trigger("sub-account-id");
 *
 * // Manage self-model facts
 * const facts = await client.selfModel.listFacts();
 * await client.selfModel.editFact("fact-id", { content: "Updated" });
 *
 * // Plugin runtime (Developer mode)
 * const plugins = await client.developer.listRuntimePlugins();
 * await client.developer.scanRuntimePlugins();
 * ```
 */

/** Configuration for the A-Cal client. */
export interface ACalClientConfig {
  baseUrl: string;
  apiKey?: string;
  fetch?: typeof fetch;
}

/** Sub-account creation parameters. */
export interface CreateSubAccountParams {
  name: string;
  kind?: string;
  sync_mode?: string;
  is_main?: boolean;
  agent_enabled?: boolean;
}

/** Provider connection creation parameters. */
export interface CreateProviderParams {
  sub_account_id: string;
  provider_type: string;
  provider_account_id: string;
  display_name?: string;
}

/** Model routing configuration. */
export interface ModelRoutingConfig {
  global_provider: string;
  global_model: string;
  per_task_overrides?: Record<string, string>;
  privacy_force_local?: boolean;
}

/** Conductor chat response. */
export interface ConductorResponse {
  response: string;
  agent?: string;
  routing_decision?: Record<string, unknown>;
  actions_taken?: unknown[];
}

/** A generic JSON response type. */
type Json = Record<string, unknown>;

/** Internal fetch wrapper. */
async function request<T>(
  url: string,
  options: RequestInit,
  fetchFn: typeof fetch
): Promise<T> {
  const res = await fetchFn(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => res.statusText);
    throw new Error(`A-Cal API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

/** A-Cal SDK client. */
export class ACalClient {
  private baseUrl: string;
  private apiKey: string | undefined;
  private fetchFn: typeof fetch;

  /** Sub-account management API. */
  readonly subAccounts: {
    list: () => Promise<Json[]>;
    create: (params: CreateSubAccountParams) => Promise<Json>;
    update: (id: string, patch: Partial<CreateSubAccountParams>) => Promise<Json>;
    delete: (id: string) => Promise<void>;
  };

  /** Provider connection management API. */
  readonly providers: {
    list: (subAccountId?: string) => Promise<Json[]>;
    listAll: () => Promise<Json[]>;
    create: (params: CreateProviderParams) => Promise<Json>;
    update: (id: string, patch: Json) => Promise<Json>;
    delete: (id: string) => Promise<void>;
  };

  /** Calendar API. */
  readonly calendar: {
    unified: (days?: number) => Promise<Json[]>;
    listEvents: (days?: number) => Promise<Json[]>;
    createEvent: (event: Json) => Promise<Json>;
    updateEvent: (id: string, patch: Json) => Promise<Json>;
    deleteEvent: (id: string) => Promise<{ status: string }>;
  };

  /** Sync engine API. */
  readonly sync: {
    trigger: (subAccountId: string) => Promise<Json>;
    listRules: () => Promise<Json[]>;
    createRule: (rule: Json) => Promise<Json>;
  };

  /** Conductor (agent chat) API. */
  readonly conductor: {
    chat: (message: string) => Promise<ConductorResponse>;
  };

  /** Agent API. */
  readonly agents: {
    list: () => Promise<Json[]>;
  };

  /** Email API. */
  readonly email: {
    listMessages: (limit?: number) => Promise<Json[]>;
    send: (params: Json) => Promise<Json>;
    scanForSchedule: () => Promise<Json>;
  };

  /** Settings API. */
  readonly settings: {
    getMode: () => Promise<Json>;
    setMode: (mode: string) => Promise<Json>;
    getModelRouting: () => Promise<ModelRoutingConfig>;
    setModelRouting: (config: ModelRoutingConfig) => Promise<ModelRoutingConfig>;
    getLLMEnabled: () => Promise<{ enabled: boolean }>;
    setLLMEnabled: (enabled: boolean) => Promise<{ enabled: boolean }>;
    getOllamaStatus: () => Promise<{ available: boolean; models: string[] }>;
    getApiKeys: () => Promise<Record<string, string>>;
    setApiKeys: (keys: Record<string, string>) => Promise<Record<string, string>>;
    getSelfModel: () => Promise<Json>;
    setSelfModel: (settings: Json) => Promise<Json>;
    getTimezone: () => Promise<{ timezone: string }>;
    setTimezone: (timezone: string) => Promise<{ timezone: string }>;
  };

  /** Self-model facts API. */
  readonly selfModel: {
    listFacts: (category?: string, depth?: string) => Promise<Json[]>;
    searchFacts: (q: string) => Promise<Json[]>;
    deleteFact: (factId: string) => Promise<{ deleted: boolean }>;
    clearAllFacts: () => Promise<{ cleared: boolean }>;
    editFact: (factId: string, patch: Json) => Promise<Json>;
    export: () => Promise<Json>;
    suggestions: (limit?: number) => Promise<Json[]>;
  };

  /** Swarm negotiation API. */
  readonly swarm: {
    negotiate: (claimA: Json, claimB: Json) => Promise<Json>;
    list: () => Promise<Json[]>;
    get: (id: string) => Promise<Json>;
    detectConflicts: (events: Json[]) => Promise<Json>;
  };

  /** Nervous system (CAS bio-mimetic architecture) API. */
  readonly nervousSystem: {
    overview: () => Promise<Json>;
    agents: () => Promise<Json[]>;
    state: () => Promise<Json>;
    route: (message: string) => Promise<Json>;
    memories: () => Promise<Json[]>;
    assessUserState: (message: string) => Promise<Json>;
    casAgents: () => Promise<Json[]>;
  };

  /** Marketplace API. */
  readonly marketplace: {
    list: (itemType?: string, tag?: string) => Promise<Json[]>;
    get: (id: string) => Promise<Json>;
    search: (q: string) => Promise<Json[]>;
    publish: (item: Json) => Promise<Json>;
    install: (id: string) => Promise<Json>;
    listInstalls: () => Promise<Json[]>;
    remix: (id: string, body: Json) => Promise<Json>;
    getRemixes: (id: string) => Promise<Json[]>;
    getRemixChain: (id: string) => Promise<Json[]>;
    rate: (id: string, stars: number) => Promise<Json>;
    // Registry: portable export/import + remote browsing
    getRegistryManifest: () => Promise<Json>;
    exportBundle: (itemIds?: string[]) => Promise<Json>;
    importBundle: (bundleJson: string) => Promise<Json>;
    browseRemoteRegistry: (registryUrl: string) => Promise<Json>;
    pullFromRemoteRegistry: (registryUrl: string, itemId: string) => Promise<Json>;
  };

  /** Developer API. */
  readonly developer: {
    listPlugins: (type?: string) => Promise<Json[]>;
    registerPlugin: (body: Json) => Promise<Json>;
    deletePlugin: (id: string) => Promise<void>;
    enablePlugin: (id: string) => Promise<Json>;
    disablePlugin: (id: string) => Promise<Json>;
    updatePluginConfig: (id: string, config: Json) => Promise<Json>;
    listAgentSpecs: () => Promise<Json[]>;
    createAgentSpec: (body: Json) => Promise<Json>;
    updateAgentSpec: (name: string, body: Json) => Promise<Json>;
    deleteAgentSpec: (name: string) => Promise<void>;
    exportConfig: () => Promise<Json>;
    importConfig: (config: Json) => Promise<Json>;
    // Plugin runtime (loaded code from ~/.a-cal/plugins/)
    listRuntimePlugins: () => Promise<Json[]>;
    scanRuntimePlugins: () => Promise<Json>;
    reloadRuntimePlugin: (pluginId: string) => Promise<Json>;
    enableRuntimePlugin: (pluginId: string) => Promise<Json>;
    disableRuntimePlugin: (pluginId: string) => Promise<Json>;
    listRuntimeHooks: () => Promise<{ hooks: string[] }>;
  };

  /** OAuth flow API. */
  readonly oauth: {
    start: (providerId: string) => Promise<Json>;
  };

  /**
   * Create a new A-Cal client.
   * @param config - Client configuration with base URL and optional API key.
   */
  constructor(config: ACalClientConfig) {
    this.baseUrl = config.baseUrl.replace(/\/$/, "");
    this.apiKey = config.apiKey;
    this.fetchFn = config.fetch ?? fetch;

    const headers = (): HeadersInit =>
      this.apiKey ? { Authorization: `Bearer ${this.apiKey}` } : {};

    const get = <T>(path: string): Promise<T> =>
      request<T>(`${this.baseUrl}${path}`, { headers: headers() }, this.fetchFn);
    const post = <T>(path: string, body?: unknown): Promise<T> =>
      request<T>(
        `${this.baseUrl}${path}`,
        { method: "POST", body: body ? JSON.stringify(body) : undefined, headers: headers() },
        this.fetchFn
      );
    const patch = <T>(path: string, body?: unknown): Promise<T> =>
      request<T>(
        `${this.baseUrl}${path}`,
        { method: "PATCH", body: body ? JSON.stringify(body) : undefined, headers: headers() },
        this.fetchFn
      );
    const del = <T>(path: string): Promise<T> =>
      request<T>(`${this.baseUrl}${path}`, { method: "DELETE", headers: headers() }, this.fetchFn);

    this.subAccounts = {
      list: () => get<Json[]>("/sub-accounts"),
      create: (p) => post<Json>("/sub-accounts", p),
      update: (id, patchData) => patch<Json>(`/sub-accounts/${id}`, patchData),
      delete: (id) => del<void>(`/sub-accounts/${id}`),
    };

    this.providers = {
      list: (subId) => get<Json[]>(`/providers${subId ? `?sub_account_id=${subId}` : ""}`),
      listAll: () => get<Json[]>("/providers/all"),
      create: (p) => post<Json>("/providers", p),
      update: (id, patchData) => patch<Json>(`/providers/${id}`, patchData),
      delete: (id) => del<void>(`/providers/${id}`),
    };

    this.calendar = {
      unified: (days = 7) => get<Json[]>(`/calendar/unified?days=${days}`),
      listEvents: (days = 30) => get<Json[]>(`/calendar/events?days=${days}`),
      createEvent: (event) => post<Json>("/calendar/events", event),
      updateEvent: (id, patchData) => patch<Json>(`/calendar/events/${id}`, patchData),
      deleteEvent: (id) => del<{ status: string }>(`/calendar/events/${id}`),
    };

    this.sync = {
      trigger: (subAccountId) => post<Json>("/sync/trigger", { sub_account_id: subAccountId }),
      listRules: () => get<Json[]>("/sync-rules"),
      createRule: (rule) => post<Json>("/sync-rules", rule),
    };

    this.conductor = {
      chat: (message) => post<ConductorResponse>("/conductor/chat", { message }),
    };

    this.agents = {
      list: () => get<Json[]>("/agents"),
    };

    this.email = {
      listMessages: (limit = 50) => get<Json[]>(`/email/messages?limit=${limit}`),
      send: (params) => post<Json>("/email/send", params),
      scanForSchedule: () => post<Json>("/email/scan-schedule"),
    };

    this.settings = {
      getMode: () => get<Json>("/settings/mode"),
      setMode: (mode) => post<Json>("/settings/mode", { mode }),
      getModelRouting: () => get<ModelRoutingConfig>("/settings/model-routing"),
      setModelRouting: (config) => post<ModelRoutingConfig>("/settings/model-routing", config),
      getLLMEnabled: () => get<{ enabled: boolean }>("/settings/llm-enabled"),
      setLLMEnabled: (enabled) => post<{ enabled: boolean }>("/settings/llm-enabled", { enabled }),
      getOllamaStatus: () => get<{ available: boolean; models: string[] }>("/settings/ollama-status"),
      getApiKeys: () => get<Record<string, string>>("/settings/api-keys"),
      setApiKeys: (keys) => post<Record<string, string>>("/settings/api-keys", { keys }),
      getSelfModel: () => get<Json>("/settings/self-model"),
      setSelfModel: (s) => post<Json>("/settings/self-model", s),
      getTimezone: () => get<{ timezone: string }>("/settings/timezone"),
      setTimezone: (tz) => post<{ timezone: string }>("/settings/timezone", { timezone: tz }),
    };

    this.selfModel = {
      listFacts: (category, depth) => {
        const params = new URLSearchParams();
        if (category) params.set("category", category);
        if (depth) params.set("depth", depth);
        const qs = params.toString();
        return get<Json[]>(`/self-model/facts${qs ? `?${qs}` : ""}`);
      },
      searchFacts: (q) => get<Json[]>(`/self-model/facts/search?q=${encodeURIComponent(q)}`),
      deleteFact: (factId) => del<{ deleted: boolean }>(`/self-model/facts/${factId}`),
      clearAllFacts: () => del<{ cleared: boolean }>("/self-model/facts"),
      editFact: (factId, patchData) => patch<Json>(`/self-model/facts/${factId}`, patchData),
      export: () => get<Json>("/self-model/export"),
      suggestions: (limit) => get<Json[]>(`/self-model/suggestions${limit ? `?limit=${limit}` : ""}`),
    };

    this.swarm = {
      negotiate: (a, b) => post<Json>("/swarm/negotiate", { claim_a: a, claim_b: b }),
      list: () => get<Json[]>("/swarm/negotiations"),
      get: (id) => get<Json>(`/swarm/negotiations/${id}`),
      detectConflicts: (events) => post<Json>("/swarm/detect-conflicts", { events }),
    };

    this.nervousSystem = {
      overview: () => get<Json>("/nervous-system/overview"),
      agents: () => get<Json[]>("/nervous-system/agents"),
      state: () => get<Json>("/nervous-system/state"),
      route: (message) => post<Json>("/nervous-system/route", { message }),
      memories: () => get<Json[]>("/nervous-system/memories"),
      assessUserState: (message) => post<Json>("/nervous-system/assess-user-state", { message }),
      casAgents: () => get<Json[]>("/nervous-system/cas-agents"),
    };

    this.marketplace = {
      list: (itemType, tag) => {
        const params = new URLSearchParams();
        if (itemType) params.set("item_type", itemType);
        if (tag) params.set("tag", tag);
        const qs = params.toString();
        return get<Json[]>(`/marketplace/items${qs ? `?${qs}` : ""}`);
      },
      get: (id) => get<Json>(`/marketplace/items/${id}`),
      search: (q) => get<Json[]>(`/marketplace/search?q=${encodeURIComponent(q)}`),
      publish: (item) => post<Json>("/marketplace/items", item),
      install: (id) => post<Json>(`/marketplace/items/${id}/install`),
      listInstalls: () => get<Json[]>("/marketplace/installs"),
      remix: (id, body) => post<Json>(`/marketplace/items/${id}/remix`, body),
      getRemixes: (id) => get<Json[]>(`/marketplace/items/${id}/remixes`),
      getRemixChain: (id) => get<Json[]>(`/marketplace/items/${id}/remix-chain`),
      rate: (id, stars) => post<Json>(`/marketplace/items/${id}/rate`, { stars }),
      getRegistryManifest: () => get<Json>("/marketplace/registry/manifest"),
      exportBundle: (itemIds = []) => post<Json>("/marketplace/export", { item_ids: itemIds }),
      importBundle: (bundleJson) => post<Json>("/marketplace/import", { bundle_json: bundleJson }),
      browseRemoteRegistry: (registryUrl) => post<Json>("/marketplace/registry/browse", { registry_url: registryUrl }),
      pullFromRemoteRegistry: (registryUrl, itemId) => post<Json>("/marketplace/registry/pull", { registry_url: registryUrl, item_id: itemId }),
    };

    this.developer = {
      listPlugins: (type) => get<Json[]>(`/developer/plugins${type ? `?plugin_type=${type}` : ""}`),
      registerPlugin: (body) => post<Json>("/developer/plugins", body),
      deletePlugin: (id) => del<void>(`/developer/plugins/${id}`),
      enablePlugin: (id) => post<Json>(`/developer/plugins/${id}/enable`),
      disablePlugin: (id) => post<Json>(`/developer/plugins/${id}/disable`),
      updatePluginConfig: (id, config) => patch<Json>(`/developer/plugins/${id}/config`, { config }),
      listAgentSpecs: () => get<Json[]>("/developer/agents"),
      createAgentSpec: (body) => post<Json>("/developer/agents", body),
      updateAgentSpec: (name, body) => patch<Json>(`/developer/agents/${name}`, body),
      deleteAgentSpec: (name) => del<void>(`/developer/agents/${name}`),
      exportConfig: () => post<Json>("/developer/config/export", {
        include_sub_accounts: true,
        include_plugins: true,
        include_custom_agents: true,
      }),
      importConfig: (config) => post<Json>("/developer/config/import", { config }),
      listRuntimePlugins: () => get<Json[]>("/developer/plugins/runtime/list"),
      scanRuntimePlugins: () => post<Json>("/developer/plugins/runtime/scan"),
      reloadRuntimePlugin: (pluginId) => post<Json>(`/developer/plugins/runtime/${pluginId}/reload`),
      enableRuntimePlugin: (pluginId) => post<Json>(`/developer/plugins/runtime/${pluginId}/enable`),
      disableRuntimePlugin: (pluginId) => post<Json>(`/developer/plugins/runtime/${pluginId}/disable`),
      listRuntimeHooks: () => get<{ hooks: string[] }>("/developer/plugins/runtime/hooks"),
    };

    this.oauth = {
      start: (providerId) => get<Json>(`/providers/${providerId}/oauth/start`),
    };
  }

  /** Check server health, including database backend type. */
  async health(): Promise<{ status: string; mode: string; version: string; database: string }> {
    const res = await this.fetchFn(`${this.baseUrl.replace("/api/a-cal", "")}/health`);
    return res.json() as Promise<{ status: string; mode: string; version: string; database: string }>;
  }
}
