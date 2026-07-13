"use client";

import { useState, useEffect } from "react";
import {
  BarChart3,
  Clock,
  TrendingUp,
  Calendar,
  Zap,
  Loader2,
  RefreshCw,
  Plus,
  Trash2,
  Wrench,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type {
  AnalyticsSummary,
  BusyTimesAnalysis,
  MeetingStats,
  EventType,
  CalendarTool,
  FreeSlot,
  SchedulingType,
} from "@/types";

const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Simple horizontal bar chart for busy-by-day. */
function BusyByDayChart({ data }: { data: number[] }) {
  const max = Math.max(...data, 1);
  return (
    <div className="space-y-1.5">
      {data.map((hours, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="text-xs text-[var(--muted-foreground)] w-8">{DAY_NAMES[i]}</span>
          <div className="flex-1 h-5 rounded-sm bg-[var(--muted)]/30 overflow-hidden">
            <div
              className="h-full bg-[var(--primary)]/60 rounded-sm transition-all"
              style={{ width: `${(hours / max) * 100}%` }}
            />
          </div>
          <span className="text-xs text-[var(--muted-foreground)] w-12 text-right">{hours.toFixed(1)}h</span>
        </div>
      ))}
    </div>
  );
}

/** Hourly busy heatmap (simplified). */
function BusyByHourChart({ data }: { data: number[] }) {
  const max = Math.max(...data, 1);
  return (
    <div className="flex items-end gap-0.5 h-20">
      {data.map((count, hour) => (
        <div
          key={hour}
          className="flex-1 rounded-t-sm bg-[var(--primary)]/40 hover:bg-[var(--primary)]/70 transition-colors relative group"
          style={{ height: `${(count / max) * 100}%`, minHeight: count > 0 ? "4px" : "1px" }}
          title={`${hour}:00 — ${count} events`}
        />
      ))}
    </div>
  );
}

export function AnalyticsPanel() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);
  const [freeSlots, setFreeSlots] = useState<FreeSlot[]>([]);
  const [showFreeSlots, setShowFreeSlots] = useState(false);
  const [eventTypes, setEventTypes] = useState<EventType[]>([]);
  const [calendarTools, setCalendarTools] = useState<CalendarTool[]>([]);
  const [showEtForm, setShowEtForm] = useState(false);
  const [etForm, setEtForm] = useState({
    title: "New Event Type",
    slug: "new-event",
    duration_minutes: 30,
    scheduling_type: "collective" as SchedulingType,
    description: "",
    color: "#3B82F6",
  });
  const [activeTab, setActiveTab] = useState<"overview" | "freeslots" | "eventtypes" | "tools">("overview");

  /** Load analytics summary from backend. */
  const loadSummary = async () => {
    setLoading(true);
    try {
      const data = await api.getAnalyticsSummary(days);
      setSummary(data);
    } catch {
      setSummary(null);
    } finally {
      setLoading(false);
    }
  };

  /** Load free slots for the next 7 days. */
  const loadFreeSlots = async () => {
    const now = new Date();
    const future = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
    try {
      const data = await api.getFreeSlots(now.toISOString(), future.toISOString(), 30);
      setFreeSlots(data.free_slots);
    } catch {
      setFreeSlots([]);
    }
  };

  /** Load event types and calendar tools. */
  const loadExtras = async () => {
    try {
      const [ets, tools] = await Promise.all([
        api.listEventTypes().catch(() => []),
        api.getCalendarTools().catch(() => ({ tools: [], count: 0 })),
      ]);
      setEventTypes(ets);
      setCalendarTools(tools.tools);
    } catch {
      // Backend not running
    }
  };

  useEffect(() => {
    loadSummary();
    loadExtras();
  }, []);

  useEffect(() => {
    if (activeTab === "freeslots" && freeSlots.length === 0) {
      loadFreeSlots();
    }
  }, [activeTab]);

  const handleCreateEventType = async () => {
    try {
      const et = await api.createEventType({
        title: etForm.title,
        slug: etForm.slug || etForm.title.toLowerCase().replace(/\s+/g, "-"),
        duration_minutes: etForm.duration_minutes,
        scheduling_type: etForm.scheduling_type,
        description: etForm.description,
        color: etForm.color,
      } as Partial<EventType>);
      setEventTypes([...eventTypes, et]);
      setShowEtForm(false);
      setEtForm({
        title: "New Event Type",
        slug: "new-event",
        duration_minutes: 30,
        scheduling_type: "collective" as SchedulingType,
        description: "",
        color: "#3B82F6",
      });
    } catch {
      // Backend not running
    }
  };

  const handleDeleteEventType = async (id: string) => {
    try {
      await api.deleteEventType(id);
    } catch {
      // Backend not running
    }
    setEventTypes(eventTypes.filter((et) => et.id !== id));
  };

  const stats = summary?.meeting_stats;
  const busy = summary?.busy_times;

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-[var(--border)]">
        {([
          { id: "overview", label: "Overview", icon: BarChart3 },
          { id: "freeslots", label: "Free Slots", icon: Clock },
          { id: "eventtypes", label: "Event Types", icon: Calendar },
          { id: "tools", label: "AI Tools", icon: Wrench },
        ] as const).map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors",
                activeTab === tab.id
                  ? "bg-[var(--primary)]/10 text-[var(--primary)] font-medium"
                  : "text-[var(--muted-foreground)] hover:bg-[var(--accent)]"
              )}
            >
              <Icon size={14} />
              {tab.label}
            </button>
          );
        })}
        <Button variant="ghost" size="sm" onClick={loadSummary} className="ml-auto">
          <RefreshCw size={14} />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {activeTab === "overview" && (
          <>
            {/* Period selector */}
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">Period:</span>
              {[7, 30, 90].map((d) => (
                <button
                  key={d}
                  onClick={() => { setDays(d); }}
                  className={cn(
                    "px-3 py-1 rounded-md text-xs font-medium transition-colors",
                    days === d
                      ? "bg-[var(--primary)]/10 text-[var(--primary)]"
                      : "text-[var(--muted-foreground)] hover:bg-[var(--accent)]"
                  )}
                >
                  {d} days
                </button>
              ))}
            </div>

            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 size={24} className="animate-spin text-[var(--muted-foreground)]" />
              </div>
            ) : summary ? (
              <>
                {/* Meeting stats cards */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="rounded-lg border border-[var(--border)] p-3">
                    <div className="flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
                      <TrendingUp size={12} /> Total Hours
                    </div>
                    <div className="text-xl font-bold mt-1">{stats?.total_meeting_hours ?? 0}h</div>
                  </div>
                  <div className="rounded-lg border border-[var(--border)] p-3">
                    <div className="flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
                      <Calendar size={12} /> Meetings
                    </div>
                    <div className="text-xl font-bold mt-1">{stats?.meeting_count ?? 0}</div>
                  </div>
                  <div className="rounded-lg border border-[var(--border)] p-3">
                    <div className="flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
                      <Clock size={12} /> Avg Length
                    </div>
                    <div className="text-xl font-bold mt-1">{stats?.average_meeting_length ?? 0}m</div>
                  </div>
                </div>

                {/* Busy by day of week */}
                <div className="rounded-lg border border-[var(--border)] p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <BarChart3 size={14} className="text-[var(--primary)]" />
                    <span className="text-sm font-medium">Busy by Day of Week</span>
                  </div>
                  {busy && <BusyByDayChart data={busy.busy_by_day_of_week} />}
                  {busy && (
                    <div className="mt-3 text-xs text-[var(--muted-foreground)]">
                      Busiest day: <span className="text-[var(--foreground)] font-medium">{busy.busiest_day}</span>
                      {" "}({busy.busiest_day_hours}h)
                    </div>
                  )}
                </div>

                {/* Busy by hour */}
                <div className="rounded-lg border border-[var(--border)] p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Zap size={14} className="text-[var(--primary)]" />
                    <span className="text-sm font-medium">Busy by Hour</span>
                  </div>
                  {busy && <BusyByHourChart data={busy.busy_by_hour} />}
                  <div className="mt-2 flex justify-between text-[10px] text-[var(--muted-foreground)]">
                    <span>12 AM</span><span>6 AM</span><span>12 PM</span><span>6 PM</span><span>11 PM</span>
                  </div>
                  {busy && (
                    <div className="mt-2 text-xs text-[var(--muted-foreground)]">
                      Peak hour: <span className="text-[var(--foreground)] font-medium">{busy.busiest_hour}:00</span>
                      {" "}({busy.busiest_hour_count} events)
                    </div>
                  )}
                </div>

                {/* Category breakdown */}
                {stats && Object.keys(stats.category_counts).length > 0 && (
                  <div className="rounded-lg border border-[var(--border)] p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <Calendar size={14} className="text-[var(--primary)]" />
                      <span className="text-sm font-medium">Categories</span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(stats.category_counts).map(([cat, count]) => (
                        <Badge key={cat} className="bg-[var(--secondary)] text-[var(--secondary-foreground)]">
                          {cat}: {count}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="text-center py-12 text-sm text-[var(--muted-foreground)]">
                No analytics data. Connect a calendar to see insights.
              </div>
            )}
          </>
        )}

        {activeTab === "freeslots" && (
          <div className="space-y-2">
            <div className="text-sm font-medium mb-2">Free slots (next 7 days, 30+ min)</div>
            {freeSlots.length === 0 ? (
              <div className="text-center py-8 text-sm text-[var(--muted-foreground)]">
                No free slots found. Try adjusting your working hours.
              </div>
            ) : (
              freeSlots.map((slot, i) => {
                const start = new Date(slot.start);
                const end = new Date(slot.end);
                return (
                  <div key={i} className="flex items-center gap-3 rounded-lg border border-[var(--border)] p-3">
                    <div className="w-10 h-10 rounded-lg bg-[var(--cal-work)]/10 flex flex-col items-center justify-center">
                      <span className="text-[10px] text-[var(--muted-foreground)]">{start.toLocaleDateString("en-US", { weekday: "short" })}</span>
                      <span className="text-sm font-bold">{start.getDate()}</span>
                    </div>
                    <div className="flex-1">
                      <div className="text-sm font-medium">
                        {start.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}
                        {" — "}
                        {end.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}
                      </div>
                      <div className="text-xs text-[var(--muted-foreground)]">{slot.duration} minutes free</div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}

        {activeTab === "eventtypes" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Event Types (cal.com-style booking pages)</span>
              <Button variant="outline" size="sm" onClick={() => setShowEtForm(!showEtForm)}>
                <Plus size={14} className="mr-1" /> New
              </Button>
            </div>
            {showEtForm && (
              <div className="rounded-lg border border-[var(--border)] p-4 space-y-3 bg-[var(--muted)]/20">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs text-[var(--muted-foreground)]">Title</label>
                    <Input
                      value={etForm.title}
                      onChange={(e) => setEtForm({ ...etForm, title: e.target.value })}
                      placeholder="30 Minute Meeting"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-[var(--muted-foreground)]">Slug</label>
                    <Input
                      value={etForm.slug}
                      onChange={(e) => setEtForm({ ...etForm, slug: e.target.value })}
                      placeholder="30-min"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-[var(--muted-foreground)]">Duration (min)</label>
                    <Input
                      type="number"
                      min={5}
                      max={480}
                      value={etForm.duration_minutes}
                      onChange={(e) => setEtForm({ ...etForm, duration_minutes: parseInt(e.target.value) || 30 })}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-[var(--muted-foreground)]">Scheduling Type</label>
                    <Select
                      value={etForm.scheduling_type}
                      onChange={(e) => setEtForm({ ...etForm, scheduling_type: e.target.value as SchedulingType })}
                    >
                      <option value="collective">Collective (all attend)</option>
                      <option value="round_robin">Round Robin (one attends)</option>
                      <option value="managed">Managed (first participant)</option>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-[var(--muted-foreground)]">Color</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="color"
                        value={etForm.color}
                        onChange={(e) => setEtForm({ ...etForm, color: e.target.value })}
                        className="h-9 w-12 rounded-md border border-[var(--input)] cursor-pointer"
                      />
                      <Input
                        value={etForm.color}
                        onChange={(e) => setEtForm({ ...etForm, color: e.target.value })}
                        className="flex-1"
                      />
                    </div>
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-[var(--muted-foreground)]">Description</label>
                    <Input
                      value={etForm.description}
                      onChange={(e) => setEtForm({ ...etForm, description: e.target.value })}
                      placeholder="Optional description"
                    />
                  </div>
                </div>
                <div className="flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={() => setShowEtForm(false)}>Cancel</Button>
                  <Button size="sm" onClick={handleCreateEventType}>Create</Button>
                </div>
              </div>
            )}
            {eventTypes.length === 0 ? (
              <div className="text-center py-8 text-sm text-[var(--muted-foreground)]">
                No event types yet. Create one to enable booking pages.
              </div>
            ) : (
              eventTypes.map((et) => (
                <div key={et.id} className="flex items-center gap-3 rounded-lg border border-[var(--border)] p-3">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: et.color + "20" }}>
                    <Calendar size={16} style={{ color: et.color }} />
                  </div>
                  <div className="flex-1">
                    <div className="text-sm font-medium">{et.title}</div>
                    <div className="text-xs text-[var(--muted-foreground)]">
                      {et.duration_minutes} min &middot; {et.scheduling_type}
                    </div>
                  </div>
                  <button
                    onClick={() => handleDeleteEventType(et.id)}
                    className="text-[var(--muted-foreground)] hover:text-[var(--destructive)] transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))
            )}
          </div>
        )}

        {activeTab === "tools" && (
          <div className="space-y-2">
            <div className="text-sm font-medium mb-2">Calendar AI Tools (zero-calendar integration)</div>
            <div className="text-xs text-[var(--muted-foreground)] mb-3">
              These tools are available to the schedule agent for natural language calendar operations.
            </div>
            {calendarTools.map((tool) => (
              <div key={tool.name} className="rounded-lg border border-[var(--border)] p-3">
                <div className="flex items-center gap-2">
                  <code className="text-sm font-mono text-[var(--primary)]">{tool.name}</code>
                  <Wrench size={12} className="text-[var(--muted-foreground)]" />
                </div>
                <p className="text-xs text-[var(--muted-foreground)] mt-1">{tool.description}</p>
                {Object.keys(tool.parameters).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {Object.entries(tool.parameters).map(([param, schema]) => (
                      <Badge key={param} className="text-[10px] bg-[var(--muted)] text-[var(--muted-foreground)]">
                        {param}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
