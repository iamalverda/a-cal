"use client";

import { useState, useEffect, useCallback } from "react";
import { Play, Loader2, Copy, Check, Code2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { GraphQLResponse, GraphQLSchema } from "@/types";

/** GraphQLExplorer — test GraphQL queries against the A-Cal API. */
export function GraphQLExplorer() {
  const [query, setQuery] = useState(`{
  eventTypes {
    id
    title
    slug
    is_paid
    price_cents
  }
  teams {
    id
    name
    slug
  }
}`);
  const [result, setResult] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [schema, setSchema] = useState<GraphQLSchema | null>(null);
  const [copied, setCopied] = useState(false);

  const loadSchema = useCallback(async () => {
    try { setSchema(await api.getGraphQLSchema()); }
    catch { setSchema(null); }
  }, []);

  useEffect(() => { loadSchema(); }, [loadSchema]);

  async function runQuery() {
    setLoading(true);
    try {
      const res: GraphQLResponse = await api.graphqlQuery(query);
      setResult(JSON.stringify(res, null, 2));
    } catch (e) {
      setResult(JSON.stringify({ error: (e as Error).message }, null, 2));
    } finally { setLoading(false); }
  }

  function copyResult() {
    navigator.clipboard.writeText(result);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const exampleQueries = [
    { label: "Event Types", query: "{\n  eventTypes {\n    id\n    title\n    slug\n    is_paid\n    price_cents\n  }\n}" },
    { label: "Bookings", query: "{\n  bookings {\n    id\n    attendee_name\n    status\n    payment_status\n  }\n}" },
    { label: "Teams", query: "{\n  teams {\n    id\n    name\n    slug\n  }\n}" },
    { label: "Events", query: "{\n  events(limit: 7) {\n    id\n    title\n    start_time\n  }\n}" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Code2 size={18} className="text-[var(--primary)]" />
        <span className="font-medium text-sm">GraphQL API</span>
        <Badge className="text-[10px] bg-[var(--primary)]/15 text-[var(--primary)]">Read-only</Badge>
      </div>

      <p className="text-sm text-[var(--muted-foreground)]">
        Query events, event types, bookings, and teams through a single GraphQL endpoint.
        Supports field selection and basic arguments.
      </p>

      <div className="flex gap-2 flex-wrap">
        {exampleQueries.map((ex) => (
          <Button key={ex.label} size="sm" variant="ghost" onClick={() => setQuery(ex.query)}>
            {ex.label}
          </Button>
        ))}
      </div>

      <div>
        <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Query</label>
        <textarea
          className="w-full h-48 rounded-md border border-[var(--input)] bg-[var(--background)] p-3 font-mono text-xs resize-y focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          spellCheck={false}
        />
      </div>

      <div className="flex gap-2">
        <Button size="sm" onClick={runQuery} disabled={loading}>
          {loading ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
          Run Query
        </Button>
      </div>

      {result && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Result</label>
            <button onClick={copyResult} className="text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
              {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
            </button>
          </div>
          <pre className="w-full rounded-md border border-[var(--border)] bg-[var(--secondary)]/30 p-3 font-mono text-xs overflow-auto max-h-64">
            {result}
          </pre>
        </div>
      )}

      {schema && (
        <div>
          <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1 block">Schema</label>
          <div className="rounded-md border border-[var(--border)] p-3 space-y-2">
            {Object.entries(schema.types).map(([typeName, typeDef]) => {
              const fields = typeDef.fields as string[] | Array<{ name: string; args: unknown[]; type: string }>;
              const fieldNames = Array.isArray(fields)
                ? typeof fields[0] === "string"
                  ? (fields as string[])
                  : (fields as Array<{ name: string }>).map((f) => f.name)
                : [];
              return (
                <div key={typeName}>
                  <span className="text-xs font-medium text-[var(--primary)]">{typeName}</span>
                  <div className="flex flex-wrap gap-1 mt-0.5">
                    {fieldNames.map((f) => (
                      <Badge key={f} className="text-[9px] bg-[var(--secondary)] font-mono">{f}</Badge>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
