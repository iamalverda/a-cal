"use client";

import { useMemo } from "react";
import {
  Calendar,
  Mail,
  Layers,
  CircleDot,
  CheckCircle2,
  AlertCircle,
  Clock,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { cn, colorFromString } from "@/lib/utils";
import type { SubAccount, ProviderConnection } from "@/types";

interface SubAccountSidebarProps {
  subAccounts: SubAccount[];
  providers: Record<string, ProviderConnection[]>;
  visibleSubAccounts: Set<string>;
  onToggleVisible: (id: string) => void;
  onSelectSubAccount: (id: string) => void;
  selectedSubAccountId: string | null;
}

const providerIcons: Record<string, typeof Calendar> = {
  google_calendar: Calendar,
  outlook_calendar: Calendar,
  caldav: Layers,
  gmail: Mail,
  imap_smtp: Mail,
};

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
}: SubAccountSidebarProps) {
  const mainAccount = subAccounts.find((s) => s.is_main);
  const subAccountsList = subAccounts.filter((s) => !s.is_main);

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
                <Switch checked={isVisible} onChange={() => onToggleVisible(sa.id)} />
              </div>
              {/* Provider connections */}
              {isSelected && saProviders.length > 0 && (
                <div className="ml-6 mt-1 space-y-1">
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
              {/* Sync mode badge */}
              {isSelected && (
                <div className="ml-6 mt-1 px-2">
                  <Badge className="bg-[var(--secondary)] text-[var(--secondary-foreground)] text-[10px]">
                    {sa.sync_mode.replace(/_/g, " ")}
                  </Badge>
                  {sa.agent_enabled && (
                    <Badge className="ml-1 bg-[var(--primary)]/15 text-[var(--primary)] text-[10px]">
                      Agent on
                    </Badge>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
