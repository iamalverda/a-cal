"use client";

import { useState, useEffect } from "react";
import {
  Settings as SettingsIcon,
  Cpu,
  Brain,
  Shield,
  Palette,
  Code2,
  Store,
  X,
  ChevronRight,
  Link as LinkIcon,
  Trash2,
  RefreshCw,
  Lock,
  Mail,
  Calendar as CalIcon,
  Search,
  Pencil,
  Download,
  Eye,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { api, oauthApi } from "@/lib/api";
import { mockModeConfig } from "@/lib/mock-data";
import type { SkillMode, ModelProvider, ModeConfig, ModelRoutingConfig, ProviderConnection, SubAccount, ProviderType, SelfModelFact } from "@/types";

interface SettingsPanelProps {
  mode: SkillMode;
  onModeChange: (mode: SkillMode) => void;
  onClose: () => void;
}

const MODE_OPTIONS: { value: SkillMode; label: string; description: string }[] = [
  { value: "simple", label: "Simple", description: "Beginners, non-technical" },
  { value: "pro", label: "Pro", description: "Power users, plugins, config" },
  { value: "developer", label: "Developer", description: "API/SDK, Developer Studio" },
];

const PROVIDER_OPTIONS: { value: ModelProvider; label: string }[] = [
  { value: "ollama", label: "Ollama (Local)" },
  { value: "llama_cpp", label: "Llama.cpp (Local)" },
  { value: "lm_studio", label: "LM Studio (Local)" },
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "google", label: "Google" },
  { value: "azure", label: "Azure OpenAI" },
  { value: "deepseek", label: "DeepSeek" },
  { value: "together", label: "Together AI" },
  { value: "groq", label: "Groq" },
  { value: "openrouter", label: "OpenRouter" },
  { value: "mistral", label: "Mistral" },
];

const SELF_MODEL_DEPTHS = [
  { value: "pattern_memory", label: "Pattern Memory", description: "Busy times, meeting cadence, response patterns" },
  { value: "attention_intent", label: "Attention & Intent", description: "What you focus on, energy patterns, meeting preferences" },
  { value: "longitudinal_identity", label: "Longitudinal Identity", description: "Goals, relationships, role context, life context" },
];

const SECTIONS = [
  { id: "mode", label: "Skill Mode", icon: SettingsIcon },
  { id: "connections", label: "Connections", icon: LinkIcon },
  { id: "model", label: "Model Routing", icon: Cpu },
  { id: "self_model", label: "Self-Model", icon: Brain },
  { id: "privacy", label: "Privacy", icon: Shield },
  { id: "developer", label: "Developer", icon: Code2 },
  { id: "marketplace", label: "Marketplace", icon: Store },
];

export function SettingsPanel({ mode, onModeChange, onClose }: SettingsPanelProps) {
  const [activeSection, setActiveSection] = useState("mode");
  const [modeConfig, setModeConfig] = useState<ModeConfig>(mockModeConfig);
  const [modelProvider, setModelProvider] = useState<ModelProvider>("ollama");
  const [modelName, setModelName] = useState("llama3.2");
  const [selfModelDepth, setSelfModelDepth] = useState("pattern_memory");
  const [cloudSync, setCloudSync] = useState(false);
  const [proactive, setProactive] = useState(false);
  const [feedCalendar, setFeedCalendar] = useState(true);
  const [feedAgents, setFeedAgents] = useState(true);
  const [llmEnabled, setLlmEnabled] = useState(false);
  const [ollamaAvailable, setOllamaAvailable] = useState(false);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [connections, setConnections] = useState<ProviderConnection[]>([]);
  const [subAccountsList, setSubAccountsList] = useState<SubAccount[]>([]);
  const [showConnForm, setShowConnForm] = useState(false);
  const [connForm, setConnForm] = useState({
    provider_type: "caldav" as ProviderType,
    sub_account_id: "",
    display_name: "",
    server_url: "",
    username: "",
    password: "",
    imap_host: "",
    smtp_host: "",
    email: "",
  });
  const [connSubmitting, setConnSubmitting] = useState(false);
  const [connError, setConnError] = useState<string | null>(null);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [apiKeyDraft, setApiKeyDraft] = useState<Record<string, string>>({});

  // Self-model facts viewer state
  const [showFacts, setShowFacts] = useState(false);
  const [facts, setFacts] = useState<SelfModelFact[]>([]);
  const [factsLoading, setFactsLoading] = useState(false);
  const [factSearch, setFactSearch] = useState("");
  const [searchResults, setSearchResults] = useState<SelfModelFact[] | null>(null);
  const [editingFactId, setEditingFactId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");

  /** Load settings from the backend on mount, falling back to mock data. */
  useEffect(() => {
    async function loadSettings() {
      try {
        const [modeCfg, routing, selfModel, llmStat, ollamaStat, keysData, connsData, subsData] = await Promise.all([
          api.getMode(),
          api.getModelRouting(),
          api.getSelfModelSettings(),
          api.getLLMEnabled(),
          api.getOllamaStatus(),
          api.getApiKeys(),
          api.listAllProviders().catch(() => []),
          api.listSubAccounts().catch(() => []),
        ]);
        setModeConfig(modeCfg);
        setModelProvider(routing.global_provider as ModelProvider);
        setModelName(routing.global_model);
        setSelfModelDepth(selfModel.depth);
        setCloudSync(selfModel.cloud_sync_enabled);
        setProactive(selfModel.proactive_suggestions_enabled);
        setFeedCalendar(selfModel.feed_into_calendar_view);
        setFeedAgents(selfModel.feed_into_agents);
        setLlmEnabled(llmStat.enabled);
        setOllamaAvailable(ollamaStat.available);
        setOllamaModels(ollamaStat.models);
        setApiKeys(keysData);
        setApiKeyDraft(keysData);
      } catch {
        // Backend not running — keep defaults (mock data already set)
      }
    }
    loadSettings();
  }, []);

  /** Switch skill mode and persist to backend. */
  const handleModeChange = async (newMode: SkillMode) => {
    onModeChange(newMode);
    try {
      const cfg = await api.setMode(newMode);
      setModeConfig(cfg);
    } catch {
      // Backend not running — UI still updates via onModeChange
    }
  };

  /** Save model routing config to backend. */
  const saveModelRouting = async (provider: ModelProvider, model: string) => {
    try {
      await api.setModelRouting({
        global_provider: provider,
        global_model: model,
        per_task_overrides: {},
        privacy_force_local: true,
      });
    } catch {
      // Backend not running — local state already updated
    }
  };

  /** Load self-model facts from the backend. */
  const loadFacts = async () => {
    setFactsLoading(true);
    try {
      const data = await api.listSelfModelFacts();
      setFacts(data);
    } catch {
      setFacts([]);
    } finally {
      setFactsLoading(false);
    }
  };

  /** Toggle the facts viewer — loads facts on first open. */
  const toggleFacts = () => {
    if (!showFacts && facts.length === 0 && !factsLoading) {
      loadFacts();
    }
    setShowFacts(!showFacts);
  };

  /** Search facts with debounce-free live search. */
  const handleFactSearch = async (query: string) => {
    setFactSearch(query);
    if (!query.trim()) {
      setSearchResults(null);
      return;
    }
    try {
      const results = await api.searchSelfModelFacts(query, 20);
      setSearchResults(results);
    } catch {
      setSearchResults([]);
    }
  };

  /** Delete a single fact and refresh the list. */
  const handleDeleteFact = async (factId: string) => {
    try {
      await api.deleteSelfModelFact(factId);
      setFacts(facts.filter((f) => f.id !== factId));
      if (searchResults) {
        setSearchResults(searchResults.filter((f) => f.id !== factId));
      }
    } catch {
      // Backend not running
    }
  };

  /** Enter edit mode for a fact. */
  const startEditFact = (fact: SelfModelFact) => {
    setEditingFactId(fact.id);
    setEditContent(fact.content);
  };

  /** Save an edited fact. */
  const handleSaveEdit = async () => {
    if (!editingFactId || !editContent.trim()) return;
    try {
      const updated = await api.editSelfModelFact(editingFactId, editContent.trim());
      setFacts(facts.map((f) => (f.id === editingFactId ? updated : f)));
      if (searchResults) {
        setSearchResults(searchResults.map((f) => (f.id === editingFactId ? updated : f)));
      }
    } catch {
      // Backend not running
    }
    setEditingFactId(null);
    setEditContent("");
  };

  /** Clear all facts after confirmation. */
  const handleClearAllFacts = async () => {
    try {
      await api.clearAllSelfModelFacts();
      setFacts([]);
      setSearchResults(null);
    } catch {
      // Backend not running
    }
  };

  /** Export facts as a downloadable JSON file. */
  const handleExportFacts = async () => {
    try {
      const data = await api.exportSelfModelFacts();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "a-cal-self-model-export.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Backend not running
    }
  };

  /** Save self-model settings to backend. */
  const saveSelfModel = async (updates: Partial<{
    depth: string;
    cloud_sync_enabled: boolean;
    proactive_suggestions_enabled: boolean;
    feed_into_calendar_view: boolean;
    feed_into_agents: boolean;
  }>) => {
    try {
      await api.setSelfModelSettings({
        depth: updates.depth ?? selfModelDepth,
        enabled_categories: {},
        cloud_sync_enabled: updates.cloud_sync_enabled ?? cloudSync,
        proactive_suggestions_enabled: updates.proactive_suggestions_enabled ?? proactive,
        feed_into_calendar_view: updates.feed_into_calendar_view ?? feedCalendar,
        feed_into_agents: updates.feed_into_agents ?? feedAgents,
      });
    } catch {
      // Backend not running — local state already updated
    }
  };

  /** Toggle LLM mode and persist to backend. */
  const handleLLMToggle = async (enabled: boolean) => {
    setLlmEnabled(enabled);
    try {
      await api.setLLMEnabled(enabled);
    } catch {
      // Backend not running — local state already updated
    }
  };

  /** Save API keys for a specific provider to backend. */
  const saveApiKey = async (provider: string, key: string) => {
    const updated = { ...apiKeys, [provider]: key };
    setApiKeys(updated);
    try {
      await api.setApiKeys(updated);
    } catch {
      // Backend not running — local state already updated
    }
  };

  const handleCreateConnection = async () => {
    setConnSubmitting(true);
    setConnError(null);
    try {
      const config: Record<string, unknown> = {};
      if (connForm.provider_type === "caldav") {
        config.server_url = connForm.server_url;
        config.username = connForm.username;
      } else if (connForm.provider_type === "imap_smtp") {
        config.imap_host = connForm.imap_host;
        config.smtp_host = connForm.smtp_host;
        config.username = connForm.email;
      } else if (connForm.provider_type === "gmail" || connForm.provider_type === "google_calendar") {
        config.email = connForm.email;
      }
      const providerAccountId = connForm.email || connForm.username || connForm.display_name || "account";
      const created = await api.createProvider({
        sub_account_id: connForm.sub_account_id || subAccountsList[0]?.id || "sa-main",
        provider_type: connForm.provider_type,
        provider_account_id: providerAccountId,
        display_name: connForm.display_name || undefined,
        config,
      });
      setConnections([...connections, created]);
      setShowConnForm(false);
      setConnForm({
        provider_type: "caldav", sub_account_id: "", display_name: "",
        server_url: "", username: "", password: "",
        imap_host: "", smtp_host: "", email: "",
      });
    } catch (err) {
      setConnError(err instanceof Error ? err.message : "Failed to create connection");
    }
    setConnSubmitting(false);
  };

  const handleDeleteConnection = async (id: string) => {
    try {
      await api.deleteProvider(id);
      setConnections(connections.filter((c) => c.id !== id));
    } catch {
      // keep on error
    }
  };

  const handleSyncConnection = async (subAccountId: string) => {
    try {
      await api.triggerSync(subAccountId);
      const refreshed = await api.listAllProviders();
      if (Array.isArray(refreshed)) setConnections(refreshed);
    } catch {
      // keep on error
    }
  };

  const OAUTH_PROVIDER_TYPES = ["google_calendar", "outlook_calendar", "gmail"];

  const handleAuthorizeOAuth = async (providerId: string) => {
    try {
      const { authorization_url } = await oauthApi.start(providerId);
      window.location.href = authorization_url;
    } catch (e) {
      setConnError(
        e instanceof Error ? e.message : "OAuth start failed — check client ID in Developer mode"
      );
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex bg-black/40" onClick={onClose}>
      <div
        className="ml-auto w-[560px] max-w-[90vw] h-full bg-[var(--card)] shadow-2xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
          <div className="flex items-center gap-2">
            <SettingsIcon size={18} className="text-[var(--primary)]" />
            <h2 className="text-lg font-semibold">Settings</h2>
            <Badge className="ml-2 bg-[var(--primary)]/15 text-[var(--primary)] text-xs capitalize">
              {mode} mode
            </Badge>
          </div>
          <button onClick={onClose} className="text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
            <X size={20} />
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Section sidebar */}
          <div className="w-48 shrink-0 border-r border-[var(--border)] py-3 px-2 space-y-1">
            {SECTIONS.map((s) => {
              const Icon = s.icon;
              const visible =
                mode === "developer" ||
                (mode === "pro" && s.id !== "developer") ||
                (mode === "simple" && ["mode", "model"].includes(s.id));
              if (!visible) return null;
              return (
                <button
                  key={s.id}
                  onClick={() => setActiveSection(s.id)}
                  className={cn(
                    "w-full flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors text-left",
                    activeSection === s.id
                      ? "bg-[var(--primary)]/10 text-[var(--primary)] font-medium"
                      : "hover:bg-[var(--accent)] text-[var(--foreground)]"
                  )}
                >
                  <Icon size={15} />
                  {s.label}
                </button>
              );
            })}
          </div>

          {/* Section content */}
          <div className="flex-1 overflow-y-auto px-6 py-5">
            {activeSection === "mode" && (
              <Section title="Skill Mode" description="Switch the UI complexity and feature set. You can change this anytime.">
                <div className="space-y-2">
                  {MODE_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => handleModeChange(opt.value)}
                      className={cn(
                        "w-full flex items-center justify-between rounded-lg border p-4 text-left transition-colors",
                        mode === opt.value
                          ? "border-[var(--primary)] bg-[var(--primary)]/5"
                          : "border-[var(--border)] hover:bg-[var(--accent)]"
                      )}
                    >
                      <div>
                        <div className="font-medium text-sm">{opt.label}</div>
                        <div className="text-xs text-[var(--muted-foreground)] mt-0.5">{opt.description}</div>
                      </div>
                      {mode === opt.value && (
                        <ChevronRight size={16} className="text-[var(--primary)]" />
                      )}
                    </button>
                  ))}
                </div>
                <div className="mt-4 p-3 rounded-md bg-[var(--muted)] text-xs text-[var(--muted-foreground)]">
                  {modeConfig.description}
                </div>
              </Section>
            )}

            {activeSection === "connections" && (
              <Section title="Connections" description="Link calendar and email providers. Sub-accounts group providers so you can control what flows to your main calendar.">
                <div className="space-y-4">
                  {/* Existing connections */}
                  {connections.length > 0 && (
                    <div className="space-y-2">
                      {connections.map((conn) => {
                        const sa = subAccountsList.find((s2) => s2.id === conn.sub_account_id);
                        const isCalendar = conn.provider_type === "google_calendar" || conn.provider_type === "outlook_calendar" || conn.provider_type === "caldav";
                        return (
                          <div key={conn.id} className="flex items-center justify-between p-3 rounded-lg border border-[var(--border)]">
                            <div className="flex items-center gap-3">
                              {isCalendar ? (
                                <CalIcon size={16} className="text-[var(--primary)]" />
                              ) : (
                                <Mail size={16} className="text-[var(--primary)]" />
                              )}
                              <div>
                                <div className="text-sm font-medium">
                                  {conn.display_name || conn.provider_type.replace(/_/g, " ")}
                                </div>
                                <div className="text-xs text-[var(--muted-foreground)]">
                                  {sa ? sa.name : conn.sub_account_id}
                                  {" \u00b7 "}
                                  {conn.provider_type.replace(/_/g, " ")}
                                </div>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              <Badge className={cn(
                                "text-xs",
                                conn.status === "connected" && "bg-[var(--cal-personal)]/15 text-[var(--cal-personal)]",
                                conn.status === "pending" && "bg-[var(--muted)] text-[var(--muted-foreground)]",
                                conn.status === "error" && "bg-[var(--destructive)]/15 text-[var(--destructive)]",
                                conn.status === "revoked" && "bg-[var(--muted)] text-[var(--muted-foreground)]",
                              )}>
                                {conn.status}
                              </Badge>
                              {OAUTH_PROVIDER_TYPES.includes(conn.provider_type) && conn.status !== "connected" && (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => handleAuthorizeOAuth(conn.id)}
                                  className="text-xs h-7"
                                >
                                  <Lock size={12} className="mr-1" />
                                  Authorize
                                </Button>
                              )}
                              <button
                                onClick={() => handleSyncConnection(conn.sub_account_id)}
                                className="p-1 rounded hover:bg-[var(--accent)] text-[var(--muted-foreground)]"
                                title="Sync"
                              >
                                <RefreshCw size={14} />
                              </button>
                              <button
                                onClick={() => handleDeleteConnection(conn.id)}
                                className="p-1 rounded hover:bg-[var(--destructive)]/15 text-[var(--muted-foreground)] hover:text-[var(--destructive)]"
                                title="Disconnect"
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {connections.length === 0 && !showConnForm && (
                    <div className="text-center py-8 text-sm text-[var(--muted-foreground)]">
                      No provider connections yet. Add one to start syncing calendars and email.
                    </div>
                  )}

                  {/* Add connection form */}
                  {showConnForm ? (
                    <div className="p-4 rounded-lg border border-[var(--border)] space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-sm">New Connection</span>
                        <button onClick={() => setShowConnForm(false)} className="text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
                          <X size={16} />
                        </button>
                      </div>

                      <div>
                        <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Provider type</label>
                        <Select
                          value={connForm.provider_type}
                          onChange={(e) => setConnForm({ ...connForm, provider_type: e.target.value as ProviderType })}
                        >
                          <option value="caldav">CalDAV (any calendar server)</option>
                          <option value="google_calendar">Google Calendar</option>
                          <option value="outlook_calendar">Outlook Calendar</option>
                          <option value="imap_smtp">IMAP/SMTP (any email)</option>
                          <option value="gmail">Gmail (OAuth)</option>
                        </Select>
                      </div>

                      <div>
                        <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Sub-account</label>
                        <Select
                          value={connForm.sub_account_id}
                          onChange={(e) => setConnForm({ ...connForm, sub_account_id: e.target.value })}
                        >
                          <option value="">Main Calendar (default)</option>
                          {subAccountsList.filter((sa) => !sa.is_main).map((sa) => (
                            <option key={sa.id} value={sa.id}>{sa.name}</option>
                          ))}
                        </Select>
                      </div>

                      <div>
                        <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Display name (optional)</label>
                        <Input
                          value={connForm.display_name}
                          onChange={(e) => setConnForm({ ...connForm, display_name: e.target.value })}
                          placeholder="Work Calendar, Personal Email..."
                        />
                      </div>

                      {connForm.provider_type === "caldav" && (
                        <>
                          <div>
                            <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Server URL</label>
                            <Input
                              value={connForm.server_url}
                              onChange={(e) => setConnForm({ ...connForm, server_url: e.target.value })}
                              placeholder="https://cal.example.com/user"
                            />
                          </div>
                          <div>
                            <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Username</label>
                            <Input
                              value={connForm.username}
                              onChange={(e) => setConnForm({ ...connForm, username: e.target.value })}
                              placeholder="username"
                            />
                          </div>
                          <div>
                            <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Password</label>
                            <Input
                              type="password"
                              value={connForm.password}
                              onChange={(e) => setConnForm({ ...connForm, password: e.target.value })}
                              placeholder="\u2022\u2022\u2022\u2022\u2022\u2022"
                            />
                          </div>
                        </>
                      )}

                      {connForm.provider_type === "imap_smtp" && (
                        <>
                          <div className="grid grid-cols-2 gap-2">
                            <div>
                              <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">IMAP host</label>
                              <Input
                                value={connForm.imap_host}
                                onChange={(e) => setConnForm({ ...connForm, imap_host: e.target.value })}
                                placeholder="imap.gmail.com"
                              />
                            </div>
                            <div>
                              <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">SMTP host</label>
                              <Input
                                value={connForm.smtp_host}
                                onChange={(e) => setConnForm({ ...connForm, smtp_host: e.target.value })}
                                placeholder="smtp.gmail.com"
                              />
                            </div>
                          </div>
                          <div>
                            <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Email address</label>
                            <Input
                              value={connForm.email}
                              onChange={(e) => setConnForm({ ...connForm, email: e.target.value })}
                              placeholder="you@example.com"
                            />
                          </div>
                          <div>
                            <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Password / App password</label>
                            <Input
                              type="password"
                              value={connForm.password}
                              onChange={(e) => setConnForm({ ...connForm, password: e.target.value })}
                              placeholder="\u2022\u2022\u2022\u2022\u2022\u2022"
                            />
                          </div>
                        </>
                      )}

                      {(connForm.provider_type === "google_calendar" || connForm.provider_type === "outlook_calendar" || connForm.provider_type === "gmail") && (
                        <div>
                          <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Account email</label>
                          <Input
                            value={connForm.email}
                            onChange={(e) => setConnForm({ ...connForm, email: e.target.value })}
                            placeholder="you@example.com"
                          />
                          <p className="text-xs text-[var(--muted-foreground)] mt-1">
                            OAuth flow will open after creation.
                          </p>
                        </div>
                      )}

                      {connError && (
                        <div className="text-sm text-[var(--destructive)]">{connError}</div>
                      )}

                      <div className="flex gap-2 pt-1">
                        <Button onClick={handleCreateConnection} disabled={connSubmitting} size="sm">
                          {connSubmitting ? "Connecting..." : "Connect"}
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => setShowConnForm(false)}>
                          Cancel
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <Button variant="outline" size="sm" onClick={() => setShowConnForm(true)}>
                      <LinkIcon size={14} className="mr-1" />
                      Add Connection
                    </Button>
                  )}

                  <div className="p-3 rounded-lg bg-[var(--muted)]/30 text-xs text-[var(--muted-foreground)]">
                    CalDAV and IMAP/SMTP work with any provider out of the box. Google and Outlook use OAuth and require setup in Developer mode.
                  </div>
                </div>
              </Section>
            )}

            {activeSection === "model" && (
              <Section title="Model Routing" description="Choose which AI model powers your agents. Local models keep data on your machine.">
                <div className="space-y-4">
                  {/* LLM Enable Toggle */}
                  <div className="flex items-start justify-between gap-3 py-2">
                    <div className="flex-1">
                      <div className="text-sm font-medium">Enable AI Agents</div>
                      <div className="text-xs text-[var(--muted-foreground)] mt-0.5">
                        When enabled, the conductor dispatches to real LLMs. When disabled, agents respond with routing-only messages.
                      </div>
                    </div>
                    <Switch checked={llmEnabled} onChange={handleLLMToggle} />
                  </div>

                  <div className={cn("space-y-4 transition-opacity", !llmEnabled && "opacity-50 pointer-events-none")}>
                    <div>
                      <label className="text-sm font-medium mb-2 block">Provider</label>
                      <Select
                        value={modelProvider}
                        onChange={(e) => {
                          const p = e.target.value as ModelProvider;
                          setModelProvider(p);
                          saveModelRouting(p, modelName);
                        }}
                      >
                        {PROVIDER_OPTIONS.map((p) => (
                          <option key={p.value} value={p.value}>{p.label}</option>
                        ))}
                      </Select>
                    </div>

                    {/* Ollama status display when Ollama is selected */}
                    {modelProvider === "ollama" && (
                      <div className={cn(
                        "p-3 rounded-md text-xs border",
                        ollamaAvailable
                          ? "bg-[var(--cal-work)]/10 border-[var(--cal-work)]/30 text-[var(--foreground)]"
                          : "bg-[var(--destructive)]/5 border-[var(--destructive)]/20 text-[var(--foreground)]"
                      )}>
                        {ollamaAvailable ? (
                          <span>Ollama is running — {ollamaModels.length} model{ollamaModels.length !== 1 ? "s" : ""} available.</span>
                        ) : (
                          <span>Ollama is not detected. Start it with <code className="bg-[var(--muted)] px-1 rounded">ollama serve</code> or choose a cloud provider.</span>
                        )}
                      </div>
                    )}

                    <div>
                      <label className="text-sm font-medium mb-2 block">Model</label>
                      <Select
                        value={modelName}
                        onChange={(e) => {
                          const m = e.target.value;
                          setModelName(m);
                          saveModelRouting(modelProvider, m);
                        }}
                      >
                        {/* Dynamic Ollama models when Ollama is selected and available */}
                        {modelProvider === "ollama" && ollamaAvailable && ollamaModels.length > 0 ? (
                          ollamaModels.map((m) => (
                            <option key={m} value={m}>{m}</option>
                          ))
                        ) : modelProvider === "ollama" ? (
                          <>
                            <option value="llama3.2">Llama 3.2 (8B)</option>
                            <option value="llama3.1">Llama 3.1 (70B)</option>
                            <option value="mistral">Mistral (7B)</option>
                            <option value="gemma3">Gemma 3 (4B)</option>
                            <option value="qwen2.5">Qwen 2.5 (7B)</option>
                          </>
                        ) : modelProvider === "openai" ? (
                          <>
                            <option value="gpt-4o">GPT-4o</option>
                            <option value="gpt-4o-mini">GPT-4o mini</option>
                            <option value="gpt-4-turbo">GPT-4 Turbo</option>
                            <option value="o1-mini">o1-mini</option>
                          </>
                        ) : modelProvider === "anthropic" ? (
                          <>
                            <option value="claude-sonnet-4-5">Claude Sonnet 4.5</option>
                            <option value="claude-opus-4">Claude Opus 4</option>
                            <option value="claude-haiku-3-5">Claude Haiku 3.5</option>
                          </>
                        ) : modelProvider === "google" ? (
                          <>
                            <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
                            <option value="gemini-2.5-pro">Gemini 2.5 Pro</option>
                          </>
                        ) : modelProvider === "azure" ? (
                          <option value="gpt-4o">GPT-4o (Azure deployment)</option>
                        ) : modelProvider === "deepseek" ? (
                          <>
                            <option value="deepseek-chat">DeepSeek Chat</option>
                            <option value="deepseek-reasoner">DeepSeek Reasoner</option>
                          </>
                        ) : modelProvider === "together" ? (
                          <>
                            <option value="meta-llama/Llama-3.3-70B-Instruct-Turbo">Llama 3.3 70B Turbo</option>
                            <option value="mistralai/Mixtral-8x22B-Instruct-v0.1">Mixtral 8x22B</option>
                          </>
                        ) : modelProvider === "groq" ? (
                          <>
                            <option value="llama-3.3-70b-versatile">Llama 3.3 70B</option>
                            <option value="llama-3.1-8b-instant">Llama 3.1 8B Instant</option>
                          </>
                        ) : modelProvider === "openrouter" ? (
                          <>
                            <option value="openai/gpt-4o">GPT-4o (via OpenRouter)</option>
                            <option value="anthropic/claude-3.5-sonnet">Claude Sonnet (via OpenRouter)</option>
                            <option value="google/gemini-2.5-flash">Gemini 2.5 Flash (via OpenRouter)</option>
                          </>
                        ) : modelProvider === "mistral" ? (
                          <>
                            <option value="mistral-large-latest">Mistral Large</option>
                            <option value="mistral-small-latest">Mistral Small</option>
                          </>
                        ) : (
                          <option value="custom">Custom model name</option>
                        )}
                      </Select>
                    </div>

                    {/* API key input for cloud providers */}
                    {!["ollama", "llama_cpp", "lm_studio"].includes(modelProvider) && (
                      <div>
                        <label className="text-sm font-medium mb-2 block">
                          API Key ({PROVIDER_OPTIONS.find((p) => p.value === modelProvider)?.label})
                        </label>
                        <div className="flex gap-2">
                          <Input
                            type="password"
                            placeholder={apiKeys[modelProvider] ? "•••••••• (saved)" : "Enter your API key"}
                            value={apiKeyDraft[modelProvider] ?? ""}
                            onChange={(e) => {
                              const val = e.target.value;
                              setApiKeyDraft((prev) => ({ ...prev, [modelProvider]: val }));
                            }}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                const val = apiKeyDraft[modelProvider] ?? "";
                                if (val) saveApiKey(modelProvider, val);
                              }
                            }}
                          />
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              const val = apiKeyDraft[modelProvider] ?? "";
                              if (val) saveApiKey(modelProvider, val);
                            }}
                          >
                            Save
                          </Button>
                        </div>
                        {apiKeys[modelProvider] && (
                          <p className="text-xs text-[var(--muted-foreground)] mt-1">
                            Key saved. Enter a new key to replace it.
                          </p>
                        )}
                      </div>
                    )}

                    {mode !== "simple" && (
                      <div className="p-3 rounded-md bg-[var(--muted)] text-xs text-[var(--muted-foreground)]">
                        <strong className="text-[var(--foreground)]">Per-task overrides:</strong> In Pro mode you can assign different models to different agent tasks (e.g. a cheap model for sync, a smarter model for negotiation).
                      </div>
                    )}
                    <div className="flex items-center gap-2 p-3 rounded-md bg-[var(--destructive)]/5 border border-[var(--destructive)]/20">
                      <Shield size={14} className="text-[var(--destructive)]" />
                      <span className="text-xs text-[var(--foreground)]">
                        Email, self-model, and negotiation tasks always use a local model regardless of this setting.
                      </span>
                    </div>
                  </div>
                </div>
              </Section>
            )}

            {activeSection === "self_model" && (
              <Section title="Self-Model" description="A-Cal learns about you at a depth you control. Everything is transparent and correctable.">
                <div className="space-y-4">
                  <div>
                    <label className="text-sm font-medium mb-2 block">Depth Level</label>
                    <div className="space-y-2">
                      {SELF_MODEL_DEPTHS.map((d) => (
                        <button
                          key={d.value}
                          onClick={() => {
                            setSelfModelDepth(d.value);
                            saveSelfModel({ depth: d.value });
                          }}
                          className={cn(
                            "w-full flex items-start gap-3 rounded-lg border p-3 text-left transition-colors",
                            selfModelDepth === d.value
                              ? "border-[var(--primary)] bg-[var(--primary)]/5"
                              : "border-[var(--border)] hover:bg-[var(--accent)]"
                          )}
                        >
                          <div className={cn(
                            "w-4 h-4 rounded-full border-2 shrink-0 mt-0.5",
                            selfModelDepth === d.value ? "border-[var(--primary)] bg-[var(--primary)]" : "border-[var(--border)]"
                          )} />
                          <div>
                            <div className="font-medium text-sm">{d.label}</div>
                            <div className="text-xs text-[var(--muted-foreground)] mt-0.5">{d.description}</div>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                  <ToggleRow
                    label="Cloud sync (encrypted)"
                    description="Sync your self-model across devices. Encrypted, off by default."
                    checked={cloudSync}
                    onChange={(v) => {
                      setCloudSync(v);
                      saveSelfModel({ cloud_sync_enabled: v });
                    }}
                  />
                  <ToggleRow
                    label="Proactive suggestions"
                    description="Unprompted nudges based on your patterns and priorities."
                    checked={proactive}
                    onChange={(v) => {
                      setProactive(v);
                      saveSelfModel({ proactive_suggestions_enabled: v });
                    }}
                  />
                  <ToggleRow
                    label="Enrich calendar view"
                    description="Color-code events by energy patterns and show context badges."
                    checked={feedCalendar}
                    onChange={(v) => {
                      setFeedCalendar(v);
                      saveSelfModel({ feed_into_calendar_view: v });
                    }}
                  />
                  <ToggleRow
                    label="Feed context to agents"
                    description="Inject self-model knowledge into agent prompts for better decisions."
                    checked={feedAgents}
                    onChange={(v) => {
                      setFeedAgents(v);
                      saveSelfModel({ feed_into_agents: v });
                    }}
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full mt-2"
                    onClick={toggleFacts}
                  >
                    {showFacts ? <Eye size={14} /> : <Brain size={14} />}
                    {showFacts ? "Hide Self-Model Facts" : "View What A-Cal Knows About Me"}
                  </Button>

                  {showFacts && (
                    <SelfModelFactsViewer
                      facts={facts}
                      loading={factsLoading}
                      factSearch={factSearch}
                      searchResults={searchResults}
                      editingFactId={editingFactId}
                      editContent={editContent}
                      onSearch={handleFactSearch}
                      onDelete={handleDeleteFact}
                      onStartEdit={startEditFact}
                      onSaveEdit={handleSaveEdit}
                      onCancelEdit={() => { setEditingFactId(null); setEditContent(""); }}
                      onEditContentChange={setEditContent}
                      onClearAll={handleClearAllFacts}
                      onExport={handleExportFacts}
                      onRefresh={loadFacts}
                    />
                  )}
                </div>
              </Section>
            )}

            {activeSection === "privacy" && (
              <Section title="Privacy" description="How your data flows between local and cloud models.">
                <div className="space-y-3">
                  <div className="p-3 rounded-md bg-[var(--muted)] text-xs text-[var(--muted-foreground)]">
                    Privacy-tiered routing ensures sensitive data never leaves your machine, even when using a cloud model for general tasks.
                  </div>
                  <PrivacyRow task="Calendar sync & fetch" />
                  <PrivacyRow task="Scheduling & slot finding" />
                  <PrivacyRow task="Email triage & replies" forced />
                  <PrivacyRow task="Self-model reasoning" forced />
                  <PrivacyRow task="Meeting negotiation" forced />
                </div>
              </Section>
            )}

            {activeSection === "developer" && mode === "developer" && (
              <Section title="Developer" description="API access, plugin development, and Developer Studio.">
                <div className="space-y-3">
                  <div className="p-4 rounded-lg border border-[var(--border)]">
                    <div className="flex items-center gap-2 mb-2">
                      <Code2 size={16} className="text-[var(--primary)]" />
                      <span className="font-medium text-sm">API & SDK</span>
                    </div>
                    <p className="text-xs text-[var(--muted-foreground)] mb-2">
                      Base URL: <code className="bg-[var(--muted)] px-1 rounded">/api/a-cal</code>
                    </p>
                    <Button variant="outline" size="sm">Open API Explorer</Button>
                  </div>
                  <div className="p-4 rounded-lg border border-[var(--border)]">
                    <div className="flex items-center gap-2 mb-2">
                      <Palette size={16} className="text-[var(--primary)]" />
                      <span className="font-medium text-sm">Developer Studio</span>
                    </div>
                    <p className="text-xs text-[var(--muted-foreground)] mb-2">
                      Build custom agents, plugins, and automations.
                    </p>
                    <Button variant="outline" size="sm">Open Developer Studio</Button>
                  </div>
                  <div className="p-4 rounded-lg border border-[var(--border)]">
                    <div className="font-medium text-sm mb-1">Config as Code</div>
                    <p className="text-xs text-[var(--muted-foreground)] mb-2">
                      Export and import your full A-Cal configuration as JSON.
                    </p>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm">Export</Button>
                      <Button variant="outline" size="sm">Import</Button>
                    </div>
                  </div>
                </div>
              </Section>
            )}

            {activeSection === "marketplace" && mode !== "simple" && (
              <Section title="Marketplace" description="Share and discover templates, themes, agent presets, and plugins.">
                <div className="space-y-3">
                  <div className="p-4 rounded-lg border border-[var(--border)]">
                    <div className="flex items-center gap-2 mb-2">
                      <Store size={16} className="text-[var(--primary)]" />
                      <span className="font-medium text-sm">Community Hub</span>
                    </div>
                    <p className="text-xs text-[var(--muted-foreground)] mb-2">
                      Browse shared configs, agent presets, and plugins from the community. Remix any shared config to make it your own.
                    </p>
                    <Button variant="outline" size="sm">Browse Marketplace</Button>
                  </div>
                  <div className="p-4 rounded-lg border border-[var(--border)]">
                    <div className="font-medium text-sm mb-1">Share Your Setup</div>
                    <p className="text-xs text-[var(--muted-foreground)] mb-2">
                      Every shared config carries structured provenance so others can audit what it does before installing.
                    </p>
                    <Button variant="outline" size="sm">Publish Config</Button>
                  </div>
                </div>
              </Section>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Section({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-base font-semibold mb-1">{title}</h3>
      <p className="text-sm text-[var(--muted-foreground)] mb-4">{description}</p>
      {children}
    </div>
  );
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-3 py-2">
      <div className="flex-1">
        <div className="text-sm font-medium">{label}</div>
        <div className="text-xs text-[var(--muted-foreground)] mt-0.5">{description}</div>
      </div>
      <Switch checked={checked} onChange={onChange} />
    </div>
  );
}

function PrivacyRow({ task, forced }: { task: string; forced?: boolean }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span>{task}</span>
      {forced ? (
        <Badge className="bg-[var(--destructive)]/15 text-[var(--destructive)]">Local only</Badge>
      ) : (
        <Badge className="bg-[var(--cal-personal)]/15 text-[var(--cal-personal)]">Can use cloud</Badge>
      )}
    </div>
  );
}

// --- Self-Model Facts Viewer ------------------------------------------------

const FACT_CATEGORY_LABELS: Record<string, string> = {
  busy_times: "Busy Times",
  meeting_patterns: "Meeting Patterns",
  timezone_habits: "Timezone Habits",
  response_cadence: "Response Cadence",
  work_focus: "Work Focus",
  energy_patterns: "Energy Patterns",
  meeting_prefs: "Meeting Preferences",
  attention_signals: "Attention Signals",
  goals: "Goals",
  relationships: "Relationships",
  role_context: "Role Context",
  life_context: "Life Context",
};

const PRIVACY_TIER_LABELS: Record<string, { label: string; color: string }> = {
  local: { label: "Local only", color: "var(--destructive)" },
  preference: { label: "Local by default", color: "var(--cal-personal)" },
  pattern: { label: "Can use cloud", color: "var(--cal-work)" },
};

function confidenceColor(confidence: number): string {
  if (confidence >= 0.8) return "var(--cal-work)";
  if (confidence >= 0.5) return "var(--cal-personal)";
  return "var(--muted-foreground)";
}

function SelfModelFactsViewer({
  facts,
  loading,
  factSearch,
  searchResults,
  editingFactId,
  editContent,
  onSearch,
  onDelete,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onEditContentChange,
  onClearAll,
  onExport,
  onRefresh,
}: {
  facts: SelfModelFact[];
  loading: boolean;
  factSearch: string;
  searchResults: SelfModelFact[] | null;
  editingFactId: string | null;
  editContent: string;
  onSearch: (q: string) => void;
  onDelete: (id: string) => void;
  onStartEdit: (fact: SelfModelFact) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onEditContentChange: (v: string) => void;
  onClearAll: () => void;
  onExport: () => void;
  onRefresh: () => void;
}) {
  const displayFacts = searchResults ?? facts;

  // Group facts by category
  const grouped: Record<string, SelfModelFact[]> = {};
  for (const fact of displayFacts) {
    if (!grouped[fact.category]) grouped[fact.category] = [];
    grouped[fact.category].push(fact);
  }
  const categories = Object.keys(grouped).sort();

  return (
    <div className="mt-4 space-y-3 rounded-lg border border-[var(--border)] p-4 bg-[var(--muted)]/30">
      {/* Search bar */}
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]" />
        <Input
          placeholder="Search facts..."
          value={factSearch}
          onChange={(e) => onSearch(e.target.value)}
          className="pl-9"
        />
        {factSearch && (
          <button
            onClick={() => onSearch("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          >
            <X size={14} />
          </button>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onRefresh} className="text-xs">
          <RefreshCw size={12} className="mr-1" />
          Refresh
        </Button>
        <Button variant="ghost" size="sm" onClick={onExport} className="text-xs" disabled={facts.length === 0}>
          <Download size={12} className="mr-1" />
          Export
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onClearAll}
          className="text-xs text-[var(--destructive)] ml-auto"
          disabled={facts.length === 0}
        >
          <Trash2 size={12} className="mr-1" />
          Clear All
        </Button>
      </div>

      {/* Facts list */}
      {loading ? (
        <div className="text-center py-8 text-sm text-[var(--muted-foreground)]">
          Loading facts...
        </div>
      ) : displayFacts.length === 0 ? (
        <div className="text-center py-8 text-sm text-[var(--muted-foreground)]">
          {factSearch ? "No facts match your search." : "A-Cal hasn't learned any facts about you yet."}
        </div>
      ) : (
        <div className="space-y-4 max-h-[400px] overflow-y-auto">
          {categories.map((category) => (
            <div key={category}>
              <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)] mb-2">
                {FACT_CATEGORY_LABELS[category] ?? category}
                <span className="ml-2 text-[var(--muted-foreground)]/60">({grouped[category].length})</span>
              </div>
              <div className="space-y-2">
                {grouped[category].map((fact) => {
                  const tier = PRIVACY_TIER_LABELS[fact.privacy_tier] ?? {
                    label: fact.privacy_tier,
                    color: "var(--muted-foreground)",
                  };
                  const isEditing = editingFactId === fact.id;
                  return (
                    <div
                      key={fact.id}
                      className="rounded-md border border-[var(--border)] bg-[var(--background)] p-3"
                    >
                      {isEditing ? (
                        <div className="space-y-2">
                          <textarea
                            value={editContent}
                            onChange={(e) => onEditContentChange(e.target.value)}
                            className="w-full min-h-[60px] rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
                            autoFocus
                          />
                          <div className="flex gap-2">
                            <Button size="sm" onClick={onSaveEdit}>Save</Button>
                            <Button size="sm" variant="ghost" onClick={onCancelEdit}>Cancel</Button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="flex items-start justify-between gap-2">
                            <p className="text-sm flex-1">{fact.content}</p>
                            <div className="flex gap-1 shrink-0">
                              <button
                                onClick={() => onStartEdit(fact)}
                                className="p-1 rounded text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--accent)]"
                                title="Edit"
                              >
                                <Pencil size={12} />
                              </button>
                              <button
                                onClick={() => onDelete(fact.id)}
                                className="p-1 rounded text-[var(--muted-foreground)] hover:text-[var(--destructive)] hover:bg-[var(--accent)]"
                                title="Delete"
                              >
                                <Trash2 size={12} />
                              </button>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 mt-2 flex-wrap">
                            {/* Confidence indicator */}
                            <div className="flex items-center gap-1">
                              <div
                                className="w-2 h-2 rounded-full"
                                style={{ backgroundColor: confidenceColor(fact.confidence) }}
                              />
                              <span className="text-xs text-[var(--muted-foreground)]">
                                {Math.round(fact.confidence * 100)}% confidence
                              </span>
                            </div>
                            {/* Privacy tier badge */}
                            <Badge
                              className="text-[10px] px-1.5 py-0"
                              style={{
                                backgroundColor: `color-mix(in srgb, ${tier.color} 15%, transparent)`,
                                color: tier.color,
                              }}
                            >
                              {tier.label}
                            </Badge>
                            {/* Provenance */}
                            {fact.provenance && (
                              <span className="text-[10px] text-[var(--muted-foreground)]/70">
                                via {fact.provenance}
                              </span>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Footer note */}
      <div className="flex items-start gap-2 text-xs text-[var(--muted-foreground)] pt-1">
        <AlertTriangle size={12} className="shrink-0 mt-0.5" />
        <span>
          Everything here is transparent and correctable. Deleting a fact means A-Cal will
          stop using it for suggestions and agent context. User-corrected facts get 100% confidence.
        </span>
      </div>
    </div>
  );
}
