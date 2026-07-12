"use client";

import { useState, useEffect, useCallback } from "react";
import { Mail, RefreshCw, Inbox, CalendarPlus, Send, Loader2, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { EmailMessage } from "@/types";

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
