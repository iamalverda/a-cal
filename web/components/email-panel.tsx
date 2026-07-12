"use client";

import { useState, useEffect, useCallback } from "react";
import { Mail, RefreshCw, Inbox, CalendarPlus, Send, Loader2, ChevronRight, ScanLine, AlertTriangle, Clock, CheckCircle2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { EmailMessage } from "@/types";

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

/**
 * EmailPanel — displays messages from connected email providers.
 *
 * Shows inbox with calendar-invite detection, sender, subject, and snippet.
 * Users can refresh, filter by invite-only, and compose new messages.
 */
export function EmailPanel() {
  const [messages, setMessages] = useState<EmailMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [invitesOnly, setInvitesOnly] = useState(false);
  const [selected, setSelected] = useState<EmailMessage | null>(null);
  const [showCompose, setShowCompose] = useState(false);
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [scanning, setScanning] = useState(false);
  const [showScan, setShowScan] = useState(false);

  const loadMessages = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listEmailMessages({ limit: 50 });
      setMessages(data);
    } catch {
      setMessages([]);
    } finally {
      setLoading(false);
    }
  }, []);

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

  const filtered = invitesOnly ? messages.filter((m) => m.has_calendar_invite) : messages;
  const inviteCount = messages.filter((m) => m.has_calendar_invite).length;

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3">
        <Button variant="ghost" size="sm" onClick={loadMessages} disabled={loading}>
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Refresh
        </Button>
        <Button
          variant={invitesOnly ? "default" : "outline"}
          size="sm"
          onClick={() => setInvitesOnly(!invitesOnly)}
        >
          <CalendarPlus size={14} />
          Invites {inviteCount > 0 && `(${inviteCount})`}
        </Button>
        <div className="flex-1" />
        <Button variant="outline" size="sm" onClick={handleScan} disabled={scanning}>
          {scanning ? <Loader2 size={14} className="animate-spin" /> : <ScanLine size={14} />}
          Scan for Schedule
        </Button>
        <Button variant="outline" size="sm" onClick={() => setShowCompose(true)}>
          <Send size={14} />
          Compose
        </Button>
      </div>

      {/* Message list + detail split */}
      <div className="flex flex-1 overflow-hidden">
        {/* List */}
        <div className={cn("overflow-y-auto", selected ? "w-[45%] border-r border-[var(--border)]" : "w-full")}>
          {loading && messages.length === 0 ? (
            <div className="flex h-32 items-center justify-center text-sm text-[var(--muted-foreground)]">
              <Loader2 size={16} className="mr-2 animate-spin" />
              Loading messages...
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex h-32 flex-col items-center justify-center gap-2 text-sm text-[var(--muted-foreground)]">
              <Inbox size={24} className="opacity-40" />
              {invitesOnly ? "No calendar invites found" : "No messages. Connect an email provider in Settings."}
            </div>
          ) : (
            filtered.map((msg) => (
              <button
                key={`${msg.provider_connection_id}:${msg.provider_message_id}`}
                onClick={() => setSelected(msg)}
                className={cn(
                  "flex w-full flex-col gap-1 border-b border-[var(--border)] px-4 py-3 text-left transition-colors hover:bg-[var(--accent)]",
                  selected?.provider_message_id === msg.provider_message_id && "bg-[var(--accent)]"
                )}
              >
                <div className="flex items-center gap-2">
                  {msg.has_calendar_invite && (
                    <CalendarPlus size={14} className="shrink-0 text-[var(--cal-personal)]" />
                  )}
                  <span className="truncate text-sm font-medium">{msg.from_address}</span>
                  <span className="ml-auto shrink-0 text-xs text-[var(--muted-foreground)]">
                    {msg.received_at ? new Date(msg.received_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : ""}
                  </span>
                </div>
                <span className="truncate text-sm">{msg.subject || "(no subject)"}</span>
                {msg.snippet && (
                  <span className="truncate text-xs text-[var(--muted-foreground)]">{msg.snippet}</span>
                )}
                {msg.labels.length > 0 && (
                  <div className="flex gap-1">
                    {msg.labels.slice(0, 3).map((label) => (
                      <Badge key={label} variant="outline" className="text-[10px] py-0">
                        {label}
                      </Badge>
                    ))}
                  </div>
                )}
              </button>
            ))
          )}
        </div>

        {/* Detail */}
        {selected && (
          <div className="flex w-[55%] flex-col overflow-y-auto p-4">
            <div className="mb-3 flex items-start justify-between">
              <div>
                <h3 className="text-base font-semibold">{selected.subject || "(no subject)"}</h3>
                <p className="text-sm text-[var(--muted-foreground)]">
                  From: {selected.from_address}
                </p>
                <p className="text-sm text-[var(--muted-foreground)]">
                  To: {selected.to_addresses.join(", ")}
                </p>
                {selected.received_at && (
                  <p className="text-xs text-[var(--muted-foreground)]">
                    {new Date(selected.received_at).toLocaleString()}
                  </p>
                )}
              </div>
              <Button variant="ghost" size="icon" onClick={() => setSelected(null)}>
                <ChevronRight size={16} />
              </Button>
            </div>
            {selected.has_calendar_invite && (
              <Badge className="mb-3 w-fit bg-[var(--cal-personal)]/15 text-[var(--cal-personal)]">
                <CalendarPlus size={12} className="mr-1" />
                Calendar invite detected
              </Badge>
            )}
            <div className="prose prose-sm max-w-none text-[var(--foreground)]">
              <p className="whitespace-pre-wrap text-sm">
                {selected.snippet || "No preview available. Open in your email client for full content."}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Scheduling scan results */}
      {showScan && (
        <ScanResultsPanel
          result={scanResult}
          scanning={scanning}
          onClose={() => setShowScan(false)}
        />
      )}

      {/* Compose modal */}
      {showCompose && <ComposeModal onClose={() => setShowCompose(false)} onSent={loadMessages} />}
    </div>
  );
}

/** Compose modal for sending email through a connected provider. */
function ComposeModal({
  onClose,
  onSent,
}: {
  onClose: () => void;
  onSent: () => void;
}) {
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [providers, setProviders] = useState<{ id: string; display_name: string | null; provider_type: string }[]>([]);
  const [selectedProvider, setSelectedProvider] = useState("");

  useEffect(() => {
    api.listAllProviders().then((all) => {
      const email = all.filter((p) => p.provider_type === "imap_smtp" || p.provider_type === "gmail");
      setProviders(email);
      if (email.length > 0) setSelectedProvider(email[0].id);
    }).catch(() => {});
  }, []);

  const handleSend = async () => {
    if (!selectedProvider || !to.trim()) return;
    setSending(true);
    setError(null);
    try {
      await api.sendEmail({
        provider_connection_id: selectedProvider,
        to: to.split(",").map((s) => s.trim()),
        subject,
        body_text: body,
      });
      onSent();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-lg border border-[var(--border)] bg-[var(--card)] p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-4 text-lg font-semibold">Compose Email</h3>
        {providers.length === 0 ? (
          <p className="text-sm text-[var(--muted-foreground)]">
            No email providers connected. Add one in Settings to send email.
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            <select
              value={selectedProvider}
              onChange={(e) => setSelectedProvider(e.target.value)}
              className="rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm"
            >
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name || p.provider_type}
                </option>
              ))}
            </select>
            <input
              type="text"
              placeholder="To (comma-separated)"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm"
            />
            <input
              type="text"
              placeholder="Subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm"
            />
            <textarea
              placeholder="Body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={6}
              className="rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm"
            />
            {error && <p className="text-sm text-red-500">{error}</p>}
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
              <Button size="sm" onClick={handleSend} disabled={sending || !to.trim()}>
                {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                Send
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


/** Panel showing scheduling suggestions from email scan. */
function ScanResultsPanel({
  result,
  scanning,
  onClose,
}: {
  result: ScanResult | null;
  scanning: boolean;
  onClose: () => void;
}) {
  const suggestionIcons: Record<string, typeof CheckCircle2> = {
    create_event: CalendarPlus,
    conflict_warning: AlertTriangle,
    decline: XCircle,
    reschedule_propose: Clock,
  };

  const suggestionColors: Record<string, string> = {
    create_event: "text-[var(--cal-work)]",
    conflict_warning: "text-orange-500",
    decline: "text-red-500",
    reschedule_propose: "text-[var(--cal-personal)]",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-lg border border-[var(--border)] bg-[var(--card)] p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">Scheduling Suggestions</h3>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <ChevronRight size={16} />
          </Button>
        </div>

        {scanning ? (
          <div className="flex h-32 items-center justify-center gap-2 text-sm text-[var(--muted-foreground)]">
            <Loader2 size={16} className="animate-spin" />
            Scanning emails for scheduling content...
          </div>
        ) : !result || result.suggestions.length === 0 ? (
          <div className="flex h-32 flex-col items-center justify-center gap-2 text-sm text-[var(--muted-foreground)]">
            <ScanLine size={24} className="opacity-40" />
            {result ? "No scheduling-related content found in recent emails." : "Scan failed. Make sure an email provider is connected."}
          </div>
        ) : (
          <>
            {result.summary && (
              <p className="mb-4 text-sm text-[var(--muted-foreground)]">{result.summary}</p>
            )}

            <div className="flex gap-4 overflow-y-auto">
              {/* Suggestions */}
              <div className="flex-1">
                <h4 className="mb-2 text-sm font-medium">
                  Suggestions ({result.suggestions.length})
                </h4>
                <div className="flex flex-col gap-2">
                  {result.suggestions.map((s, i) => {
                    const Icon = suggestionIcons[s.type] || Clock;
                    const color = suggestionColors[s.type] || "text-[var(--foreground)]";
                    return (
                      <div
                        key={i}
                        className="rounded-md border border-[var(--border)] p-3"
                      >
                        <div className="mb-1 flex items-center gap-2">
                          <Icon size={16} className={color} />
                          <span className="text-sm font-medium capitalize">
                            {s.type.replace(/_/g, " ")}
                          </span>
                          {s.confidence > 0 && (
                            <Badge variant="outline" className="ml-auto text-[10px] py-0">
                              {Math.round(s.confidence * 100)}%
                            </Badge>
                          )}
                        </div>
                        <p className="text-sm text-[var(--foreground)]">{s.message}</p>
                        {s.proposed_time && (
                          <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                            Proposed: {s.proposed_time.raw_text}
                            {s.proposed_time.datetime && ` (${new Date(s.proposed_time.datetime).toLocaleString()})`}
                          </p>
                        )}
                        {s.conflict_with && (
                          <p className="mt-1 text-xs text-orange-500">
                            Conflicts with: {s.conflict_with}
                          </p>
                        )}
                        {s.suggested_alternative && (
                          <p className="mt-1 text-xs text-[var(--cal-personal)]">
                            Alternative: {s.suggested_alternative}
                          </p>
                        )}
                        <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                          From: {s.email_from}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Detections */}
              {result.detections.length > 0 && (
                <div className="w-[40%]">
                  <h4 className="mb-2 text-sm font-medium">
                    Detected ({result.detections.length})
                  </h4>
                  <div className="flex flex-col gap-1.5">
                    {result.detections
                      .filter((d) => d.is_scheduling_related)
                      .map((d, i) => (
                        <div key={i} className="rounded-md border border-[var(--border)] p-2">
                          <p className="truncate text-xs font-medium">{d.subject || "(no subject)"}</p>
                          <div className="flex gap-1">
                            {d.is_meeting_proposal && (
                              <Badge variant="outline" className="text-[10px] py-0">Proposal</Badge>
                            )}
                            {d.is_calendar_invite && (
                              <Badge variant="outline" className="text-[10px] py-0">Invite</Badge>
                            )}
                            {d.is_reschedule && (
                              <Badge variant="outline" className="text-[10px] py-0">Reschedule</Badge>
                            )}
                            {d.is_cancellation && (
                              <Badge variant="outline" className="text-[10px] py-0">Cancel</Badge>
                            )}
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
    </div>
  );
}
