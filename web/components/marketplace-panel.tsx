"use client";

/** Marketplace panel — browse, search, install, remix, share, and pull from remote registries.

Visible in Pro and Developer modes. Three tabs:
  - Browse: local marketplace with provenance metadata
  - Share: export items as a portable bundle, import bundles from others
  - Remote: browse a remote A-Cal registry and pull items locally
 */

import { useState, useEffect, useCallback } from "react";
import { marketplaceApi } from "@/lib/api";
import type { MarketplaceItem } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Download, Upload, Globe, Loader2, AlertCircle, CheckCircle2, ArrowDownToLine } from "lucide-react";

const ITEM_TYPE_LABELS: Record<string, string> = {
  agent_spec: "Agent",
  sync_rule_pack: "Sync Rules",
  negotiation_strategy: "Strategy",
  ui_theme: "Theme",
  plugin_config: "Plugin",
};

type Tab = "browse" | "share" | "remote";

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

export function MarketplacePanel() {
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

  const handleInstall = async (itemId: string) => {
    try {
      await marketplaceApi.install(itemId);
      setInstalledIds((prev) => new Set(prev).add(itemId));
    } catch (e) {
      console.error("install failed", e);
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

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* Tab switcher */}
      <div className="flex gap-1 border-b border-border">
        {(["browse", "share", "remote"] as Tab[]).map((t) => (
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
            {items.map((item) => (
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

                <div className="flex items-center gap-2 pt-1">
                  {installedIds.has(item.id) ? (
                    <Badge variant="secondary">Installed</Badge>
                  ) : (
                    <Button size="sm" onClick={() => handleInstall(item.id)}>
                      Install
                    </Button>
                  )}
                  <span className="text-xs text-muted-foreground">by {item.author}</span>
                  {item.remixed_from && (
                    <Badge variant="outline" className="text-xs">Remix</Badge>
                  )}
                </div>
              </div>
            ))}
          </div>
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
