"use client";

/** Marketplace panel — browse, search, install, and remix shared configs.

Visible in Pro and Developer modes. Shows the community marketplace with
provenance metadata for each item so users can audit what a config does
before installing it.
 */

import { useState, useEffect, useCallback } from "react";
import { marketplaceApi } from "@/lib/api";
import type { MarketplaceItem } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

const ITEM_TYPE_LABELS: Record<string, string> = {
  agent_spec: "Agent",
  sync_rule_pack: "Sync Rules",
  negotiation_strategy: "Strategy",
  ui_theme: "Theme",
  plugin_config: "Plugin",
};

export function MarketplacePanel() {
  const [items, setItems] = useState<MarketplaceItem[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());

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
    loadItems();
  }, [loadItems]);

  const handleInstall = async (itemId: string) => {
    try {
      await marketplaceApi.install(itemId);
      setInstalledIds((prev) => new Set(prev).add(itemId));
    } catch (e) {
      console.error("install failed", e);
    }
  };

  return (
    <div className="flex flex-col gap-4 p-4">
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
    </div>
  );
}
