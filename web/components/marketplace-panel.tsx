"use client";

/** Marketplace panel — browse, search, install, remix, share, and pull from remote registries.

Mode-tiered discovery (Q9): the visible surface adapts to the user's skill mode.
  - Simple: curated one-click templates/themes only (Browse tab, no code/config)
  - Pro: plugins, recipes, automation galleries with remix (Browse + Share + Remote)
  - Developer: full marketplace including raw SDK packages, agent spec source,
    provenance/config details (Browse + Share + Remote)
 */

import { useState, useEffect, useCallback } from "react";
import { marketplaceApi } from "@/lib/api";
import type { MarketplaceItem, SkillMode } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Download, Upload, Globe, Loader2, AlertCircle, CheckCircle2, ArrowDownToLine, GitFork, Sparkles, Flag, ShieldCheck, AlertTriangle } from "lucide-react";

const ITEM_TYPE_LABELS: Record<string, string> = {
  agent_spec: "Agent",
  sync_rule_pack: "Sync Rules",
  negotiation_strategy: "Strategy",
  ui_theme: "Theme",
  plugin_config: "Plugin",
};

type Tab = "browse" | "share" | "remote";

/** Item types surfaced in Simple mode — curated, no-code one-click installs. */
const SIMPLE_ITEM_TYPES: ReadonlySet<string> = new Set(["ui_theme", "plugin_config"]);

/** Tabs visible per skill mode. */
const TABS_BY_MODE: Record<SkillMode, Tab[]> = {
  simple: ["browse"],
  pro: ["browse", "share", "remote"],
  developer: ["browse", "share", "remote"],
};

/** Preview hint shown at the bottom of Browse — what the next tier unlocks. */
const TIER_PREVIEW: Partial<Record<SkillMode, string>> = {
  simple: "Pro mode unlocks plugins, recipes, sharing, and remote registries.",
  pro: "Developer mode unlocks raw SDK packages, agent spec source, and per-item config details.",
};

interface ManifestSummary {
  id: string;
  name: string;
  item_type: string;
  author: string;
  description: string;
  tags: string[];
}

interface RegistryManifest {
  format: string;
  version: string;
  name: string;
  description: string;
  registry_url: string;
  items: ManifestSummary[];
}

export function MarketplacePanel({ mode = "pro" }: { mode?: SkillMode }) {
  const [tab, setTab] = useState<Tab>("browse");
  const [items, setItems] = useState<MarketplaceItem[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());

  // Share tab state
  const [exporting, setExporting] = useState(false);
  const [importText, setImportText] = useState("");
  const [importing, setImporting] = useState(false);
  const [shareMsg, setShareMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  // Remote registry tab state
  const [registryUrl, setRegistryUrl] = useState("");
  const [browsing, setBrowsing] = useState(false);
  const [manifest, setManifest] = useState<RegistryManifest | null>(null);
  const [remoteMsg, setRemoteMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [pullingId, setPullingId] = useState<string | null>(null);

  // Remix form state
  const [remixingId, setRemixingId] = useState<string | null>(null);
  const [remixName, setRemixName] = useState("");
  const [remixDesc, setRemixDesc] = useState("");
  const [remixChanges, setRemixChanges] = useState("");
  const [remixConfig, setRemixConfig] = useState("");
  const [remixing, setRemixing] = useState(false);
  const [remixMsg, setRemixMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  // Trust & moderation state
  const [flaggingId, setFlaggingId] = useState<string | null>(null);
  const [flagReason, setFlagReason] = useState("");
  const [flagging, setFlagging] = useState(false);
  const [flagMsg, setFlagMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const visibleTabs = TABS_BY_MODE[mode];
  const isSimple = mode === "simple";
  const isDeveloper = mode === "developer";
  const displayedItems = isSimple
    ? items.filter((it) => SIMPLE_ITEM_TYPES.has(it.item_type))
    : items;

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const data = query
        ? await marketplaceApi.search(query)
        : await marketplaceApi.listItems();
      setItems(data);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    if (tab === "browse") loadItems();
  }, [loadItems, tab]);

  // Reset to a visible tab if the current tab isn't available in this mode.
  useEffect(() => {
    if (!visibleTabs.includes(tab)) setTab(visibleTabs[0] ?? "browse");
  }, [visibleTabs, tab]);

  const handleInstall = async (itemId: string) => {
    try {
      await marketplaceApi.install(itemId);
      setInstalledIds((prev) => new Set(prev).add(itemId));
    } catch (e) {
      console.error("install failed", e);
    }
  };

  const handleRemix = async (itemId: string) => {
    if (!remixName.trim()) return;
    setRemixing(true);
    setRemixMsg(null);
    let overrides: Record<string, unknown> = {};
    if (remixConfig.trim()) {
      try {
        overrides = JSON.parse(remixConfig.trim());
      } catch {
        setRemixMsg({ type: "err", text: "Config overrides must be valid JSON." });
        setRemixing(false);
        return;
      }
    }
    try {
      const child = await marketplaceApi.remix(itemId, {
        name: remixName.trim(),
        description: remixDesc.trim(),
        changes_summary: remixChanges.trim(),
        config_overrides: overrides,
      });
      setRemixMsg({ type: "ok", text: `Remixed as "${child.name}".` });
      setRemixingId(null);
      setRemixName(""); setRemixDesc(""); setRemixChanges(""); setRemixConfig("");
      loadItems();
    } catch (e) {
      setRemixMsg({ type: "err", text: `Remix failed: ${e}` });
    } finally {
      setRemixing(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    setShareMsg(null);
    try {
      const bundle = await marketplaceApi.exportBundle();
      const json = JSON.stringify(bundle, null, 2);
      const blob = new Blob([json], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `a-cal-marketplace-bundle-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setShareMsg({ type: "ok", text: "Bundle exported and downloaded." });
    } catch (e) {
      setShareMsg({ type: "err", text: `Export failed: ${e}` });
    } finally {
      setExporting(false);
    }
  };

  const handleImport = async () => {
    if (!importText.trim()) return;
    setImporting(true);
    setShareMsg(null);
    try {
      const result = await marketplaceApi.importBundle(importText.trim());
      setShareMsg({
        type: "ok",
        text: `Imported ${result.imported} item(s), skipped ${result.skipped} existing.`,
      });
      setImportText("");
    } catch (e) {
      setShareMsg({ type: "err", text: `Import failed: ${e}` });
    } finally {
      setImporting(false);
    }
  };

  const handleBrowseRemote = async () => {
    if (!registryUrl.trim()) return;
    setBrowsing(true);
    setRemoteMsg(null);
    setManifest(null);
    try {
      const data = await marketplaceApi.browseRemoteRegistry(registryUrl.trim());
      setManifest(data as unknown as RegistryManifest);
    } catch (e) {
      setRemoteMsg({ type: "err", text: `Failed to fetch registry: ${e}` });
    } finally {
      setBrowsing(false);
    }
  };

  const handlePull = async (itemId: string) => {
    if (!registryUrl.trim()) return;
    setPullingId(itemId);
    setRemoteMsg(null);
    try {
      const result = await marketplaceApi.pullFromRemoteRegistry(registryUrl.trim(), itemId);
      setRemoteMsg({
        type: "ok",
        text: result.published
          ? `Pulled and installed "${result.item.name}".`
          : `"${result.item.name}" already installed.`,
      });
      setInstalledIds((prev) => new Set(prev).add(result.item.id));
    } catch (e) {
      setRemoteMsg({ type: "err", text: `Pull failed: ${e}` });
    } finally {
      setPullingId(null);
    }
  };

  /** Flag a marketplace item for moderation. */
  const handleFlag = async (itemId: string) => {
    if (!flagReason.trim()) return;
    setFlagging(true);
    setFlagMsg(null);
    try {
      await marketplaceApi.flagItem(itemId, flagReason.trim());
      setFlagMsg({ type: "ok", text: "Item flagged for review." });
      setFlaggingId(null);
      setFlagReason("");
      loadItems();
    } catch (e) {
      setFlagMsg({ type: "err", text: `Flag failed: ${e}` });
    } finally {
      setFlagging(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* Tab switcher */}
      <div className="flex gap-1 border-b border-border">
        {visibleTabs.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t
                ? "border-[var(--primary)] text-[var(--primary)]"
                : "border-transparent text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            }`}
          >
            {t === "browse" ? "Browse" : t === "share" ? "Share" : "Remote"}
          </button>
        ))}
      </div>

      {/* Global flag/moderation message */}
      {flagMsg && (
        <div className={`flex items-center gap-2 text-xs ${flagMsg.type === "ok" ? "text-green-600" : "text-red-500"}`}>
          {flagMsg.type === "ok" ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
          {flagMsg.text}
        </div>
      )}

      {/* --- Browse tab --- */}
      {tab === "browse" && (
        <>
          <div className="flex items-center gap-2">
            <Input
              placeholder="Search marketplace..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="flex-1"
            />
            <Button variant="outline" onClick={loadItems}>
              Refresh
            </Button>
          </div>

          {loading && <p className="text-sm text-muted-foreground">Loading...</p>}

          {!loading && items.length === 0 && (
            <p className="text-sm text-muted-foreground">No items found.</p>
          )}

          <div className="grid gap-3">
            {displayedItems.map((item) => (
              <div
                key={item.id}
                className="rounded-lg border border-border p-4 flex flex-col gap-2"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-medium">{item.name}</h3>
                      <Badge variant="secondary">
                        {ITEM_TYPE_LABELS[item.item_type] ?? item.item_type}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">{item.description}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span className="text-xs text-muted-foreground">
                      {item.install_count} installs
                    </span>
                    {item.rating > 0 && (
                      <span className="text-xs text-muted-foreground">
                        {item.rating.toFixed(1)} / 5
                      </span>
                    )}
                    {/* Trust score badge */}
                    {item.verification_status === "verified" ? (
                      <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
                        <ShieldCheck size={12} />
                        Verified
                      </span>
                    ) : item.verification_status === "flagged" ? (
                      <span className="flex items-center gap-1 text-xs text-red-500 font-medium">
                        <AlertTriangle size={12} />
                        Flagged
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">
                        Trust: {item.trust_score?.toFixed(0) ?? "—"}
                      </span>
                    )}
                  </div>
                </div>

                {item.provenance.summary && (
                  <p className="text-xs text-muted-foreground italic">
                    {item.provenance.summary}
                  </p>
                )}

                <div className="flex items-center gap-2 flex-wrap">
                  {item.tags.map((tag) => (
                    <Badge key={tag} variant="outline" className="text-xs">
                      {tag}
                    </Badge>
                  ))}
                </div>

                {isDeveloper && (
                  <details className="text-xs text-muted-foreground">
                    <summary className="cursor-pointer select-none">Config &amp; provenance</summary>
                    <div className="mt-1 flex flex-col gap-0.5 pl-2 border-l border-border">
                      <span>type: <code className="font-mono">{item.item_type}</code></span>
                      <span>id: <code className="font-mono">{item.id}</code></span>
                      {item.provenance.summary && <span>{item.provenance.summary}</span>}
                    </div>
                  </details>
                )}

                <div className="flex items-center gap-2 pt-1 flex-wrap">
                  {installedIds.has(item.id) ? (
                    <Badge variant="secondary">Installed</Badge>
                  ) : (
                    <Button size="sm" onClick={() => handleInstall(item.id)}>
                      Install
                    </Button>
                  )}
                  {!isSimple && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        if (remixingId === item.id) {
                          setRemixingId(null);
                        } else {
                          setRemixingId(item.id);
                          setRemixName(`${item.name} (remix)`);
                          setRemixDesc("");
                          setRemixChanges("");
                          setRemixConfig("");
                          setRemixMsg(null);
                        }
                      }}
                    >
                      <GitFork size={14} />
                      Remix
                    </Button>
                  )}
                  <span className="text-xs text-muted-foreground">by {item.author}</span>
                  {item.remixed_from && !isSimple && (
                    <Badge variant="outline" className="text-xs">Remix</Badge>
                  )}
                  {!isSimple && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-xs text-muted-foreground px-2"
                      onClick={() => {
                        if (flaggingId === item.id) {
                          setFlaggingId(null);
                        } else {
                          setFlaggingId(item.id);
                          setFlagReason("");
                          setFlagMsg(null);
                        }
                      }}
                    >
                      <Flag size={12} />
                      Flag
                    </Button>
                  )}
                </div>

                {/* Flag form */}
                {flaggingId === item.id && !isSimple && (
                  <div className="mt-2 rounded-md border border-border p-3 flex flex-col gap-2 bg-[var(--muted)]/30">
                    <Input
                      placeholder="Reason for flagging (e.g. spam, malicious, broken)"
                      value={flagReason}
                      onChange={(e) => setFlagReason(e.target.value)}
                      className="text-sm"
                    />
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        onClick={() => handleFlag(item.id)}
                        disabled={flagging || !flagReason.trim()}
                      >
                        {flagging ? <Loader2 size={14} className="animate-spin" /> : <Flag size={14} />}
                        Submit Flag
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => { setFlaggingId(null); setFlagReason(""); setFlagMsg(null); }}
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}

                {remixingId === item.id && !isSimple && (
                  <div className="mt-2 rounded-md border border-border p-3 flex flex-col gap-2 bg-[var(--muted)]/30">
                    <Input
                      placeholder="Remix name"
                      value={remixName}
                      onChange={(e) => setRemixName(e.target.value)}
                      className="text-sm"
                    />
                    <Input
                      placeholder="Description (optional)"
                      value={remixDesc}
                      onChange={(e) => setRemixDesc(e.target.value)}
                      className="text-sm"
                    />
                    <Input
                      placeholder="What changed? (optional)"
                      value={remixChanges}
                      onChange={(e) => setRemixChanges(e.target.value)}
                      className="text-sm"
                    />
                    <textarea
                      placeholder='Config overrides JSON, e.g. {"key":"value"}'
                      value={remixConfig}
                      onChange={(e) => setRemixConfig(e.target.value)}
                      className="w-full min-h-[60px] rounded-md border border-border bg-transparent p-2 text-xs font-mono resize-y focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
                    />
                    {remixMsg && remixingId === item.id && (
                      <div className={`flex items-center gap-2 text-xs ${remixMsg.type === "ok" ? "text-green-600" : "text-red-500"}`}>
                        {remixMsg.type === "ok" ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                        {remixMsg.text}
                      </div>
                    )}
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        onClick={() => handleRemix(item.id)}
                        disabled={remixing || !remixName.trim()}
                      >
                        {remixing ? <Loader2 size={14} className="animate-spin" /> : <GitFork size={14} />}
                        Fork &amp; Publish
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setRemixingId(null)}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {TIER_PREVIEW[mode] && (
            <div className="mt-2 flex items-start gap-2 rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">
              <Sparkles size={14} className="text-[var(--primary)] shrink-0 mt-0.5" />
              <span>{TIER_PREVIEW[mode]}</span>
            </div>
          )}
        </>
      )}

      {/* --- Share tab --- */}
      {tab === "share" && (
        <div className="flex flex-col gap-4">
          <div className="rounded-lg border border-border p-4 flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Download size={16} className="text-[var(--primary)]" />
              <h3 className="text-sm font-medium">Export Bundle</h3>
            </div>
            <p className="text-xs text-muted-foreground">
              Export all local marketplace items as a portable JSON bundle. Share the file with others or back it up.
            </p>
            <Button onClick={handleExport} disabled={exporting} className="w-fit">
              {exporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
              Export All Items
            </Button>
          </div>

          <div className="rounded-lg border border-border p-4 flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Upload size={16} className="text-[var(--primary)]" />
              <h3 className="text-sm font-medium">Import Bundle</h3>
            </div>
            <p className="text-xs text-muted-foreground">
              Paste a bundle JSON below to import items from another A-Cal instance. Existing items are skipped.
            </p>
            <textarea
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              placeholder='{"format":"a-cal-bundle","version":1,...}'
              className="w-full min-h-[120px] rounded-md border border-border bg-transparent p-3 text-xs font-mono resize-y focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
            />
            <Button onClick={handleImport} disabled={importing || !importText.trim()} className="w-fit">
              {importing ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              Import
            </Button>
          </div>

          {shareMsg && (
            <div className={`flex items-center gap-2 text-xs ${shareMsg.type === "ok" ? "text-green-600" : "text-red-500"}`}>
              {shareMsg.type === "ok" ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
              {shareMsg.text}
            </div>
          )}
        </div>
      )}

      {/* --- Remote Registry tab --- */}
      {tab === "remote" && (
        <div className="flex flex-col gap-4">
          <div className="rounded-lg border border-border p-4 flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Globe size={16} className="text-[var(--primary)]" />
              <h3 className="text-sm font-medium">Browse Remote Registry</h3>
            </div>
            <p className="text-xs text-muted-foreground">
              Enter the URL of another A-Cal instance&apos;s registry to browse and pull items into your local marketplace.
            </p>
            <div className="flex items-center gap-2">
              <Input
                placeholder="https://other-a-cal.example.com"
                value={registryUrl}
                onChange={(e) => setRegistryUrl(e.target.value)}
                className="flex-1"
              />
              <Button onClick={handleBrowseRemote} disabled={browsing || !registryUrl.trim()}>
                {browsing ? <Loader2 size={14} className="animate-spin" /> : <Globe size={14} />}
                Browse
              </Button>
            </div>
          </div>

          {remoteMsg && (
            <div className={`flex items-center gap-2 text-xs ${remoteMsg.type === "ok" ? "text-green-600" : "text-red-500"}`}>
              {remoteMsg.type === "ok" ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
              {remoteMsg.text}
            </div>
          )}

          {manifest && (
            <div className="flex flex-col gap-2">
              {manifest.name && (
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-medium">{manifest.name}</h3>
                  <Badge variant="secondary">{manifest.items.length} items</Badge>
                </div>
              )}
              {manifest.description && (
                <p className="text-xs text-muted-foreground">{manifest.description}</p>
              )}
              <div className="grid gap-3 mt-2">
                {manifest.items.map((item) => (
                  <div
                    key={item.id}
                    className="rounded-lg border border-border p-4 flex flex-col gap-2"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-medium">{item.name}</h4>
                          <Badge variant="secondary">
                            {ITEM_TYPE_LABELS[item.item_type] ?? item.item_type}
                          </Badge>
                        </div>
                        {item.description && (
                          <p className="text-xs text-muted-foreground">{item.description}</p>
                        )}
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handlePull(item.id)}
                        disabled={pullingId === item.id}
                      >
                        {pullingId === item.id ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : (
                          <ArrowDownToLine size={14} />
                        )}
                        Pull
                      </Button>
                    </div>
                    {item.tags && item.tags.length > 0 && (
                      <div className="flex items-center gap-2 flex-wrap">
                        {item.tags.map((tag) => (
                          <Badge key={tag} variant="outline" className="text-xs">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    )}
                    <span className="text-xs text-muted-foreground">by {item.author}</span>
                  </div>
                ))}
                {manifest.items.length === 0 && (
                  <p className="text-sm text-muted-foreground">This registry has no items.</p>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
