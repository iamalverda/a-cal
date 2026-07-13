"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import type { ReactNode } from "react";
import { Settings, Moon, Sun, Sparkles, Bot, Store, Code2, Workflow, Mail, BarChart3, User, Menu, X } from "lucide-react";
import { Network, Brain } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { CalendarView } from "@/components/calendar-view";
import { SubAccountSidebar } from "@/components/sub-account-sidebar";
import { ConductorPanel } from "@/components/conductor-panel";
import { SettingsPanel } from "@/components/settings-panel";
import { MarketplacePanel } from "@/components/marketplace-panel";
import { CommunityProfilePanel } from "@/components/community-profile-panel";
import { SwarmPanel } from "@/components/swarm-panel";
import { DeveloperPanel } from "@/components/developer-panel";
import { WorkflowBuilder } from "@/components/workflow-builder";
import { NervousSystemPanel } from "@/components/nervous-system-panel";
import { EmailPanel } from "@/components/email-panel";
import { AnalyticsPanel } from "@/components/analytics-panel";
import { AddAccountWizard } from "@/components/add-account-wizard";
import { ProactiveSuggestions } from "@/components/proactive-suggestions";
import { CommandBar } from "@/components/command-bar";
import { api } from "@/lib/api";
import {
  mockSubAccounts,
  mockProviders,
  mockEvents,
  mockAgents,
} from "@/lib/mock-data";
import type { SkillMode, SubAccount, ProviderConnection, UnifiedEvent, AgentSpec } from "@/types";

export default function Page() {
  const [mode, setMode] = useState<SkillMode>("pro");
  const [showSettings, setShowSettings] = useState(false);
  const [dark, setDark] = useState(true);

  /** Sync the dark class on <html> with the dark state. */
  useEffect(() => {
    const root = document.documentElement;
    if (dark) root.classList.add("dark");
    else root.classList.remove("dark");
  }, [dark]);
  const [subAccounts, setSubAccounts] = useState<SubAccount[]>(mockSubAccounts);
  const [providers, setProviders] = useState<Record<string, ProviderConnection[]>>(mockProviders);
  const [events, setEvents] = useState<UnifiedEvent[]>(mockEvents);
  const [agents, setAgents] = useState<AgentSpec[]>(mockAgents);
  const [visibleSubAccounts, setVisibleSubAccounts] = useState<Set<string>>(
    new Set(mockSubAccounts.filter((s) => !s.is_main).map((s) => s.id))
  );
  const [selectedSubAccountId, setSelectedSubAccountId] = useState<string | null>(null);
  const [showConductor, setShowConductor] = useState(true);
  const [showAgents, setShowAgents] = useState(false);
  const [showMarketplace, setShowMarketplace] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [showSwarm, setShowSwarm] = useState(false);
  const [showDeveloper, setShowDeveloper] = useState(false);
  const [showWorkflow, setShowWorkflow] = useState(false);
  const [showNervousSystem, setShowNervousSystem] = useState(false);
  const [showEmail, setShowEmail] = useState(false);
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [oauthResult, setOauthResult] = useState<string | null>(null);
  const [proactiveEnabled, setProactiveEnabled] = useState(false);
  const [showCommandBar, setShowCommandBar] = useState(false);
  const [showAddWizard, setShowAddWizard] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  /** Load real data from the backend on mount, falling back to mock data. */
  useEffect(() => {
    async function loadRealData() {
      try {
        const [subsRes, eventsRes, agentsData] = await Promise.all([
          fetch("/api/a-cal/sub-accounts"),
          fetch("/api/a-cal/calendar/unified?days=7"),
          api.listAgents().catch(() => null),
        ]);
        if (subsRes.ok) {
          const subs = await subsRes.json();
          if (subs.length > 0) {
            setSubAccounts(subs);
            setVisibleSubAccounts(new Set(subs.filter((s: SubAccount) => !s.is_main).map((s: SubAccount) => s.id)));
          }
        }
        if (eventsRes.ok) {
          const evs = await eventsRes.json();
          if (evs.length > 0) setEvents(evs);
        }
        if (agentsData && agentsData.length > 0) {
          setAgents(agentsData);
        }

        // Warm up the local LLM model in the background so the first
        // chat message is fast. Fire-and-forget — if it fails, the first
        // real request will cold-start the model (just slower).
        fetch("/api/a-cal/settings/preload-model", { method: "POST" }).catch(() => {});

        // Check if proactive suggestions are enabled
        try {
          const smResp = await fetch("/api/a-cal/settings/self-model");
          if (smResp.ok) {
            const sm = await smResp.json();
            setProactiveEnabled(sm.proactive_suggestions_enabled && sm.feed_into_proactive);
          }
        } catch {
          // keep default (false)
        }
      } catch {
        // Backend not running — use mock data (already set)
      }
    }
    loadRealData();
  }, []);

  /** Handle OAuth callback redirect (?oauth_result=success|error|denied). */
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const result = params.get("oauth_result");
    if (result) {
      setOauthResult(result);
      // Clean the URL so the notification doesn't persist on refresh
      const url = new URL(window.location.href);
      url.searchParams.delete("oauth_result");
      url.searchParams.delete("provider_id");
      url.searchParams.delete("error");
      window.history.replaceState({}, "", url.toString());
      // Auto-dismiss after 5 seconds
      const timer = setTimeout(() => setOauthResult(null), 5000);
      return () => clearTimeout(timer);
    }
  }, []);

  /** Listen for cmd+k / ctrl+k to open the command bar. */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setShowCommandBar((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  /** Trigger sync for all sub-accounts. */
  const handleSyncAll = useCallback(async () => {
    for (const sub of subAccounts) {
      if (sub.is_main) continue;
      try {
        await api.triggerSync(sub.id);
      } catch {
        // continue to next sub-account
      }
    }
    // Refresh events after sync
    try {
      const res = await fetch("/api/a-cal/calendar/unified?days=7");
      if (res.ok) {
        const evs = await res.json();
        if (evs.length > 0) setEvents(evs);
      }
    } catch {
      // keep current events
    }
  }, [subAccounts]);

  /** Switch skill mode and persist to backend. */
  const handleModeChange = async (newMode: SkillMode) => {
    setMode(newMode);
    try {
      await api.setMode(newMode);
    } catch {
      // Backend not running — local state already updated
    }
  };

  const toggleVisible = (id: string) => {
    setVisibleSubAccounts((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  /** Update a sub-account in local state after a backend PATCH. */
  const handleSubAccountUpdated = (updated: SubAccount) => {
    setSubAccounts((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
  };

  /** Remove a sub-account from local state after deletion. */
  const handleSubAccountDeleted = (id: string) => {
    setSubAccounts((prev) => prev.filter((s) => s.id !== id));
    setVisibleSubAccounts((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    if (selectedSubAccountId === id) setSelectedSubAccountId(null);
  };

  /** Handle new sub-account created by the wizard — add to state and select it. */
  const handleSubAccountCreated = (sub: SubAccount) => {
    setSubAccounts((prev) => [...prev, sub]);
    setVisibleSubAccounts((prev) => new Set(prev).add(sub.id));
    setSelectedSubAccountId(sub.id);
  };

  const agentCount = agents.length;
  const connectedProviders = useMemo(
    () => Object.values(providers).flat().filter((p) => p.status === "connected").length,
    [providers]
  );

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Left sidebar — branding + sub-accounts */}
      <aside className={cn(
        "w-64 shrink-0 border-r border-[var(--border)] flex-col bg-[var(--card)] z-50",
        "fixed inset-y-0 left-0 transition-transform md:static md:translate-x-0 md:flex",
        mobileSidebarOpen ? "translate-x-0 flex" : "-translate-x-0 md:translate-x-0",
        !mobileSidebarOpen && "hidden md:flex",
      )}>
        {/* Logo */}
        <div className="px-4 py-4 border-b border-[var(--border)] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-[var(--primary)] flex items-center justify-center">
              <Sparkles size={18} className="text-[var(--primary-foreground)]" />
            </div>
            <div>
              <div className="font-bold text-base">A-Cal</div>
              <div className="text-xs text-[var(--muted-foreground)]">Agentic Calendar</div>
            </div>
          </div>
          <button
            onClick={() => setMobileSidebarOpen(false)}
            className="md:hidden p-1.5 rounded-md hover:bg-[var(--accent)]"
            title="Close menu"
          >
            <X size={16} />
          </button>
        </div>

        {/* Sub-account sidebar */}
        <div className="flex-1 overflow-hidden">
          <SubAccountSidebar
            subAccounts={subAccounts}
            providers={providers}
            visibleSubAccounts={visibleSubAccounts}
            onToggleVisible={toggleVisible}
            onSelectSubAccount={setSelectedSubAccountId}
            selectedSubAccountId={selectedSubAccountId}
            onAddAccount={() => setShowAddWizard(true)}
            onSubAccountUpdated={handleSubAccountUpdated}
            onSubAccountDeleted={handleSubAccountDeleted}
          />
        </div>

        {/* Bottom nav */}
        <div className="border-t border-[var(--border)] px-2 py-2 space-y-1">
          <button
            onClick={() => setShowAgents(!showAgents)}
            className="w-full flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-[var(--accent)] transition-colors"
          >
            <Bot size={15} className="text-[var(--muted-foreground)]" />
            <span>Agents</span>
            <Badge className="ml-auto bg-[var(--secondary)] text-[var(--secondary-foreground)] text-[10px]">
              {agentCount}
            </Badge>
          </button>
          {mode !== "simple" && (
            <button
              onClick={() => setShowEmail(true)}
              className="w-full flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-[var(--accent)] transition-colors"
            >
              <Mail size={15} className="text-[var(--muted-foreground)]" />
              <span>Email</span>
            </button>
          )}
          <button
            onClick={() => setShowAnalytics(true)}
            className="w-full flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-[var(--accent)] transition-colors"
          >
            <BarChart3 size={15} className="text-[var(--muted-foreground)]" />
            <span>Analytics</span>
          </button>
          <button
            onClick={() => setShowMarketplace(true)}
            className="w-full flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-[var(--accent)] transition-colors"
          >
            <Store size={15} className="text-[var(--muted-foreground)]" />
            <span>Marketplace</span>
          </button>
          {mode !== "simple" && (
            <button
              onClick={() => setShowProfile(true)}
              className="w-full flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-[var(--accent)] transition-colors"
            >
              <User size={15} className="text-[var(--muted-foreground)]" />
              <span>My Profile</span>
            </button>
          )}
          {mode !== "simple" && (
            <button
              onClick={() => setShowSwarm(true)}
              className="w-full flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-[var(--accent)] transition-colors"
            >
              <Network size={15} className="text-[var(--muted-foreground)]" />
              <span>Swarm</span>
            </button>
          )}
          {mode !== "simple" && (
            <button
              onClick={() => setShowNervousSystem(true)}
              className="w-full flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-[var(--accent)] transition-colors"
            >
              <Brain size={15} className="text-[var(--muted-foreground)]" />
              <span>Nervous System</span>
            </button>
          )}
          {mode !== "simple" && (
            <button
              onClick={() => setShowWorkflow(true)}
              className="w-full flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-[var(--accent)] transition-colors"
            >
              <Workflow size={15} className="text-[var(--muted-foreground)]" />
              <span>Workflow Builder</span>
            </button>
          )}
          {mode === "developer" && (
            <button
              onClick={() => setShowDeveloper(true)}
              className="w-full flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-[var(--accent)] transition-colors"
            >
              <Code2 size={15} className="text-[var(--muted-foreground)]" />
              <span>Developer Studio</span>
            </button>
          )}
          <button
            onClick={() => setDark(!dark)}
            className="w-full flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-[var(--accent)] transition-colors"
          >
            {dark ? <Moon size={15} /> : <Sun size={15} />}
            <span>{dark ? "Dark" : "Light"}</span>
          </button>
        </div>
      </aside>

      {/* Mobile sidebar backdrop */}
      {mobileSidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 md:hidden"
          onClick={() => setMobileSidebarOpen(false)}
        />
      )}

      {/* Center — calendar */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileSidebarOpen(true)}
              className="md:hidden p-1.5 rounded-md hover:bg-[var(--accent)]"
              title="Open menu"
            >
              <Menu size={18} />
            </button>
            <div className="flex rounded-md border border-[var(--border)] overflow-hidden">
              {(["simple", "pro", "developer"] as SkillMode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => handleModeChange(m)}
                  className={`px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
                    mode === m
                      ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                      : "hover:bg-[var(--accent)]"
                  } ${m !== "simple" ? "border-l border-[var(--border)]" : ""}`}
                >
                  {m}
                </button>
              ))}
            </div>
            <Badge className="bg-[var(--secondary)] text-[var(--secondary-foreground)] text-xs">
              {connectedProviders} providers connected
            </Badge>
            {mode !== "simple" && (
              <Badge className="bg-[var(--cal-personal)]/15 text-[var(--cal-personal)] text-xs">
                <Sparkles size={10} className="mr-1" />
                {agentCount} agents active
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant={showConductor ? "default" : "outline"}
              size="sm"
              onClick={() => setShowConductor(!showConductor)}
            >
              <Bot size={14} />
              Conductor
            </Button>
            <Button variant="ghost" size="icon" onClick={() => setShowSettings(true)}>
              <Settings size={18} />
            </Button>
          </div>
        </div>

        {/* OAuth result notification */}
        {oauthResult && (
          <div className={cn(
            "px-4 py-2 text-sm flex items-center gap-2 border-b",
            oauthResult === "success" && "bg-[var(--cal-personal)]/10 text-[var(--cal-personal)] border-[var(--cal-personal)]/20",
            oauthResult === "denied" && "bg-[var(--muted)]/30 text-[var(--muted-foreground)] border-[var(--border)]",
            oauthResult === "error" && "bg-[var(--destructive)]/10 text-[var(--destructive)] border-[var(--destructive)]/20",
          )}>
            {oauthResult === "success" && "Provider connected successfully."}
            {oauthResult === "denied" && "Authorization was denied."}
            {oauthResult === "error" && "Connection failed — check your OAuth client ID in Developer mode."}
            <button
              onClick={() => setOauthResult(null)}
              className="ml-auto text-xs opacity-60 hover:opacity-100"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Calendar + conductor */}
        <div className="flex flex-1 overflow-hidden">
          <div className="flex-1 overflow-hidden">
            <CalendarView
              events={events}
              subAccounts={subAccounts}
              visibleSubAccounts={visibleSubAccounts}
              onEventCreated={async () => {
                try {
                  const res = await fetch("/api/a-cal/calendar/unified?days=7");
                  if (res.ok) {
                    const evs = await res.json();
                    if (evs.length > 0) setEvents(evs);
                  }
                } catch {
                  // keep current events on error
                }
              }}
              onEventUpdated={async () => {
                try {
                  const res = await fetch("/api/a-cal/calendar/unified?days=7");
                  if (res.ok) {
                    const evs = await res.json();
                    if (evs.length > 0) setEvents(evs);
                  }
                } catch {
                  // keep current events on error
                }
              }}
            />
          </div>
          {showConductor && (
            <div className={cn(
              "shrink-0 border-l border-[var(--border)] bg-[var(--card)]",
              "w-[380px] max-w-[85vw]",
            )}>
              <ConductorPanel />
            </div>
          )}
        </div>
      </main>

      {/* Settings overlay */}
      {showSettings && (
        <SettingsPanel
          mode={mode}
          onModeChange={handleModeChange}
          onClose={() => setShowSettings(false)}
        />
      )}

      {/* Agents overlay */}
      {showAgents && (
        <AgentsOverlay agents={agents} onClose={() => setShowAgents(false)} />
      )}

      {/* Email overlay */}
      {showEmail && (
        <SlideInOverlay title="Email" icon={<Mail size={18} className="text-[var(--primary)]" />} onClose={() => setShowEmail(false)}>
          <EmailPanel />
        </SlideInOverlay>
      )}

      {/* Analytics overlay */}
      {showAnalytics && (
        <SlideInOverlay title="Analytics" icon={<BarChart3 size={18} className="text-[var(--primary)]" />} onClose={() => setShowAnalytics(false)}>
          <AnalyticsPanel />
        </SlideInOverlay>
      )}

      {/* Marketplace overlay */}
      {showMarketplace && (
        <SlideInOverlay title="Marketplace" icon={<Store size={18} className="text-[var(--primary)]" />} onClose={() => setShowMarketplace(false)}>
          <MarketplacePanel mode={mode} />
        </SlideInOverlay>
      )}

      {/* Community profile overlay */}
      {showProfile && (
        <SlideInOverlay title="My Profile" icon={<User size={18} className="text-[var(--primary)]" />} onClose={() => setShowProfile(false)}>
          <CommunityProfilePanel />
        </SlideInOverlay>
      )}

      {/* Swarm overlay */}
      {showSwarm && (
        <SlideInOverlay title="Swarm Negotiations" icon={<Network size={18} className="text-[var(--primary)]" />} onClose={() => setShowSwarm(false)}>
          <SwarmPanel />
        </SlideInOverlay>
      )}

      {/* Workflow Builder overlay */}
      {showWorkflow && (
        <SlideInOverlay title="Workflow Builder" icon={<Workflow size={18} className="text-[var(--primary)]" />} onClose={() => setShowWorkflow(false)}>
          <WorkflowBuilder />
        </SlideInOverlay>
      )}

      {/* Nervous System overlay */}
      {showNervousSystem && (
        <SlideInOverlay title="Nervous System" icon={<Brain size={18} className="text-[var(--primary)]" />} onClose={() => setShowNervousSystem(false)}>
          <NervousSystemPanel />
        </SlideInOverlay>
      )}

      {/* Developer Studio overlay */}
      {showDeveloper && (
        <SlideInOverlay title="Developer Studio" icon={<Code2 size={18} className="text-[var(--primary)]" />} onClose={() => setShowDeveloper(false)}>
          <DeveloperPanel />
        </SlideInOverlay>
      )}

      {/* Contextual command bar — cmd+k palette */}
      <CommandBar
        open={showCommandBar}
        onClose={() => setShowCommandBar(false)}
        onOpenSettings={() => setShowSettings(true)}
        onOpenMarketplace={() => setShowMarketplace(true)}
        onOpenEmail={() => setShowEmail(true)}
        onOpenAnalytics={() => setShowAnalytics(true)}
        onOpenConductor={() => setShowConductor(true)}
        onSyncCalendars={handleSyncAll}
        mode={mode}
      />

      {/* Proactive suggestions — floating notifications */}
      <ProactiveSuggestions enabled={proactiveEnabled} />

      {/* Add Sub-Calendar wizard */}
      {showAddWizard && (
        <AddAccountWizard
          onClose={() => setShowAddWizard(false)}
          onCreated={handleSubAccountCreated}
        />
      )}
    </div>
  );
}

/** Reusable slide-in overlay panel with backdrop, header, and close button. */
function SlideInOverlay({
  title,
  icon,
  children,
  onClose,
}: {
  title: string;
  icon: ReactNode;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex bg-black/40" onClick={onClose}>
      <div
        className="ml-auto w-[560px] max-w-[90vw] h-full bg-[var(--card)] shadow-2xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
          <div className="flex items-center gap-2">
            {icon}
            <h2 className="text-lg font-semibold">{title}</h2>
          </div>
          <button onClick={onClose} className="text-[var(--muted-foreground)] hover:text-[var(--foreground)] text-xl">
            &times;
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {children}
        </div>
      </div>
    </div>
  );
}

function AgentsOverlay({ agents, onClose }: { agents: AgentSpec[]; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex bg-black/40" onClick={onClose}>
      <div
        className="ml-auto w-[480px] max-w-[90vw] h-full bg-[var(--card)] shadow-2xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
          <div className="flex items-center gap-2">
            <Bot size={18} className="text-[var(--primary)]" />
            <h2 className="text-lg font-semibold">Agents</h2>
            <Badge className="ml-1 bg-[var(--primary)]/15 text-[var(--primary)] text-xs">
              {agents.length}
            </Badge>
          </div>
          <button onClick={onClose} className="text-[var(--muted-foreground)] hover:text-[var(--foreground)] text-xl">
            &times;
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {agents.map((agent) => (
            <div key={agent.name} className="rounded-lg border border-[var(--border)] p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-[var(--primary)]/15 flex items-center justify-center">
                    <Bot size={15} className="text-[var(--primary)]" />
                  </div>
                  <div>
                    <div className="font-medium text-sm">{agent.display_name}</div>
                    <div className="text-xs text-[var(--muted-foreground)]">{agent.default_tier} tier</div>
                  </div>
                </div>
                <div className="flex gap-1">
                  {agent.privacy_force_local && (
                    <Badge className="bg-[var(--destructive)]/15 text-[var(--destructive)] text-[10px]">local</Badge>
                  )}
                  {agent.can_negotiate && (
                    <Badge className="bg-[var(--cal-personal)]/15 text-[var(--cal-personal)] text-[10px]">P2P</Badge>
                  )}
                </div>
              </div>
              <p className="text-xs text-[var(--muted-foreground)] mb-2">{agent.description}</p>
              <div className="flex flex-wrap gap-1">
                {agent.capabilities.map((cap) => (
                  <Badge key={cap} className="bg-[var(--secondary)] text-[var(--secondary-foreground)] text-[10px]">
                    {cap.replace(/_/g, " ")}
                  </Badge>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
