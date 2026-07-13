"use client";

/** Community profile / showcase panel (charter §9).

Shows the user's authored marketplace items, remixes, installs, and stats
in a shareable showcase view. This is the "profiles, showcases" piece of
the community hub — a local, self-hostable version that aggregates the
user's contributions to the marketplace.
 */

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import type { CommunityProfile, MarketplaceItem } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Download, Star, GitFork, Package, TrendingUp } from "lucide-react";

const ITEM_TYPE_LABELS: Record<string, string> = {
  agent_spec: "Agent",
  sync_rule_pack: "Sync Rules",
  negotiation_strategy: "Strategy",
  ui_theme: "Theme",
  plugin_config: "Plugin",
};

export function CommunityProfilePanel() {
  const [profile, setProfile] = useState<CommunityProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getCommunityProfile()
      .then(setProfile)
      .catch(() => setProfile(null))
      .finally(() => setLoading(false));
  }, []);

  const handleExportShowcase = () => {
    if (!profile) return;
    const json = JSON.stringify(profile, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `a-cal-showcase-${profile.user_id}-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return <p className="text-sm text-muted-foreground p-4">Loading profile...</p>;
  }

  if (!profile) {
    return <p className="text-sm text-muted-foreground p-4">Unable to load profile.</p>;
  }

  const { stats } = profile;

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-3">
        <StatCard icon={<Package size={16} />} label="Authored" value={stats.total_authored} />
        <StatCard icon={<GitFork size={16} />} label="Remixes" value={stats.total_remixes} />
        <StatCard icon={<Download size={16} />} label="Installs" value={stats.total_installs_of_authored} />
        <StatCard icon={<TrendingUp size={16} />} label="Remixed by others" value={stats.total_remixes_of_authored} />
      </div>

      {stats.avg_rating > 0 && (
        <div className="flex items-center gap-2 text-sm">
          <Star size={14} className="text-yellow-500" />
          <span className="font-medium">{stats.avg_rating.toFixed(1)}</span>
          <span className="text-muted-foreground">avg rating across authored items</span>
        </div>
      )}

      {/* Export showcase */}
      <Button variant="outline" onClick={handleExportShowcase} className="w-fit">
        <Download size={14} />
        Export Showcase
      </Button>

      {/* Authored items */}
      {profile.authored.length > 0 ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Your Marketplace Items</h3>
          {profile.authored.map((item) => (
            <ProfileItemRow key={item.id} item={item} />
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          You haven&apos;t published any marketplace items yet. Use the marketplace
          to publish configs, agents, or themes — they&apos;ll show up here.
        </p>
      )}

      {/* Installed items count */}
      {profile.installed.length > 0 && (
        <div className="text-xs text-muted-foreground border-t border-border pt-3">
          {profile.installed.length} item{profile.installed.length !== 1 ? "s" : ""} installed
        </div>
      )}
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border p-3 flex flex-col gap-1">
      <div className="flex items-center gap-2 text-muted-foreground">
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <span className="text-2xl font-semibold">{value}</span>
    </div>
  );
}

function ProfileItemRow({ item }: { item: MarketplaceItem }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border p-3">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{item.name}</span>
          <Badge variant="secondary" className="text-xs">
            {ITEM_TYPE_LABELS[item.item_type] ?? item.item_type}
          </Badge>
          {item.remixed_from && (
            <Badge variant="outline" className="text-xs">Remix</Badge>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>{item.install_count} install{item.install_count !== 1 ? "s" : ""}</span>
          {item.rating > 0 && (
            <span className="flex items-center gap-1">
              <Star size={10} className="text-yellow-500" />
              {item.rating.toFixed(1)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
