"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Calendar, Clock, Video, CheckCircle2, ChevronLeft, ChevronRight,
  Loader2, AlertTriangle, User, Mail, Globe, ArrowLeft,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { EventType, BookingSlot, CustomQuestion } from "@/types";

/**
 * BookingPage — the public-facing booking page for an event type.
 *
 * Shows the event type title, duration, and description, then lets the
 * visitor pick a date, select an available time slot, fill in any custom
 * questions, and confirm the booking. On success, shows a confirmation
 * screen with the video link (if any).
 */
export function BookingPage({ slug, isEmbed = false }: { slug: string; isEmbed?: boolean }) {
  const [eventType, setEventType] = useState<EventType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return d;
  });
  const [slots, setSlots] = useState<BookingSlot[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState<BookingSlot | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [timezone, setTimezone] = useState(
    Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
  );
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [confirmed, setConfirmed] = useState<{
    bookingId: string;
    videoLink: string | null;
    startTime: string;
    endTime: string;
  } | null>(null);

  const loadEventType = useCallback(async () => {
    try {
      const et = await api.getPublicEventType(slug);
      setEventType(et);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Booking page not found");
    } finally {
      setLoading(false);
    }
  }, [slug]);

  const loadSlots = useCallback(async () => {
    if (!eventType) return;
    setSlotsLoading(true);
    setSelectedSlot(null);
    try {
      const dateStr = selectedDate.toISOString().split("T")[0];
      const result = await api.getBookingSlots(slug, dateStr, timezone);
      setSlots(result.slots);
    } catch {
      setSlots([]);
    } finally {
      setSlotsLoading(false);
    }
  }, [slug, eventType, selectedDate, timezone]);

  useEffect(() => {
    loadEventType();
  }, [loadEventType]);

  useEffect(() => {
    if (eventType) loadSlots();
  }, [loadSlots]);

  const handlePrevDay = useCallback(() => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() - 1);
    if (d >= new Date()) setSelectedDate(d);
  }, [selectedDate]);

  const handleNextDay = useCallback(() => {
    const maxDays = eventType?.max_booking_days || 60;
    const maxDate = new Date();
    maxDate.setDate(maxDate.getDate() + maxDays);
    const d = new Date(selectedDate);
    d.setDate(d.getDate() + 1);
    if (d <= maxDate) setSelectedDate(d);
  }, [selectedDate, eventType]);

  const handleSubmit = useCallback(async () => {
    if (!selectedSlot || !name.trim() || !email.trim()) return;
    setSubmitting(true);
    try {
      const result = await api.createPublicBooking(slug, {
        attendee_name: name,
        attendee_email: email,
        attendee_timezone: timezone,
        start_time: selectedSlot.start,
        answers,
      });
      setConfirmed({
        bookingId: result.booking_id,
        videoLink: result.video_link,
        startTime: result.start_time,
        endTime: result.end_time,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Booking failed");
    } finally {
      setSubmitting(false);
    }
  }, [slug, selectedSlot, name, email, timezone, answers]);

  const dateLabel = useMemo(() => {
    return selectedDate.toLocaleDateString("en-US", {
      weekday: "long",
      month: "long",
      day: "numeric",
    });
  }, [selectedDate]);

  const isToday = useMemo(() => {
    const today = new Date();
    return selectedDate.toDateString() === today.toDateString();
  }, [selectedDate]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 size={24} className="animate-spin text-[var(--primary)]" />
      </div>
    );
  }

  if (error && !eventType) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
        <AlertTriangle size={32} className="text-[var(--destructive)]" />
        <p className="text-sm text-[var(--muted-foreground)]">{error}</p>
        {!isEmbed && (
          <a href="/" className="text-sm text-[var(--primary)] hover:underline">
            Back to A-Cal
          </a>
        )}
      </div>
    );
  }

  if (confirmed) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
        <CheckCircle2 size={48} className="text-[var(--primary)]" />
        <h2 className="text-xl font-semibold">Booking Confirmed!</h2>
        <p className="text-sm text-[var(--muted-foreground)]">
          {eventType?.title} — {new Date(confirmed.startTime).toLocaleString("en-US", {
            weekday: "long", month: "long", day: "numeric",
            hour: "numeric", minute: "2-digit",
          })}
        </p>
        {confirmed.videoLink && (
          <a
            href={confirmed.videoLink}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2"
          >
            <Button>
              <Video size={16} />
              Join Video Meeting
            </Button>
          </a>
        )}
        <p className="mt-4 text-xs text-[var(--muted-foreground)]">
          A confirmation email has been sent to {email}
        </p>
      </div>
    );
  }

  return (
    <div className={cn("flex h-full flex-col", isEmbed ? "p-4" : "p-6 max-w-2xl mx-auto")}>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold">{eventType?.title}</h1>
        <div className="mt-2 flex items-center gap-3 text-sm text-[var(--muted-foreground)]">
          <span className="flex items-center gap-1">
            <Clock size={14} />
            {eventType?.duration_minutes} min
          </span>
          {eventType?.video_provider && (
            <span className="flex items-center gap-1">
              <Video size={14} />
              {eventType.video_provider === "meet" ? "Google Meet" :
               eventType.video_provider === "zoom" ? "Zoom" :
               eventType.video_provider === "teams" ? "Teams" : eventType.video_provider}
            </span>
          )}
        </div>
        {eventType?.description && (
          <p className="mt-2 text-sm text-[var(--muted-foreground)]">{eventType.description}</p>
        )}
      </div>

      <div className="flex flex-1 gap-6">
        {/* Date + slot picker */}
        <div className="w-64 shrink-0 space-y-3">
          <div className="flex items-center justify-between">
            <button onClick={handlePrevDay} disabled={isToday} className="text-[var(--muted-foreground)] disabled:opacity-30">
              <ChevronLeft size={20} />
            </button>
            <span className="text-sm font-medium">{dateLabel}</span>
            <button onClick={handleNextDay} className="text-[var(--muted-foreground)]">
              <ChevronRight size={20} />
            </button>
          </div>

          {slotsLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 size={20} className="animate-spin text-[var(--primary)]" />
            </div>
          ) : slots.length === 0 ? (
            <div className="py-8 text-center text-sm text-[var(--muted-foreground)]">
              No available times on this day
            </div>
          ) : (
            <div className="max-h-80 space-y-1.5 overflow-y-auto">
              {slots.map((slot) => {
                const slotTime = new Date(slot.start).toLocaleTimeString("en-US", {
                  hour: "numeric", minute: "2-digit",
                });
                const isSelected = selectedSlot?.start === slot.start;
                return (
                  <button
                    key={slot.start}
                    onClick={() => setSelectedSlot(slot)}
                    className={cn(
                      "w-full rounded-md border px-3 py-2 text-sm transition-colors",
                      isSelected
                        ? "border-[var(--primary)] bg-[var(--primary)]/10 font-medium"
                        : "border-[var(--border)] hover:border-[var(--primary)]/50 hover:bg-[var(--accent)]/30"
                    )}
                  >
                    {slotTime}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Booking form */}
        <div className="flex-1 space-y-3">
          {selectedSlot ? (
            <>
              <div className="flex items-center gap-2 text-sm">
                <Calendar size={14} className="text-[var(--primary)]" />
                <span>
                  {new Date(selectedSlot.start).toLocaleString("en-US", {
                    weekday: "long", month: "long", day: "numeric",
                    hour: "numeric", minute: "2-digit",
                  })}
                </span>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium text-[var(--muted-foreground)]">Your Name</label>
                <div className="flex items-center gap-2">
                  <User size={14} className="text-[var(--muted-foreground)]" />
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Jane Doe"
                    className="h-9 text-sm"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium text-[var(--muted-foreground)]">Email</label>
                <div className="flex items-center gap-2">
                  <Mail size={14} className="text-[var(--muted-foreground)]" />
                  <Input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="jane@example.com"
                    className="h-9 text-sm"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium text-[var(--muted-foreground)]">Timezone</label>
                <div className="flex items-center gap-2">
                  <Globe size={14} className="text-[var(--muted-foreground)]" />
                  <Input
                    value={timezone}
                    onChange={(e) => setTimezone(e.target.value)}
                    className="h-9 text-sm"
                  />
                </div>
              </div>

              {/* Custom questions */}
              {eventType?.custom_questions?.map((q) => (
                <div key={q.id} className="space-y-2">
                  <label className="text-xs font-medium text-[var(--muted-foreground)]">
                    {q.label}
                    {q.required && <span className="text-[var(--destructive)]"> *</span>}
                  </label>
                  {q.type === "textarea" ? (
                    <textarea
                      value={answers[q.id] || ""}
                      onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
                      placeholder={q.placeholder || ""}
                      className="w-full resize-none rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
                      rows={3}
                    />
                  ) : q.type === "select" ? (
                    <Select
                      value={answers[q.id] || ""}
                      onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
                      className="h-9 text-sm"
                    >
                      <option value="">Select...</option>
                      {q.options.map((opt) => (
                        <option key={opt} value={opt}>{opt}</option>
                      ))}
                    </Select>
                  ) : (
                    <Input
                      type={q.type === "phone" ? "tel" : "text"}
                      value={answers[q.id] || ""}
                      onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
                      placeholder={q.placeholder || ""}
                      className="h-9 text-sm"
                    />
                  )}
                </div>
              ))}

              {error && (
                <div className="flex items-center gap-2 text-sm text-[var(--destructive)]">
                  <AlertTriangle size={14} />
                  {error}
                </div>
              )}

              <Button
                onClick={handleSubmit}
                disabled={submitting || !name.trim() || !email.trim()}
                className="w-full"
              >
                {submitting ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
                Confirm Booking
              </Button>
            </>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-[var(--muted-foreground)]">
              Select a time slot to continue
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
