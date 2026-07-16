"use client";

import { useState, useEffect, useCallback } from "react";
import {
  CalendarPlus, Clock, Video, Bell, Copy, Trash2, Plus,
  Loader2, ExternalLink, Code, X, ChevronDown, ChevronRight,
  AlertTriangle, CheckCircle2, Users, Calendar,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { EventType, Booking, CustomQuestion } from "@/types";

/**
 * SchedulingPanel — manage event types and view bookings.
 *
 * Lets the user create and configure Calendly-style booking pages with
 * scheduling constraints (buffer time, min notice, max window), recurring
 * patterns, custom questions, video provider selection, and reminders.
 * Also shows upcoming bookings with cancel/manage actions.
 */
export function SchedulingPanel() {
  const [eventTypes, setEventTypes] = useState<EventType[]>([]);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedEt, setSelectedEt] = useState<EventType | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showBookings, setShowBookings] = useState(false);
  const [copiedSlug, setCopiedSlug] = useState<string | null>(null);

  const loadEventTypes = useCallback(async () => {
    try {
      const data = await api.listEventTypes();
      setEventTypes(data);
    } catch {
      setEventTypes([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadBookings = useCallback(async () => {
    try {
      const data = await api.listBookings();
      setBookings(data);
    } catch {
      setBookings([]);
    }
  }, []);

  useEffect(() => {
    loadEventTypes();
  }, [loadEventTypes]);

  useEffect(() => {
    if (showBookings) loadBookings();
  }, [showBookings, loadBookings]);

  const handleCopyLink = useCallback((slug: string) => {
    const url = `${window.location.origin}/booking/${slug}`;
    navigator.clipboard.writeText(url);
    setCopiedSlug(slug);
    setTimeout(() => setCopiedSlug(null), 2000);
  }, []);

  const handleDeleteEt = useCallback(async (id: string) => {
    try {
      await api.deleteEventType(id);
      loadEventTypes();
    } catch {
      // keep state on error
    }
  }, [loadEventTypes]);

  const handleCancelBooking = useCallback(async (id: string) => {
    try {
      await api.updateBooking(id, { status: "cancelled" });
      loadBookings();
    } catch {
      // keep state on error
    }
  }, [loadBookings]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 size={24} className="animate-spin text-[var(--primary)]" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-[var(--border)] px-4 py-2">
        <button
          onClick={() => setShowBookings(false)}
          className={cn(
            "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
            !showBookings ? "bg-[var(--accent)] text-[var(--foreground)]" : "text-[var(--muted-foreground)] hover:bg-[var(--accent)]/50"
          )}
        >
          <CalendarPlus size={14} />
          Event Types
        </button>
        <button
          onClick={() => setShowBookings(true)}
          className={cn(
            "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
            showBookings ? "bg-[var(--accent)] text-[var(--foreground)]" : "text-[var(--muted-foreground)] hover:bg-[var(--accent)]/50"
          )}
        >
          <Calendar size={14} />
          Bookings
          {bookings.length > 0 && (
            <Badge className="ml-1 text-[10px] py-0 px-1.5">{bookings.length}</Badge>
          )}
        </button>
        <div className="flex-1" />
        {!showBookings && (
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus size={14} />
            New Event Type
          </Button>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {!showBookings ? (
          /* Event types list */
          <div className="space-y-2">
            {eventTypes.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
                <CalendarPlus size={32} className="text-[var(--muted-foreground)]" />
                <p className="text-sm text-[var(--muted-foreground)]">
                  No event types yet. Create one to start accepting bookings.
                </p>
                <Button size="sm" onClick={() => setShowCreate(true)}>
                  <Plus size={14} />
                  Create Event Type
                </Button>
              </div>
            ) : (
              eventTypes.map((et) => (
                <div
                  key={et.id}
                  className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-4"
                >
                  <div className="flex items-start justify-between">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <div
                          className="h-3 w-3 rounded-full"
                          style={{ backgroundColor: et.color }}
                        />
                        <span className="font-medium">{et.title}</span>
                        <Badge variant="outline" className="text-[10px] py-0">
                          {et.duration_minutes} min
                        </Badge>
                        {et.video_provider && (
                          <Badge variant="outline" className="text-[10px] py-0">
                            <Video size={8} className="mr-1" />
                            {et.video_provider}
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-[var(--muted-foreground)]">
                        /{et.slug}
                        {et.buffer_before_minutes > 0 || et.buffer_after_minutes > 0
                          ? ` · ${et.buffer_before_minutes}+${et.buffer_after_minutes}min buffer`
                          : ""}
                        {et.min_notice_hours > 0 ? ` · ${et.min_notice_hours}h notice` : ""}
                        {et.custom_questions?.length > 0
                          ? ` · ${et.custom_questions.length} questions`
                          : ""}
                      </p>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleCopyLink(et.slug)}
                      >
                        {copiedSlug === et.slug ? <CheckCircle2 size={14} /> : <Copy size={14} />}
                      </Button>
                      <a href={`/booking/${et.slug}`} target="_blank" rel="noopener noreferrer">
                        <Button variant="ghost" size="sm">
                          <ExternalLink size={14} />
                        </Button>
                      </a>
                      <Button variant="ghost" size="sm" onClick={() => setSelectedEt(et)}>
                        <ChevronRight size={14} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteEt(et.id)}
                      >
                        <Trash2 size={14} className="text-[var(--destructive)]" />
                      </Button>
                    </div>
                  </div>

                  {/* Embed code */}
                  <div className="mt-3 flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
                    <Code size={12} />
                    <code className="rounded bg-[var(--muted)] px-1.5 py-0.5">
                      {`<iframe src="${typeof window !== "undefined" ? window.location.origin : ""}/embed/${et.slug}" width="100%" height="600" frameborder="0" />`}
                    </code>
                  </div>
                </div>
              ))
            )}
          </div>
        ) : (
          /* Bookings list */
          <div className="space-y-2">
            {bookings.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
                <Calendar size={32} className="text-[var(--muted-foreground)]" />
                <p className="text-sm text-[var(--muted-foreground)]">No bookings yet.</p>
              </div>
            ) : (
              bookings.map((b) => {
                const et = eventTypes.find((e) => e.id === b.event_type_id);
                return (
                  <div
                    key={b.id}
                    className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-4"
                  >
                    <div className="flex items-start justify-between">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{b.attendee_name}</span>
                          <Badge
                            variant="outline"
                            className={cn(
                              "text-[10px] py-0",
                              b.status === "confirmed" && "border-[var(--primary)] text-[var(--primary)]",
                              b.status === "cancelled" && "border-[var(--destructive)] text-[var(--destructive)]",
                            )}
                          >
                            {b.status}
                          </Badge>
                        </div>
                        <p className="text-xs text-[var(--muted-foreground)]">
                          {b.attendee_email}
                        </p>
                        <p className="text-xs text-[var(--muted-foreground)]">
                          {et?.title || "Event"} —{" "}
                          {b.start_time ? new Date(b.start_time).toLocaleString("en-US", {
                            weekday: "short", month: "short", day: "numeric",
                            hour: "numeric", minute: "2-digit",
                          }) : "Unknown time"}
                        </p>
                        {b.video_link && (
                          <a
                            href={b.video_link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-[var(--primary)] hover:underline"
                          >
                            <Video size={10} />
                            Video link
                          </a>
                        )}
                      </div>
                      {b.status === "confirmed" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleCancelBooking(b.id)}
                        >
                          Cancel
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>

      {/* Create/Edit modal */}
      {(showCreate || selectedEt) && (
        <EventTypeEditor
          eventTypes={eventTypes}
          editing={selectedEt}
          onClose={() => { setShowCreate(false); setSelectedEt(null); }}
          onSaved={() => { setShowCreate(false); setSelectedEt(null); loadEventTypes(); }}
        />
      )}
    </div>
  );
}

/**
 * EventTypeEditor — create or edit an event type with full scheduling config.
 */
function EventTypeEditor({
  eventTypes,
  editing,
  onClose,
  onSaved,
}: {
  eventTypes: EventType[];
  editing: EventType | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(editing?.title ?? "");
  const [slug, setSlug] = useState(editing?.slug ?? "");
  const [duration, setDuration] = useState(editing?.duration_minutes ?? 30);
  const [description, setDescription] = useState(editing?.description ?? "");
  const [color, setColor] = useState(editing?.color ?? "#3B82F6");
  const [bufferBefore, setBufferBefore] = useState(editing?.buffer_before_minutes ?? 0);
  const [bufferAfter, setBufferAfter] = useState(editing?.buffer_after_minutes ?? 0);
  const [minNotice, setMinNotice] = useState(editing?.min_notice_hours ?? 24);
  const [maxDays, setMaxDays] = useState(editing?.max_booking_days ?? 60);
  const [recurring, setRecurring] = useState(editing?.recurring_pattern ?? "none");
  const [recurringInterval, setRecurringInterval] = useState(editing?.recurring_interval ?? 1);
  const [videoProvider, setVideoProvider] = useState(editing?.video_provider ?? "");
  const [reminderEnabled, setReminderEnabled] = useState(editing?.reminder_enabled ?? true);
  const [reminderMinutes, setReminderMinutes] = useState(editing?.reminder_minutes_before ?? 60);
  const [confirmationEnabled, setConfirmationEnabled] = useState(editing?.confirmation_email_enabled ?? true);
  const [questions, setQuestions] = useState<CustomQuestion[]>(editing?.custom_questions ?? []);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAddQuestion = useCallback(() => {
    setQuestions([...questions, {
      id: `q${Date.now()}`,
      label: "",
      type: "text",
      required: false,
      options: [],
      placeholder: "",
    }]);
  }, [questions]);

  const handleUpdateQuestion = useCallback((idx: number, patch: Partial<CustomQuestion>) => {
    setQuestions(questions.map((q, i) => i === idx ? { ...q, ...patch } : q));
  }, [questions]);

  const handleRemoveQuestion = useCallback((idx: number) => {
    setQuestions(questions.filter((_, i) => i !== idx));
  }, [questions]);

  const handleSave = useCallback(async () => {
    if (!title.trim() || !slug.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const data = {
        title,
        slug,
        duration_minutes: duration,
        description,
        color,
        buffer_before_minutes: bufferBefore,
        buffer_after_minutes: bufferAfter,
        min_notice_hours: minNotice,
        max_booking_days: maxDays,
        recurring_pattern: recurring,
        recurring_interval: recurringInterval,
        custom_questions: questions,
        video_provider: videoProvider,
        reminder_enabled: reminderEnabled,
        reminder_minutes_before: reminderMinutes,
        confirmation_email_enabled: confirmationEnabled,
      };
      if (editing) {
        await api.updateEventType(editing.id, data);
      } else {
        await api.createEventType(data);
      }
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }, [title, slug, duration, description, color, bufferBefore, bufferAfter,
      minNotice, maxDays, recurring, recurringInterval, questions, videoProvider,
      reminderEnabled, reminderMinutes, confirmationEnabled, editing, onSaved]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-[var(--border)] bg-[var(--background)] shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 flex items-center gap-2 border-b border-[var(--border)] bg-[var(--background)] px-4 py-3">
          <CalendarPlus size={16} className="text-[var(--primary)]" />
          <span className="text-sm font-semibold">{editing ? "Edit" : "New"} Event Type</span>
          <div className="flex-1" />
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X size={16} />
          </Button>
        </div>

        <div className="space-y-4 p-4">
          {/* Basic fields */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">Title</label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="30 Minute Meeting" className="h-9 text-sm" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">URL Slug</label>
              <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="30-min" className="h-9 text-sm font-mono" />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">Duration (min)</label>
              <Input type="number" value={duration} onChange={(e) => setDuration(Number(e.target.value))} className="h-9 text-sm" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">Color</label>
              <Input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-9 text-sm" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">Video Provider</label>
              <Select value={videoProvider} onChange={(e) => setVideoProvider(e.target.value)} className="h-9 text-sm">
                <option value="">None</option>
                <option value="meet">Google Meet</option>
                <option value="zoom">Zoom</option>
                <option value="teams">Microsoft Teams</option>
              </Select>
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What is this meeting about?"
              className="w-full resize-none rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
              rows={2}
            />
          </div>

          {/* Advanced settings toggle */}
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex w-full items-center gap-1 text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          >
            {showAdvanced ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            Scheduling Constraints & Reminders
          </button>

          {showAdvanced && (
            <div className="space-y-3 rounded-md border border-[var(--border)] bg-[var(--muted)]/30 p-3">
              {/* Buffer time */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-[var(--muted-foreground)]">Buffer Before (min)</label>
                  <Input type="number" value={bufferBefore} onChange={(e) => setBufferBefore(Number(e.target.value))} className="h-8 text-sm" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-[var(--muted-foreground)]">Buffer After (min)</label>
                  <Input type="number" value={bufferAfter} onChange={(e) => setBufferAfter(Number(e.target.value))} className="h-8 text-sm" />
                </div>
              </div>

              {/* Notice + window */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-[var(--muted-foreground)]">Min Notice (hours)</label>
                  <Input type="number" value={minNotice} onChange={(e) => setMinNotice(Number(e.target.value))} className="h-8 text-sm" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-[var(--muted-foreground)]">Max Booking Window (days)</label>
                  <Input type="number" value={maxDays} onChange={(e) => setMaxDays(Number(e.target.value))} className="h-8 text-sm" />
                </div>
              </div>

              {/* Recurring */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-[var(--muted-foreground)]">Recurring Pattern</label>
                  <Select value={recurring} onChange={(e) => setRecurring(e.target.value)} className="h-8 text-sm">
                    <option value="none">None (one-off)</option>
                    <option value="daily">Daily</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                  </Select>
                </div>
                {recurring !== "none" && (
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-[var(--muted-foreground)]">Interval (every N {recurring === "daily" ? "days" : recurring === "weekly" ? "weeks" : "months"})</label>
                    <Input type="number" value={recurringInterval} onChange={(e) => setRecurringInterval(Number(e.target.value))} min={1} className="h-8 text-sm" />
                  </div>
                )}
              </div>

              {/* Reminders */}
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={reminderEnabled} onChange={(e) => setReminderEnabled(e.target.checked)} />
                  <Bell size={12} />
                  Reminder
                </label>
                {reminderEnabled && (
                  <div className="flex items-center gap-2 text-xs">
                    <Input type="number" value={reminderMinutes} onChange={(e) => setReminderMinutes(Number(e.target.value))} className="h-8 w-20 text-sm" />
                    <span className="text-[var(--muted-foreground)]">min before</span>
                  </div>
                )}
                <label className="flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={confirmationEnabled} onChange={(e) => setConfirmationEnabled(e.target.checked)} />
                  Confirmation email
                </label>
              </div>
            </div>
          )}

          {/* Custom questions */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">Custom Questions</label>
              <Button variant="ghost" size="sm" onClick={handleAddQuestion}>
                <Plus size={12} />
                Add
              </Button>
            </div>
            {questions.map((q, idx) => (
              <div key={q.id} className="flex items-center gap-2 rounded-md border border-[var(--border)] p-2">
                <Input
                  value={q.label}
                  onChange={(e) => handleUpdateQuestion(idx, { label: e.target.value })}
                  placeholder="Question text"
                  className="h-8 flex-1 text-sm"
                />
                <Select
                  value={q.type}
                  onChange={(e) => handleUpdateQuestion(idx, { type: e.target.value as CustomQuestion["type"] })}
                  className="h-8 w-28 text-sm"
                >
                  <option value="text">Text</option>
                  <option value="textarea">Long text</option>
                  <option value="select">Dropdown</option>
                  <option value="phone">Phone</option>
                </Select>
                <label className="flex items-center gap-1 text-xs">
                  <input
                    type="checkbox"
                    checked={q.required}
                    onChange={(e) => handleUpdateQuestion(idx, { required: e.target.checked })}
                  />
                  Req
                </label>
                <Button variant="ghost" size="sm" onClick={() => handleRemoveQuestion(idx)}>
                  <X size={12} />
                </Button>
              </div>
            ))}
          </div>

          {error && (
            <div className="flex items-center gap-2 text-sm text-[var(--destructive)]">
              <AlertTriangle size={14} />
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 flex justify-end gap-2 border-t border-[var(--border)] bg-[var(--background)] px-4 py-3">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={handleSave} disabled={saving || !title.trim() || !slug.trim()}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
            {editing ? "Update" : "Create"}
          </Button>
        </div>
      </div>
    </div>
  );
}
