"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Filter,
  Plus,
  Trash2,
  Eye,
  EyeOff,
  RefreshCw,
  Bot,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { SubAccount, SyncRule, RuleType, RuleField } from "@/types";

interface SyncRulesEditorProps {
  subAccount: SubAccount;
  onRulesChanged?: () => void;
}

const RULE_TYPES: { value: RuleType; label: string; icon: typeof Eye; description: string }[] = [
  { value: "include", label: "Include", icon: Eye, description: "Show matching events on main calendar" },
  { value: "exclude", label: "Exclude", icon: EyeOff, description: "Hide matching events from main calendar" },
  { value: "transform", label: "Transform", icon: RefreshCw, description: "Modify matching events (rename, recolor, tag)" },
  { value: "agent", label: "Agent Review", icon: Bot, description: "Flag matching events for agent review" },
];

const RULE_FIELDS: { value: RuleField; label: string }[] = [
  { value: "title", label: "Event Title" },
  { value: "keyword", label: "Title + Description" },
  { value: "calendar_id", label: "Calendar ID" },
  { value: "category", label: "Category" },
  { value: "attendee", label: "Attendee Email" },
];

const RULE_TYPE_COLORS: Record<RuleType, string> = {
  include: "var(--cal-personal)",
  exclude: "var(--destructive)",
  transform: "var(--cal-email)",
  agent: "var(--primary)",
};

export function SyncRulesEditor({ subAccount, onRulesChanged }: SyncRulesEditorProps) {
  const [rules, setRules] = useState<SyncRule[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [loading, setLoading] = useState(false);

  // New rule form state
  const [ruleType, setRuleType] = useState<RuleType>("exclude");
  const [ruleField, setRuleField] = useState<RuleField>("title");
  const [pattern, setPattern] = useState("");
  const [transformRename, setTransformRename] = useState("");

  const loadRules = useCallback(async () => {
    try {
      const data = await api.listSyncRules(subAccount.id);
      setRules(data);
    } catch {
      setRules([]);
    }
  }, [subAccount.id]);

  useEffect(() => {
    if (expanded) {
      loadRules();
    }
  }, [expanded, loadRules]);

  const handleAddRule = async () => {
    if (!pattern.trim()) return;
    setLoading(true);
    const action: Record<string, unknown> = {};
    if (ruleType === "transform" && transformRename.trim()) {
      action.rename = transformRename.trim();
    }
    try {
      await api.createSyncRule({
        sub_account_id: subAccount.id,
        rule_type: ruleType,
        field: ruleField,
        pattern: pattern.trim(),
        action,
        priority: rules.length,
      });
      await loadRules();
      setShowAddForm(false);
      setPattern("");
      setTransformRename("");
      onRulesChanged?.();
    } catch {
      // Backend not running — add locally for UI feedback
      const localRule: SyncRule = {
        id: `local-${Date.now()}`,
        sub_account_id: subAccount.id,
        rule_type: ruleType,
        field: ruleField,
        pattern: pattern.trim(),
        action,
        priority: rules.length,
        is_active: true,
      };
      setRules((r) => [...r, localRule]);
      setShowAddForm(false);
      setPattern("");
      setTransformRename("");
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    setLoading(true);
    try {
      await api.deleteSyncRule(ruleId);
      await loadRules();
      onRulesChanged?.();
    } catch {
      setRules((r) => r.filter((rule) => rule.id !== ruleId));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-1">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 w-full px-2 py-1.5 text-xs rounded-md hover:bg-[var(--accent)]/50 transition-colors"
      >
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Filter size={12} className="text-[var(--muted-foreground)]" />
        <span className="font-medium flex-1 text-left">Sync Rules</span>
        {rules.length > 0 && (
          <Badge className="text-[10px] px-1.5 py-0" variant="outline">
            {rules.length}
          </Badge>
        )}
      </button>

      {expanded && (
        <div className="ml-3 border-l-2 border-[var(--border)] pl-3 space-y-1.5">
          {rules.length === 0 && !showAddForm && (
            <p className="text-xs text-[var(--muted-foreground)] px-2 py-1.5">
              No rules configured. All events from this sub-calendar will appear on the main calendar.
            </p>
          )}

          {rules.map((rule) => {
            const rt = RULE_TYPES.find((t) => t.value === rule.rule_type);
            const rf = RULE_FIELDS.find((f) => f.value === rule.field);
            const RuleIcon = rt?.icon || Filter;
            return (
              <div
                key={rule.id}
                className="flex items-start gap-2 px-2 py-1.5 rounded-md bg-[var(--accent)]/30 group"
              >
                <RuleIcon size={12} className="mt-0.5 shrink-0" style={{ color: RULE_TYPE_COLORS[rule.rule_type] }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium">{rt?.label || rule.rule_type}</span>
                    <span className="text-[10px] text-[var(--muted-foreground)]">{rf?.label || rule.field}</span>
                  </div>
                  <div className="text-xs text-[var(--muted-foreground)] truncate font-mono">
                    {rule.pattern}
                  </div>
                  {rule.rule_type === "transform"  && typeof rule.action.rename === "string" && (
                    <div className="text-[10px] text-[var(--muted-foreground)] mt-0.5">
                      Rename to: {String(rule.action.rename)}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => handleDeleteRule(rule.id)}
                  disabled={loading}
                  className="opacity-0 group-hover:opacity-100 text-[var(--destructive)] hover:bg-[var(--destructive)]/10 rounded p-0.5 transition-opacity"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            );
          })}

          {showAddForm ? (
            <div className="px-2 py-2 space-y-2 rounded-md border border-[var(--border)] bg-[var(--background)]">
              {/* Rule type selector */}
              <div>
                <label className="block text-[10px] font-medium text-[var(--muted-foreground)] mb-1">Rule Type</label>
                <div className="grid grid-cols-2 gap-1">
                  {RULE_TYPES.map((rt) => {
                    const Icon = rt.icon;
                    return (
                      <button
                        key={rt.value}
                        type="button"
                        onClick={() => setRuleType(rt.value)}
                        className={cn(
                          "flex items-center gap-1.5 px-2 py-1.5 text-xs rounded-md border transition-colors text-left",
                          ruleType === rt.value
                            ? "border-[var(--primary)] bg-[var(--primary)]/8"
                            : "border-[var(--border)] hover:bg-[var(--accent)]/50"
                        )}
                      >
                        <Icon size={12} style={{ color: RULE_TYPE_COLORS[rt.value] }} />
                        <span className="font-medium">{rt.label}</span>
                      </button>
                    );
                  })}
                </div>
                <p className="text-[10px] text-[var(--muted-foreground)] mt-1">
                  {RULE_TYPES.find((rt) => rt.value === ruleType)?.description}
                </p>
              </div>

              {/* Field selector */}
              <div>
                <label className="block text-[10px] font-medium text-[var(--muted-foreground)] mb-1">Match Field</label>
                <select
                  value={ruleField}
                  onChange={(e) => setRuleField(e.target.value as RuleField)}
                  className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
                >
                  {RULE_FIELDS.map((f) => (
                    <option key={f.value} value={f.value}>{f.label}</option>
                  ))}
                </select>
              </div>

              {/* Pattern input */}
              <div>
                <label className="block text-[10px] font-medium text-[var(--muted-foreground)] mb-1">
                  Pattern <span className="font-normal">(text, glob *, or regex)</span>
                </label>
                <input
                  type="text"
                  value={pattern}
                  onChange={(e) => setPattern(e.target.value)}
                  placeholder="e.g. *private* or dentist or ^work:"
                  className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-2 py-1.5 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
                  autoFocus
                />
              </div>

              {/* Transform-specific options */}
              {ruleType === "transform" && (
                <div>
                  <label className="block text-[10px] font-medium text-[var(--muted-foreground)] mb-1">
                    Rename to <span className="font-normal">(use {`{title}`} for original)</span>
                  </label>
                  <input
                    type="text"
                    value={transformRename}
                    onChange={(e) => setTransformRename(e.target.value)}
                    placeholder="e.g. Busy: {title}"
                    className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
                  />
                </div>
              )}

              {/* Action buttons */}
              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={handleAddRule}
                  disabled={loading || !pattern.trim()}
                  className="flex-1 px-3 py-1.5 text-xs font-medium rounded-md bg-[var(--primary)] text-[var(--primary-foreground)] disabled:opacity-50 transition-opacity"
                >
                  {loading ? "Adding..." : "Add Rule"}
                </button>
                <button
                  type="button"
                  onClick={() => { setShowAddForm(false); setPattern(""); setTransformRename(""); }}
                  className="px-3 py-1.5 text-xs font-medium rounded-md border border-[var(--border)] hover:bg-[var(--accent)]/50 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowAddForm(true)}
              className="flex items-center gap-1.5 w-full px-2 py-1.5 text-xs text-[var(--primary)] hover:bg-[var(--primary)]/8 rounded-md transition-colors"
            >
              <Plus size={12} />
              Add Rule
            </button>
          )}
        </div>
      )}
    </div>
  );
}
