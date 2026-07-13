"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  Mail, RefreshCw, Inbox, CalendarPlus, Send, Loader2, ChevronRight,
  ScanLine, AlertTriangle, Clock, CheckCircle2, XCircle, Star, Search,
  Trash2, MailOpen, Reply, ReplyAll, Forward, X, Plus, User, Folder,
  Archive, PenSquare, CircleDot, Paperclip, FileText, Image as ImageIcon,
  Tag, Sparkles, CalendarClock, Settings, Filter, Bell, BellOff,
  ChevronDown, Palette,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type {
  EmailMessage, EmailAccount, EmailFolder, EmailAttachment,
  EmailLabel, EmailFilter, EmailSnooze, EmailTemplate, VacationConfig,
} from "@/types";

interface ExtractedTime {
  raw_text: string;
  datetime: string | null;
  duration_minutes: number | null;
  confidence: number;
}

interface SchedulingDetection {
  is_scheduling_related: boolean;
  is_meeting_proposal: boolean;
  is_calendar_invite: boolean;
  is_reschedule: boolean;
  is_cancellation: boolean;
  detected_keywords: string[];
  extracted_times: ExtractedTime[];
  proposed_by: string;
  subject: string;
  snippet: string;
  confidence: number;
}

interface SchedulingSuggestion {
  type: string;
  email_subject: string;
  email_from: string;
  proposed_time: ExtractedTime | null;
  conflict_with: string | null;
  suggested_alternative: string | null;
  confidence: number;
  message: string;
}

interface ScanResult {
  detections: SchedulingDetection[];
  suggestions: SchedulingSuggestion[];
  summary: string;
  stats: Record<string, number>;
}

const FOLDERS: { key: EmailFolder; label: string; icon: typeof Inbox }[] = [
  { key: "INBOX", label: "Inbox", icon: Inbox },
  { key: "STARRED", label: "Starred", icon: Star },
  { key: "SENT", label: "Sent", icon: Send },
  { key: "DRAFT", label: "Drafts", icon: PenSquare },
  { key: "ALL", label: "All Mail", icon: Archive },
];

const ACCOUNT_COLORS = [
  "oklch(0.62 0.18 264)",
  "oklch(0.68 0.16 165)",
  "oklch(0.72 0.14 75)",
  "oklch(0.65 0.12 330)",
  "oklch(0.60 0.15 200)",
  "oklch(0.65 0.18 30)",
];

const LABEL_COLORS = [
  "oklch(0.62 0.18 264)", "oklch(0.68 0.16 165)", "oklch(0.72 0.14 75)",
  "oklch(0.65 0.12 330)", "oklch(0.60 0.15 200)", "oklch(0.65 0.18 30)",
  "oklch(0.55 0.20 0)", "oklch(0.50 0.18 145)",
];

/** Quick snooze presets expressed as ISO-string offsets from now. */
const SNOOZE_PRESETS: { label: string; hours: number }[] = [
  { label: "Later today", hours: 4 },
  { label: "Tomorrow", hours: 24 },
  { label: "This weekend", hours: 72 },
  { label: "Next week", hours: 168 },
];

/**
 * EmailPanel — unified multi-account email inbox.
 *
 * Shows all emails from all connected accounts in one unified view, with
 * the ability to filter by individual account. Includes folder navigation
 * (Inbox, Starred, Sent, Drafts, All Mail, Snoozed), search across all
 * accounts, star/unstar, mark read/unread, delete, snooze, AI summarization,
 * and compose with account selector, templates, and scheduled send.
 *
 * The scheduling scan feature detects meeting proposals and calendar invites
 * in emails, unique to A-Cal's agentic layer. Custom labels, filters, and a
 * vacation auto-responder are managed in the settings modal.
 */
export function EmailPanel() {
  const [messages, setMessages] = useState<EmailMessage[]>([]);
  const [accounts, setAccounts] = useState<EmailAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null);
  const [folder, setFolder] = useState<EmailFolder>("INBOX");
  const [selected, setSelected] = useState<EmailMessage | null>(null);
  const [showCompose, setShowCompose] = useState(false);
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [scanning, setScanning] = useState(false);
  const [showScan, setShowScan] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [showReply, setShowReply] = useState(false);
  const [replyMode, setReplyMode] = useState<"reply" | "replyall" | "forward">("reply");
  const [replyBody, setReplyBody] = useState("");

  // Phase 4 state
  const [labels, setLabels] = useState<EmailLabel[]>([]);
  const [filters, setFilters] = useState<EmailFilter[]>([]);
  const [snoozed, setSnoozed] = useState<EmailSnooze[]>([]);
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [vacation, setVacation] = useState<VacationConfig | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showSnoozed, setShowSnoozed] = useState(false);
  const [aiSummary, setAiSummary] = useState<string | null>(null);
  const [summarizing, setSummarizing] = useState(false);
  const [showSnoozePicker, setShowSnoozePicker] = useState(false);
  const [snoozeCustomDate, setSnoozeCustomDate] = useState("");
  const [newLabelName, setNewLabelName] = useState("");
  const [newLabelColor, setNewLabelColor] = useState(LABEL_COLORS[0]);
  const [showLabelForm, setShowLabelForm] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const loadAccounts = useCallback(async () => {
    try {
      const data = await api.listEmailAccounts();
      setAccounts(data);
    } catch {
      setAccounts([]);
    }
  }, []);

  const loadMessages = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listEmailMessages({
        providerConnectionId: selectedAccount ?? undefined,
        folder,
        limit: 50,
      });
      setMessages(data);
    } catch {
      setMessages([]);
    } finally {
      setLoading(false);
    }
  }, [selectedAccount, folder]);

  const loadLabels = useCallback(async () => {
    try {
      const data = await api.listEmailLabels();
      setLabels(data);
    } catch {
      setLabels([]);
    }
  }, []);

  const loadFilters = useCallback(async () => {
    try {
      const data = await api.listEmailFilters();
      setFilters(data);
    } catch {
      setFilters([]);
    }
  }, []);

  const loadSnoozed = useCallback(async () => {
    try {
      const data = await api.listSnoozedEmails();
      setSnoozed(data);
    } catch {
      setSnoozed([]);
    }
  }, []);

  const loadTemplates = useCallback(async () => {
    try {
      const data = await api.listEmailTemplates();
      setTemplates(data);
    } catch {
      setTemplates([]);
    }
  }, []);

  const loadVacation = useCallback(async () => {
    try {
      const data = await api.getVacationConfig();
      setVacation(data);
    } catch {
      setVacation(null);
    }
  }, []);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  useEffect(() => {
    if (!showSnoozed) {
      loadMessages();
    } else {
      loadSnoozed();
    }
  }, [loadMessages, loadSnoozed, showSnoozed]);

  useEffect(() => {
    loadLabels();
    loadFilters();
    loadTemplates();
    loadVacation();
  }, [loadLabels, loadFilters, loadTemplates, loadVacation]);

  const handleScan = useCallback(async () => {
    setScanning(true);
    setShowScan(true);
    try {
      const result = await api.scanEmailForSchedule() as unknown as ScanResult;
      setScanResult(result);
    } catch {
      setScanResult(null);
    } finally {
      setScanning(false);
    }
  }, []);

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) {
      loadMessages();
      return;
    }
    setSearching(true);
    try {
      const data = await api.searchEmail({
        q: searchQuery,
        providerConnectionId: selectedAccount ?? undefined,
        limit: 50,
      });
      setMessages(data);
    } catch {
      setMessages([]);
    } finally {
      setSearching(false);
    }
  }, [searchQuery, selectedAccount, loadMessages]);

  const handleStar = useCallback(async (msg: EmailMessage, starred: boolean) => {
    setActionLoading(`star-${msg.provider_message_id}`);
    try {
      await api.starEmail({
        provider_connection_id: msg.provider_connection_id,
        provider_message_id: msg.provider_message_id,
        starred,
      });
      setMessages((prev) =>
        prev.map((m) =>
          m.provider_message_id === msg.provider_message_id &&
          m.provider_connection_id === msg.provider_connection_id
            ? { ...m, is_starred: starred, labels: starred ? [...m.labels, "STARRED"] : m.labels.filter((l) => l !== "STARRED") }
            : m
        )
      );
      if (selected?.provider_message_id === msg.provider_message_id) {
        setSelected((prev) => prev ? { ...prev, is_starred: starred } : prev);
      }
    } catch {
      // keep state on error
    } finally {
      setActionLoading(null);
    }
  }, [selected]);

  const handleMarkRead = useCallback(async (msg: EmailMessage, read: boolean) => {
    setActionLoading(`read-${msg.provider_message_id}`);
    try {
      await api.markEmailRead({
        provider_connection_id: msg.provider_connection_id,
        provider_message_id: msg.provider_message_id,
        read,
      });
      setMessages((prev) =>
        prev.map((m) =>
          m.provider_message_id === msg.provider_message_id &&
          m.provider_connection_id === msg.provider_connection_id
            ? { ...m, is_unread: !read }
            : m
        )
      );
      if (selected?.provider_message_id === msg.provider_message_id) {
        setSelected((prev) => prev ? { ...prev, is_unread: !read } : prev);
      }
    } catch {
      // keep state on error
    } finally {
      setActionLoading(null);
    }
  }, [selected]);

  const handleDelete = useCallback(async (msg: EmailMessage) => {
    setActionLoading(`del-${msg.provider_message_id}`);
    try {
      await api.deleteEmail({
        provider_connection_id: msg.provider_connection_id,
        provider_message_id: msg.provider_message_id,
      });
      setMessages((prev) =>
        prev.filter(
          (m) =>
            !(m.provider_message_id === msg.provider_message_id &&
              m.provider_connection_id === msg.provider_connection_id)
        )
      );
      if (selected?.provider_message_id === msg.provider_message_id) {
        setSelected(null);
      }
    } catch {
      // keep state on error
    } finally {
      setActionLoading(null);
    }
  }, [selected]);

  const handleSelectMessage = useCallback(async (msg: EmailMessage) => {
    setSelected(msg);
    setShowReply(false);
    setAiSummary(null);
    setShowSnoozePicker(false);
    if (msg.is_unread) {
      handleMarkRead(msg, true);
    }
  }, [handleMarkRead]);

  const handleSendReply = useCallback(async () => {
    if (!selected || !replyBody.trim()) return;
    setActionLoading("send-reply");
    try {
      const replyTo = selected.from_address;
      const subject = selected.subject.startsWith("Re:") || selected.subject.startsWith("Fwd:")
        ? selected.subject
        : replyMode === "forward"
          ? `Fwd: ${selected.subject}`
          : `Re: ${selected.subject}`;
      const toAddrs = replyMode === "replyall"
        ? [replyTo, ...selected.to_addresses].filter((v, i, a) => a.indexOf(v) === i)
        : replyMode === "forward"
          ? []
          : [replyTo];

      await api.sendEmail({
        provider_connection_id: selected.provider_connection_id,
        to: toAddrs,
        subject,
        body_text: replyBody,
      });
      setShowReply(false);
      setReplyBody("");
    } catch {
      // keep state on error
    } finally {
      setActionLoading(null);
    }
  }, [selected, replyBody, replyMode]);

  /** Create a new custom label and refresh the label list. */
  const handleCreateLabel = useCallback(async () => {
    if (!newLabelName.trim()) return;
    setActionLoading("create-label");
    try {
      await api.createEmailLabel(newLabelName.trim(), newLabelColor);
      setNewLabelName("");
      setShowLabelForm(false);
      await loadLabels();
    } catch {
      // keep state on error
    } finally {
      setActionLoading(null);
    }
  }, [newLabelName, newLabelColor, loadLabels]);

  /** Delete a custom label by id and refresh the list. */
  const handleDeleteLabel = useCallback(async (labelId: string) => {
    setActionLoading(`del-label-${labelId}`);
    try {
      await api.deleteEmailLabel(labelId);
      await loadLabels();
    } catch {
      // keep state on error
    } finally {
      setActionLoading(null);
    }
  }, [loadLabels]);

  /** Snooze the currently selected email until the given ISO timestamp. */
  const handleSnooze = useCallback(async (untilIso: string) => {
    if (!selected || !untilIso) return;
    setActionLoading(`snooze-${selected.provider_message_id}`);
    setShowSnoozePicker(false);
    try {
      await api.snoozeEmail(
        selected.provider_connection_id,
        selected.provider_message_id,
        untilIso,
      );
      // Remove from current message list
      setMessages((prev) =>
        prev.filter(
          (m) =>
            !(m.provider_message_id === selected.provider_message_id &&
              m.provider_connection_id === selected.provider_connection_id)
        )
      );
      setSelected(null);
      await loadSnoozed();
    } catch {
      // keep state on error
    } finally {
      setActionLoading(null);
    }
  }, [selected, loadSnoozed]);

  /** Remove a snooze so the email returns to the inbox. */
  const handleUnsnooze = useCallback(async (snoozeId: string) => {
    setActionLoading(`unsnooze-${snoozeId}`);
    try {
      await api.unsnoozeEmail(snoozeId);
      await loadSnoozed();
    } catch {
      // keep state on error
    } finally {
      setActionLoading(null);
    }
  }, [loadSnoozed]);

  /** Generate an AI summary of the selected email and display it inline. */
  const handleSummarize = useCallback(async () => {
    if (!selected) return;
    setSummarizing(true);
    setAiSummary(null);
    try {
      const result = await api.summarizeEmail(
        selected.body_text || selected.snippet || "",
        selected.subject,
      );
      setAiSummary(result.summary);
    } catch {
      setAiSummary("Failed to generate summary.");
    } finally {
      setSummarizing(false);
    }
  }, [selected]);

  /** Save vacation auto-responder configuration. */
  const handleSaveVacation = useCallback(async (config: VacationConfig) => {
    setActionLoading("save-vacation");
    try {
      const result = await api.updateVacationConfig(config);
      setVacation(result);
    } catch {
      // keep state on error
    } finally {
      setActionLoading(null);
    }
  }, []);

  const accountColor = useCallback((connId: string) => {
    const idx = accounts.findIndex((a) => a.provider_connection_id === connId);
    return ACCOUNT_COLORS[idx % ACCOUNT_COLORS.length] ?? "var(--cal-email)";
  }, [accounts]);

  const accountName = useCallback((msg: EmailMessage) => {
    return msg.account_display_name || msg.account_email || msg.provider_type;
  }, []);

  const totalUnread = useMemo(() => accounts.reduce((sum, a) => sum + a.unread_count, 0), [accounts]);

  // Extract selected IDs outside conditional branches so TypeScript does not
  // narrow them to undefined inside the !selected rendering branch.
  const selectedMsgId = selected?.provider_message_id;
  const selectedConnId = selected?.provider_connection_id;

  // Keyboard shortcuts: j/k navigate, s star, e delete, r reply, c compose
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) {
        return;
      }
      if (showCompose || showSettings) return;

      if (e.key === "j") {
        e.preventDefault();
        const idx = selected ? messages.findIndex((m) =>
          m.provider_message_id === selected.provider_message_id &&
          m.provider_connection_id === selected.provider_connection_id
        ) : -1;
        const next = messages[idx + 1];
        if (next) handleSelectMessage(next);
      } else if (e.key === "k") {
        e.preventDefault();
        const idx = selected ? messages.findIndex((m) =>
          m.provider_message_id === selected.provider_message_id &&
          m.provider_connection_id === selected.provider_connection_id
        ) : messages.length;
        const prev = messages[idx - 1];
        if (prev) handleSelectMessage(prev);
      } else if (e.key === "s" && selected) {
        e.preventDefault();
        handleStar(selected, !selected.is_starred);
      } else if (e.key === "e" && selected) {
        e.preventDefault();
        handleDelete(selected);
      } else if (e.key === "r" && selected) {
        e.preventDefault();
        setReplyMode("reply");
        setShowReply(true);
      } else if (e.key === "c") {
        e.preventDefault();
        setShowCompose(true);
      } else if (e.key === "Escape" && selected) {
        e.preventDefault();
        setSelected(null);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [selected, messages, showCompose, showSettings, handleSelectMessage, handleStar, handleDelete]);

  return (
    <div className="flex h-full" ref={containerRef}>
      {/* Account sidebar */}
      <div className="flex w-56 flex-col border-r border-[var(--border)] bg-[var(--muted)]">
        <div className="flex items-center gap-2 px-3 py-3 border-b border-[var(--border)]">
          <Mail size={16} className="text-[var(--primary)]" />
          <span className="text-sm font-semibold">Email</span>
          <Badge variant="outline" className="ml-auto text-[10px] py-0">
            {accounts.length}
          </Badge>
        </div>

        {/* All Accounts */}
        <button
          onClick={() => { setSelectedAccount(null); setSelected(null); setShowSnoozed(false); }}
          className={cn(
            "flex items-center gap-2 px-3 py-2 text-sm transition-colors text-left",
            selectedAccount === null && !showSnoozed
              ? "bg-[var(--accent)] font-medium"
              : "hover:bg-[var(--accent)]/50"
          )}
        >
          <Inbox size={14} className="text-[var(--primary)]" />
          <span className="flex-1">All Accounts</span>
          {totalUnread > 0 && (
            <Badge className="text-[10px] py-0 px-1.5 bg-[var(--primary)] text-[var(--primary-foreground)]">
              {totalUnread}
            </Badge>
          )}
        </button>

        {/* Per-account entries */}
        {accounts.map((acct) => (
          <button
            key={acct.provider_connection_id}
            onClick={() => { setSelectedAccount(acct.provider_connection_id); setSelected(null); setShowSnoozed(false); }}
            className={cn(
              "flex items-center gap-2 px-3 py-2 text-sm transition-colors text-left",
              selectedAccount === acct.provider_connection_id && !showSnoozed
                ? "bg-[var(--accent)] font-medium"
                : "hover:bg-[var(--accent)]/50"
            )}
          >
            <div
              className="h-2.5 w-2.5 rounded-full shrink-0"
              style={{ backgroundColor: accountColor(acct.provider_connection_id) }}
            />
            <div className="flex-1 min-w-0">
              <div className="truncate">{acct.display_name}</div>
              {acct.email && (
                <div className="truncate text-[10px] text-[var(--muted-foreground)]">{acct.email}</div>
              )}
            </div>
            {acct.unread_count > 0 && (
              <Badge className="text-[10px] py-0 px-1.5 bg-[var(--primary)] text-[var(--primary-foreground)]">
                {acct.unread_count}
              </Badge>
            )}
          </button>
        ))}

        {accounts.length === 0 && (
          <div className="px-3 py-4 text-xs text-[var(--muted-foreground)]">
            No email accounts connected. Add one in Settings.
          </div>
        )}

        {/* Folder navigation */}
        <div className="mt-2 border-t border-[var(--border)] pt-2">
          <div className="px-3 py-1 text-[10px] font-medium uppercase tracking-wide text-[var(--muted-foreground)]">
            Folders
          </div>
          {FOLDERS.map((f) => {
            const Icon = f.icon;
            return (
              <button
                key={f.key}
                onClick={() => { setFolder(f.key); setSelected(null); setShowSnoozed(false); }}
                className={cn(
                  "flex items-center gap-2 px-3 py-1.5 text-sm transition-colors text-left w-full",
                  folder === f.key && !showSnoozed
                    ? "bg-[var(--accent)] font-medium"
                    : "hover:bg-[var(--accent)]/50"
                )}
              >
                <Icon size={14} className="text-[var(--muted-foreground)]" />
                <span className="flex-1">{f.label}</span>
              </button>
            );
          })}

          {/* Snoozed virtual folder */}
          <button
            onClick={() => { setShowSnoozed(true); setSelected(null); }}
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 text-sm transition-colors text-left w-full",
              showSnoozed
                ? "bg-[var(--accent)] font-medium"
                : "hover:bg-[var(--accent)]/50"
            )}
          >
            <Clock size={14} className="text-[var(--muted-foreground)]" />
            <span className="flex-1">Snoozed</span>
            {snoozed.length > 0 && (
              <Badge variant="outline" className="text-[10px] py-0 px-1.5">
                {snoozed.length}
              </Badge>
            )}
          </button>
        </div>

        {/* Labels section */}
        <div className="mt-2 border-t border-[var(--border)] pt-2">
          <div className="flex items-center px-3 py-1">
            <span className="text-[10px] font-medium uppercase tracking-wide text-[var(--muted-foreground)]">
              Labels
            </span>
            <button
              onClick={() => setShowLabelForm((v) => !v)}
              className="ml-auto text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            >
              <Plus size={12} />
            </button>
          </div>

          {showLabelForm && (
            <div className="px-3 py-2 space-y-2">
              <Input
                value={newLabelName}
                onChange={(e) => setNewLabelName(e.target.value)}
                placeholder="Label name"
                className="h-7 text-xs"
                onKeyDown={(e) => e.key === "Enter" && handleCreateLabel()}
              />
              <div className="flex items-center gap-1.5">
                <div className="flex flex-wrap gap-1">
                  {LABEL_COLORS.map((c) => (
                    <button
                      key={c}
                      onClick={() => setNewLabelColor(c)}
                      className={cn(
                        "h-4 w-4 rounded-full border",
                        newLabelColor === c ? "border-[var(--foreground)] ring-1 ring-[var(--foreground)]" : "border-transparent"
                      )}
                      style={{ backgroundColor: c }}
                    />
                  ))}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs"
                  onClick={handleCreateLabel}
                  disabled={actionLoading === "create-label" || !newLabelName.trim()}
                >
                  {actionLoading === "create-label" ? <Loader2 size={10} className="animate-spin" /> : "Add"}
                </Button>
              </div>
            </div>
          )}

          {labels.map((label) => (
            <div
              key={label.id}
              className="group flex items-center gap-2 px-3 py-1 text-sm"
            >
              <div
                className="h-2.5 w-2.5 rounded-full shrink-0"
                style={{ backgroundColor: label.color }}
              />
              <span className="flex-1 truncate text-xs">{label.name}</span>
              <button
                onClick={() => handleDeleteLabel(label.id)}
                className="text-[var(--muted-foreground)] opacity-0 group-hover:opacity-100 hover:text-[var(--destructive)]"
              >
                <X size={11} />
              </button>
            </div>
          ))}
          {labels.length === 0 && !showLabelForm && (
            <div className="px-3 py-1 text-[10px] text-[var(--muted-foreground)]">
              No labels yet.
            </div>
          )}
        </div>

        {/* Settings + Scan buttons */}
        <div className="mt-auto space-y-1.5 p-3 border-t border-[var(--border)]">
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => setShowSettings(true)}
          >
            <Settings size={14} />
            Email Settings
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={handleScan}
            disabled={scanning}
          >
            {scanning ? <Loader2 size={14} className="animate-spin" /> : <ScanLine size={14} />}
            Scan for Schedule
          </Button>
        </div>
      </div>

      {/* Main content area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Toolbar with search */}
        <div className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-2">
          <div className="relative flex-1 max-w-md">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="Search all accounts..."
              className="pl-8 h-8 text-sm"
            />
            {searchQuery && (
              <button
                onClick={() => { setSearchQuery(""); loadMessages(); }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              >
                <X size={14} />
              </button>
            )}
          </div>
          <Button variant="ghost" size="sm" onClick={loadMessages} disabled={loading || searching}>
            {loading || searching ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setShowCompose(true)}>
            <PenSquare size={14} />
            Compose
          </Button>
        </div>

        {/* Snoozed view */}
        {showSnoozed && (
          <div className="flex flex-1 flex-col overflow-hidden">
            <div className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-2">
              <Clock size={14} className="text-[var(--primary)]" />
              <span className="text-sm font-medium">Snoozed Emails</span>
              <Badge variant="outline" className="text-[10px] py-0">{snoozed.length}</Badge>
            </div>
            <div className="flex-1 overflow-y-auto">
              {snoozed.length === 0 ? (
                <div className="flex h-32 flex-col items-center justify-center gap-2 text-sm text-[var(--muted-foreground)]">
                  <Clock size={24} className="opacity-40" />
                  No snoozed emails.
                </div>
              ) : (
                snoozed.map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center gap-3 border-b border-[var(--border)] px-4 py-3"
                  >
                    <Clock size={14} className="text-[var(--muted-foreground)] shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="truncate text-sm">
                        {s.provider_message_id}
                      </div>
                      <div className="text-xs text-[var(--muted-foreground)]">
                        Returns: {new Date(s.snooze_until).toLocaleString()}
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleUnsnooze(s.id)}
                      disabled={actionLoading === `unsnooze-${s.id}`}
                    >
                      {actionLoading === `unsnooze-${s.id}` ? <Loader2 size={12} className="animate-spin" /> : <X size={12} />}
                      UnSnooze
                    </Button>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* Message list */}
        {!showSnoozed && !selected && (
          /* Message list */
          <div className="flex flex-1 flex-col overflow-hidden">
            <div className="flex-1 overflow-y-auto">
              {loading ? (
                <div className="flex h-32 items-center justify-center">
                  <Loader2 size={20} className="animate-spin text-[var(--muted-foreground)]" />
                </div>
              ) : messages.length > 0 ? (
                messages.map((msg) => {
                  const isSelected = selectedMsgId === msg.provider_message_id &&
                    selectedConnId === msg.provider_connection_id;
                  return (
                    <div
                      key={`${msg.provider_connection_id}-${msg.provider_message_id}`}
                      onClick={() => handleSelectMessage(msg)}
                      className={cn(
                        "flex cursor-pointer gap-3 border-b border-[var(--border)] px-4 py-3 transition-colors",
                        isSelected ? "bg-[var(--accent)]" : "hover:bg-[var(--accent)]/50",
                        msg.is_unread && "font-medium"
                      )}
                    >
                      {/* Account color indicator */}
                      <div
                        className="mt-0.5 h-2 w-2 rounded-full shrink-0"
                        style={{ backgroundColor: accountColor(msg.provider_connection_id) }}
                        title={accountName(msg)}
                      />
                      {/* Star */}
                      <button
                        onClick={(e) => { e.stopPropagation(); handleStar(msg, !msg.is_starred); }}
                        className="mt-0.5 shrink-0"
                      >
                        <Star
                          size={14}
                          className={cn(
                            msg.is_starred
                              ? "fill-[var(--cal-email)] text-[var(--cal-email)]"
                              : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                          )}
                        />
                      </button>
                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="truncate text-sm">{msg.from_address}</span>
                          {msg.is_unread && (
                            <CircleDot size={8} className="shrink-0 text-[var(--primary)]" />
                          )}
                          {msg.has_calendar_invite && (
                            <CalendarPlus size={12} className="shrink-0 text-[var(--cal-email)]" />
                          )}
                          <span className="ml-auto shrink-0 text-[10px] text-[var(--muted-foreground)]">
                            {msg.received_at && new Date(msg.received_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                          </span>
                        </div>
                        <div className="truncate text-sm text-[var(--foreground)]">{msg.subject || "(no subject)"}</div>
                        <div className="truncate text-xs text-[var(--muted-foreground)]">{msg.snippet}</div>
                        {/* Account badge */}
                        {!selectedAccount && (
                          <div className="mt-1 flex items-center gap-1">
                            <Badge
                              variant="outline"
                              className="text-[9px] py-0 px-1"
                              style={{ color: accountColor(msg.provider_connection_id) }}
                            >
                              {accountName(msg)}
                            </Badge>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="flex h-32 flex-col items-center justify-center gap-2 text-sm text-[var(--muted-foreground)]">
                  <Inbox size={24} className="opacity-40" />
                  {searchQuery ? "No results found" : "No messages in this folder."}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Message detail */}
        {selected && !showSnoozed && (
          <div className="flex flex-1 flex-col overflow-hidden">
            <div className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelected(null)}
              >
                <X size={14} />
              </Button>
              <div className="flex-1" />

              {/* Snooze button with dropdown */}
              <div className="relative">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowSnoozePicker((v) => !v)}
                  disabled={actionLoading?.startsWith("snooze-")}
                >
                  {actionLoading?.startsWith("snooze-") ? <Loader2 size={14} className="animate-spin" /> : <Clock size={14} />}
                  Snooze
                </Button>
                {showSnoozePicker && (
                  <div className="absolute right-0 top-full z-20 mt-1 w-48 rounded-md border border-[var(--border)] bg-[var(--background)] shadow-lg">
                    {SNOOZE_PRESETS.map((preset) => (
                      <button
                        key={preset.label}
                        onClick={() => {
                          const until = new Date(Date.now() + preset.hours * 3600_000).toISOString();
                          handleSnooze(until);
                        }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-[var(--accent)] text-left"
                      >
                        <Clock size={12} className="text-[var(--muted-foreground)]" />
                        {preset.label}
                      </button>
                    ))}
                    <div className="border-t border-[var(--border)] p-2">
                      <Input
                        type="datetime-local"
                        value={snoozeCustomDate}
                        onChange={(e) => setSnoozeCustomDate(e.target.value)}
                        className="h-8 text-xs"
                      />
                      <Button
                        variant="ghost"
                        size="sm"
                        className="mt-1 w-full text-xs"
                        disabled={!snoozeCustomDate}
                        onClick={() => {
                          const until = new Date(snoozeCustomDate).toISOString();
                          handleSnooze(until);
                        }}
                      >
                        Snooze to selected time
                      </Button>
                    </div>
                  </div>
                )}
              </div>

              {/* AI Summarize button */}
              <Button
                variant="ghost"
                size="sm"
                onClick={handleSummarize}
                disabled={summarizing}
                title="AI Summarize"
              >
                {summarizing ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                Summarize
              </Button>

              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleStar(selected, !selected.is_starred)}
                disabled={actionLoading === `star-${selected.provider_message_id}`}
              >
                <Star
                  size={14}
                  className={cn(
                    selected.is_starred
                      ? "fill-[var(--cal-email)] text-[var(--cal-email)]"
                      : "text-[var(--muted-foreground)]"
                  )}
                />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleMarkRead(selected, !selected.is_unread)}
                disabled={actionLoading === `read-${selected.provider_message_id}`}
              >
                {selected.is_unread ? <MailOpen size={14} /> : <Mail size={14} />}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleDelete(selected)}
                disabled={actionLoading === `del-${selected.provider_message_id}`}
              >
                <Trash2 size={14} className="text-[var(--destructive)]" />
              </Button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-4">
              {/* Account badge */}
              <div className="mb-3 flex items-center gap-2">
                <div
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: accountColor(selected.provider_connection_id) }}
                />
                <Badge variant="outline" className="text-[10px] py-0">
                  {accountName(selected)}
                </Badge>
                {selected.has_calendar_invite && (
                  <Badge className="text-[10px] py-0 bg-[var(--cal-email)] text-white">
                    <CalendarPlus size={10} className="mr-1" />
                    Calendar Invite
                  </Badge>
                )}
              </div>

              <h2 className="mb-3 text-lg font-semibold">{selected.subject || "(no subject)"}</h2>

              <div className="mb-4 space-y-1 text-sm">
                <div className="flex gap-2">
                  <span className="w-16 text-[var(--muted-foreground)]">From</span>
                  <span>{selected.from_address}</span>
                </div>
                <div className="flex gap-2">
                  <span className="w-16 text-[var(--muted-foreground)]">To</span>
                  <span>{selected.to_addresses.join(", ")}</span>
                </div>
                <div className="flex gap-2">
                  <span className="w-16 text-[var(--muted-foreground)]">Date</span>
                  <span>
                    {selected.received_at
                      ? new Date(selected.received_at).toLocaleString()
                      : "Unknown"}
                  </span>
                </div>
              </div>

              <div className="prose prose-sm max-w-none whitespace-pre-wrap text-sm leading-relaxed">
                {selected.body_text || selected.snippet || "(no body content available)"}
              </div>

              {/* AI Summary */}
              {aiSummary !== null && (
                <div className="mt-4 rounded-md border border-[var(--primary)]/30 bg-[var(--primary)]/5 p-3">
                  <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-[var(--primary)]">
                    <Sparkles size={12} />
                    AI Summary
                  </div>
                  <p className="text-sm leading-relaxed">{aiSummary}</p>
                </div>
              )}

              {/* Attachments */}
              {selected.attachments && selected.attachments.length > 0 && (
                <div className="mt-4 border-t border-[var(--border)] pt-3">
                  <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-[var(--muted-foreground)]">
                    <Paperclip size={12} />
                    {selected.attachments.length} attachment{selected.attachments.length > 1 ? "s" : ""}
                  </div>
                  <div className="space-y-1.5">
                    {selected.attachments.map((att, idx) => (
                      <div
                        key={idx}
                        className="flex items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--muted)] px-3 py-2 text-sm"
                      >
                        {att.content_type.startsWith("image/")
                          ? <ImageIcon size={14} className="text-[var(--primary)]" />
                          : <FileText size={14} className="text-[var(--primary)]" />}
                        <span className="flex-1 truncate">{att.filename}</span>
                        <span className="text-xs text-[var(--muted-foreground)]">
                          {att.size > 1024 * 1024
                            ? `${(att.size / (1024 * 1024)).toFixed(1)} MB`
                            : att.size > 1024
                              ? `${Math.ceil(att.size / 1024)} KB`
                              : `${att.size} B`}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Reply bar */}
            {!showReply ? (
              <div className="flex items-center gap-2 border-t border-[var(--border)] px-4 py-2">
                <Button variant="outline" size="sm" onClick={() => { setReplyMode("reply"); setShowReply(true); }}>
                  <Reply size={14} />
                  Reply
                </Button>
                <Button variant="outline" size="sm" onClick={() => { setReplyMode("replyall"); setShowReply(true); }}>
                  <ReplyAll size={14} />
                  Reply All
                </Button>
                <Button variant="outline" size="sm" onClick={() => { setReplyMode("forward"); setShowReply(true); }}>
                  <Forward size={14} />
                  Forward
                </Button>
              </div>
            ) : (
              <div className="border-t border-[var(--border)] px-4 py-3 space-y-2">
                <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
                  {replyMode === "reply" && <Reply size={12} />}
                  {replyMode === "replyall" && <ReplyAll size={12} />}
                  {replyMode === "forward" && <Forward size={12} />}
                  <span className="font-medium capitalize">{replyMode === "replyall" ? "Reply All" : replyMode}</span>
                  <button
                    onClick={() => setShowReply(false)}
                    className="ml-auto text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  >
                    <X size={14} />
                  </button>
                </div>
                <textarea
                  value={replyBody}
                  onChange={(e) => setReplyBody(e.target.value)}
                  placeholder="Type your reply..."
                  className="w-full resize-none rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
                  rows={4}
                  autoFocus
                />
                <div className="flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={() => setShowReply(false)}>Cancel</Button>
                  <Button size="sm" onClick={handleSendReply} disabled={actionLoading === "send-reply" || !replyBody.trim()}>
                    {actionLoading === "send-reply" ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                    Send
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Scan results panel */}
        {showScan && (
          <div className="border-t border-[var(--border)] bg-[var(--muted)] px-4 py-3 max-h-[40%] overflow-y-auto">
            <div className="mb-3 flex items-center gap-2">
              <ScanLine size={16} className="text-[var(--primary)]" />
              <span className="text-sm font-semibold">Schedule Scan Results</span>
              <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setShowScan(false)}>
                <X size={14} />
              </Button>
            </div>
            {scanning ? (
              <div className="flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
                <Loader2 size={16} className="animate-spin" />
                Scanning emails for scheduling content...
              </div>
            ) : !scanResult || (scanResult.suggestions.length === 0 && scanResult.detections.length === 0) ? (
              <div className="flex flex-col items-center justify-center gap-2 py-4 text-sm text-[var(--muted-foreground)]">
                <ScanLine size={24} className="opacity-40" />
                {scanResult ? "No scheduling-related content found in recent emails." : "Scan failed. Make sure an email provider is connected."}
              </div>
            ) : (
              <>
                {scanResult.summary && (
                  <p className="mb-3 text-sm text-[var(--muted-foreground)]">{scanResult.summary}</p>
                )}
                <div className="flex gap-4">
                  <div className="flex-1">
                    <h4 className="mb-2 text-xs font-medium">Suggestions ({scanResult.suggestions.length})</h4>
                    <div className="flex flex-col gap-2">
                      {scanResult.suggestions.map((s, i) => (
                        <div key={i} className="rounded-md border border-[var(--border)] bg-[var(--background)] p-3">
                          <div className="mb-1 flex items-center gap-2">
                            <Clock size={14} className="text-[var(--primary)]" />
                            <span className="text-sm font-medium capitalize">{s.type.replace(/_/g, " ")}</span>
                            {s.confidence > 0 && (
                              <Badge variant="outline" className="ml-auto text-[10px] py-0">
                                {Math.round(s.confidence * 100)}%
                              </Badge>
                            )}
                          </div>
                          <p className="text-sm">{s.message}</p>
                          {s.proposed_time && (
                            <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                              Proposed: {s.proposed_time.raw_text}
                              {s.proposed_time.datetime && ` (${new Date(s.proposed_time.datetime).toLocaleString()})`}
                            </p>
                          )}
                          {s.conflict_with && (
                            <p className="mt-1 text-xs text-orange-500">Conflicts with: {s.conflict_with}</p>
                          )}
                          {s.suggested_alternative && (
                            <p className="mt-1 text-xs text-[var(--cal-personal)]">Alternative: {s.suggested_alternative}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                  {scanResult.detections.length > 0 && (
                    <div className="w-[40%]">
                      <h4 className="mb-2 text-xs font-medium">Detected ({scanResult.detections.length})</h4>
                      <div className="flex flex-col gap-1.5">
                        {scanResult.detections.filter((d) => d.is_scheduling_related).map((d, i) => (
                          <div key={i} className="rounded-md border border-[var(--border)] bg-[var(--background)] p-2">
                            <p className="truncate text-xs font-medium">{d.subject || "(no subject)"}</p>
                            <div className="flex gap-1">
                              {d.is_meeting_proposal && <Badge variant="outline" className="text-[10px] py-0">Proposal</Badge>}
                              {d.is_calendar_invite && <Badge variant="outline" className="text-[10px] py-0">Invite</Badge>}
                              {d.is_reschedule && <Badge variant="outline" className="text-[10px] py-0">Reschedule</Badge>}
                              {d.is_cancellation && <Badge variant="outline" className="text-[10px] py-0">Cancel</Badge>}
                            </div>
                            {d.extracted_times.length > 0 && (
                              <p className="mt-1 text-[10px] text-[var(--muted-foreground)]">
                                Times: {d.extracted_times.map((t) => t.raw_text).join(", ")}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Compose modal */}
      {showCompose && (
        <ComposeModal
          accounts={accounts}
          templates={templates}
          onClose={() => setShowCompose(false)}
          onSent={() => { setShowCompose(false); loadMessages(); }}
        />
      )}

      {/* Settings modal */}
      {showSettings && (
        <EmailSettingsModal
          filters={filters}
          vacation={vacation}
          actionLoading={actionLoading}
          onReloadFilters={loadFilters}
          onSaveVacation={handleSaveVacation}
          onClose={() => setShowSettings(false)}
        />
      )}
    </div>
  );
}

/**
 * ComposeModal — compose a new email with account selector, templates,
 * and scheduled send.
 *
 * Lets the user pick which connected email account to send from, choose a
 * pre-saved template to pre-fill subject and body, enter recipients,
 * subject, and body text, attach files, and either send immediately or
 * schedule delivery for a future time.
 */
function ComposeModal({
  accounts,
  templates,
  onClose,
  onSent,
}: {
  accounts: EmailAccount[];
  templates: EmailTemplate[];
  onClose: () => void;
  onSent: () => void;
}) {
  const [fromId, setFromId] = useState(accounts[0]?.provider_connection_id ?? "");
  const [to, setTo] = useState("");
  const [cc, setCc] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<{ filename: string; content_type: string; content: string }[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [showSchedule, setShowSchedule] = useState(false);
  const [scheduleDate, setScheduleDate] = useState("");

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    const newAttachments: { filename: string; content_type: string; content: string }[] = [];
    for (const file of Array.from(files)) {
      const content = await new Promise<string>((resolve) => {
        const reader = new FileReader();
        reader.onload = () => {
          const result = reader.result as string;
          // Strip the data URL prefix (e.g. "data:image/png;base64,")
          const base64 = result.includes(",") ? result.split(",")[1] : result;
          resolve(base64);
        };
        reader.readAsDataURL(file);
      });
      newAttachments.push({
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        content,
      });
    }
    setAttachments((prev) => [...prev, ...newAttachments]);
    // Reset the input so the same file can be selected again.
    e.target.value = "";
  }, []);

  const removeAttachment = useCallback((idx: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  /** Apply a saved template to the subject and body fields. */
  const handleTemplateChange = useCallback((tplId: string) => {
    setSelectedTemplate(tplId);
    if (!tplId) {
      return;
    }
    const tpl = templates.find((t) => t.id === tplId);
    if (!tpl) return;
    if (tpl.subject) setSubject(tpl.subject);
    setBody(tpl.body_text);
  }, [templates]);

  const handleSend = useCallback(async () => {
    if (!fromId || !to.trim()) return;
    setSending(true);
    setError(null);
    try {
      const toList = to.split(",").map((s) => s.trim()).filter(Boolean);
      await api.sendEmail({
        provider_connection_id: fromId,
        to: toList,
        subject: subject || "(no subject)",
        body_text: body,
        ...(attachments.length > 0 ? { attachments } : {}),
      });
      onSent();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send");
    } finally {
      setSending(false);
    }
  }, [fromId, to, subject, body, attachments, onSent]);

  /** Schedule the email for delivery at the chosen future time. */
  const handleScheduleSend = useCallback(async () => {
    if (!fromId || !to.trim() || !scheduleDate) return;
    setSending(true);
    setError(null);
    try {
      const toList = to.split(",").map((s) => s.trim()).filter(Boolean);
      await api.scheduleEmail({
        provider_connection_id: fromId,
        to_addresses: toList,
        subject: subject || "(no subject)",
        body_text: body,
        scheduled_for: new Date(scheduleDate).toISOString(),
        ...(attachments.length > 0 ? { attachments } : {}),
      });
      onSent();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to schedule");
    } finally {
      setSending(false);
    }
  }, [fromId, to, subject, body, attachments, scheduleDate, onSent]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="w-full max-w-2xl rounded-lg border border-[var(--border)] bg-[var(--background)] shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3">
          <PenSquare size={16} className="text-[var(--primary)]" />
          <span className="text-sm font-semibold">New Message</span>
          <div className="flex-1" />
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X size={16} />
          </Button>
        </div>

        {/* Form */}
        <div className="space-y-3 p-4">
          {/* Template selector */}
          {templates.length > 0 && (
            <div className="flex items-center gap-2">
              <label className="w-12 text-xs font-medium text-[var(--muted-foreground)]">Template</label>
              <Select
                value={selectedTemplate}
                onChange={(e) => handleTemplateChange(e.target.value)}
                className="flex-1 h-8 text-sm"
              >
                <option value="">No template</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </Select>
            </div>
          )}

          {/* From (account selector) */}
          <div className="flex items-center gap-2">
            <label className="w-12 text-xs font-medium text-[var(--muted-foreground)]">From</label>
            <Select value={fromId} onChange={(e) => setFromId(e.target.value)} className="flex-1 h-8 text-sm">
              {accounts.map((a) => (
                <option key={a.provider_connection_id} value={a.provider_connection_id}>
                  {a.display_name}{a.email ? ` (${a.email})` : ""}
                </option>
              ))}
            </Select>
          </div>

          {/* To */}
          <div className="flex items-center gap-2">
            <label className="w-12 text-xs font-medium text-[var(--muted-foreground)]">To</label>
            <Input
              value={to}
              onChange={(e) => setTo(e.target.value)}
              placeholder="recipient@example.com (comma-separated)"
              className="h-8 text-sm"
            />
          </div>

          {/* Subject */}
          <div className="flex items-center gap-2">
            <label className="w-12 text-xs font-medium text-[var(--muted-foreground)]">Subject</label>
            <Input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Subject"
              className="h-8 text-sm"
            />
          </div>

          {/* Body */}
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Compose your message..."
            className="w-full resize-none rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
            rows={8}
          />

          {/* Attachments */}
          <div className="space-y-1.5">
            {attachments.map((att, idx) => (
              <div
                key={idx}
                className="flex items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--muted)] px-3 py-1.5 text-sm"
              >
                <Paperclip size={12} className="text-[var(--muted-foreground)]" />
                <span className="flex-1 truncate">{att.filename}</span>
                <button
                  onClick={() => removeAttachment(idx)}
                  className="text-[var(--muted-foreground)] hover:text-[var(--destructive)]"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
            <label className="flex cursor-pointer items-center gap-1.5 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
              <Paperclip size={12} />
              Attach files
              <input
                type="file"
                multiple
                onChange={handleFileSelect}
                className="hidden"
              />
            </label>
          </div>

          {/* Scheduled send */}
          {showSchedule && (
            <div className="flex items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--muted)] px-3 py-2">
              <CalendarClock size={14} className="text-[var(--primary)]" />
              <Input
                type="datetime-local"
                value={scheduleDate}
                onChange={(e) => setScheduleDate(e.target.value)}
                className="h-8 text-sm flex-1"
              />
              <Button
                variant="ghost"
                size="sm"
                onClick={() => { setShowSchedule(false); setScheduleDate(""); }}
              >
                <X size={12} />
              </Button>
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 text-sm text-[var(--destructive)]">
              <AlertTriangle size={14} />
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 border-t border-[var(--border)] px-4 py-3">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          {showSchedule && scheduleDate ? (
            <Button size="sm" onClick={handleScheduleSend} disabled={sending || !to.trim()}>
              {sending ? <Loader2 size={14} className="animate-spin" /> : <CalendarClock size={14} />}
              Schedule Send
            </Button>
          ) : (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowSchedule(true)}
                disabled={sending || !to.trim()}
              >
                <CalendarClock size={14} />
                Schedule
              </Button>
              <Button size="sm" onClick={handleSend} disabled={sending || !to.trim()}>
                {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                Send
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * EmailSettingsModal — manage email filters and vacation auto-responder.
 *
 * Provides a tabbed interface for creating/deleting auto-apply filter rules
 * and configuring the vacation auto-responder (enable toggle, subject, body,
 * and date range).
 */
function EmailSettingsModal({
  filters,
  vacation,
  actionLoading,
  onReloadFilters,
  onSaveVacation,
  onClose,
}: {
  filters: EmailFilter[];
  vacation: VacationConfig | null;
  actionLoading: string | null;
  onReloadFilters: () => void;
  onSaveVacation: (config: VacationConfig) => void;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<"filters" | "vacation">("filters");

  // Filter form state
  const [fName, setFName] = useState("");
  const [fField, setFField] = useState("from");
  const [fPattern, setFPattern] = useState("");
  const [fAction, setFAction] = useState("mark_read");
  const [fActionValue, setFActionValue] = useState("");
  const [filterSaving, setFilterSaving] = useState(false);

  // Vacation form state
  const [vEnabled, setVEnabled] = useState(vacation?.enabled ?? false);
  const [vSubject, setVSubject] = useState(vacation?.subject ?? "Out of Office");
  const [vBody, setVBody] = useState(vacation?.body_text ?? "");
  const [vStart, setVStart] = useState(vacation?.start_date ?? "");
  const [vEnd, setVEnd] = useState(vacation?.end_date ?? "");
  const [vacationSaving, setVacationSaving] = useState(false);

  /** Create a new filter rule and refresh the list. */
  const handleCreateFilter = useCallback(async () => {
    if (!fName.trim() || !fPattern.trim()) return;
    setFilterSaving(true);
    try {
      await api.createEmailFilter({
        name: fName.trim(),
        field: fField,
        pattern: fPattern.trim(),
        action: fAction,
        action_value: fActionValue.trim() || undefined,
      });
      setFName("");
      setFPattern("");
      setFActionValue("");
      await onReloadFilters();
    } catch {
      // keep state on error
    } finally {
      setFilterSaving(false);
    }
  }, [fName, fField, fPattern, fAction, fActionValue, onReloadFilters]);

  /** Delete a filter rule by id. */
  const handleDeleteFilter = useCallback(async (filterId: string) => {
    try {
      await api.deleteEmailFilter(filterId);
      await onReloadFilters();
    } catch {
      // keep state on error
    }
  }, [onReloadFilters]);

  /** Persist vacation responder configuration. */
  const handleSaveVacation = useCallback(async () => {
    setVacationSaving(true);
    try {
      await onSaveVacation({
        enabled: vEnabled,
        subject: vSubject,
        body_text: vBody,
        start_date: vStart || null,
        end_date: vEnd || null,
      });
    } finally {
      setVacationSaving(false);
    }
  }, [vEnabled, vSubject, vBody, vStart, vEnd, onSaveVacation]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-lg border border-[var(--border)] bg-[var(--background)] shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3">
          <Settings size={16} className="text-[var(--primary)]" />
          <span className="text-sm font-semibold">Email Settings</span>
          <div className="flex-1" />
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X size={16} />
          </Button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[var(--border)]">
          <button
            onClick={() => setTab("filters")}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors",
              tab === "filters"
                ? "border-b-2 border-[var(--primary)] text-[var(--foreground)]"
                : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            )}
          >
            <Filter size={14} />
            Filters
          </button>
          <button
            onClick={() => setTab("vacation")}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors",
              tab === "vacation"
                ? "border-b-2 border-[var(--primary)] text-[var(--foreground)]"
                : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            )}
          >
            {vEnabled ? <Bell size={14} /> : <BellOff size={14} />}
            Vacation Responder
          </button>
        </div>

        <div className="max-h-[60vh] overflow-y-auto p-4">
          {tab === "filters" ? (
            <div className="space-y-4">
              {/* Create filter form */}
              <div className="space-y-2 rounded-md border border-[var(--border)] bg-[var(--muted)] p-3">
                <div className="text-xs font-medium">New Filter Rule</div>
                <Input
                  value={fName}
                  onChange={(e) => setFName(e.target.value)}
                  placeholder="Filter name (e.g. Newsletters)"
                  className="h-8 text-sm"
                />
                <div className="grid grid-cols-2 gap-2">
                  <Select value={fField} onChange={(e) => setFField(e.target.value)} className="h-8 text-sm">
                    <option value="from">From</option>
                    <option value="to">To</option>
                    <option value="subject">Subject</option>
                    <option value="body">Body</option>
                  </Select>
                  <Input
                    value={fPattern}
                    onChange={(e) => setFPattern(e.target.value)}
                    placeholder="Pattern to match"
                    className="h-8 text-sm"
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <Select value={fAction} onChange={(e) => setFAction(e.target.value)} className="h-8 text-sm">
                    <option value="mark_read">Mark as Read</option>
                    <option value="star">Star</option>
                    <option value="archive">Archive</option>
                    <option value="delete">Delete</option>
                    <option value="label">Apply Label</option>
                  </Select>
                  {fAction === "label" && (
                    <Input
                      value={fActionValue}
                      onChange={(e) => setFActionValue(e.target.value)}
                      placeholder="Label name"
                      className="h-8 text-sm"
                    />
                  )}
                </div>
                <Button
                  size="sm"
                  onClick={handleCreateFilter}
                  disabled={filterSaving || !fName.trim() || !fPattern.trim()}
                >
                  {filterSaving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                  Add Filter
                </Button>
              </div>

              {/* Existing filters */}
              <div className="space-y-1.5">
                {filters.length === 0 ? (
                  <div className="py-4 text-center text-sm text-[var(--muted-foreground)]">
                    No filters configured.
                  </div>
                ) : (
                  filters.map((f) => (
                    <div
                      key={f.id}
                      className="group flex items-center gap-2 rounded-md border border-[var(--border)] px-3 py-2 text-sm"
                    >
                      <Filter size={12} className="text-[var(--muted-foreground)] shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="truncate font-medium">{f.name}</div>
                        <div className="text-xs text-[var(--muted-foreground)]">
                          {f.field} contains &ldquo;{f.pattern}&rdquo; &rarr; {f.action.replace(/_/g, " ")}
                          {f.action_value ? ` (${f.action_value})` : ""}
                        </div>
                      </div>
                      {f.is_active && (
                        <Badge variant="outline" className="text-[10px] py-0">Active</Badge>
                      )}
                      <button
                        onClick={() => handleDeleteFilter(f.id)}
                        className="text-[var(--muted-foreground)] opacity-0 group-hover:opacity-100 hover:text-[var(--destructive)]"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Enable toggle */}
              <div className="flex items-center gap-3">
                <Switch checked={vEnabled} onCheckedChange={setVEnabled} />
                <div>
                  <div className="text-sm font-medium">
                    {vEnabled ? "Vacation responder is ON" : "Vacation responder is OFF"}
                  </div>
                  <div className="text-xs text-[var(--muted-foreground)]">
                    Auto-reply to incoming emails while you are away.
                  </div>
                </div>
              </div>

              {/* Subject */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-[var(--muted-foreground)]">Subject</label>
                <Input
                  value={vSubject}
                  onChange={(e) => setVSubject(e.target.value)}
                  placeholder="Out of Office"
                  className="h-8 text-sm"
                />
              </div>

              {/* Body */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-[var(--muted-foreground)]">Message</label>
                <textarea
                  value={vBody}
                  onChange={(e) => setVBody(e.target.value)}
                  placeholder="I am currently out of the office and will respond when I return."
                  className="w-full resize-none rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
                  rows={5}
                />
              </div>

              {/* Date range */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-[var(--muted-foreground)]">Start date (optional)</label>
                  <Input
                    type="date"
                    value={vStart}
                    onChange={(e) => setVStart(e.target.value)}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-[var(--muted-foreground)]">End date (optional)</label>
                  <Input
                    type="date"
                    value={vEnd}
                    onChange={(e) => setVEnd(e.target.value)}
                    className="h-8 text-sm"
                  />
                </div>
              </div>

              <div className="flex justify-end">
                <Button size="sm" onClick={handleSaveVacation} disabled={vacationSaving || actionLoading === "save-vacation"}>
                  {vacationSaving || actionLoading === "save-vacation"
                    ? <Loader2 size={14} className="animate-spin" />
                    : <CheckCircle2 size={14} />}
                  Save Vacation Settings
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
