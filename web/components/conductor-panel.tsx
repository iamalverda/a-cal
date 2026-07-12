"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Sparkles, Bot, User, Loader2, Zap, ChevronDown, ChevronRight, Brain, Activity } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { mockConductorResponse } from "@/lib/mock-data";
import type { ConductorResponse, RoutingTrace } from "@/types";

interface Message {
  id: string;
  role: "user" | "conductor";
  content: string;
  routing?: ConductorResponse["routing"];
  routingTrace?: RoutingTrace | null;
  casModules?: string[];
  actions?: ConductorResponse["actions"];
  timestamp: string;
}

const INTENT_COLORS: Record<string, string> = {
  sync: "var(--cal-work)",
  schedule: "var(--cal-personal)",
  email: "var(--cal-email)",
  negotiate: "var(--cal-other)",
  self_model: "var(--primary)",
  chat: "var(--muted-foreground)",
};

const CAS_LABELS: Record<string, string> = {
  cas_thalamus_gate: "Thalamus Gate",
  cas_hippocampus: "Hippocampus",
  cas_ras: "RAS",
  cas_autonomic: "Autonomic",
  cas_insula: "Insula",
  cas_cerebellum: "Cerebellum",
  cas_basal_ganglia: "Basal Ganglia",
  cas_claustrum: "Claustrum",
  cas_limbic: "Limbic",
  cas_vagal_tone: "Vagal Tone",
};

export function ConductorPanel() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "conductor",
      content: "Hi! I'm the A-Cal Conductor. I can sync your calendars, find open slots, triage your inbox, negotiate reschedules, and tell you what I know about your patterns. What do you need?",
      timestamp: new Date().toISOString(),
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const send = async () => {
    if (!input.trim()) return;
    const userMsg: Message = {
      id: `msg-${Date.now()}`,
      role: "user",
      content: input,
      timestamp: new Date().toISOString(),
    };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);

    let response: ConductorResponse;
    try {
      const res = await fetch("/api/a-cal/conductor/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg.content }),
      });
      if (!res.ok) throw new Error("API unavailable");
      response = await res.json();
    } catch {
      response = mockConductorResponse(userMsg.content);
    }

    const conductorMsg: Message = {
      id: `msg-${Date.now()}-r`,
      role: "conductor",
      content: response.response || `[Routed to ${response.routing.specialist}] Connect the Python backend for real agent responses.`,
      routing: response.routing,
      routingTrace: response.routing_trace,
      casModules: response.cas_modules_engaged,
      actions: response.actions,
      timestamp: response.timestamp,
    };
    setMessages((m) => [...m, conductorMsg]);
    setLoading(false);
  };

  const suggestions = [
    "Find a free 30-min slot tomorrow afternoon",
    "Sync all my providers",
    "Check inbox for calendar invites",
    "What patterns do you see in my schedule?",
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--border)]">
        <div className="w-8 h-8 rounded-full bg-[var(--primary)]/15 flex items-center justify-center">
          <Sparkles size={16} className="text-[var(--primary)]" />
        </div>
        <div>
          <div className="text-sm font-semibold">Conductor</div>
          <div className="text-xs text-[var(--muted-foreground)]">Agent orchestration</div>
        </div>
        <Button variant="ghost" size="sm" className="ml-auto text-xs" onClick={() => setMessages([messages[0]])}>
          <Zap size={12} />
          Clear
        </Button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn("flex gap-3", msg.role === "user" && "flex-row-reverse")}
          >
            <div
              className={cn(
                "w-7 h-7 rounded-full shrink-0 flex items-center justify-center",
                msg.role === "user"
                  ? "bg-[var(--secondary)]"
                  : "bg-[var(--primary)]/15"
              )}
            >
              {msg.role === "user" ? (
                <User size={14} className="text-[var(--secondary-foreground)]" />
              ) : (
                <Bot size={14} className="text-[var(--primary)]" />
              )}
            </div>
            <div className={cn("max-w-[80%]", msg.role === "user" && "text-right")}>
              <div
                className={cn(
                  "rounded-lg px-3 py-2 text-sm inline-block text-left whitespace-pre-line",
                  msg.role === "user"
                    ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                    : "bg-[var(--secondary)] text-[var(--secondary-foreground)]"
                )}
              >
                {msg.content}
              </div>

              {/* Routing metadata */}
              {msg.routing && (
                <RoutingBadges routing={msg.routing} casModules={msg.casModules} />
              )}

              {/* Nervous system trace (expandable) */}
              {msg.routingTrace && (
                <NervousSystemTrace trace={msg.routingTrace} />
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex gap-3">
            <div className="w-7 h-7 rounded-full bg-[var(--primary)]/15 flex items-center justify-center">
              <Bot size={14} className="text-[var(--primary)]" />
            </div>
            <div className="flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
              <Loader2 size={14} className="animate-spin" />
              <span>Routing through nervous system...</span>
            </div>
          </div>
        )}
      </div>

      {/* Suggestions */}
      {messages.length <= 2 && (
        <div className="px-4 pb-2 flex flex-wrap gap-1.5">
          {suggestions.map((s) => (
            <button
              key={s}
              onClick={() => setInput(s)}
              className="text-xs rounded-full px-3 py-1 bg-[var(--secondary)] text-[var(--secondary-foreground)] hover:opacity-80 transition-opacity"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="px-4 py-3 border-t border-[var(--border)] flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask the conductor anything..."
          disabled={loading}
        />
        <Button size="icon" onClick={send} disabled={loading || !input.trim()}>
          <Send size={16} />
        </Button>
      </div>
    </div>
  );
}

/** Routing badges shown under each conductor response. */
function RoutingBadges({
  routing,
  casModules,
}: {
  routing: NonNullable<Message["routing"]>;
  casModules?: string[];
}) {
  return (
    <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
      <Badge
        className="text-[10px]"
        style={{
          backgroundColor: `color-mix(in oklch, ${INTENT_COLORS[routing.intent] || "var(--muted-foreground)"} 15%, transparent)`,
          color: INTENT_COLORS[routing.intent] || "var(--muted-foreground)",
        }}
      >
        {routing.intent}
      </Badge>
      {routing.specialist && (
        <Badge className="text-[10px] bg-[var(--muted)] text-[var(--muted-foreground)]">
          {routing.specialist.replace("a_cal_", "").replace("_agent", "")}
        </Badge>
      )}
      {routing.force_local && (
        <Badge className="text-[10px] bg-[var(--destructive)]/15 text-[var(--destructive)]">
          local only
        </Badge>
      )}
      <Badge className="text-[10px] bg-[var(--muted)] text-[var(--muted-foreground)]">
        {routing.tier}
      </Badge>
      {casModules && casModules.length > 0 && (
        <Badge className="text-[10px] bg-[var(--primary)]/10 text-[var(--primary)] flex items-center gap-1">
          <Brain size={9} />
          {casModules.length} CAS
        </Badge>
      )}
    </div>
  );
}

/** Expandable nervous system trace for developer-mode visibility. */
function NervousSystemTrace({ trace }: { trace: RoutingTrace }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="mt-1.5">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-[10px] text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
      >
        {expanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
        <Activity size={10} />
        Nervous system trace ({trace.total_latency_ms}ms)
      </button>

      {expanded && (
        <div className="mt-1.5 rounded-md border border-[var(--border)] p-2.5 space-y-2 bg-[var(--card)]/50">
          {/* Signal path */}
          <div className="flex items-center gap-1 flex-wrap text-[10px]">
            <span className="text-[var(--muted-foreground)]">Path:</span>
            <span className="text-[var(--primary)]">Thalamus</span>
            <ChevronRight size={8} className="text-[var(--muted-foreground)]" />
            <span className="text-[var(--primary)]">RAS</span>
            <ChevronRight size={8} className="text-[var(--muted-foreground)]" />
            <span className="text-[var(--primary)]">Basal Ganglia</span>
            <ChevronRight size={8} className="text-[var(--muted-foreground)]" />
            <span className="text-[var(--primary)]">Conductor</span>
            <ChevronRight size={8} className="text-[var(--muted-foreground)]" />
            <span className="text-[var(--primary)]">Hippocampus</span>
          </div>

          {/* Thalamus gate evaluation */}
          <div className="flex items-center gap-2 text-[10px]">
            <span className="text-[var(--muted-foreground)]">Gate:</span>
            <Badge className="text-[9px] bg-[var(--muted)] text-[var(--muted-foreground)]">
              {trace.thalamus_gate.gate_state}
            </Badge>
            <span className="text-[var(--muted-foreground)]">
              urgency {trace.thalamus_gate.urgency}/10
            </span>
            <span className="text-[var(--muted-foreground)]">
              relevance {trace.thalamus_gate.relevance}/10
            </span>
          </div>

          {/* Activation state */}
          <div className="flex items-center gap-2 text-[10px]">
            <span className="text-[var(--muted-foreground)]">State:</span>
            <Badge className="text-[9px] bg-[var(--muted)] text-[var(--muted-foreground)]">
              {trace.activation_state}
            </Badge>
            <Badge className="text-[9px] bg-[var(--muted)] text-[var(--muted-foreground)]">
              {trace.autonomic_mode}
            </Badge>
          </div>

          {/* Conductor decision */}
          <div className="flex items-center gap-2 text-[10px]">
            <span className="text-[var(--muted-foreground)]">Decision:</span>
            <span className="text-[var(--foreground)]">
              {trace.conductor_decision.chosen_display_name}
            </span>
            <span className="text-[var(--muted-foreground)]">
              ({trace.conductor_decision.confidence}% confidence)
            </span>
          </div>

          {/* CAS modules engaged */}
          {trace.cas_modules_engaged.length > 0 && (
            <div className="flex items-center gap-1 flex-wrap text-[10px]">
              <span className="text-[var(--muted-foreground)]">CAS:</span>
              {trace.cas_modules_engaged.map((mod) => (
                <Badge
                  key={mod}
                  className="text-[9px] bg-[var(--primary)]/10 text-[var(--primary)] flex items-center gap-0.5"
                >
                  <Brain size={8} />
                  {CAS_LABELS[mod] || mod.replace("cas_", "")}
                </Badge>
              ))}
            </div>
          )}

          {/* Basal ganglia rankings */}
          {trace.basal_ganglia_ranking.length > 0 && (
            <div className="text-[10px] space-y-0.5">
              <span className="text-[var(--muted-foreground)]">Specialist ranking:</span>
              {trace.basal_ganglia_ranking.map((r, i) => (
                <div key={r.name} className="flex items-center gap-2 pl-3">
                  <span className="text-[var(--muted-foreground)] w-3">{i + 1}.</span>
                  <span className="text-[var(--foreground)]">{r.display_name}</span>
                  <div className="flex-1 max-w-[80px] h-1 rounded-full bg-[var(--muted)] overflow-hidden">
                    <div
                      className="h-full bg-[var(--primary)]"
                      style={{ width: `${r.confidence}%` }}
                    />
                  </div>
                  <span className="text-[var(--muted-foreground)]">{r.confidence}%</span>
                </div>
              ))}
            </div>
          )}

          {/* Hippocampus memory encoding */}
          {trace.hippocampus_encoding && (
            <div className="flex items-center gap-1 text-[10px]">
              <span className="text-[var(--muted-foreground)]">Memory encoded:</span>
              <span className="text-[var(--foreground)]">
                {String(trace.hippocampus_encoding.signal || "").slice(0, 40)}
                {String(trace.hippocampus_encoding.signal || "").length > 40 ? "..." : ""}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
