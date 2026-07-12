"use client";

/** Swarm panel — view negotiation history and audit trails.

Shows the federated swarm negotiation log: which sub-accounts conflicted,
how the negotiation resolved (or escalated), and the full message audit
trail for each negotiation.
 */

import { useState, useEffect, useCallback } from "react";
import { swarmApi } from "@/lib/api";
import type { SwarmNegotiation } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const STATE_COLORS: Record<string, "default" | "secondary" | "destructive"> = {
  resolved: "default",
  escalated: "destructive",
  initiated: "secondary",
  probing: "secondary",
  proposing: "secondary",
};

const MSG_LABELS: Record<string, string> = {
  probe: "Probe",
  claim: "Claim",
  propose: "Propose",
  accept: "Accept",
  reject: "Reject",
  concede: "Concede",
  escalate: "Escalate",
  resolve: "Resolve",
};

export function SwarmPanel() {
  const [negotiations, setNegotiations] = useState<SwarmNegotiation[]>([]);
  const [selected, setSelected] = useState<SwarmNegotiation | null>(null);
  const [loading, setLoading] = useState(true);

  const loadNegotiations = useCallback(async () => {
    setLoading(true);
    try {
      const data = await swarmApi.listNegotiations();
      setNegotiations(data);
    } catch {
      setNegotiations([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadNegotiations();
  }, [loadNegotiations]);

  const handleSelect = async (id: string) => {
    try {
      const neg = await swarmApi.getNegotiation(id);
      setSelected(neg);
    } catch (e) {
      console.error("failed to load negotiation", e);
    }
  };

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium">Negotiation History</h2>
        <Button variant="outline" size="sm" onClick={loadNegotiations}>
          Refresh
        </Button>
      </div>

      {loading && <p className="text-sm text-muted-foreground">Loading...</p>}

      {!loading && negotiations.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No negotiations yet. Conflicts between sub-accounts will appear here.
        </p>
      )}

      <div className="grid gap-2">
        {negotiations.map((neg) => (
          <button
            key={neg.id}
            onClick={() => handleSelect(neg.id)}
            className="text-left rounded-lg border border-border p-3 hover:bg-accent transition-colors"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono">
                  {neg.claims[0]?.event_title} vs {neg.claims[1]?.event_title}
                </span>
              </div>
              <Badge variant={STATE_COLORS[neg.state] ?? "secondary"}>
                {neg.state}
              </Badge>
            </div>
            {neg.resolution_reason && (
              <p className="text-xs text-muted-foreground mt-1">
                {neg.resolution_reason}
              </p>
            )}
          </button>
        ))}
      </div>

      {selected && (
        <div className="rounded-lg border border-border p-4 mt-2">
          <h3 className="text-sm font-medium mb-3">Audit Trail</h3>
          <div className="flex flex-col gap-2">
            {selected.messages.map((msg) => (
              <div key={msg.id} className="text-xs flex flex-col gap-1 border-l-2 border-border pl-3">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-xs">
                    {MSG_LABELS[msg.message_type] ?? msg.message_type}
                  </Badge>
                  <span className="text-muted-foreground font-mono">
                    {msg.from_sub_account_id} → {msg.to_sub_account_id}
                  </span>
                </div>
                {msg.reasoning && (
                  <p className="text-muted-foreground">{msg.reasoning}</p>
                )}
                {msg.proposal && (
                  <p className="text-muted-foreground italic">
                    Proposed: {msg.proposal.proposed_start}
                  </p>
                )}
              </div>
            ))}
          </div>
          {selected.winner_sub_account_id && (
            <div className="mt-3 pt-3 border-t border-border">
              <p className="text-xs">
                <span className="font-medium">Winner:</span>{" "}
                <span className="font-mono">{selected.winner_sub_account_id}</span>
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
