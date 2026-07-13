"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Mail, RefreshCw, Inbox, CalendarPlus, Send, Loader2, ChevronRight,
  ScanLine, AlertTriangle, Clock, CheckCircle2, XCircle, Star, Search,
  Trash2, MailOpen, Reply, ReplyAll, Forward, X, Plus, User, Folder,
  Archive, PenSquare, CircleDot,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { EmailMessage, EmailAccount, EmailFolder } from "@/types";

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

/**
 * EmailPanel — unified multi-account email inbox.
 *
 * Shows all emails from all connected accounts in one unified view, with
 * the ability to filter by individual account. Includes folder navigation
 * (Inbox, Starred, Sent, Drafts, All Mail), search across all accounts,
 * star/unstar, mark read/unread, delete, and compose with account selector.
 *
 * The scheduling scan feature detects meeting proposals and calendar invites
 * in emails, unique to A-Cal's agentic layer.
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

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  useEffect(() => {
    loadMessages();
  }, [loadMessages]);

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

  const accountColor = useCallback((connId: string) => {
    const idx = accounts.findIndex((a) => a.provider_connection_id === connId);
    return ACCOUNT_COLORS[idx % ACCOUNT_COLORS.length] ?? "var(--cal-email)";
  }, [accounts]);

  const accountName = useCallback((msg: EmailMessage) => {
    return msg.account_display_name || msg.account_email || msg.provider_type;
  }, []);

  const totalUnread = useMemo(() => accounts.reduce((sum, a) => sum + a.unread_count, 0), [accounts]);

  return (
    <div className="flex h-full">
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
          onClick={() => { setSelectedAccount(null); setSelected(null); }}
          className={cn(
            "flex items-center gap-2 px-3 py-2 text-sm transition-colors text-left",
            selectedAccount === null
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
            onClick={() => { setSelectedAccount(acct.provider_connection_id); setSelected(null); }}
            className={cn(
              "flex items-center gap-2 px-3 py-2 text-sm transition-colors text-left",
              selectedAccount === acct.provider_connection_id
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
                onClick={() => { setFolder(f.key); setSelected(null); }}
                className={cn(
                  "flex items-center gap-2 px-3 py-1.5 text-sm transition-colors text-left w-full",
                  folder === f.key
                    ? "bg-[var(--accent)] font-medium"
                    : "hover:bg-[var(--accent)]/50"
                )}
              >
                <Icon size={14} className="text-[var(--muted-foreground)]" />
                <span className="flex-1">{f.label}</span>
              </button>
            );
          })}
        </div>

        {/* Scan button */}
        <div className="mt-auto p-3 border-t border-[var(--border)]">
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
          <Button variant="ghost" size="sm" onClick={loadMessages} disabled={loading}>
            {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setShowCompose(true)}>
            <PenSquare size={14} />
            Compose
          </Button>
        </div>

        {/* Message list + detail split */}
        <div className="flex flex-1 overflow-hidden">
          {/* Message list */}
          <div className={cn("overflow-y-auto", selected ? "w-[42%] border-r border-[var(--border)]" : "w-full")}>
            {/* Account header */}
            <div className="px-4 py-2 border-b border-[var(--border)] bg-[var(--muted)]/50">
              <span className="text-xs font-medium text-[var(--muted-foreground)]">
                {selectedAccount
                  ? accounts.find((a) => a.provider_connection_id === selectedAccount)?.display_name ?? "Account"
                  : "All Accounts"}
                {" / "}
                {FOLDERS.find((f) => f.key === folder)?.label ?? "Inbox"}
              </span>
              <span className="ml-2 text-xs text-[var(--muted-foreground)]">
                {messages.length} {messages.length === 1 ? "message" : "messages"}
              </span>
            </div>

            {loading && messages.length === 0 ? (
              <div className="flex h-32 items-center justify-center text-sm text-[var(--muted-foreground)]">
                <Loader2 size={16} className="mr-2 animate-spin" />
                Loading messages...
              </div>
            ) : messages.length === 0 ? (
              <div className="flex h-32 flex-col items-center justify-center gap-2 text-sm text-[var(--muted-foreground)]">
                <Inbox size={24} className="opacity-40" />
                {searchQuery ? "No results found" : "No messages in this folder."}
              </div>
            ) : (
              messages.map((msg) => {
                const isSelected = selected?.provider_message_id === msg.provider_message_id &&
                  selected?.provider_connection_id === msg.provider_connection_id;
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
            )}
          </div>

          {/* Message detail */}
          {selected && (
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
                <div className="border-t border-[var(--border)] p-3">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="text-xs font-medium">
                      {replyMode === "reply" ? "Reply" : replyMode === "replyall" ? "Reply All" : "Forward"}
                    </span>
                    <span className="text-xs text-[var(--muted-foreground)]">
                      to {selected.from_address}
                    </span>
                    <div className="flex-1" />
                    <Button variant="ghost" size="sm" onClick={() => { setShowReply(false); setReplyBody(""); }}>
                      <X size={14} />
                    </Button>
                  </div>
                  <textarea
                    value={replyBody}
                    onChange={(e) => setReplyBody(e.target.value)}
                    placeholder="Type your reply..."
                    className="mb-2 w-full resize-none rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
                    rows={4}
                  />
                  <div className="flex justify-end gap-2">
                    <Button
                      size="sm"
                      onClick={handleSendReply}
                      disabled={!replyBody.trim() || actionLoading === "send-reply"}
                    >
                      {actionLoading === "send-reply" ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Send size={14} />
                      )}
                      Send
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Scan results overlay */}
        {showScan && (
          <div className="border-t border-[var(--border)] bg-[var(--muted)]/50 px-4 py-3 max-h-[50%] overflow-y-auto">
            <div className="mb-2 flex items-center gap-2">
              <ScanLine size={16} className="text-[var(--primary)]" />
              <span className="text-sm font-medium">Schedule Scan Results</span>
              <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setShowScan(false)}>
                <X size={14} />
              </Button>
            </div>
            {scanning ? (
              <div className="flex items-center gap-2 py-4 text-sm text-[var(--muted-foreground)]">
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
          onClose={() => setShowCompose(false)}
          onSent={() => { setShowCompose(false); loadMessages(); }}
        />
      )}
    </div>
  );
}

/**
 * ComposeModal — compose a new email with account selector.
 *
 * Lets the user pick which connected email account to send from, enter
 * recipients, subject, and body text.
 */
function ComposeModal({
  accounts,
  onClose,
  onSent,
}: {
  accounts: EmailAccount[];
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
      });
      onSent();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send");
    } finally {
      setSending(false);
    }
  }, [fromId, to, subject, body, onSent]);

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
          <Button size="sm" onClick={handleSend} disabled={sending || !to.trim()}>
            {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            Send
          </Button>
        </div>
      </div>
    </div>
  );
}
