"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Brain,
  Activity,
  Heart,
  Eye,
  Zap,
  Shield,
  Clock,
  MemoryStick,
  Filter,
  GitBranch,
  Layers,
  Send,
  ChevronRight,
  AlertTriangle,
  CheckCircle2,
  CircleDot,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type {
  SystemState,
  RoutingTrace,
  CASAgentSpec,
  NervousSystemOverview,
  ActivationState,
  GateState,
  AutonomicMode,
} from "@/types";

const LAYER_ICONS: Record<string, typeof Brain> = {
  brainstem: Activity,
  peripheral: Heart,
  subcortical: Filter,
  limbic: Layers,
  cortical: Eye,
  hindbrain: GitBranch,
};

const LAYER_COLORS: Record<string, string> = {
  brainstem: "#ef4444",
  peripheral: "#ec4899",
  subcortical: "#8b5cf6",
  limbic: "#f59e0b",
  cortical: "#3b82f6",
  hindbrain: "#10b981",
};

const ACTIVATION_LABELS: Record<string, string> = {
  awake: "Awake",
  light_sleep: "Light Sleep",
  deep_sleep: "Deep Sleep",
  wake_up_transition: "Waking Up",
};

const GATE_LABELS: Record<string, string> = {
  open: "OPEN",
  throttled: "THROTTLED",
  closed: "CLOSED",
  priority: "PRIORITY",
};

const GATE_COLORS: Record<string, string> = {
  open: "#10b981",
  throttled: "#f59e0b",
  closed: "#6b7280",
  priority: "#ef4444",
};

const AUTONOMIC_LABELS: Record<AutonomicMode, string> = {
  sympathetic: "Sympathetic (Active)",
  balanced: "Balanced",
  parasympathetic: "Parasympathetic (Rest)",
};

export function NervousSystemPanel() {
  const [overview, setOverview] = useState<NervousSystemOverview | null>(null);
  const [trace, setTrace] = useState<RoutingTrace | null>(null);
  const [signalInput, setSignalInput] = useState("");
  const [loading, setLoading] = useState(false);

  const loadOverview = useCallback(async () => {
    try {
      const data = await api.getNervousSystemOverview();
      setOverview(data);
    } catch {
      // Backend not running
    }
  }, []);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const handleRoute = async () => {
    if (!signalInput.trim()) return;
    setLoading(true);
    try {
      const result = await api.routeThroughNervousSystem(signalInput);
      setTrace(result);
      loadOverview(); // Refresh memory count
    } catch {
      // Backend not running
    }
    setLoading(false);
  };

  if (!overview) {
    return (
      <div className="p-6 space-y-4">
        <div className="flex items-center gap-2">
          <Brain size={20} className="text-[var(--primary)]" />
          <h3 className="font-semibold">Nervous System</h3>
        </div>
        <p className="text-sm text-[var(--muted-foreground)]">
          Connect to the backend to see the bio-mimetic agent architecture.
        </p>
      </div>
    );
  }

  const { state, cas_agents, memory_count, habit_count } = overview;

  // Group agents by nervous system layer
  const layerOrder = ["brainstem", "peripheral", "subcortical", "limbic", "cortical", "hindbrain"];
  const agentsByLayer: Record<string, CASAgentSpec[]> = {};
  for (const agent of cas_agents) {
    const layer = agent.cas?.nervous_system_layer || "cortical";
    if (!agentsByLayer[layer]) agentsByLayer[layer] = [];
    agentsByLayer[layer].push(agent);
  }

  return (
    <div className="p-4 space-y-5">
      {/* System State Dashboard */}
      <SystemStateDashboard state={state} memoryCount={memory_count} habitCount={habit_count} />

      {/* Signal Router */}
      <div className="rounded-lg border border-[var(--border)] p-4">
        <div className="flex items-center gap-2 mb-3">
          <Send size={16} className="text-[var(--primary)]" />
          <h4 className="font-medium text-sm">Signal Router</h4>
        </div>
        <p className="text-xs text-[var(--muted-foreground)] mb-3">
          Trace how a signal flows through the nervous system: thalamus gate → RAS → basal ganglia → conductor → CAS modules → hippocampus.
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            value={signalInput}
            onChange={(e) => setSignalInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleRoute()}
            placeholder="e.g. reschedule my 3pm meeting"
            className="flex-1 rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)]/40"
          />
          <Button size="sm" onClick={handleRoute} disabled={loading || !signalInput.trim()}>
            <Zap size={14} />
            Trace
          </Button>
        </div>
      </div>

      {/* Routing Trace */}
      {trace && <RoutingTraceView trace={trace} />}

      {/* Bio-mimetic Agent Architecture */}
      <div className="rounded-lg border border-[var(--border)] p-4">
        <div className="flex items-center gap-2 mb-3">
          <Brain size={16} className="text-[var(--primary)]" />
          <h4 className="font-medium text-sm">Bio-mimetic Architecture</h4>
          <Badge className="ml-auto bg-[var(--primary)]/15 text-[var(--primary)] text-xs">
            {cas_agents.length} modules
          </Badge>
        </div>
        <div className="space-y-3">
          {layerOrder.map((layer) => {
            const agents = agentsByLayer[layer];
            if (!agents || agents.length === 0) return null;
            const Icon = LAYER_ICONS[layer] || Brain;
            const color = LAYER_COLORS[layer] || "#6b7280";
            return (
              <div key={layer}>
                <div className="flex items-center gap-2 mb-2">
                  <Icon size={12} style={{ color }} />
                  <span className="text-xs font-medium uppercase text-[var(--muted-foreground)]">
                    {layer.replace(/_/g, " ")}
                  </span>
                  <div className="flex-1 h-px bg-[var(--border)]" />
                </div>
                <div className="space-y-1.5 pl-4">
                  {agents.map((agent) => (
                    <CASAgentCard key={agent.name} agent={agent} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Recent Memories */}
      {overview.recent_memories.length > 0 && (
        <div className="rounded-lg border border-[var(--border)] p-4">
          <div className="flex items-center gap-2 mb-3">
            <MemoryStick size={16} className="text-[var(--primary)]" />
            <h4 className="font-medium text-sm">Recent Memories</h4>
            <Badge className="ml-auto bg-[var(--secondary)] text-[var(--secondary-foreground)] text-xs">
              {memory_count} total
            </Badge>
          </div>
          <div className="space-y-2">
            {overview.recent_memories.map((mem, i) => (
              <div key={i} className="rounded-md border border-[var(--border)]/50 px-3 py-2 text-xs">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium">{String(mem.signal || "").slice(0, 50)}</span>
                  <div className="flex gap-1 ml-auto">
                    {Array.isArray(mem.tags) && mem.tags.map((tag: string) => (
                      <Badge key={tag} className="bg-[var(--secondary)] text-[var(--secondary-foreground)] text-[10px]">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="text-[var(--muted-foreground)]">
                  → {String(mem.specialist || "")} · {String(mem.outcome || "")}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SystemStateDashboard({
  state,
  memoryCount,
  habitCount,
}: {
  state: SystemState;
  memoryCount: number;
  habitCount: number;
}) {
  const activationColor =
    state.activation === "awake" ? "#10b981" :
    state.activation === "wake_up_transition" ? "#f59e0b" :
    "#6b7280";

  const autonomicColor =
    state.autonomic_mode === "sympathetic" ? "#ef4444" :
    state.autonomic_mode === "parasympathetic" ? "#10b981" :
    "#3b82f6";

  return (
    <div className="rounded-lg border border-[var(--border)] p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Activity size={16} className="text-[var(--primary)]" />
        <h4 className="font-medium text-sm">System State</h4>
      </div>

      {/* Activation + Autonomic */}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-md border border-[var(--border)]/50 p-3">
          <div className="flex items-center gap-2 mb-1">
            <CircleDot size={12} style={{ color: activationColor }} />
            <span className="text-xs text-[var(--muted-foreground)]">Activation</span>
          </div>
          <div className="text-sm font-medium" style={{ color: activationColor }}>
            {ACTIVATION_LABELS[state.activation]}
          </div>
        </div>
        <div className="rounded-md border border-[var(--border)]/50 p-3">
          <div className="flex items-center gap-2 mb-1">
            <Heart size={12} style={{ color: autonomicColor }} />
            <span className="text-xs text-[var(--muted-foreground)]">Autonomic</span>
          </div>
          <div className="text-sm font-medium" style={{ color: autonomicColor }}>
            {AUTONOMIC_LABELS[state.autonomic_mode]}
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-[var(--border)] overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{ width: `${state.sympathetic_score * 10}%`, backgroundColor: autonomicColor }}
            />
          </div>
        </div>
      </div>

      {/* Wellness indicators */}
      <div className="grid grid-cols-3 gap-2">
        <Metric label="Meeting Load" value={`${state.meeting_load_hours.toFixed(1)}h`} warning={state.overload_risk} />
        <Metric label="Break Quality" value={`${Math.round(state.break_adequacy * 100)}%`} warning={state.break_adequacy < 0.3} />
        <Metric label="Binding" value={`${Math.round(state.binding_quality * 100)}%`} warning={state.binding_quality < 0.8} />
      </div>

      {/* Risk flags */}
      {(state.overload_risk || state.burnout_risk) && (
        <div className="flex gap-2">
          {state.overload_risk && (
            <div className="flex items-center gap-1 text-xs text-[var(--destructive)]">
              <AlertTriangle size={12} />
              <span>Overload risk detected</span>
            </div>
          )}
          {state.burnout_risk && (
            <div className="flex items-center gap-1 text-xs text-[var(--destructive)]">
              <AlertTriangle size={12} />
              <span>Burnout risk — cooldown recommended</span>
            </div>
          )}
        </div>
      )}

      {/* Spotlight */}
      {state.spotlight_target && (
        <div className="flex items-center gap-2 text-xs">
          <Eye size={12} className="text-[var(--primary)]" />
          <span className="text-[var(--muted-foreground)]">Spotlight:</span>
          <span className="font-medium">{state.spotlight_target}</span>
          <Badge className="bg-[var(--primary)]/15 text-[var(--primary)] text-[10px]">
            P{state.spotlight_priority}
          </Badge>
        </div>
      )}

      {/* Memory + Habits */}
      <div className="flex items-center gap-4 text-xs text-[var(--muted-foreground)]">
        <div className="flex items-center gap-1">
          <MemoryStick size={12} />
          <span>{memoryCount} memories</span>
        </div>
        <div className="flex items-center gap-1">
          <Clock size={12} />
          <span>{habitCount} habits</span>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, warning }: { label: string; value: string; warning: boolean }) {
  return (
    <div className="rounded-md border border-[var(--border)]/50 p-2 text-center">
      <div className="text-xs text-[var(--muted-foreground)] mb-1">{label}</div>
      <div className={cn("text-sm font-semibold", warning && "text-[var(--destructive)]")}>
        {value}
      </div>
    </div>
  );
}

function CASAgentCard({ agent }: { agent: CASAgentSpec }) {
  const [expanded, setExpanded] = useState(false);
  const color = LAYER_COLORS[agent.cas?.nervous_system_layer || "cortical"] || "#6b7280";

  return (
    <div
      className="rounded-md border border-[var(--border)]/50 px-3 py-2 cursor-pointer transition-colors hover:bg-[var(--accent)]/30"
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} />
        <span className="text-sm font-medium flex-1">{agent.display_name}</span>
        {agent.privacy_force_local && (
          <Shield size={10} className="text-[var(--destructive)]" />
        )}
        <ChevronRight
          size={12}
          className={cn("text-[var(--muted-foreground)] transition-transform", expanded && "rotate-90")}
        />
      </div>
      {expanded && (
        <div className="mt-2 space-y-1.5 pl-4">
          <p className="text-xs text-[var(--muted-foreground)]">{agent.description}</p>
          <div className="flex flex-wrap gap-1">
            {agent.capabilities.map((cap) => (
              <Badge key={cap} className="bg-[var(--secondary)] text-[var(--secondary-foreground)] text-[10px]">
                {cap.replace(/_/g, " ")}
              </Badge>
            ))}
          </div>
          <div className="text-xs text-[var(--muted-foreground)]">
            <span>Brain region: </span>
            <span className="font-medium">{agent.cas?.brain_region}</span>
            <span> · Augments: </span>
            <span className="font-medium">{agent.cas?.augments.replace(/_/g, " ").replace("a cal ", "")}</span>
          </div>
          <div className="text-xs text-[var(--muted-foreground)]">
            <span>Tier: </span>
            <span className="font-medium">{agent.default_tier}</span>
            <span> · Tools: </span>
            <span className="font-medium">{agent.tools.length}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function RoutingTraceView({ trace }: { trace: RoutingTrace }) {
  const steps = [
    {
      icon: Filter,
      label: "Thalamus Gate",
      detail: `${GATE_LABELS[trace.thalamus_gate.gate_state]} · urgency ${trace.thalamus_gate.urgency}/10`,
      color: GATE_COLORS[trace.thalamus_gate.gate_state],
      reasoning: trace.thalamus_gate.reasoning,
    },
    {
      icon: Activity,
      label: "RAS",
      detail: ACTIVATION_LABELS[trace.activation_state],
      color: trace.activation_state === "awake" ? "#10b981" : "#6b7280",
    },
    {
      icon: GitBranch,
      label: "Basal Ganglia",
      detail: trace.basal_ganglia_ranking[0]?.display_name || "—",
      color: "#8b5cf6",
      ranking: trace.basal_ganglia_ranking,
    },
    {
      icon: Brain,
      label: "Conductor",
      detail: trace.conductor_decision.chosen_display_name,
      color: "#3b82f6",
      confidence: trace.conductor_decision.confidence,
    },
    {
      icon: Layers,
      label: "CAS Modules",
      detail: `${trace.cas_modules_engaged.length} engaged`,
      color: "#f59e0b",
      modules: trace.cas_modules_engaged,
    },
    {
      icon: MemoryStick,
      label: "Hippocampus",
      detail: trace.hippocampus_encoding ? "Encoded" : "Skipped",
      color: "#10b981",
    },
  ];

  return (
    <div className="rounded-lg border border-[var(--border)] p-4">
      <div className="flex items-center gap-2 mb-3">
        <GitBranch size={16} className="text-[var(--primary)]" />
        <h4 className="font-medium text-sm">Routing Trace</h4>
        <span className="ml-auto text-xs text-[var(--muted-foreground)]">
          {trace.total_latency_ms}ms
        </span>
      </div>

      {/* Signal */}
      <div className="rounded-md bg-[var(--primary)]/10 px-3 py-2 mb-3">
        <span className="text-xs text-[var(--muted-foreground)]">Signal: </span>
        <span className="text-sm font-medium">{trace.signal}</span>
      </div>

      {/* Flow steps */}
      <div className="space-y-2">
        {steps.map((step, i) => {
          const Icon = step.icon;
          return (
            <div key={i} className="flex items-start gap-3">
              <div className="flex flex-col items-center">
                <div
                  className="w-7 h-7 rounded-full flex items-center justify-center shrink-0"
                  style={{ backgroundColor: `${step.color}20` }}
                >
                  <Icon size={14} style={{ color: step.color }} />
                </div>
                {i < steps.length - 1 && (
                  <div className="w-px h-4 bg-[var(--border)]" />
                )}
              </div>
              <div className="flex-1 pb-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium">{step.label}</span>
                  <span className="text-xs text-[var(--muted-foreground)]">{step.detail}</span>
                  {step.confidence !== undefined && (
                    <Badge className="bg-[var(--secondary)] text-[var(--secondary-foreground)] text-[10px]">
                      {step.confidence}%
                    </Badge>
                  )}
                </div>
                {step.reasoning && (
                  <p className="text-xs text-[var(--muted-foreground)] mt-0.5">{step.reasoning}</p>
                )}
                {step.ranking && Array.isArray(step.ranking) && step.ranking.length > 1 && (
                  <div className="mt-1 space-y-0.5">
                    {step.ranking.slice(1, 3).map((r) => (
                      <div key={r.name} className="text-xs text-[var(--muted-foreground)] flex items-center gap-1">
                        <ChevronRight size={10} />
                        <span>{r.display_name}: {r.confidence}% — {r.reason}</span>
                      </div>
                    ))}
                  </div>
                )}
                {step.modules && Array.isArray(step.modules) && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {step.modules.map((m) => (
                      <Badge key={m} className="bg-[var(--secondary)] text-[var(--secondary-foreground)] text-[10px]">
                        {m.replace("cas_", "").replace(/_/g, " ")}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Binding check */}
      {trace.binding_check && (
        <div className="mt-3 flex items-center gap-2 text-xs">
          {trace.binding_check.verified ? (
            <CheckCircle2 size={14} className="text-[var(--primary)]" />
          ) : (
            <AlertTriangle size={14} className="text-[var(--destructive)]" />
          )}
          <span className="text-[var(--muted-foreground)]">
            Binding quality: {Math.round(trace.binding_check.binding_quality * 100)}%
          </span>
        </div>
      )}
    </div>
  );
}
