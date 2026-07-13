"use client";

/** Proactive suggestions — unprompted nudges from the self-model.

Displays self-model facts ranked by priority tier as dismissible
notification cards. Appears when the user has enabled proactive
suggestions in settings. Polls the backend periodically for new
suggestions.
 */

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { Lightbulb, X, Zap, Brain, TrendingUp } from "lucide-react";

interface Suggestion {
  fact_id: string;
  content: string;
  category: string;
  priority: number;
  confidence: number;
}

const PRIORITY_CONFIG: Record<number, { label: string; icon: typeof Zap; color: string }> = {
  3: { label: "High", icon: Brain, color: "var(--cal-work)" },
  2: { label: "Medium", icon: Zap, color: "var(--cal-personal)" },
  1: { label: "Pattern", icon: TrendingUp, color: "var(--muted-foreground)" },
};

const CATEGORY_LABELS: Record<string, string> = {
  busy_times: "Busy Times",
  meeting_patterns: "Meeting Patterns",
  meeting_prefs: "Meeting Preferences",
  energy_patterns: "Energy Patterns",
  relationships: "Relationships",
  response_cadence: "Response Cadence",
  goals: "Goals",
  work_focus: "Work Focus",
  communication_style: "Communication Style",
  scheduling_constraints: "Scheduling Constraints",
  attention_patterns: "Attention Patterns",
  identity: "Identity",
};

const POLL_INTERVAL = 30_000;

export function ProactiveSuggestions({ enabled }: { enabled: boolean }) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState(false);

  const loadSuggestions = useCallback(async () => {
    if (!enabled) {
      setSuggestions([]);
      return;
    }
    try {
      const data = await api.getProactiveSuggestions(5);
      setSuggestions(data);
    } catch {
      setSuggestions([]);
    }
  }, [enabled]);

  useEffect(() => {
    loadSuggestions();
    if (!enabled) return;
    const interval = setInterval(loadSuggestions, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [loadSuggestions, enabled]);

  const visible = suggestions.filter((s) => !dismissed.has(s.fact_id));
  if (visible.length === 0) return null;

  const dismiss = (id: string) => {
    setDismissed((prev) => new Set(prev).add(id));
  };

  const shown = expanded ? visible : visible.slice(0, 1);

  return (
    <div className="fixed bottom-4 right-4 z-40 flex flex-col gap-2 w-80 max-w-[90vw]">
      {shown.map((s) => {
        const config = PRIORITY_CONFIG[s.priority] ?? PRIORITY_CONFIG[1];
        const Icon = config.icon;
        const catLabel = CATEGORY_LABELS[s.category] ?? s.category;

        return (
          <div
            key={s.fact_id}
            className="rounded-lg border bg-[var(--card)] shadow-lg p-3 flex flex-col gap-2 animate-in slide-in-from-bottom-2 duration-200"
            style={{ borderLeftColor: config.color, borderLeftWidth: "3px" }}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <Icon size={14} style={{ color: config.color }} />
                <span className="text-xs font-medium" style={{ color: config.color }}>
                  {config.label}
                </span>
                <span className="text-xs text-[var(--muted-foreground)]">{catLabel}</span>
              </div>
              <button
                onClick={() => dismiss(s.fact_id)}
                className="text-[var(--muted-foreground)] hover:text-[var(--foreground)] shrink-0"
              >
                <X size={14} />
              </button>
            </div>

            <p className="text-xs text-[var(--foreground)] leading-relaxed">{s.content}</p>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1">
                <Lightbulb size={12} className="text-[var(--muted-foreground)]" />
                <span className="text-xs text-[var(--muted-foreground)]">
                  {Math.round(s.confidence * 100)}% confidence
                </span>
              </div>
              <button
                onClick={() => {
                  const event = new CustomEvent("a-cal:conductor-message", {
                    detail: `Based on my self-model, I know that: ${s.content}. Can you help me use this?`,
                  });
                  window.dispatchEvent(event);
                }}
                className="text-xs text-[var(--primary)] hover:underline"
              >
                Tell agent
              </button>
            </div>
          </div>
        );
      })}

      {visible.length > 1 && !expanded && (
        <button
          onClick={() => setExpanded(true)}
          className="text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] text-center py-1"
        >
          +{visible.length - 1} more suggestion{visible.length - 1 > 1 ? "s" : ""}
        </button>
      )}

      {expanded && visible.length > 1 && (
        <button
          onClick={() => setExpanded(false)}
          className="text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] text-center py-1"
        >
          Show less
        </button>
      )}
    </div>
  );
}
