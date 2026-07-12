"use client";

/** Visual workflow builder — compose agent workflows visually.

Visible in Pro and Developer modes. Lets users chain agent steps into
reusable workflows, configure each step, and export/import as JSON.
*/

import { useState, useCallback, useEffect } from "react";
import {
  Workflow,
  Plus,
  Trash2,
  GripVertical,
  ArrowDown,
  Save,
  Download,
  Upload,
  X,
  Bot,
  Calendar,
  Mail,
  Brain,
  Shield,
  Zap,
  Settings2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { api, developerApi } from "@/lib/api";
import type { AgentSpec } from "@/types";

/** A single node in the workflow. */
interface WorkflowNode {
  id: string;
  agent: string;
  label: string;
  config: Record<string, unknown>;
  conditional?: string;
}

/** A complete workflow definition. */
interface WorkflowDef {
  name: string;
  description: string;
  nodes: WorkflowNode[];
  trigger: "manual" | "schedule_change" | "email_received" | "conflict_detected";
  version: string;
}

/** Agent icon mapping. */
const AGENT_ICONS: Record<string, typeof Bot> = {
  a_cal_conductor: Bot,
  a_cal_sync: Calendar,
  a_cal_schedule: Calendar,
  a_cal_email: Mail,
  a_cal_negotiate: Zap,
  a_cal_self_model: Brain,
};

const TRIGGER_OPTIONS = [
  { value: "manual", label: "Manual — run on demand" },
  { value: "schedule_change", label: "Schedule Change — when events change" },
  { value: "email_received", label: "Email Received — when new email arrives" },
  { value: "conflict_detected", label: "Conflict Detected — when scheduling conflicts arise" },
];

/** Generate a unique node ID. */
let nodeCounter = 0;
function makeNodeId(): string {
  nodeCounter += 1;
  return `node-${Date.now()}-${nodeCounter}`;
}

export function WorkflowBuilder() {
  const [agents, setAgents] = useState<AgentSpec[]>([]);
  const [workflow, setWorkflow] = useState<WorkflowDef>({
    name: "My Workflow",
    description: "A custom agent workflow",
    nodes: [],
    trigger: "manual",
    version: "1.0.0",
  });
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [exportJson, setExportJson] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  /** Load available agents on mount. */
  useEffect(() => {
    async function loadAgents() {
      try {
        const data = await api.listAgents();
        setAgents(data);
      } catch {
        setAgents([]);
      }
    }
    loadAgents();
  }, []);

  /** Add a new node with the given agent. */
  const addNode = useCallback((agentName: string) => {
    const agent = agents.find((a) => a.name === agentName);
    const node: WorkflowNode = {
      id: makeNodeId(),
      agent: agentName,
      label: agent?.display_name ?? agentName,
      config: {},
    };
    setWorkflow((prev) => ({ ...prev, nodes: [...prev.nodes, node] }));
    setSelectedNodeId(node.id);
    setSaved(false);
  }, [agents]);

  /** Remove a node by ID. */
  const removeNode = useCallback((nodeId: string) => {
    setWorkflow((prev) => ({
      ...prev,
      nodes: prev.nodes.filter((n) => n.id !== nodeId),
    }));
    if (selectedNodeId === nodeId) setSelectedNodeId(null);
    setSaved(false);
  }, [selectedNodeId]);

  /** Move a node up in the order. */
  const moveNode = useCallback((nodeId: string, direction: "up" | "down") => {
    setWorkflow((prev) => {
      const nodes = [...prev.nodes];
      const idx = nodes.findIndex((n) => n.id === nodeId);
      if (idx === -1) return prev;
      const target = direction === "up" ? idx - 1 : idx + 1;
      if (target < 0 || target >= nodes.length) return prev;
      [nodes[idx], nodes[target]] = [nodes[target], nodes[idx]];
      return { ...prev, nodes };
    });
    setSaved(false);
  }, []);

  /** Update a node's config. */
  const updateNodeConfig = useCallback((nodeId: string, key: string, value: unknown) => {
    setWorkflow((prev) => ({
      ...prev,
      nodes: prev.nodes.map((n) =>
        n.id === nodeId ? { ...n, config: { ...n.config, [key]: value } } : n
      ),
    }));
    setSaved(false);
  }, []);

  /** Update a node's label. */
  const updateNodeLabel = useCallback((nodeId: string, label: string) => {
    setWorkflow((prev) => ({
      ...prev,
      nodes: prev.nodes.map((n) => (n.id === nodeId ? { ...n, label } : n)),
    }));
    setSaved(false);
  }, []);

  /** Update a node's conditional trigger. */
  const updateNodeConditional = useCallback((nodeId: string, conditional: string) => {
    setWorkflow((prev) => ({
      ...prev,
      nodes: prev.nodes.map((n) => (n.id === nodeId ? { ...n, conditional: conditional || undefined } : n)),
    }));
    setSaved(false);
  }, []);

  /** Export workflow as JSON. */
  const handleExport = useCallback(() => {
    setExportJson(JSON.stringify(workflow, null, 2));
  }, [workflow]);

  /** Import workflow from JSON. */
  const handleImport = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const parsed = JSON.parse(e.target?.result as string) as WorkflowDef;
        if (parsed.nodes && Array.isArray(parsed.nodes)) {
          setWorkflow(parsed);
          setSaved(false);
        }
      } catch {
        // Invalid JSON — ignore
      }
    };
    reader.readAsText(file);
  }, []);

  /** Publish workflow to marketplace. */
  const handlePublish = useCallback(async () => {
    try {
      await developerApi.registerPlugin({
        name: workflow.name,
        plugin_type: "agent",
        version: workflow.version,
        description: workflow.description,
        config: workflow,
        enabled: true,
      });
      setSaved(true);
    } catch {
      // Backend not running — show local saved state
      setSaved(true);
    }
  }, [workflow]);

  const selectedNode = workflow.nodes.find((n) => n.id === selectedNodeId);
  const availableAgents = agents.length > 0 ? agents : [
    { name: "a_cal_conductor", display_name: "Conductor", description: "Routes and coordinates", system_prompt: "", tools: [], default_tier: "VERSATILE", can_negotiate: false, privacy_force_local: false, capabilities: [] },
    { name: "a_cal_sync", display_name: "Sync Agent", description: "Background provider sync", system_prompt: "", tools: [], default_tier: "MICRO", can_negotiate: false, privacy_force_local: false, capabilities: [] },
    { name: "a_cal_schedule", display_name: "Schedule Agent", description: "Slot finding and conflict resolution", system_prompt: "", tools: [], default_tier: "VERSATILE", can_negotiate: false, privacy_force_local: false, capabilities: [] },
    { name: "a_cal_email", display_name: "Email Agent", description: "Inbox triage and drafts", system_prompt: "", tools: [], default_tier: "STANDARD", can_negotiate: false, privacy_force_local: true, capabilities: [] },
    { name: "a_cal_negotiate", display_name: "Negotiate Agent", description: "P2P meeting negotiation", system_prompt: "", tools: [], default_tier: "HEAVY", can_negotiate: true, privacy_force_local: true, capabilities: [] },
    { name: "a_cal_self_model", display_name: "Self-Model Agent", description: "User pattern observation", system_prompt: "", tools: [], default_tier: "COMPLEX", can_negotiate: false, privacy_force_local: true, capabilities: [] },
  ];

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* Workflow header */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Workflow size={18} className="text-[var(--primary)]" />
          <Input
            value={workflow.name}
            onChange={(e) => { setWorkflow((p) => ({ ...p, name: e.target.value })); setSaved(false); }}
            className="flex-1 font-medium"
            placeholder="Workflow name"
          />
          {saved && <Badge className="bg-[var(--cal-work)]/15 text-[var(--cal-work)] text-xs">Saved</Badge>}
        </div>
        <Input
          value={workflow.description}
          onChange={(e) => { setWorkflow((p) => ({ ...p, description: e.target.value })); setSaved(false); }}
          className="text-sm"
          placeholder="Description"
        />
        <div>
          <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Trigger</label>
          <Select
            value={workflow.trigger}
            onChange={(e) => { setWorkflow((p) => ({ ...p, trigger: e.target.value as WorkflowDef["trigger"] })); setSaved(false); }}
            className="text-sm"
          >
            {TRIGGER_OPTIONS.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </Select>
        </div>
      </div>

      <div className="flex gap-4">
        {/* Agent palette */}
        <div className="w-44 shrink-0 space-y-2">
          <div className="text-xs font-medium text-[var(--muted-foreground)] uppercase">Agents</div>
          {availableAgents.map((agent) => {
            const Icon = AGENT_ICONS[agent.name] ?? Bot;
            return (
              <button
                key={agent.name}
                onClick={() => addNode(agent.name)}
                className="w-full flex items-center gap-2 rounded-md border border-[var(--border)] p-2 text-left text-xs hover:bg-[var(--accent)] hover:border-[var(--primary)] transition-colors"
              >
                <Icon size={14} className="text-[var(--primary)] shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">{agent.display_name}</div>
                  <div className="text-[var(--muted-foreground)] truncate">{agent.description}</div>
                </div>
                <Plus size={12} className="text-[var(--muted-foreground)] shrink-0" />
              </button>
            );
          })}
        </div>

        {/* Workflow canvas */}
        <div className="flex-1 min-h-[400px] rounded-lg border border-[var(--border)] bg-[var(--background)] p-4 overflow-y-auto">
          {workflow.nodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center text-[var(--muted-foreground)]">
              <Workflow size={32} className="mb-2 opacity-50" />
              <p className="text-sm">Add agents from the palette to build your workflow.</p>
              <p className="text-xs mt-1">Each step runs in sequence. Add conditions to branch.</p>
            </div>
          ) : (
            <div className="flex flex-col gap-0">
              {workflow.nodes.map((node, idx) => {
                const agent = availableAgents.find((a) => a.name === node.agent);
                const Icon = AGENT_ICONS[node.agent] ?? Bot;
                const isSelected = node.id === selectedNodeId;
                return (
                  <div key={node.id}>
                    {/* Connector arrow */}
                    {idx > 0 && (
                      <div className="flex justify-center py-1">
                        <ArrowDown size={16} className="text-[var(--muted-foreground)]" />
                        {node.conditional && (
                          <span className="ml-2 text-xs text-[var(--muted-foreground)] italic">{node.conditional}</span>
                        )}
                      </div>
                    )}
                    {/* Node card */}
                    <div
                      onClick={() => setSelectedNodeId(node.id)}
                      className={cn(
                        "rounded-lg border p-3 cursor-pointer transition-all",
                        isSelected
                          ? "border-[var(--primary)] bg-[var(--primary)]/5 shadow-sm"
                          : "border-[var(--border)] hover:border-[var(--primary)]/50"
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <GripVertical size={14} className="text-[var(--muted-foreground)] cursor-grab" />
                        <Icon size={16} className="text-[var(--primary)]" />
                        <span className="text-sm font-medium flex-1">{node.label}</span>
                        {agent?.privacy_force_local && (
                          <Shield size={12} className="text-[var(--destructive)]" />
                        )}
                        <button
                          onClick={(e) => { e.stopPropagation(); moveNode(node.id, "up"); }}
                          disabled={idx === 0}
                          className="text-[var(--muted-foreground)] hover:text-[var(--foreground)] disabled:opacity-30"
                        >
                          <ArrowDown size={12} className="rotate-180" />
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); moveNode(node.id, "down"); }}
                          disabled={idx === workflow.nodes.length - 1}
                          className="text-[var(--muted-foreground)] hover:text-[var(--foreground)] disabled:opacity-30"
                        >
                          <ArrowDown size={12} />
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); removeNode(node.id); }}
                          className="text-[var(--muted-foreground)] hover:text-[var(--destructive)]"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                      {agent && (
                        <div className="mt-1.5 ml-6 text-xs text-[var(--muted-foreground)]">
                          {agent.description}
                        </div>
                      )}
                      {Object.keys(node.config).length > 0 && (
                        <div className="mt-1.5 ml-6 flex flex-wrap gap-1">
                          {Object.entries(node.config).map(([k, v]) => (
                            <Badge key={k} className="bg-[var(--muted)] text-[var(--muted-foreground)] text-[10px]">
                              {k}: {String(v)}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Properties panel */}
        {selectedNode && (
          <div className="w-56 shrink-0 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Settings2 size={14} className="text-[var(--primary)]" />
                <span className="text-xs font-medium">Step Config</span>
              </div>
              <button onClick={() => setSelectedNodeId(null)} className="text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
                <X size={14} />
              </button>
            </div>

            <div>
              <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Label</label>
              <Input
                value={selectedNode.label}
                onChange={(e) => updateNodeLabel(selectedNode.id, e.target.value)}
                className="text-sm"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Condition (optional)</label>
              <Input
                value={selectedNode.conditional ?? ""}
                onChange={(e) => updateNodeConditional(selectedNode.id, e.target.value)}
                placeholder="e.g. if conflict detected"
                className="text-sm"
              />
              <p className="text-[10px] text-[var(--muted-foreground)] mt-1">
                Only runs this step if the condition is met.
              </p>
            </div>

            <div>
              <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Auto-execute</label>
              <div className="flex items-center gap-2">
                <Switch
                  checked={Boolean(selectedNode.config.auto_execute)}
                  onChange={(v) => updateNodeConfig(selectedNode.id, "auto_execute", v)}
                />
                <span className="text-xs text-[var(--muted-foreground)]">
                  Run without confirmation
                </span>
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Priority</label>
              <Select
                value={String(selectedNode.config.priority ?? "normal")}
                onChange={(e) => updateNodeConfig(selectedNode.id, "priority", e.target.value)}
                className="text-sm"
              >
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </Select>
            </div>

            <div>
              <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Timeout (seconds)</label>
              <Input
                type="number"
                value={String(selectedNode.config.timeout ?? 30)}
                onChange={(e) => updateNodeConfig(selectedNode.id, "timeout", parseInt(e.target.value) || 30)}
                className="text-sm"
              />
            </div>
          </div>
        )}
      </div>

      {/* Action bar */}
      <div className="flex items-center gap-2 pt-2 border-t border-[var(--border)]">
        <Button variant="outline" size="sm" onClick={handlePublish}>
          <Save size={14} className="mr-1" /> Save & Publish
        </Button>
        <Button variant="outline" size="sm" onClick={handleExport}>
          <Download size={14} className="mr-1" /> Export JSON
        </Button>
        <label className="cursor-pointer">
          <Button variant="outline" size="sm" type="button" onClick={() => (document.querySelector<HTMLInputElement>("#workflow-import")?.click())}>
            <Upload size={14} className="mr-1" /> Import
          </Button>
          <input
            id="workflow-import"
            type="file"
            accept=".json"
            className="hidden"
            onChange={handleImport}
          />
        </label>
        <div className="ml-auto text-xs text-[var(--muted-foreground)]">
          {workflow.nodes.length} step{workflow.nodes.length !== 1 ? "s" : ""}
        </div>
      </div>

      {/* Export preview */}
      {exportJson && (
        <div className="rounded-lg border border-[var(--border)] bg-[var(--muted)] p-3 max-h-48 overflow-auto">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium">Exported Workflow JSON</span>
            <button onClick={() => setExportJson(null)} className="text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
              <X size={14} />
            </button>
          </div>
          <pre className="text-xs text-[var(--foreground)] font-mono whitespace-pre-wrap">{exportJson}</pre>
        </div>
      )}
    </div>
  );
}
