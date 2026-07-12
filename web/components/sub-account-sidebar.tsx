"use client";

import { useState } from "react";
import {
  Calendar,
  Mail,
  Layers,
  CircleDot,
  CheckCircle2,
  AlertCircle,
  Clock,
  Plus,
  Trash2,
  Bot,
  ChevronDown,
  Check,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn, colorFromString } from "@/lib/utils";
import { api } from "@/lib/api";
import type { SubAccount, ProviderConnection, SyncMode } from "@/types";
import { SyncRulesEditor } from "@/components/sync-rules-editor";

interface SubAccountSidebarProps {
  subAccounts: SubAccount[];
  providers: Record<string, ProviderConnection[]>;
  visibleSubAccounts: Set<string>;
  onToggleVisible: (id: string) => void;
  onSelectSubAccount: (id: string) => void;
  selectedSubAccountId: string | null;
  onAddAccount: () => void;
  onSubAccountUpdated: (sub: SubAccount) => void;
  onSubAccountDeleted: (id: string) => void;
}

const providerIcons: Record<string, typeof Calendar> = {
  google_calendar: Calendar,
  outlook_calendar: Calendar,
  caldav: Layers,
  gmail: Mail,
  imap_smtp: Mail,
};

const SYNC_MODE_LABELS: Record<SyncMode, string> = {
  mirror_filter: "Mirror + Filter",
  intelligent_merge: "Intelligent Merge",
  layered_federation: "Layered Federation",
  per_sub_agent: "Per Sub-Agent",
};

const SYNC_MODES: SyncMode[] = ["mirror_filter", "intelligent_merge", "layered_federation", "per_sub_agent"];

function statusIcon(status: string) {
  switch (status) {
    case "connected": return <CheckCircle2 size={12} className="text-[var(--cal-personal)]" />;
    case "pending": return <Clock size={12} className="text-[var(--cal-email)]" />;
    case "error": return <AlertCircle size={12} className="text-[var(--destructive)]" />;
    default: return <CircleDot size={12} className="text-[var(--muted-foreground)]" />;
  }
}

export function SubAccountSidebar({
  subAccounts,
  providers,
  visibleSubAccounts,
  onToggleVisible,
  onSelectSubAccount,
  selectedSubAccountId,
  onAddAccount,
  onSubAccountUpdated,
  onSubAccountDeleted,
}: SubAccountSidebarProps) {
  const [showSyncMenu, setShowSyncMenu] = useState(false);
  const [updating, setUpdating] = useState(false);

  const mainAccount = subAccounts.find((s) => s.is_main);
  const subAccountsList = subAccounts.filter((s) => !s.is_main);
  const selected = subAccounts.find((s) => s.id === selectedSubAccountId);

  /** Update sync mode for the selected sub-account. */
  const handleSyncModeChange = async (mode: SyncMode) => {
    if (!selected) return;
    setShowSyncMenu(false);
    setUpdating(true);
    try {
      const updated = await api.updateSubAccount(selected.id, { sync_mode: mode });
      onSubAccountUpdated(updated);
    } catch {
      // Backend not running — update locally
      onSubAccountUpdated({ ...selected, sync_mode: mode });
    } finally {
      setUpdating(false);
    }
  };

  /** Toggle agent for the selected sub-account. */
  const handleAgentToggle = async () => {
    if (!selected) return;
    setUpdating(true);
    try {
      const updated = await api.updateSubAccount(selected.id, {
        agent_enabled: !selected.agent_enabled,
      });
      onSubAccountUpdated(updated);
    } catch {
      onSubAccountUpdated({ ...selected, agent_enabled: !selected.agent_enabled });
    } finally {
      setUpdating(false);
    }
  };

  /** Delete the selected sub-account. */
  const handleDelete = async () => {
    if (!selected) return;
    setUpdating(true);
    try {
      await api.deleteSubAccount(selected.id);
    } catch {
      // Backend not running — delete locally
    }
    onSubAccountDeleted(selected.id);
    setUpdating(false);
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Main account */}
      {mainAccount && (
        <div className="px-3 py-3 border-b border-[var(--border)]">
          <div className="flex items-center gap-2 mb-1">
            <Layers size={16} className="text-[var(--primary)]" />
            <span className="text-sm font-semibold">{mainAccount.name}</span>
            <Badge className="ml-auto bg-[var(--primary)]/15 text-[var(--primary)] text-[10px]">
              Main
            </Badge>
          </div>
          <p className="text-xs text-[var(--muted-foreground)] pl-6">
            Unified conductor view
          </p>
        </div>
      )}

      {/* Sub-accounts */}
      <div className="flex-1 px-2 py-2 space-y-1">
        <div className="text-xs font-medium text-[var(--muted-foreground)] uppercase px-2 py-1">
          Sub-Calendars
        </div>
        {subAccountsList.map((sa) => {
          const color = colorFromString(sa.id);
          const saProviders = providers[sa.id] || [];
          const isVisible = visibleSubAccounts.has(sa.id);
          const isSelected = selectedSubAccountId === sa.id;
          const Icon = sa.kind === "email" ? Mail : Calendar;

          return (
            <div key={sa.id}>
              <div
                className={cn(
                  "flex items-center gap-2 rounded-md px-2 py-1.5 cursor-pointer transition-colors",
                  isSelected ? "bg-[var(--accent)]" : "hover:bg-[var(--accent)]/50"
                )}
                onClick={() => onSelectSubAccount(sa.id)}
              >
                <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: color }} />
                <Icon size={14} className="text-[var(--muted-foreground)] shrink-0" />
                <span className="text-sm truncate flex-1">{sa.name}</span>
                <button
                  role="switch"
                  aria-checked={isVisible}
                  onClick={(e) => { e.stopPropagation(); onToggleVisible(sa.id); }}
                  className={cn(
                    "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors",
                    isVisible ? "bg-[var(--primary)]" : "bg-[var(--secondary)]"
                  )}
                >
                  <span className={cn(
                    "pointer-events-none block h-4 w-4 rounded-full bg-white shadow-lg transition-transform",
                    isVisible ? "translate-x-4" : "translate-x-0"
                  )} />
                </button>
              </div>

              {/* Expanded controls for selected sub-account */}
              {isSelected && (
                <div className="ml-3 mt-1 mb-2 space-y-2 border-l-2 border-[var(--border)] pl-3">
                  {/* Provider connections */}
                  {saProviders.length > 0 && (
                    <div className="space-y-1">
                      {saProviders.map((p) => {
                        const PIcon = providerIcons[p.provider_type] || Calendar;
                        return (
                          <div key={p.id} className="flex items-center gap-2 px-2 py-1 text-xs">
                            <PIcon size={12} className="text-[var(--muted-foreground)]" />
                            <span className="truncate flex-1">{p.display_name || p.provider_account_id}</span>
                            {statusIcon(p.status)}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Sync mode selector */}
                  <div className="relative">
                    <button
                      onClick={() => setShowSyncMenu(!showSyncMenu)}
                      className="flex items-center gap-1.5 w-full px-2 py-1.5 text-xs rounded-md border border-[var(--border)] hover:bg-[var(--accent)]/50 transition-colors"
                      disabled={updating}
                    >
                      <span className="font-medium">Sync:</span>
                      <span className="text-[var(--muted-foreground)] flex-1 text-left">
                        {SYNC_MODE_LABELS[sa.sync_mode]}
                      </span>
                      <ChevronDown size={12} className="text-[var(--muted-foreground)]" />
                    </button>
                    {showSyncMenu && (
                      <div className="absolute z-20 left-0 right-0 mt-1 rounded-md border border-[var(--border)] bg-[var(--card)] shadow-lg overflow-hidden">
                        {SYNC_MODES.map((mode) => (
                          <button
                            key={mode}
                            onClick={() => handleSyncModeChange(mode)}
                            className={cn(
                              "flex items-center gap-2 w-full px-3 py-2 text-xs text-left hover:bg-[var(--accent)]/50 transition-colors",
                              sa.sync_mode === mode && "bg-[var(--primary)]/8 font-medium"
                            )}
                          >
                            {SYNC_MODE_LABELS[mode]}
                            {sa.sync_mode === mode && <Check size={12} className="ml-auto text-[var(--primary)]" />}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Agent toggle */}
                  <div className="flex items-center gap-2 px-2 py-1.5">
                    <Bot size={12} className={cn(sa.agent_enabled ? "text-[var(--primary)]" : "text-[var(--muted-foreground)]")} />
                    <span className="text-xs flex-1">Agent</span>
                    <button
                      role="switch"
                      aria-checked={sa.agent_enabled}
                      onClick={handleAgentToggle}
                      disabled={updating}
                      className={cn(
                        "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors",
                        sa.agent_enabled ? "bg-[var(--primary)]" : "bg-[var(--secondary)]"
                      )}
                    >
                      <span className={cn(
                        "pointer-events-none block h-4 w-4 rounded-full bg-white shadow-lg transition-transform",
                        sa.agent_enabled ? "translate-x-4" : "translate-x-0"
                      )} />
                    </button>
                  </div>

                  {/* Sync rules */}
                  <SyncRulesEditor subAccount={sa} />

                  {/* Delete */}
                  <button
                    onClick={handleDelete}
                    disabled={updating}
                    className="flex items-center gap-1.5 px-2 py-1.5 text-xs text-[var(--destructive)] hover:bg-[var(--destructive)]/8 rounded-md transition-colors w-full"
                  >
                    <Trash2 size={12} />
                    Remove sub-calendar
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Add account button */}
      <div className="px-2 py-2 border-t border-[var(--border)]">
        <button
          onClick={onAddAccount}
          className="flex items-center gap-2 w-full px-3 py-2 rounded-md text-sm text-[var(--primary)] hover:bg-[var(--primary)]/8 transition-colors font-medium"
        >
          <Plus size={16} />
          Add Sub-Calendar
        </button>
      </div>
    </div>
  );
}
