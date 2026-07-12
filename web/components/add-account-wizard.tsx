"use client";

import { useState } from "react";
import {
  Calendar,
  Mail,
  Layers,
  Plus,
  X,
  ArrowRight,
  ArrowLeft,
  Check,
  Loader2,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { api, oauthApi } from "@/lib/api";
import type { SubAccount, ProviderType, SyncMode } from "@/types";

const PROVIDER_OPTIONS: Array<{
  type: ProviderType;
  label: string;
  icon: typeof Calendar;
  description: string;
  oauth: boolean;
  configFields?: Array<{ key: string; label: string; placeholder: string; type?: string }>;
}> = [
  {
    type: "google_calendar",
    label: "Google Calendar",
    icon: Calendar,
    description: "Connect via OAuth — syncs all calendars on your Google account",
    oauth: true,
  },
  {
    type: "outlook_calendar",
    label: "Outlook Calendar",
    icon: Calendar,
    description: "Connect via Microsoft OAuth — syncs all Outlook calendars",
    oauth: true,
  },
  {
    type: "caldav",
    label: "CalDAV Server",
    icon: Layers,
    description: "Any CalDAV-compatible server (Radicale, Nextcloud, Fastmail, etc.)",
    oauth: false,
    configFields: [
      { key: "url", label: "CalDAV Server URL", placeholder: "https://cal.example.com/dav" },
      { key: "username", label: "Username", placeholder: "your@email.com" },
      { key: "password", label: "Password / App Password", placeholder: "••••••••", type: "password" },
    ],
  },
  {
    type: "gmail",
    label: "Gmail",
    icon: Mail,
    description: "Connect via OAuth — read and send email through Gmail",
    oauth: true,
  },
  {
    type: "imap_smtp",
    label: "IMAP / SMTP",
    icon: Mail,
    description: "Any email provider with IMAP/SMTP access",
    oauth: false,
    configFields: [
      { key: "imap_host", label: "IMAP Host", placeholder: "imap.example.com" },
      { key: "imap_port", label: "IMAP Port", placeholder: "993" },
      { key: "smtp_host", label: "SMTP Host", placeholder: "smtp.example.com" },
      { key: "smtp_port", label: "SMTP Port", placeholder: "587" },
      { key: "username", label: "Username", placeholder: "your@email.com" },
      { key: "password", label: "Password / App Password", placeholder: "••••••••", type: "password" },
    ],
  },
];

const SYNC_MODES: Array<{
  value: SyncMode;
  label: string;
  description: string;
}> = [
  {
    value: "mirror_filter",
    label: "Mirror + Filter",
    description: "Copy all events to main calendar, then filter what shows. Simple and predictable.",
  },
  {
    value: "intelligent_merge",
    label: "Intelligent Merge",
    description: "Agent merges events into main calendar, resolving duplicates and suggesting optimal slots.",
  },
  {
    value: "layered_federation",
    label: "Layered Federation",
    description: "Keep events on sub-calendar, show as overlay on main. Full separation with visibility control.",
  },
  {
    value: "per_sub_agent",
    label: "Per Sub-Agent",
    description: "Dedicated agent manages this sub-calendar autonomously. Negotiates with other agents for conflicts.",
  },
];

interface AddAccountWizardProps {
  onClose: () => void;
  onCreated: (subAccount: SubAccount) => void;
}

export function AddAccountWizard({ onClose, onCreated }: AddAccountWizardProps) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [providerType, setProviderType] = useState<ProviderType | null>(null);
  const [syncMode, setSyncMode] = useState<SyncMode>("mirror_filter");
  const [agentEnabled, setAgentEnabled] = useState(false);
  const [configValues, setConfigValues] = useState<Record<string, string>>({});
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdSub, setCreatedSub] = useState<SubAccount | null>(null);
  const [providerId, setProviderId] = useState<string | null>(null);

  const selectedProvider = PROVIDER_OPTIONS.find((p) => p.type === providerType);
  const isEmailProvider = providerType === "gmail" || providerType === "imap_smtp";

  const handleCreate = async () => {
    if (!providerType) return;
    setCreating(true);
    setError(null);
    try {
      const sub = await api.createSubAccount({
        name: name || `${selectedProvider?.label ?? "New"} Account`,
        kind: isEmailProvider ? "email" : "calendar",
        sync_mode: syncMode,
        agent_enabled: agentEnabled,
      });

      const provider = await api.createProvider({
        sub_account_id: sub.id,
        provider_type: providerType,
        provider_account_id: configValues.username || configValues.url || sub.id,
        display_name: name || selectedProvider?.label,
        config: configValues,
      });

      setCreatedSub(sub);
      setProviderId(provider.id);
      setStep(3);
      onCreated(sub);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create account");
    } finally {
      setCreating(false);
    }
  };

  const handleOAuthConnect = async () => {
    if (!providerId) return;
    try {
      const result = await oauthApi.start(providerId);
      window.location.href = result.authorization_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start OAuth flow");
    }
  };

  const canProceed = (s: number): boolean => {
    if (s === 0) return name.trim().length > 0;
    if (s === 1) return providerType !== null;
    if (s === 2) {
      if (!selectedProvider) return false;
      if (selectedProvider.oauth) return true;
      return (selectedProvider.configFields ?? []).every(
        (f) => (configValues[f.key] ?? "").trim().length > 0
      );
    }
    return false;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="w-[520px] max-w-[92vw] max-h-[88vh] bg-[var(--card)] rounded-xl shadow-2xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
          <div className="flex items-center gap-2">
            <Plus size={18} className="text-[var(--primary)]" />
            <h2 className="text-lg font-semibold">Add Sub-Calendar</h2>
          </div>
          <button onClick={onClose} className="text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
            <X size={20} />
          </button>
        </div>

        {/* Step indicator */}
        {step < 3 && (
          <div className="flex items-center gap-2 px-5 py-3 border-b border-[var(--border)]">
            {["Name", "Provider", "Configure"].map((label, i) => (
              <div key={label} className="flex items-center gap-2">
                <div
                  className={cn(
                    "w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium transition-colors",
                    i < step && "bg-[var(--primary)] text-[var(--primary-foreground)]",
                    i === step && "bg-[var(--primary)] text-[var(--primary-foreground)] ring-2 ring-[var(--primary)]/30",
                    i > step && "bg-[var(--secondary)] text-[var(--muted-foreground)]"
                  )}
                >
                  {i < step ? <Check size={14} /> : i + 1}
                </div>
                <span className={cn("text-xs", i === step ? "text-[var(--foreground)] font-medium" : "text-[var(--muted-foreground)]")}>
                  {label}
                </span>
                {i < 2 && <div className="w-6 h-px bg-[var(--border)] mx-1" />}
              </div>
            ))}
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {/* Step 0: Name */}
          {step === 0 && (
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium block mb-2">What do you want to call this sub-calendar?</label>
                <Input
                  autoFocus
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Work Google, Personal, Side Project Email"
                  onKeyDown={(e) => { if (e.key === "Enter" && canProceed(0)) setStep(1); }}
                />
                <p className="text-xs text-[var(--muted-foreground)] mt-2">
                  This name appears in your sidebar. You can rename it later.
                </p>
              </div>
            </div>
          )}

          {/* Step 1: Provider selection */}
          {step === 1 && (
            <div className="space-y-2">
              <label className="text-sm font-medium block mb-3">Choose a provider</label>
              {PROVIDER_OPTIONS.map((p) => {
                const Icon = p.icon;
                const isSelected = providerType === p.type;
                return (
                  <button
                    key={p.type}
                    onClick={() => setProviderType(p.type)}
                    className={cn(
                      "w-full flex items-start gap-3 p-3 rounded-lg border text-left transition-all",
                      isSelected
                        ? "border-[var(--primary)] bg-[var(--primary)]/8"
                        : "border-[var(--border)] hover:border-[var(--primary)]/40 hover:bg-[var(--accent)]/30"
                    )}
                  >
                    <div className={cn(
                      "w-10 h-10 rounded-lg flex items-center justify-center shrink-0",
                      isSelected ? "bg-[var(--primary)]/15" : "bg-[var(--secondary)]"
                    )}>
                      <Icon size={18} className={isSelected ? "text-[var(--primary)]" : "text-[var(--muted-foreground)]"} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{p.label}</span>
                        {p.oauth && (
                          <Badge className="bg-[var(--primary)]/15 text-[var(--primary)] text-[10px]">OAuth</Badge>
                        )}
                      </div>
                      <p className="text-xs text-[var(--muted-foreground)] mt-0.5">{p.description}</p>
                    </div>
                    {isSelected && <Check size={18} className="text-[var(--primary)] shrink-0 mt-1" />}
                  </button>
                );
              })}
            </div>
          )}

          {/* Step 2: Configure */}
          {step === 2 && selectedProvider && (
            <div className="space-y-5">
              {/* Sync mode */}
              <div>
                <label className="text-sm font-medium block mb-2">Sync Mode</label>
                <div className="grid grid-cols-2 gap-2">
                  {SYNC_MODES.map((m) => (
                    <button
                      key={m.value}
                      onClick={() => setSyncMode(m.value)}
                      className={cn(
                        "p-3 rounded-lg border text-left transition-all",
                        syncMode === m.value
                          ? "border-[var(--primary)] bg-[var(--primary)]/8"
                          : "border-[var(--border)] hover:border-[var(--primary)]/40"
                      )}
                    >
                      <div className="text-sm font-medium">{m.label}</div>
                      <p className="text-xs text-[var(--muted-foreground)] mt-1">{m.description}</p>
                    </button>
                  ))}
                </div>
              </div>

              {/* Agent toggle */}
              <div className="flex items-center justify-between p-3 rounded-lg border border-[var(--border)]">
                <div>
                  <div className="text-sm font-medium">Enable Agent</div>
                  <p className="text-xs text-[var(--muted-foreground)] mt-0.5">
                    Let the conductor agent manage this sub-calendar autonomously
                  </p>
                </div>
                <button
                  onClick={() => setAgentEnabled(!agentEnabled)}
                  className={cn(
                    "relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors",
                    agentEnabled ? "bg-[var(--primary)]" : "bg-[var(--secondary)]"
                  )}
                >
                  <span className={cn(
                    "pointer-events-none block h-5 w-5 rounded-full bg-white shadow-lg transition-transform",
                    agentEnabled ? "translate-x-5" : "translate-x-0"
                  )} />
                </button>
              </div>

              {/* Provider config fields (non-OAuth) */}
              {selectedProvider.configFields && (
                <div className="space-y-3">
                  <label className="text-sm font-medium block">Connection Details</label>
                  {selectedProvider.configFields.map((field) => (
                    <div key={field.key}>
                      <label className="text-xs text-[var(--muted-foreground)] block mb-1">{field.label}</label>
                      <Input
                        type={field.type ?? "text"}
                        value={configValues[field.key] ?? ""}
                        onChange={(e) => setConfigValues({ ...configValues, [field.key]: e.target.value })}
                        placeholder={field.placeholder}
                      />
                    </div>
                  ))}
                </div>
              )}

              {/* OAuth note */}
              {selectedProvider.oauth && (
                <div className="p-3 rounded-lg bg-[var(--primary)]/8 border border-[var(--primary)]/20">
                  <p className="text-xs text-[var(--foreground)]">
                    You will be redirected to {selectedProvider.label} to authorize access after creating the sub-calendar.
                  </p>
                </div>
              )}

              {error && (
                <div className="p-3 rounded-lg bg-[var(--destructive)]/10 border border-[var(--destructive)]/20 text-sm text-[var(--destructive)]">
                  {error}
                </div>
              )}
            </div>
          )}

          {/* Step 3: Success */}
          {step === 3 && createdSub && (
            <div className="space-y-4 text-center py-6">
              <div className="w-16 h-16 rounded-full bg-[var(--cal-personal)]/15 flex items-center justify-center mx-auto">
                <Check size={32} className="text-[var(--cal-personal)]" />
              </div>
              <div>
                <h3 className="text-lg font-semibold">Sub-calendar created</h3>
                <p className="text-sm text-[var(--muted-foreground)] mt-1">
                  &ldquo;{createdSub.name}&rdquo; is ready. {selectedProvider?.oauth ? "Now connect it to your provider." : "Your connection has been saved."}
                </p>
              </div>

              {selectedProvider?.oauth && providerId && (
                <Button onClick={handleOAuthConnect} className="w-full" size="lg">
                  <ExternalLink size={16} />
                  Connect to {selectedProvider.label}
                </Button>
              )}

              <Button onClick={onClose} variant="outline" className="w-full">
                Done
              </Button>
            </div>
          )}
        </div>

        {/* Footer navigation */}
        {step < 3 && (
          <div className="flex items-center justify-between px-5 py-4 border-t border-[var(--border)]">
            <Button
              variant="ghost"
              onClick={() => (step > 0 ? setStep(step - 1) : onClose())}
              disabled={creating}
            >
              <ArrowLeft size={16} />
              {step === 0 ? "Cancel" : "Back"}
            </Button>
            {step < 2 ? (
              <Button onClick={() => setStep(step + 1)} disabled={!canProceed(step)}>
                Next
                <ArrowRight size={16} />
              </Button>
            ) : (
              <Button onClick={handleCreate} disabled={!canProceed(2) || creating}>
                {creating ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
                {creating ? "Creating..." : "Create Sub-Calendar"}
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
