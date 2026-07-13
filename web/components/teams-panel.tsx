"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Users, Plus, Trash2, Edit3, X, Loader2, Copy, Check,
  Webhook, CreditCard, GitBranch, Zap, Send, AlertTriangle,
  CheckCircle2, Mail, ChevronDown, ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type {
  Team, TeamMember, RoutingForm, WebhookConfig, WebhookDelivery,
  PaymentConfig, WorkflowTriggerConfig,
} from "@/types";

type Tab = "teams" | "routing" | "webhooks" | "payments" | "workflows";

/** TeamsPanel — manage teams, routing forms, webhooks, payments, and workflow triggers. */
export function TeamsPanel() {
  const [tab, setTab] = useState<Tab>("teams");

  const tabs: { id: Tab; label: string; icon: typeof Users }[] = [
    { id: "teams", label: "Teams", icon: Users },
    { id: "routing", label: "Routing Forms", icon: GitBranch },
    { id: "webhooks", label: "Webhooks", icon: Webhook },
    { id: "payments", label: "Payments", icon: CreditCard },
    { id: "workflows", label: "Triggers", icon: Zap },
  ];

  return (
    <div className="flex flex-col h-full">
      <div className="flex gap-1 px-4 pt-3 border-b border-[var(--border)]">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-t-lg transition-colors",
              tab === t.id
                ? "text-[var(--primary)] border-b-2 border-[var(--primary)]"
                : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            )}
          >
            <t.icon size={15} />
            {t.label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {tab === "teams" && <TeamsTab />}
        {tab === "routing" && <RoutingTab />}
        {tab === "webhooks" && <WebhooksTab />}
        {tab === "payments" && <PaymentsTab />}
        {tab === "workflows" && <WorkflowsTab />}
      </div>
    </div>
  );
}

// --- Teams Tab -------------------------------------------------------------

function TeamsTab() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [expandedTeam, setExpandedTeam] = useState<string | null>(null);
  const [newTeam, setNewTeam] = useState({ name: "", slug: "", description: "" });

  const load = useCallback(async () => {
    try {
      setTeams(await api.listTeams());
    } catch { setTeams([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleCreate() {
    if (!newTeam.name.trim()) return;
    try {
      await api.createTeam(newTeam);
      setNewTeam({ name: "", slug: "", description: "" });
      setShowCreate(false);
      load();
    } catch (e) { console.error(e); }
  }

  async function handleDelete(id: string) {
    try {
      await api.deleteTeam(id);
      load();
    } catch (e) { console.error(e); }
  }

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="animate-spin text-[var(--muted-foreground)]" /></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--muted-foreground)]">
          Create teams for round-robin or collective scheduling.
        </p>
        <Button size="sm" onClick={() => setShowCreate(!showCreate)}>
          <Plus size={15} /> New Team
        </Button>
      </div>

      {showCreate && (
        <div className="rounded-lg border border-[var(--border)] p-4 space-y-3 bg-[var(--secondary)]/30">
          <Input
            placeholder="Team name"
            value={newTeam.name}
            onChange={(e) => setNewTeam({ ...newTeam, name: e.target.value })}
          />
          <Input
            placeholder="URL slug (optional)"
            value={newTeam.slug}
            onChange={(e) => setNewTeam({ ...newTeam, slug: e.target.value })}
          />
          <Input
            placeholder="Description (optional)"
            value={newTeam.description}
            onChange={(e) => setNewTeam({ ...newTeam, description: e.target.value })}
          />
          <div className="flex gap-2">
            <Button size="sm" onClick={handleCreate}>Create</Button>
            <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
          </div>
        </div>
      )}

      {teams.length === 0 && !loading && (
        <p className="text-center text-sm text-[var(--muted-foreground)] py-8">
          No teams yet. Create one to enable team scheduling.
        </p>
      )}

      {teams.map((team) => (
        <div key={team.id} className="rounded-lg border border-[var(--border)]">
          <div className="flex items-center justify-between p-3">
            <button
              className="flex items-center gap-2 flex-1 text-left"
              onClick={() => setExpandedTeam(expandedTeam === team.id ? null : team.id)}
            >
              {expandedTeam === team.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              <Users size={16} className="text-[var(--primary)]" />
              <span className="font-medium text-sm">{team.name}</span>
              {team.slug && <Badge className="text-[10px] bg-[var(--secondary)]">/{team.slug}</Badge>}
              {team.members && (
                <Badge className="text-[10px] bg-[var(--primary)]/15 text-[var(--primary)]">
                  {team.members.length} members
                </Badge>
              )}
            </button>
            <button onClick={() => handleDelete(team.id)} className="text-[var(--muted-foreground)] hover:text-[var(--destructive)]">
              <Trash2 size={15} />
            </button>
          </div>
          {expandedTeam === team.id && (
            <TeamMembers team={team} onUpdate={load} />
          )}
        </div>
      ))}
    </div>
  );
}

function TeamMembers({ team, onUpdate }: { team: Team; onUpdate: () => void }) {
  const [members, setMembers] = useState<TeamMember[]>(team.members ?? []);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("member");

  async function addMember() {
    if (!email.trim()) return;
    try {
      const m = await api.addTeamMember(team.id, { email, display_name: name, role });
      setMembers([...members, m]);
      setEmail(""); setName(""); setRole("member");
      onUpdate();
    } catch (e) { console.error(e); }
  }

  async function removeMember(memberId: string) {
    try {
      await api.removeTeamMember(team.id, memberId);
      setMembers(members.filter((m) => m.id !== memberId));
    } catch (e) { console.error(e); }
  }

  async function toggleActive(member: TeamMember) {
    try {
      await api.updateTeamMember(team.id, member.id, { is_active: !member.is_active });
      setMembers(members.map((m) => m.id === member.id ? { ...m, is_active: !m.is_active } : m));
    } catch (e) { console.error(e); }
  }

  return (
    <div className="border-t border-[var(--border)] p-3 space-y-3">
      {members.map((m) => (
        <div key={m.id} className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            <Mail size={14} className="text-[var(--muted-foreground)]" />
            <span>{m.email}</span>
            {m.display_name && <span className="text-[var(--muted-foreground)]">({m.display_name})</span>}
            <Badge className={cn("text-[10px]", m.role === "admin" ? "bg-[var(--primary)]/15 text-[var(--primary)]" : "bg-[var(--secondary)]")}>
              {m.role}
            </Badge>
          </div>
          <div className="flex items-center gap-2">
            <Switch checked={m.is_active} onCheckedChange={() => toggleActive(m)} />
            <button onClick={() => removeMember(m.id)} className="text-[var(--muted-foreground)] hover:text-[var(--destructive)]">
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      ))}
      <div className="flex gap-2 pt-2 border-t border-[var(--border)]">
        <Input placeholder="email@example.com" value={email} onChange={(e) => setEmail(e.target.value)} className="flex-1" />
        <Input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} className="w-32" />
        <Select value={role} onChange={(e) => setRole(e.target.value)} className="w-28">
          <option value="member">Member</option>
          <option value="admin">Admin</option>
        </Select>
        <Button size="sm" onClick={addMember}><Plus size={15} /></Button>
      </div>
    </div>
  );
}

// --- Routing Forms Tab -----------------------------------------------------

function RoutingTab() {
  const [forms, setForms] = useState<RoutingForm[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newForm, setNewForm] = useState({ name: "", description: "" });

  const load = useCallback(async () => {
    try { setForms(await api.listRoutingForms()); }
    catch { setForms([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleCreate() {
    if (!newForm.name.trim()) return;
    try {
      await api.createRoutingForm(newForm);
      setNewForm({ name: "", description: "" });
      setShowCreate(false);
      load();
    } catch (e) { console.error(e); }
  }

  async function handleDelete(id: string) {
    try { await api.deleteRoutingForm(id); load(); }
    catch (e) { console.error(e); }
  }

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="animate-spin text-[var(--muted-foreground)]" /></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--muted-foreground)]">
          Route attendees to the right event type or team member based on their answers.
        </p>
        <Button size="sm" onClick={() => setShowCreate(!showCreate)}>
          <Plus size={15} /> New Form
        </Button>
      </div>

      {showCreate && (
        <div className="rounded-lg border border-[var(--border)] p-4 space-y-3 bg-[var(--secondary)]/30">
          <Input placeholder="Form name" value={newForm.name} onChange={(e) => setNewForm({ ...newForm, name: e.target.value })} />
          <Input placeholder="Description (optional)" value={newForm.description} onChange={(e) => setNewForm({ ...newForm, description: e.target.value })} />
          <div className="flex gap-2">
            <Button size="sm" onClick={handleCreate}>Create</Button>
            <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
          </div>
        </div>
      )}

      {forms.length === 0 && !loading && (
        <p className="text-center text-sm text-[var(--muted-foreground)] py-8">
          No routing forms yet.
        </p>
      )}

      {forms.map((form) => (
        <div key={form.id} className="rounded-lg border border-[var(--border)] p-3">
          <div className="flex items-center justify-between">
            <div>
              <span className="font-medium text-sm">{form.name}</span>
              {form.description && <p className="text-xs text-[var(--muted-foreground)] mt-0.5">{form.description}</p>}
            </div>
            <div className="flex items-center gap-2">
              <Badge className={cn("text-[10px]", form.is_active ? "bg-green-500/15 text-green-500" : "bg-[var(--secondary)]")}>
                {form.is_active ? "Active" : "Inactive"}
              </Badge>
              <Badge className="text-[10px] bg-[var(--secondary)]">{form.questions.length} questions</Badge>
              <button onClick={() => handleDelete(form.id)} className="text-[var(--muted-foreground)] hover:text-[var(--destructive)]">
                <Trash2 size={15} />
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// --- Webhooks Tab ----------------------------------------------------------

function WebhooksTab() {
  const [hooks, setHooks] = useState<WebhookConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newHook, setNewHook] = useState({ url: "", events: "*", is_active: true });
  const [testResult, setTestResult] = useState<string | null>(null);
  const [deliveries, setDeliveries] = useState<Record<string, WebhookDelivery[]>>({});

  const load = useCallback(async () => {
    try { setHooks(await api.listWebhooks()); }
    catch { setHooks([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleCreate() {
    if (!newHook.url.trim()) return;
    try {
      const events = newHook.events.split(",").map((e) => e.trim()).filter(Boolean);
      await api.createWebhook({ url: newHook.url, events, is_active: newHook.is_active });
      setNewHook({ url: "", events: "*", is_active: true });
      setShowCreate(false);
      load();
    } catch (e) { console.error(e); }
  }

  async function handleDelete(id: string) {
    try { await api.deleteWebhook(id); load(); }
    catch (e) { console.error(e); }
  }

  async function handleTest() {
    try {
      const result = await api.testWebhook("test.event");
      setTestResult(`Dispatched to ${result.dispatched} webhook(s)`);
    } catch (e) {
      setTestResult(`Error: ${(e as Error).message}`);
    }
  }

  async function loadDeliveries(hookId: string) {
    try {
      const dels = await api.listWebhookDeliveries(hookId);
      setDeliveries({ ...deliveries, [hookId]: dels });
    } catch (e) { console.error(e); }
  }

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="animate-spin text-[var(--muted-foreground)]" /></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--muted-foreground)]">
          Receive event notifications when bookings are created, cancelled, or rescheduled.
        </p>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={handleTest}>Test</Button>
          <Button size="sm" onClick={() => setShowCreate(!showCreate)}>
            <Plus size={15} /> New Webhook
          </Button>
        </div>
      </div>

      {testResult && (
        <div className="rounded-md border border-[var(--border)] p-2 text-sm bg-[var(--secondary)]/30">
          {testResult}
        </div>
      )}

      {showCreate && (
        <div className="rounded-lg border border-[var(--border)] p-4 space-y-3 bg-[var(--secondary)]/30">
          <Input placeholder="https://your-endpoint.com/webhook" value={newHook.url} onChange={(e) => setNewHook({ ...newHook, url: e.target.value })} />
          <Input placeholder="Events (comma-separated, or * for all)" value={newHook.events} onChange={(e) => setNewHook({ ...newHook, events: e.target.value })} />
          <div className="flex gap-2">
            <Button size="sm" onClick={handleCreate}>Create</Button>
            <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
          </div>
        </div>
      )}

      {hooks.length === 0 && !loading && (
        <p className="text-center text-sm text-[var(--muted-foreground)] py-8">
          No webhooks configured.
        </p>
      )}

      {hooks.map((hook) => (
        <div key={hook.id} className="rounded-lg border border-[var(--border)] p-3 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-mono truncate">{hook.url}</span>
                <Badge className={cn("text-[10px]", hook.is_active ? "bg-green-500/15 text-green-500" : "bg-[var(--secondary)]")}>
                  {hook.is_active ? "Active" : "Inactive"}
                </Badge>
              </div>
              <div className="flex gap-1 mt-1">
                {hook.events.map((ev) => (
                  <Badge key={ev} className="text-[10px] bg-[var(--primary)]/10 text-[var(--primary)]">{ev}</Badge>
                ))}
              </div>
              {hook.last_delivery_at && (
                <p className="text-[10px] text-[var(--muted-foreground)] mt-1">
                  Last: {new Date(hook.last_delivery_at).toLocaleString()} (HTTP {hook.last_status ?? "?"})
                </p>
              )}
            </div>
            <div className="flex gap-1">
              <Button size="sm" variant="ghost" onClick={() => loadDeliveries(hook.id)}>History</Button>
              <button onClick={() => handleDelete(hook.id)} className="text-[var(--muted-foreground)] hover:text-[var(--destructive)]">
                <Trash2 size={15} />
              </button>
            </div>
          </div>
          {deliveries[hook.id] && (
            <div className="border-t border-[var(--border)] pt-2 space-y-1">
              {deliveries[hook.id].length === 0 ? (
                <p className="text-xs text-[var(--muted-foreground)]">No deliveries yet.</p>
              ) : (
                deliveries[hook.id].map((d) => (
                  <div key={d.id} className="flex items-center gap-2 text-xs">
                    {d.status_code && d.status_code < 300 ? (
                      <CheckCircle2 size={12} className="text-green-500" />
                    ) : (
                      <AlertTriangle size={12} className="text-[var(--destructive)]" />
                    )}
                    <span>{d.event_type}</span>
                    <Badge className="text-[9px] bg-[var(--secondary)]">HTTP {d.status_code ?? "?"}</Badge>
                    <span className="text-[var(--muted-foreground)]">{d.delivered_at && new Date(d.delivered_at).toLocaleTimeString()}</span>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// --- Payments Tab ----------------------------------------------------------

function PaymentsTab() {
  const [config, setConfig] = useState<PaymentConfig | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getPaymentConfig()
      .then(setConfig)
      .catch(() => setConfig(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="animate-spin text-[var(--muted-foreground)]" /></div>;
  if (!config) return <p className="text-sm text-[var(--muted-foreground)]">Unable to load payment config.</p>;

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-[var(--border)] p-4">
        <div className="flex items-center gap-2 mb-3">
          <CreditCard size={18} className="text-[var(--primary)]" />
          <span className="font-medium text-sm">Stripe Integration</span>
        </div>
        <div className="space-y-2 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-[var(--muted-foreground)]">Status</span>
            {config.is_configured ? (
              <Badge className="bg-green-500/15 text-green-500 text-xs">Connected</Badge>
            ) : (
              <Badge className="bg-[var(--secondary)] text-xs">Mock Mode</Badge>
            )}
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[var(--muted-foreground)]">Publishable Key</span>
            <span className="font-mono text-xs">{config.publishable_key ? config.publishable_key.slice(0, 12) + "..." : "Not set"}</span>
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-[var(--border)] p-4 space-y-2">
        <p className="text-sm font-medium">How Paid Events Work</p>
        <ol className="text-sm text-[var(--muted-foreground)] space-y-1 list-decimal list-inside">
          <li>Set <code className="text-xs">is_paid</code> and <code className="text-xs">price_cents</code> on an event type</li>
          <li>When an attendee books, a Stripe PaymentIntent is created</li>
          <li>Booking status is <code className="text-xs">pending_payment</code> until payment confirms</li>
          <li>Webhook events fire on booking creation with payment metadata</li>
        </ol>
      </div>

      <div className="rounded-lg border border-[var(--border)] p-4">
        <p className="text-sm font-medium mb-2">Configuration</p>
        <p className="text-xs text-[var(--muted-foreground)]">
          Set <code className="text-xs">STRIPE_SECRET_KEY</code> and <code className="text-xs">STRIPE_PUBLISHABLE_KEY</code>
          environment variables to enable live Stripe payments. Without keys, the system
          operates in mock mode for development.
        </p>
      </div>
    </div>
  );
}

// --- Workflow Triggers Tab -------------------------------------------------

function WorkflowsTab() {
  const [config, setConfig] = useState<WorkflowTriggerConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getWorkflowTriggers()
      .then(setConfig)
      .catch(() => setConfig(null))
      .finally(() => setLoading(false));
  }, []);

  async function toggle(key: keyof WorkflowTriggerConfig, value: boolean) {
    if (!config) return;
    const updated = { ...config, [key]: value };
    setConfig(updated);
    setSaving(true);
    try { await api.setWorkflowTriggers(updated); }
    catch (e) { console.error(e); }
    finally { setSaving(false); }
  }

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="animate-spin text-[var(--muted-foreground)]" /></div>;
  if (!config) return <p className="text-sm text-[var(--muted-foreground)]">Unable to load trigger config.</p>;

  const triggers: { key: keyof WorkflowTriggerConfig; label: string; desc: string }[] = [
    { key: "booking_created", label: "Booking Created", desc: "Fire workflows when a new booking is made" },
    { key: "booking_cancelled", label: "Booking Cancelled", desc: "Fire workflows when a booking is cancelled" },
    { key: "booking_rescheduled", label: "Booking Rescheduled", desc: "Fire workflows when a booking is rescheduled" },
  ];

  return (
    <div className="space-y-4">
      <p className="text-sm text-[var(--muted-foreground)]">
        Configure which booking lifecycle events trigger workflow automations.
        Workflows are managed in the Workflow Builder.
      </p>
      {saving && <p className="text-xs text-[var(--primary)]">Saving...</p>}
      {triggers.map((t) => (
        <div key={t.key} className="flex items-center justify-between rounded-lg border border-[var(--border)] p-3">
          <div>
            <div className="text-sm font-medium">{t.label}</div>
            <div className="text-xs text-[var(--muted-foreground)]">{t.desc}</div>
          </div>
          <Switch checked={config[t.key]} onCheckedChange={(v) => toggle(t.key, v)} />
        </div>
      ))}
    </div>
  );
}
