"use client";

/** Contextual command bar — the default interaction model (Q6).

A cmd+k palette that lets users type commands or natural language anywhere
in the app. Quick actions are context-aware; free text routes to the
conductor agent. Keyboard-navigable with arrow keys, enter, and esc.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "@/lib/api";
import {
  Search,
  CalendarSync,
  Clock,
  Mail,
  Brain,
  Plus,
  Settings,
  Store,
  Zap,
  Loader2,
  Bot,
  X,
} from "lucide-react";

interface QuickAction {
  id: string;
  label: string;
  description: string;
  icon: typeof Search;
  keywords: string[];
  action: () => void;
}

interface CommandBarProps {
  open: boolean;
  onClose: () => void;
  onOpenSettings: () => void;
  onOpenMarketplace: () => void;
  onOpenEmail: () => void;
  onOpenAnalytics: () => void;
  onOpenConductor: () => void;
  onSyncCalendars: () => void;
  mode: string;
}

export function CommandBar({
  open,
  onClose,
  onOpenSettings,
  onOpenMarketplace,
  onOpenEmail,
  onOpenAnalytics,
  onOpenConductor,
  onSyncCalendars,
  mode,
}: CommandBarProps) {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [agentResponse, setAgentResponse] = useState<string | null>(null);
  const [isAgentMode, setIsAgentMode] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const quickActions: QuickAction[] = [
    {
      id: "sync",
      label: "Sync calendars",
      description: "Pull latest events from all connected providers",
      icon: CalendarSync,
      keywords: ["sync", "refresh", "pull", "update", "calendars"],
      action: () => {
        onSyncCalendars();
        onClose();
      },
    },
    {
      id: "find-slot",
      label: "Find open slot",
      description: "Search for free time in your calendar",
      icon: Clock,
      keywords: ["find", "slot", "free", "open", "available", "time", "schedule"],
      action: () => {
        setQuery("Find me an open 30-minute slot this week");
        setIsAgentMode(true);
      },
    },
    {
      id: "check-email",
      label: "Check email for schedule",
      description: "Scan inbox for meeting invites and schedule-related emails",
      icon: Mail,
      keywords: ["email", "inbox", "scan", "invites", "check"],
      action: () => {
        onOpenEmail();
        onClose();
      },
    },
    {
      id: "self-model",
      label: "What does the agent know about me?",
      description: "View the self-model's learned facts",
      icon: Brain,
      keywords: ["self", "model", "know", "about", "me", "facts", "learned", "memory"],
      action: () => {
        setQuery("What do you know about me?");
        setIsAgentMode(true);
      },
    },
    {
      id: "analytics",
      label: "Show calendar analytics",
      description: "View meeting stats, busy times, and patterns",
      icon: Zap,
      keywords: ["analytics", "stats", "patterns", "busy", "meetings", "insights"],
      action: () => {
        onOpenAnalytics();
        onClose();
      },
    },
    {
      id: "marketplace",
      label: "Open marketplace",
      description: "Browse community templates, plugins, and agents",
      icon: Store,
      keywords: ["marketplace", "browse", "community", "templates", "plugins", "share"],
      action: () => {
        onOpenMarketplace();
        onClose();
      },
    },
    {
      id: "settings",
      label: "Open settings",
      description: "Configure model routing, self-model, and preferences",
      icon: Settings,
      keywords: ["settings", "config", "preferences", "model", "routing", "privacy"],
      action: () => {
        onOpenSettings();
        onClose();
      },
    },
    {
      id: "conductor",
      label: "Open conductor chat",
      description: "Full conversation with the conductor agent",
      icon: Bot,
      keywords: ["conductor", "chat", "agent", "talk", "ask"],
      action: () => {
        onOpenConductor();
        onClose();
      },
    },
  ];

  // Filter quick actions by query
  const filteredActions = query && !isAgentMode
    ? quickActions.filter((a) => {
        const q = query.toLowerCase();
        return (
          a.label.toLowerCase().includes(q) ||
          a.description.toLowerCase().includes(q) ||
          a.keywords.some((k) => k.includes(q) || q.includes(k))
        );
      })
    : quickActions;

  // Focus input when opened + global Escape handler
  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      setAgentResponse(null);
      setIsAgentMode(false);
      setTimeout(() => inputRef.current?.focus(), 50);

      // Global Escape handler (in case input doesn't have focus)
      const escHandler = (e: KeyboardEvent) => {
        if (e.key === "Escape") {
          e.preventDefault();
          onClose();
        }
      };
      window.addEventListener("keydown", escHandler);
      return () => window.removeEventListener("keydown", escHandler);
    }
  }, [open, onClose]);

  // Reset to quick actions when query is cleared
  useEffect(() => {
    if (query === "" && isAgentMode) {
      setIsAgentMode(false);
      setAgentResponse(null);
    }
  }, [query, isAgentMode]);

  // Keep selected index in bounds
  useEffect(() => {
    if (selectedIndex >= filteredActions.length) {
      setSelectedIndex(0);
    }
  }, [filteredActions.length, selectedIndex]);

  const sendToAgent = useCallback(async (message: string) => {
    setLoading(true);
    setAgentResponse(null);
    try {
      const result = await api.sendToConductor(message);
      const response = result.response ?? "I'm not sure how to help with that.";
      setAgentResponse(response);
    } catch {
      setAgentResponse("I couldn't reach the backend. Is the server running?");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSubmit = useCallback(() => {
    if (!query.trim()) return;

    // If a quick action is selected and we're not in agent mode, run it
    if (!isAgentMode && filteredActions[selectedIndex]) {
      filteredActions[selectedIndex].action();
      return;
    }

    // Otherwise, send to the conductor agent
    setIsAgentMode(true);
    sendToAgent(query);
  }, [query, isAgentMode, filteredActions, selectedIndex, sendToAgent]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, filteredActions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  };

  // Scroll selected item into view
  useEffect(() => {
    const el = listRef.current?.children[selectedIndex] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center pt-[15vh] bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-[560px] max-w-[90vw] rounded-xl bg-[var(--card)] shadow-2xl border border-[var(--border)] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--border)]">
          <Search size={18} className="text-[var(--muted-foreground)] shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              if (isAgentMode) {
                setIsAgentMode(false);
                setAgentResponse(null);
              }
              setSelectedIndex(0);
            }}
            onKeyDown={handleKeyDown}
            placeholder={isAgentMode ? "Ask the conductor..." : "Type a command or ask anything..."}
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--muted-foreground)]"
          />
          {loading && <Loader2 size={16} className="animate-spin text-[var(--primary)]" />}
          <kbd className="text-xs text-[var(--muted-foreground)] border border-[var(--border)] rounded px-1.5 py-0.5 shrink-0">
            ESC
          </kbd>
        </div>

        {/* Agent response */}
        {isAgentMode && agentResponse && (
          <div className="px-4 py-3 border-b border-[var(--border)]">
            <div className="flex items-start gap-2">
              <Bot size={14} className="text-[var(--primary)] mt-0.5 shrink-0" />
              <p className="text-sm text-[var(--foreground)] leading-relaxed">{agentResponse}</p>
            </div>
            <button
              onClick={() => {
                onOpenConductor();
                onClose();
              }}
              className="mt-2 text-xs text-[var(--primary)] hover:underline"
            >
              Continue in conductor chat
            </button>
          </div>
        )}

        {/* Quick actions list */}
        {!isAgentMode && (
          <div ref={listRef} className="max-h-[320px] overflow-y-auto">
            {filteredActions.length === 0 && query && (
              <div className="px-4 py-3">
                <p className="text-sm text-[var(--muted-foreground)]">
                  No quick action matches. Press Enter to ask the conductor.
                </p>
              </div>
            )}
            {filteredActions.map((action, i) => {
              const Icon = action.icon;
              const isSelected = i === selectedIndex;
              return (
                <button
                  key={action.id}
                  onClick={action.action}
                  onMouseEnter={() => setSelectedIndex(i)}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                    isSelected ? "bg-[var(--accent)]" : "hover:bg-[var(--accent)]/50"
                  }`}
                >
                  <Icon size={16} className="text-[var(--muted-foreground)] shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{action.label}</div>
                    <div className="text-xs text-[var(--muted-foreground)] truncate">
                      {action.description}
                    </div>
                  </div>
                  {isSelected && (
                    <kbd className="text-xs text-[var(--muted-foreground)] border border-[var(--border)] rounded px-1.5 py-0.5 shrink-0">
                      ↵
                    </kbd>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-2 border-t border-[var(--border)] text-xs text-[var(--muted-foreground)]">
          <div className="flex items-center gap-3">
            <span><kbd className="border border-[var(--border)] rounded px-1">↑↓</kbd> navigate</span>
            <span><kbd className="border border-[var(--border)] rounded px-1">↵</kbd> select</span>
          </div>
          <span>Mode: {mode}</span>
        </div>
      </div>
    </div>
  );
}
