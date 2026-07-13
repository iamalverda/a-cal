"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Globe, Loader2, Copy, Check, Code2, ExternalLink, Save,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { GraphQLExplorer } from "@/components/graphql-explorer";
import type { CustomDomainConfig } from "@/types";

type Tab = "domain" | "embed" | "graphql";

/** PlatformPanel — custom domain, embed snippets, and GraphQL explorer (Phase 6). */
export function PlatformPanel() {
  const [tab, setTab] = useState<Tab>("domain");

  const tabs: { id: Tab; label: string; icon: typeof Globe }[] = [
    { id: "domain", label: "Custom Domain", icon: Globe },
    { id: "embed", label: "Embed", icon: Code2 },
    { id: "graphql", label: "GraphQL", icon: ExternalLink },
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
        {tab === "domain" && <DomainTab />}
        {tab === "embed" && <EmbedTab />}
        {tab === "graphql" && <GraphQLExplorer />}
      </div>
    </div>
  );
}

// --- Custom Domain Tab -----------------------------------------------------

function DomainTab() {
  const [config, setConfig] = useState<CustomDomainConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [domain, setDomain] = useState("");
  const [isActive, setIsActive] = useState(true);

  const load = useCallback(async () => {
    try {
      const c = await api.getCustomDomain();
      setConfig(c);
      setDomain(c.domain);
      setIsActive(c.is_active);
    } catch { setConfig(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function save() {
    setSaving(true);
    try {
      const c = await api.setCustomDomain({ domain, is_active: isActive, ssl_verified: false });
      setConfig(c);
    } catch (e) { console.error(e); }
    finally { setSaving(false); }
  }

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="animate-spin text-[var(--muted-foreground)]" /></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Globe size={18} className="text-[var(--primary)]" />
        <span className="font-medium text-sm">Custom Domain</span>
      </div>

      <p className="text-sm text-[var(--muted-foreground)]">
        Serve your booking pages from your own domain (e.g. book.yourcompany.com).
        Configure a CNAME record pointing to your A-Cal instance, then set the domain here.
      </p>

      <div className="rounded-lg border border-[var(--border)] p-4 space-y-3">
        <div>
          <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Domain</label>
          <Input
            placeholder="book.yourcompany.com"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
          />
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm">Active</span>
          <Switch checked={isActive} onCheckedChange={setIsActive} />
        </div>
        <Button size="sm" onClick={save} disabled={saving}>
          {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
          Save Domain
        </Button>
      </div>

      {config && config.domain && (
        <div className="rounded-lg border border-[var(--border)] p-4 space-y-2">
          <p className="text-sm font-medium">Current Configuration</p>
          <div className="flex items-center justify-between text-sm">
            <span className="text-[var(--muted-foreground)]">Domain</span>
            <span className="font-mono text-xs">{config.domain}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-[var(--muted-foreground)]">Status</span>
            <Badge className={cn("text-xs", config.is_active ? "bg-green-500/15 text-green-500" : "bg-[var(--secondary)]")}>
              {config.is_active ? "Active" : "Inactive"}
            </Badge>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-[var(--muted-foreground)]">SSL</span>
            <Badge className={cn("text-xs", config.ssl_verified ? "bg-green-500/15 text-green-500" : "bg-[var(--secondary)]")}>
              {config.ssl_verified ? "Verified" : "Pending"}
            </Badge>
          </div>
        </div>
      )}

      <div className="rounded-lg border border-[var(--border)] p-4">
        <p className="text-sm font-medium mb-2">DNS Setup</p>
        <div className="text-xs text-[var(--muted-foreground)] space-y-1 font-mono">
          <p>Type: CNAME</p>
          <p>Name: book (or your subdomain)</p>
          <p>Value: your-acal-instance.example.com</p>
        </div>
      </div>
    </div>
  );
}

// --- Embed Tab -------------------------------------------------------------

function EmbedTab() {
  const [slug, setSlug] = useState("");
  const [embedType, setEmbedType] = useState<"iframe" | "popup" | "text">("iframe");
  const [copied, setCopied] = useState(false);

  const origin = typeof window !== "undefined" ? window.location.origin : "https://your-acal.example.com";
  const bookingUrl = `${origin}/booking/${slug || "your-slug"}`;
  const embedUrl = `${origin}/embed/${slug || "your-slug"}`;

  const snippets: Record<typeof embedType, string> = {
    iframe: `<iframe\n  src="${embedUrl}"\n  width="100%"\n  height="600"\n  frameborder="0"\n  style="border-radius: 8px; border: 1px solid #e0e0e0;"\n></iframe>`,
    popup: `<script src="${origin}/embed.js" data-slug="${slug || "your-slug"}"></script>`,
    text: `<a href="${bookingUrl}">Book a meeting with me</a>`,
  };

  function copy() {
    navigator.clipboard.writeText(snippets[embedType]);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Code2 size={18} className="text-[var(--primary)]" />
        <span className="font-medium text-sm">Embed Widget</span>
      </div>

      <p className="text-sm text-[var(--muted-foreground)]">
        Embed your booking page on any website with an iframe, popup widget, or text link.
      </p>

      <div>
        <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Event Type Slug</label>
        <Input
          placeholder="your-slug"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
        />
      </div>

      <div className="flex gap-2">
        {(["iframe", "popup", "text"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setEmbedType(t)}
            className={cn(
              "px-3 py-1.5 text-sm rounded-md border transition-colors capitalize",
              embedType === t
                ? "border-[var(--primary)] text-[var(--primary)] bg-[var(--primary)]/10"
                : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            )}
          >
            {t === "text" ? "Text Link" : t}
          </button>
        ))}
      </div>

      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="text-xs font-medium text-[var(--muted-foreground)]">Embed Code</label>
          <button onClick={copy} className="text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
            {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
          </button>
        </div>
        <pre className="w-full rounded-md border border-[var(--border)] bg-[var(--secondary)]/30 p-3 font-mono text-xs overflow-auto">
          {snippets[embedType]}
        </pre>
      </div>

      {slug && (
        <div>
          <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Preview URL</label>
          <a
            href={bookingUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-[var(--primary)] hover:underline flex items-center gap-1"
          >
            {bookingUrl} <ExternalLink size={13} />
          </a>
        </div>
      )}
    </div>
  );
}
