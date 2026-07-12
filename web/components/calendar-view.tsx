"use client";

import { useMemo, useState } from "react";
import {
  addDays,
  addWeeks,
  addMonths,
  startOfWeek,
  endOfWeek,
  startOfMonth,
  endOfMonth,
  eachDayOfInterval,
  format,
  isSameDay,
  isSameMonth,
  isToday,
  parseISO,
} from "date-fns";
import {
  ChevronLeft,
  ChevronRight,
  Calendar as CalendarIcon,
  Plus,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn, colorFromString } from "@/lib/utils";
import { api } from "@/lib/api";
import type { UnifiedEvent, SubAccount } from "@/types";

interface CalendarViewProps {
  events: UnifiedEvent[];
  subAccounts: SubAccount[];
  visibleSubAccounts: Set<string>;
  onEventCreated?: () => void;
  onEventUpdated?: () => void;
}

type ViewMode = "day" | "week" | "month";

export function CalendarView({ events, subAccounts, visibleSubAccounts, onEventCreated, onEventUpdated }: CalendarViewProps) {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [viewMode, setViewMode] = useState<ViewMode>("week");
  const [selectedEvent, setSelectedEvent] = useState<UnifiedEvent | null>(null);
  const [showNewEvent, setShowNewEvent] = useState(false);
  const [draggedEvent, setDraggedEvent] = useState<UnifiedEvent | null>(null);
  const [dragOverSlot, setDragOverSlot] = useState<string | null>(null);

  const subAccountMap = useMemo(() => {
    const map: Record<string, SubAccount> = {};
    for (const sa of subAccounts) map[sa.id] = sa;
    return map;
  }, [subAccounts]);

  const filteredEvents = useMemo(
    () => events.filter((e) => !e.source_sub_account_id || visibleSubAccounts.has(e.source_sub_account_id)),
    [events, visibleSubAccounts]
  );

  const { days, headerLabel } = useMemo(() => {
    if (viewMode === "day") {
      return {
        days: [currentDate],
        headerLabel: format(currentDate, "EEEE, MMMM d, yyyy"),
      };
    }
  if (viewMode === "week") {
      const start = startOfWeek(currentDate, { weekStartsOn: 0 });
      const end = endOfWeek(currentDate, { weekStartsOn: 0 });
      return {
        days: eachDayOfInterval({ start, end }),
        headerLabel: `${format(start, "MMM d")} – ${format(end, "MMM d, yyyy")}`,
      };
    }
    const start = startOfWeek(startOfMonth(currentDate), { weekStartsOn: 0 });
    const end = endOfWeek(endOfMonth(currentDate), { weekStartsOn: 0 });
    return {
      days: eachDayOfInterval({ start, end }),
      headerLabel: format(currentDate, "MMMM yyyy"),
    };
  }, [currentDate, viewMode]);

  const eventsByDay = useMemo(() => {
    const map: Record<string, UnifiedEvent[]> = {};
    for (const ev of filteredEvents) {
      const dayKey = format(parseISO(ev.start), "yyyy-MM-dd");
      if (!map[dayKey]) map[dayKey] = [];
      map[dayKey].push(ev);
    }
    for (const key of Object.keys(map)) {
      map[key].sort((a, b) => a.start.localeCompare(b.start));
    }
    return map;
  }, [filteredEvents]);

  const navigate = (dir: "prev" | "next" | "today") => {
    if (dir === "today") {
      setCurrentDate(new Date());
      return;
    }
    const delta = dir === "next" ? 1 : -1;
    if (viewMode === "day") setCurrentDate(addDays(currentDate, delta));
    else if (viewMode === "week") setCurrentDate(addWeeks(currentDate, delta));
    else setCurrentDate(addMonths(currentDate, delta));
  };

  const hours = Array.from({ length: 24 }, (_, i) => i);

  const handleDropEvent = async (day: Date, hour: number) => {
    if (!draggedEvent) return;
    const start = parseISO(draggedEvent.start);
    const end = parseISO(draggedEvent.end);
    const durationMin = (end.getTime() - start.getTime()) / (1000 * 60);
    const newStart = new Date(day);
    newStart.setHours(hour, start.getMinutes(), 0, 0);
    const newEnd = new Date(newStart.getTime() + durationMin * 60 * 1000);
    setDraggedEvent(null);
    setDragOverSlot(null);
    try {
      await api.updateEvent(draggedEvent.provider_event_id, {
        start: newStart.toISOString(),
        end: newEnd.toISOString(),
      });
      onEventUpdated?.();
    } catch {
      // keep current state on error
    }
  };

  if (viewMode === "day") {
    return (
      <div className="flex flex-col h-full">
        <CalendarHeader
          label={headerLabel}
          viewMode={viewMode}
          setViewMode={setViewMode}
          navigate={navigate}
          onNewEvent={() => setShowNewEvent(true)}
        />
        <div className="flex flex-1 overflow-hidden">
          <div className="w-16 shrink-0 border-r border-[var(--border)]">
            <div className="h-12 border-b border-[var(--border)]" />
            {hours.map((h) => (
              <div key={h} className="h-14 border-b border-[var(--border)]/50 px-2 pt-1 text-xs text-[var(--muted-foreground)]">
                {h === 0 ? "" : format(new Date().setHours(h, 0, 0, 0), "ha").toLowerCase()}
              </div>
            ))}
          </div>
          <div className="flex flex-1 overflow-x-auto">
            {days.map((day) => {
              const dayKey = format(day, "yyyy-MM-dd");
              const dayEvents = eventsByDay[dayKey] || [];
              return (
                <div key={dayKey} className="flex-1 min-w-[300px] border-r border-[var(--border)] last:border-r-0">
                  <div
                    className={cn(
                      "h-12 border-b border-[var(--border)] flex flex-col items-center justify-center",
                      isToday(day) && "bg-[var(--primary)]/10"
                    )}
                  >
                    <span className="text-xs text-[var(--muted-foreground)] uppercase">
                      {format(day, "EEE")}
                    </span>
                    <span
                      className={cn(
                        "text-sm font-semibold",
                        isToday(day) && "text-[var(--primary)]"
                      )}
                    >
                      {format(day, "d")}
                    </span>
                  </div>
                  <div className="relative">
                    {hours.map((h) => (
                      <div
                        key={h}
                        className={cn(
                          "h-14 border-b border-[var(--border)]/30 transition-colors",
                          dragOverSlot === `${dayKey}-${h}` && "bg-[var(--primary)]/10"
                        )}
                        onDragOver={(e) => { e.preventDefault(); setDragOverSlot(`${dayKey}-${h}`); }}
                        onDragLeave={() => setDragOverSlot(null)}
                        onDrop={() => handleDropEvent(day, h)}
                      />
                    ))}
                    {dayEvents.map((ev) => {
                      const start = parseISO(ev.start);
                      const end = parseISO(ev.end);
                      const startHour = start.getHours() + start.getMinutes() / 60;
                      const duration = (end.getTime() - start.getTime()) / (1000 * 60 * 60);
                      const top = startHour * 56 + 48;
                      const height = Math.max(duration * 56 - 2, 20);
                      const sa = ev.source_sub_account_id ? subAccountMap[ev.source_sub_account_id] : null;
                      const color = sa ? colorFromString(sa.id) : "var(--cal-other)";
                      const hasConflict = Boolean(ev.metadata?.conflict);
                      return (
                        <button
                          key={ev.provider_event_id}
                          draggable
                          onDragStart={() => setDraggedEvent(ev)}
                          onClick={() => setSelectedEvent(ev)}
                          className={cn(
                            "absolute left-1 right-1 rounded-md px-2 py-1 text-left text-xs overflow-hidden transition-opacity hover:opacity-80 cursor-grab active:cursor-grabbing",
                            hasConflict && "ring-1 ring-[var(--destructive)]"
                          )}
                          style={{
                            top: `${top}px`,
                            height: `${height}px`,
                            backgroundColor: `color-mix(in oklch, ${color} 15%, transparent)`,
                            borderLeft: `3px solid ${color}`,
                          }}
                        >
                          <div className="font-medium truncate text-[var(--foreground)]">
                            {ev.title}
                          </div>
                          {height > 35 && (
                            <div className="text-[var(--muted-foreground)] truncate">
                              {format(start, "h:mma").toLowerCase()}
                            </div>
                          )}
                          {hasConflict && height > 50 && (
                            <div className="flex items-center gap-1 text-[var(--destructive)] mt-0.5">
                              <AlertCircle size={10} />
                              <span className="text-[10px]">Conflict</span>
                            </div>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        {selectedEvent && (
          <EventDetailPanel
            event={selectedEvent}
            subAccount={selectedEvent.source_sub_account_id ? subAccountMap[selectedEvent.source_sub_account_id] : null}
            onClose={() => setSelectedEvent(null)}
          />
        )}
        {showNewEvent && (
          <NewEventModal
            defaultDate={currentDate}
            subAccounts={subAccounts}
            onClose={() => setShowNewEvent(false)}
            onCreated={() => {
              setShowNewEvent(false);
              onEventCreated?.();
            }}
          />
        )}
      </div>
    );
  }

  if (viewMode === "week") {
    return (
      <div className="flex flex-col h-full">
        <CalendarHeader
          label={headerLabel}
          viewMode={viewMode}
          setViewMode={setViewMode}
          navigate={navigate}
          onNewEvent={() => setShowNewEvent(true)}
        />
        <div className="flex flex-1 overflow-hidden">
          {/* Time column */}
          <div className="w-16 shrink-0 border-r border-[var(--border)]">
            <div className="h-12 border-b border-[var(--border)]" />
            {hours.map((h) => (
              <div key={h} className="h-14 border-b border-[var(--border)]/50 px-2 pt-1 text-xs text-[var(--muted-foreground)]">
                {h === 0 ? "" : format(new Date().setHours(h, 0, 0, 0), "ha").toLowerCase()}
              </div>
            ))}
          </div>
          {/* Day columns */}
          <div className="flex flex-1 overflow-x-auto">
            {days.map((day) => {
              const dayKey = format(day, "yyyy-MM-dd");
              const dayEvents = eventsByDay[dayKey] || [];
              const inMonth = true;
              return (
                <div
                  key={dayKey}
                  className={cn(
                    "flex-1 min-w-[120px] border-r border-[var(--border)] last:border-r-0",
                    !inMonth && "opacity-40"
                  )}
                >
                  <div
                    className={cn(
                      "h-12 border-b border-[var(--border)] flex flex-col items-center justify-center",
                      isToday(day) && "bg-[var(--primary)]/10"
                    )}
                  >
                    <span className="text-xs text-[var(--muted-foreground)] uppercase">
                      {format(day, "EEE")}
                    </span>
                    <span
                      className={cn(
                        "text-sm font-semibold",
                        isToday(day) && "text-[var(--primary)]"
                      )}
                    >
                      {format(day, "d")}
                    </span>
                  </div>
                  <div className="relative">
                    {hours.map((h) => (
                      <div
                        key={h}
                        className={cn(
                          "h-14 border-b border-[var(--border)]/30 transition-colors",
                          dragOverSlot === `${dayKey}-${h}` && "bg-[var(--primary)]/10"
                        )}
                        onDragOver={(e) => { e.preventDefault(); setDragOverSlot(`${dayKey}-${h}`); }}
                        onDragLeave={() => setDragOverSlot(null)}
                        onDrop={() => handleDropEvent(day, h)}
                      />
                    ))}
                    {dayEvents.map((ev) => {
                      const start = parseISO(ev.start);
                      const end = parseISO(ev.end);
                      const startHour = start.getHours() + start.getMinutes() / 60;
                      const duration = (end.getTime() - start.getTime()) / (1000 * 60 * 60);
                      const top = startHour * 56 + 48;
                      const height = Math.max(duration * 56 - 2, 20);
                      const sa = ev.source_sub_account_id ? subAccountMap[ev.source_sub_account_id] : null;
                      const color = sa ? colorFromString(sa.id) : "var(--cal-other)";
                      const hasConflict = Boolean(ev.metadata?.conflict);
                      return (
                        <button
                          key={ev.provider_event_id}
                          draggable
                          onDragStart={() => setDraggedEvent(ev)}
                          onClick={() => setSelectedEvent(ev)}
                          className={cn(
                            "absolute left-1 right-1 rounded-md px-2 py-1 text-left text-xs overflow-hidden transition-opacity hover:opacity-80 cursor-grab active:cursor-grabbing",
                            hasConflict && "ring-1 ring-[var(--destructive)]"
                          )}
                          style={{
                            top: `${top}px`,
                            height: `${height}px`,
                            backgroundColor: `color-mix(in oklch, ${color} 15%, transparent)`,
                            borderLeft: `3px solid ${color}`,
                          }}
                        >
                          <div className="font-medium truncate text-[var(--foreground)]">
                            {ev.title}
                          </div>
                          {height > 35 && (
                            <div className="text-[var(--muted-foreground)] truncate">
                              {format(start, "h:mma").toLowerCase()}
                            </div>
                          )}
                          {hasConflict && height > 50 && (
                            <div className="flex items-center gap-1 text-[var(--destructive)] mt-0.5">
                              <AlertCircle size={10} />
                              <span className="text-[10px]">Conflict</span>
                            </div>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        {selectedEvent && (
          <EventDetailPanel
            event={selectedEvent}
            subAccount={selectedEvent.source_sub_account_id ? subAccountMap[selectedEvent.source_sub_account_id] : null}
            onClose={() => setSelectedEvent(null)}
          />
        )}
        {showNewEvent && (
          <NewEventModal
            defaultDate={currentDate}
            subAccounts={subAccounts}
            onClose={() => setShowNewEvent(false)}
            onCreated={() => {
              setShowNewEvent(false);
              onEventCreated?.();
            }}
          />
        )}
      </div>
    );
  }

  // Month view
  return (
    <div className="flex flex-col h-full">
      <CalendarHeader
        label={headerLabel}
        viewMode={viewMode}
        setViewMode={setViewMode}
        navigate={navigate}
        onNewEvent={() => setShowNewEvent(true)}
      />
      <div className="grid grid-cols-7 border-b border-[var(--border)]">
        {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
          <div key={d} className="py-2 text-center text-xs font-medium text-[var(--muted-foreground)] uppercase">
            {d}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 flex-1 overflow-auto">
        {days.map((day) => {
          const dayKey = format(day, "yyyy-MM-dd");
          const dayEvents = eventsByDay[dayKey] || [];
          const inMonth = isSameMonth(day, currentDate);
          return (
            <div
              key={dayKey}
              className={cn(
                "min-h-[100px] border-b border-r border-[var(--border)] p-1 last:border-r-0",
                !inMonth && "opacity-40 bg-[var(--muted)]/30"
              )}
            >
              <div className={cn("text-xs mb-1", isToday(day) && "font-bold text-[var(--primary)]")}>
                {format(day, "d")}
              </div>
              <div className="space-y-0.5">
                {dayEvents.slice(0, 4).map((ev) => {
                  const sa = ev.source_sub_account_id ? subAccountMap[ev.source_sub_account_id] : null;
                  const color = sa ? colorFromString(sa.id) : "var(--cal-other)";
                  return (
                    <button
                      key={ev.provider_event_id}
                      onClick={() => setSelectedEvent(ev)}
                      className="w-full text-left rounded px-1 py-0.5 text-xs truncate hover:opacity-80 transition-opacity"
                      style={{
                        backgroundColor: `color-mix(in oklch, ${color} 15%, transparent)`,
                        borderLeft: `2px solid ${color}`,
                      }}
                    >
                      {ev.title}
                    </button>
                  );
                })}
                {dayEvents.length > 4 && (
                  <div className="text-xs text-[var(--muted-foreground)] px-1">
                    +{dayEvents.length - 4} more
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      {selectedEvent && (
        <EventDetailPanel
          event={selectedEvent}
          subAccount={selectedEvent.source_sub_account_id ? subAccountMap[selectedEvent.source_sub_account_id] : null}
          onClose={() => setSelectedEvent(null)}
        />
      )}
      {showNewEvent && (
        <NewEventModal
          defaultDate={currentDate}
          subAccounts={subAccounts}
          onClose={() => setShowNewEvent(false)}
          onCreated={() => {
            setShowNewEvent(false);
            onEventCreated?.();
          }}
        />
      )}
    </div>
  );
}

function CalendarHeader({
  label,
  viewMode,
  setViewMode,
  navigate,
  onNewEvent,
}: {
  label: string;
  viewMode: ViewMode;
  setViewMode: (m: ViewMode) => void;
  navigate: (dir: "prev" | "next" | "today") => void;
  onNewEvent: () => void;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
      <div className="flex items-center gap-3">
        <CalendarIcon size={18} className="text-[var(--primary)]" />
        <h2 className="text-lg font-semibold">{label}</h2>
      </div>
      <div className="flex items-center gap-2">
        <div className="flex rounded-md border border-[var(--border)] overflow-hidden">
          <button
            onClick={() => setViewMode("day")}
            className={cn(
              "px-3 py-1.5 text-xs font-medium transition-colors",
              viewMode === "day" ? "bg-[var(--primary)] text-[var(--primary-foreground)]" : "hover:bg-[var(--accent)]"
            )}
          >
            Day
          </button>
          <button
            onClick={() => setViewMode("week")}
            className={cn(
              "px-3 py-1.5 text-xs font-medium transition-colors border-l border-[var(--border)]",
              viewMode === "week" ? "bg-[var(--primary)] text-[var(--primary-foreground)]" : "hover:bg-[var(--accent)]"
            )}
          >
            Week
          </button>
          <button
            onClick={() => setViewMode("month")}
            className={cn(
              "px-3 py-1.5 text-xs font-medium transition-colors border-l border-[var(--border)]",
              viewMode === "month" ? "bg-[var(--primary)] text-[var(--primary-foreground)]" : "hover:bg-[var(--accent)]"
            )}
          >
            Month
          </button>
        </div>
        <Button variant="outline" size="sm" onClick={() => navigate("today")}>
          Today
        </Button>
        <Button variant="ghost" size="icon" onClick={() => navigate("prev")}>
          <ChevronLeft size={16} />
        </Button>
        <Button variant="ghost" size="icon" onClick={() => navigate("next")}>
          <ChevronRight size={16} />
        </Button>
        <Button variant="default" size="sm" onClick={onNewEvent}>
          <Plus size={14} />
          New Event
        </Button>
      </div>
    </div>
  );
}

function EventDetailPanel({
  event,
  subAccount,
  onClose,
}: {
  event: UnifiedEvent;
  subAccount: SubAccount | null;
  onClose: () => void;
}) {
  const start = parseISO(event.start);
  const end = parseISO(event.end);
  const color = subAccount ? colorFromString(subAccount.id) : "var(--cal-other)";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="w-[420px] max-w-[90vw] rounded-xl bg-[var(--card)] shadow-2xl border border-[var(--border)] p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-4 h-4 rounded-full" style={{ backgroundColor: color }} />
            <h3 className="text-lg font-semibold">{event.title}</h3>
          </div>
          <button onClick={onClose} className="text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
            <ChevronRight size={18} className="rotate-90" />
          </button>
        </div>
        <div className="space-y-3 text-sm">
          <div>
            <span className="text-[var(--muted-foreground)]">Time: </span>
            <span>{format(start, "EEE, MMM d, h:mma")} – {format(end, "h:mma")}</span>
          </div>
          {event.location && (
            <div>
              <span className="text-[var(--muted-foreground)]">Location: </span>
              <span>{event.location}</span>
            </div>
          )}
          {event.description && (
            <div>
              <span className="text-[var(--muted-foreground)]">Description: </span>
              <span>{event.description}</span>
            </div>
          )}
          {subAccount && (
            <div>
              <span className="text-[var(--muted-foreground)]">Sub-account: </span>
              <Badge style={{ backgroundColor: `color-mix(in oklch, ${color} 15%, transparent)`, color }}>
                {subAccount.name}
              </Badge>
            </div>
          )}
            {Boolean(event.metadata?.conflict) && (
            <div className="flex items-center gap-2 text-[var(--destructive)]">
              <AlertCircle size={14} />
              <span>This event conflicts with another. Ask the conductor to resolve.</span>
            </div>
          )}
          {Array.isArray(event.metadata?.tags) && event.metadata.tags.length > 0 && (
            <div className="flex gap-1 flex-wrap">
              {(event.metadata.tags as string[]).map((tag) => (
                <Badge key={tag} className="bg-[var(--secondary)] text-[var(--secondary-foreground)]">
                  {tag}
                </Badge>
              ))}
            </div>
          )}
        </div>
        <div className="flex gap-2 mt-6">
          <Button variant="outline" size="sm" className="flex-1">Edit</Button>
          <Button variant="ghost" size="sm">Ask agent to reschedule</Button>
        </div>
      </div>
    </div>
  );
}

function NewEventModal({
  defaultDate,
  subAccounts,
  onClose,
  onCreated,
}: {
  defaultDate: Date;
  subAccounts: SubAccount[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(format(defaultDate, "yyyy-MM-dd"));
  const [startTime, setStartTime] = useState("09:00");
  const [duration, setDuration] = useState(30);
  const [subAccountId, setSubAccountId] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Title is required");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const startDt = new Date(`${date}T${startTime}`);
      const endDt = new Date(startDt.getTime() + duration * 60 * 1000);
      await api.createEvent({
        title: title.trim(),
        start: startDt.toISOString(),
        end: endDt.toISOString(),
        location: location.trim() || undefined,
        description: description.trim() || undefined,
        source_sub_account_id: subAccountId || undefined,
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create event");
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="w-[460px] max-w-[90vw] rounded-xl bg-[var(--card)] shadow-2xl border border-[var(--border)] p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <h3 className="text-lg font-semibold">New Event</h3>
          <button onClick={onClose} className="text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
            <ChevronRight size={18} className="rotate-90" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Meeting title"
              autoFocus
              className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Date</label>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Start time</label>
              <input
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Duration (minutes)</label>
            <div className="flex gap-2">
              {[15, 30, 45, 60, 90].map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDuration(d)}
                  className={cn(
                    "px-3 py-1.5 text-xs font-medium rounded-md border transition-colors",
                    duration === d
                      ? "bg-[var(--primary)] text-[var(--primary-foreground)] border-[var(--primary)]"
                      : "border-[var(--border)] hover:bg-[var(--accent)]"
                  )}
                >
                  {d}m
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Sub-account (optional)</label>
            <select
              value={subAccountId}
              onChange={(e) => setSubAccountId(e.target.value)}
              className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
            >
              <option value="">None (local)</option>
              {subAccounts.map((sa) => (
                <option key={sa.id} value={sa.id}>{sa.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Location (optional)</label>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Zoom, office, etc."
              className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Description (optional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Notes..."
              rows={2}
              className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--primary)] resize-none"
            />
          </div>
          {error && (
            <div className="flex items-center gap-2 text-sm text-[var(--destructive)]">
              <AlertCircle size={14} />
              <span>{error}</span>
            </div>
          )}
          <div className="flex gap-2 pt-2">
            <Button type="submit" disabled={submitting} className="flex-1">
              {submitting ? "Creating..." : "Create Event"}
            </Button>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
