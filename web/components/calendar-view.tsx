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
  Repeat,
  Users,
  Trash2,
  Edit3,
  Clock,
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
                      const eventColor = ev.color || (sa ? colorFromString(sa.id) : "var(--cal-other)");
                      const hasConflict = Boolean(ev.metadata?.conflict);
                      const isAllDay = ev.is_all_day;
                      if (isAllDay) return null;
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
                            backgroundColor: `color-mix(in oklch, ${eventColor} 15%, transparent)`,
                            borderLeft: `3px solid ${eventColor}`,
                          }}
                        >
                          <div className="font-medium truncate text-[var(--foreground)] flex items-center gap-1">
                            {ev.recurrence_rule && <Repeat size={10} className="shrink-0 opacity-60" />}
                            {ev.title}
                          </div>
                          {height > 35 && (
                            <div className="text-[var(--muted-foreground)] truncate">
                              {format(start, "h:mma").toLowerCase()}
                            </div>
                          )}
                          {ev.attendees && ev.attendees.length > 0 && height > 50 && (
                            <div className="flex items-center gap-1 text-[var(--muted-foreground)] mt-0.5">
                              <Users size={10} />
                              <span className="text-[10px]">{ev.attendees.length}</span>
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
            onEventUpdated={onEventUpdated}
            onEventDeleted={onEventUpdated}
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
                      const eventColor = ev.color || (sa ? colorFromString(sa.id) : "var(--cal-other)");
                      const hasConflict = Boolean(ev.metadata?.conflict);
                      if (ev.is_all_day) return null;
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
                            backgroundColor: `color-mix(in oklch, ${eventColor} 15%, transparent)`,
                            borderLeft: `3px solid ${eventColor}`,
                          }}
                        >
                          <div className="font-medium truncate text-[var(--foreground)] flex items-center gap-1">
                            {ev.recurrence_rule && <Repeat size={10} className="shrink-0 opacity-60" />}
                            {ev.title}
                          </div>
                          {height > 35 && (
                            <div className="text-[var(--muted-foreground)] truncate">
                              {format(start, "h:mma").toLowerCase()}
                            </div>
                          )}
                          {ev.attendees && ev.attendees.length > 0 && height > 50 && (
                            <div className="flex items-center gap-1 text-[var(--muted-foreground)] mt-0.5">
                              <Users size={10} />
                              <span className="text-[10px]">{ev.attendees.length}</span>
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
            onEventUpdated={onEventUpdated}
            onEventDeleted={onEventUpdated}
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
                  const eventColor = ev.color || (sa ? colorFromString(sa.id) : "var(--cal-other)");
                  return (
                    <button
                      key={ev.provider_event_id}
                      onClick={() => setSelectedEvent(ev)}
                      className="w-full text-left rounded px-1 py-0.5 text-xs truncate hover:opacity-80 transition-opacity flex items-center gap-1"
                      style={{
                        backgroundColor: `color-mix(in oklch, ${eventColor} 15%, transparent)`,
                        borderLeft: `2px solid ${eventColor}`,
                      }}
                    >
                      {ev.is_all_day && <span className="text-[10px] opacity-60">all day</span>}
                      {ev.recurrence_rule && <Repeat size={9} className="shrink-0 opacity-60" />}
                      <span className="truncate">{ev.title}</span>
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
          onEventUpdated={onEventUpdated}
          onEventDeleted={onEventUpdated}
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
  onEventUpdated,
  onEventDeleted,
}: {
  event: UnifiedEvent;
  subAccount: SubAccount | null;
  onClose: () => void;
  onEventUpdated?: () => void;
  onEventDeleted?: () => void;
}) {
  const start = parseISO(event.start);
  const end = parseISO(event.end);
  const eventColor = event.color || (subAccount ? colorFromString(subAccount.id) : "var(--cal-other)");
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [editTitle, setEditTitle] = useState(event.title);
  const [editLocation, setEditLocation] = useState(event.location || "");
  const [editDescription, setEditDescription] = useState(event.description || "");
  const [editColor, setEditColor] = useState(event.color || "");

  /** Save edits to the event. */
  const handleSaveEdit = async () => {
    setEditing(false);
    try {
      await api.updateEvent(event.provider_event_id, {
        title: editTitle,
        location: editLocation || null,
        description: editDescription || null,
        color: editColor || null,
      });
      onEventUpdated?.();
      onClose();
    } catch {
      // keep current state on error
    }
  };

  /** Delete the event after confirmation. */
  const handleDelete = async () => {
    setDeleting(false);
    try {
      await api.deleteEvent(event.provider_event_id);
      onEventDeleted?.();
      onClose();
    } catch {
      // keep current state on error
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="w-[420px] max-w-[90vw] rounded-xl bg-[var(--card)] shadow-2xl border border-[var(--border)] p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-4 h-4 rounded-full" style={{ backgroundColor: eventColor }} />
            <h3 className="text-lg font-semibold">{event.title}</h3>
          </div>
          <button onClick={onClose} className="text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
            <ChevronRight size={18} className="rotate-90" />
          </button>
        </div>
        {editing ? (
          <div className="space-y-3 text-sm">
            <div>
              <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Title</label>
              <input
                type="text"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Location</label>
              <input
                type="text"
                value={editLocation}
                onChange={(e) => setEditLocation(e.target.value)}
                className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Description</label>
              <textarea
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                rows={2}
                className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--primary)] resize-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Color</label>
              <div className="flex gap-2 items-center">
                <input
                  type="color"
                  value={editColor || "#6366f1"}
                  onChange={(e) => setEditColor(e.target.value)}
                  className="w-8 h-8 rounded border border-[var(--border)] cursor-pointer"
                />
                <button
                  type="button"
                  onClick={() => setEditColor("")}
                  className="text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                >
                  Clear
                </button>
              </div>
            </div>
            <div className="flex gap-2 pt-2">
              <Button size="sm" className="flex-1" onClick={handleSaveEdit}>Save</Button>
              <Button size="sm" variant="outline" onClick={() => setEditing(false)}>Cancel</Button>
            </div>
          </div>
        ) : deleting ? (
          <div className="space-y-3 text-sm">
            <div className="flex items-center gap-2 text-[var(--destructive)]">
              <AlertCircle size={16} />
              <span>Delete "{event.title}"? This cannot be undone.</span>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="destructive" className="flex-1" onClick={handleDelete}>Delete</Button>
              <Button size="sm" variant="outline" onClick={() => setDeleting(false)}>Cancel</Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3 text-sm">
            <div>
              <span className="text-[var(--muted-foreground)]">Time: </span>
              <span>{event.is_all_day ? "All day" : `${format(start, "EEE, MMM d, h:mma")} – ${format(end, "h:mma")}`}</span>
            </div>
            {event.recurrence_rule && (
              <div className="flex items-center gap-2">
                <Repeat size={14} className="text-[var(--muted-foreground)]" />
                <span className="text-[var(--muted-foreground)]">Recurring: </span>
                <span>{event.recurrence_rule}</span>
              </div>
            )}
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
            {event.attendees && event.attendees.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <Users size={14} className="text-[var(--muted-foreground)]" />
                  <span className="text-[var(--muted-foreground)]">Attendees ({event.attendees.length}):</span>
                </div>
                <div className="ml-5 space-y-0.5">
                  {event.attendees.map((a, i) => (
                    <div key={i} className="text-xs flex items-center gap-2">
                      <span>{a.name || a.email}</span>
                      {a.status && (
                        <Badge className={cn(
                          "text-[10px]",
                          a.status === "accepted" && "bg-[var(--cal-personal)]/15 text-[var(--cal-personal)]",
                          a.status === "tentative" && "bg-yellow-500/15 text-yellow-600",
                          a.status === "declined" && "bg-[var(--destructive)]/15 text-[var(--destructive)]",
                        )}>
                          {a.status}
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {subAccount && (
              <div>
                <span className="text-[var(--muted-foreground)]">Sub-account: </span>
                <Badge style={{ backgroundColor: `color-mix(in oklch, ${eventColor} 15%, transparent)`, color: eventColor }}>
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
        )}
        {!editing && !deleting && (
          <div className="flex gap-2 mt-6">
            <Button variant="outline" size="sm" className="flex-1" onClick={() => setEditing(true)}>
              <Edit3 size={14} /> Edit
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setDeleting(true)} className="text-[var(--destructive)]">
              <Trash2 size={14} /> Delete
            </Button>
          </div>
        )}
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
  const [isAllDay, setIsAllDay] = useState(false);
  const [color, setColor] = useState("");
  const [recurrence, setRecurrence] = useState("none");
  const [attendeesInput, setAttendeesInput] = useState("");
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
            {!isAllDay && (
              <div>
                <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Start time</label>
                <input
                  type="time"
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                  className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
                />
              </div>
            )}
            {isAllDay && <div />}
          </div>
          <div>
            <label className="flex items-center gap-2 text-xs font-medium text-[var(--muted-foreground)] mb-1 cursor-pointer">
              <input
                type="checkbox"
                checked={isAllDay}
                onChange={(e) => setIsAllDay(e.target.checked)}
                className="rounded border-[var(--border)]"
              />
              All-day event
            </label>
          </div>
          {!isAllDay && (
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
          )}
          <div>
            <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Recurrence</label>
            <select
              value={recurrence}
              onChange={(e) => setRecurrence(e.target.value)}
              className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
            >
              <option value="none">No recurrence</option>
              <option value="FREQ=DAILY;INTERVAL=1">Daily</option>
              <option value="FREQ=WEEKLY;INTERVAL=1">Weekly</option>
              <option value="FREQ=WEEKLY;INTERVAL=2">Bi-weekly</option>
              <option value="FREQ=MONTHLY;INTERVAL=1">Monthly</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Color (optional)</label>
            <div className="flex gap-2 items-center">
              <input
                type="color"
                value={color || "#6366f1"}
                onChange={(e) => setColor(e.target.value)}
                className="w-8 h-8 rounded border border-[var(--border)] cursor-pointer"
              />
              {color && (
                <button
                  type="button"
                  onClick={() => setColor("")}
                  className="text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                >
                  Clear
                </button>
              )}
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Attendees (comma-separated emails)</label>
            <input
              type="text"
              value={attendeesInput}
              onChange={(e) => setAttendeesInput(e.target.value)}
              placeholder="alice@example.com, bob@example.com"
              className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
            />
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
