"use client";

/** API Explorer — browse and test A-Cal REST API endpoints.

Visible in Developer mode as part of the Developer Studio. Lets developers:
- Browse all registered API routes grouped by tag
- View endpoint details (method, path, parameters, body schema)
- Try endpoints live with editable path params, query params, and request body
- See the raw JSON response

This fulfills the "API explorer" feature from the end goal charter.
*/

import { useState, useEffect, useMemo, useCallback } from "react";
import {
  Search,
  ChevronRight,
  Loader2,
  Play,
  Copy,
  Check,
  ArrowLeft,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { developerApi } from "@/lib/api";
import type { ApiRouteInfo } from "@/types";

/** Method color mapping. */
const METHOD_COLORS: Record<string, string> = {
  GET: "text-[var(--cal-work)] bg-[var(--cal-work)]/10",
  POST: "text-[var(--cal-personal)] bg-[var(--cal-personal)]/10",
  PATCH: "text-[var(--cal-sync)] bg-[var(--cal-sync)]/10",
  PUT: "text-[var(--cal-sync)] bg-[var(--cal-sync)]/10",
  DELETE: "text-[var(--destructive)] bg-[var(--destructive)]/10",
};

/** Tag display names. */
const TAG_NAMES: Record<string, string> = {
  "a-cal-agents": "Agents & Conductor",
  "a-cal-data": "Sub-Accounts & Calendar",
  "a-cal-developer": "Developer",
  "a-cal-marketplace": "Marketplace",
  "a-cal-swarm": "Federated Swarm",
  "a-cal-analytics": "Analytics",
  "a-cal-oauth": "OAuth",
  "": "System",
};

export function ApiExplorer() {
  const [routes, setRoutes] = useState<ApiRouteInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedRoute, setSelectedRoute] = useState<ApiRouteInfo | null>(null);
  const [pathParamValues, setPathParamValues] = useState<Record<string, string>>({});
  const [queryParamValues, setQueryParamValues] = useState<Record<string, string>>({});
  const [bodyText, setBodyText] = useState("{}");
  const [response, setResponse] = useState<string | null>(null);
  const [responseStatus, setResponseStatus] = useState<number | null>(null);
  const [executing, setExecuting] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    developerApi.getApiRoutes().then((data) => {
      setRoutes(data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  /** Group routes by tag. */
  const groupedRoutes = useMemo(() => {
    const groups: Record<string, ApiRouteInfo[]> = {};
    for (const r of routes) {
      const tag = r.tag || "System";
      if (!groups[tag]) groups[tag] = [];
      groups[tag].push(r);
    }
    return groups;
  }, [routes]);

  /** Filter routes by search query. */
  const filteredGroups = useMemo(() => {
    if (!search.trim()) return groupedRoutes;
    const q = search.toLowerCase();
    const result: Record<string, ApiRouteInfo[]> = {};
    for (const [tag, rs] of Object.entries(groupedRoutes)) {
      const filtered = rs.filter(
        (r) =>
          r.path.toLowerCase().includes(q) ||
          r.summary.toLowerCase().includes(q) ||
          r.method.toLowerCase().includes(q),
      );
      if (filtered.length > 0) result[tag] = filtered;
    }
    return result;
  }, [groupedRoutes, search]);

  /** Build the full URL with path and query params filled in. */
  const buildUrl = useCallback((route: ApiRouteInfo): string => {
    let path = route.path;
    for (const param of route.path_params) {
      const val = pathParamValues[param.name] || `{${param.name}}`;
      path = path.replace(`{${param.name}}`, encodeURIComponent(val));
    }
    const queryParams = route.query_params
      .filter((p) => queryParamValues[p.name])
      .map((p) => `${p.name}=${encodeURIComponent(queryParamValues[p.name])}`)
      .join("&");
    return queryParams ? `${path}?${queryParams}` : path;
  }, [pathParamValues, queryParamValues]);

  /** Execute the selected endpoint. */
  const handleExecute = useCallback(async () => {
    if (!selectedRoute) return;
    setExecuting(true);
    setResponse(null);
    setResponseStatus(null);
    try {
      const url = buildUrl(selectedRoute);
      const method = selectedRoute.method.split(",")[0].toUpperCase();
      const options: RequestInit = {
        method,
        headers: { "Content-Type": "application/json" },
      };
      if (method !== "GET" && method !== "DELETE") {
        options.body = bodyText;
      }
      const res = await fetch(url, options);
      setResponseStatus(res.status);
      const text = await res.text();
      try {
        setResponse(JSON.stringify(JSON.parse(text), null, 2));
      } catch {
        setResponse(text);
      }
    } catch (err) {
      setResponse(`Error: ${err instanceof Error ? err.message : String(err)}`);
      setResponseStatus(0);
    } finally {
      setExecuting(false);
    }
  }, [selectedRoute, buildUrl, bodyText]);

  /** Copy the response to clipboard. */
  const handleCopy = useCallback(() => {
    if (response) {
      navigator.clipboard.writeText(response);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [response]);

  /** Select a route and initialize param values. */
  const handleSelectRoute = useCallback((route: ApiRouteInfo) => {
    setSelectedRoute(route);
    setPathParamValues({});
    const initialQuery: Record<string, string> = {};
    for (const p of route.query_params) {
      if (p.default) initialQuery[p.name] = p.default;
    }
    setQueryParamValues(initialQuery);
    if (route.body_schema) {
      const body: Record<string, unknown> = {};
      for (const [fname, finfo] of Object.entries(route.body_schema.fields)) {
        body[fname] = finfo.default || "";
      }
      setBodyText(JSON.stringify(body, null, 2));
    } else {
      setBodyText("{}");
    }
    setResponse(null);
    setResponseStatus(null);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 size={20} className="animate-spin text-[var(--muted-foreground)]" />
      </div>
    );
  }

  // --- Route detail view ---
  if (selectedRoute) {
    const method = selectedRoute.method.split(",")[0].toUpperCase();
    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => setSelectedRoute(null)}>
            <ArrowLeft size={16} />
          </Button>
          <Badge className={cn("font-mono text-xs px-2 py-0.5", METHOD_COLORS[method] || "")}>
            {method}
          </Badge>
          <code className="text-sm font-mono text-[var(--foreground)] break-all">
            {selectedRoute.path}
          </code>
        </div>

        {selectedRoute.summary && (
          <p className="text-sm text-[var(--muted-foreground)]">{selectedRoute.summary}</p>
        )}

        {/* Path parameters */}
        {selectedRoute.path_params.length > 0 && (
          <div className="flex flex-col gap-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
              Path Parameters
            </h4>
            {selectedRoute.path_params.map((p) => (
              <div key={p.name} className="flex items-center gap-2">
                <code className="text-xs font-mono text-[var(--cal-work)] min-w-[120px]">{p.name}</code>
                <Input
                  value={pathParamValues[p.name] || ""}
                  onChange={(e) =>
                    setPathParamValues((prev) => ({ ...prev, [p.name]: e.target.value }))
                  }
                  placeholder={`Enter ${p.name}...`}
                  className="h-8 text-sm flex-1"
                />
              </div>
            ))}
          </div>
        )}

        {/* Query parameters */}
        {selectedRoute.query_params.length > 0 && (
          <div className="flex flex-col gap-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
              Query Parameters
            </h4>
            {selectedRoute.query_params.map((p) => (
              <div key={p.name} className="flex items-center gap-2">
                <code className="text-xs font-mono text-[var(--cal-sync)] min-w-[120px]">{p.name}</code>
                <Input
                  value={queryParamValues[p.name] || ""}
                  onChange={(e) =>
                    setQueryParamValues((prev) => ({ ...prev, [p.name]: e.target.value }))
                  }
                  placeholder={p.default || `Enter ${p.name}...`}
                  className="h-8 text-sm flex-1"
                />
              </div>
            ))}
          </div>
        )}

        {/* Request body */}
        {selectedRoute.body_schema && method !== "GET" && method !== "DELETE" && (
          <div className="flex flex-col gap-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
              Request Body
            </h4>
            <div className="text-xs text-[var(--muted-foreground)] mb-1">
              Fields: {Object.entries(selectedRoute.body_schema.fields)
                .filter(([, f]) => f.required)
                .map(([n]) => n)
                .join(", ") || "none required"}
            </div>
            <textarea
              value={bodyText}
              onChange={(e) => setBodyText(e.target.value)}
              className="w-full h-40 rounded-md border border-[var(--border)] bg-[var(--background)] p-3 font-mono text-xs resize-y focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
              spellCheck={false}
            />
          </div>
        )}

        {/* Execute button */}
        <div className="flex items-center gap-3">
          <Button
            variant="default"
            size="sm"
            onClick={handleExecute}
            disabled={executing}
          >
            {executing ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            Send Request
          </Button>
          <code className="text-xs font-mono text-[var(--muted-foreground)]">
            {method} {buildUrl(selectedRoute)}
          </code>
        </div>

        {/* Response */}
        {response !== null && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                  Response
                </h4>
                {responseStatus !== null && (
                  <Badge
                    className={cn(
                      "text-xs font-mono",
                      responseStatus >= 200 && responseStatus < 300
                        ? "text-[var(--cal-personal)] bg-[var(--cal-personal)]/10"
                        : "text-[var(--destructive)] bg-[var(--destructive)]/10",
                    )}
                  >
                    {responseStatus}
                  </Badge>
                )}
              </div>
              <Button variant="ghost" size="icon" onClick={handleCopy} className="h-7 w-7">
                {copied ? <Check size={14} /> : <Copy size={14} />}
              </Button>
            </div>
            <pre className="w-full max-h-96 overflow-auto rounded-md border border-[var(--border)] bg-[var(--muted)]/30 p-3 font-mono text-xs whitespace-pre-wrap break-all">
              {response}
            </pre>
          </div>
        )}
      </div>
    );
  }

  // --- Route list view ---
  return (
    <div className="flex flex-col gap-3">
      {/* Search */}
      <div className="relative">
        <Search
          size={14}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
        />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search endpoints..."
          className="h-8 pl-9 text-sm"
        />
      </div>

      {/* Route count */}
      <div className="text-xs text-[var(--muted-foreground)]">
        {routes.length} endpoints across {Object.keys(groupedRoutes).length} categories
      </div>

      {/* Grouped routes */}
      {Object.entries(filteredGroups).map(([tag, rs]) => (
        <div key={tag} className="flex flex-col gap-1">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)] py-1">
            {TAG_NAMES[tag] || tag}
          </h4>
          {rs.map((route) => {
            const method = route.method.split(",")[0].toUpperCase();
            return (
              <button
                key={`${route.method}-${route.path}`}
                onClick={() => handleSelectRoute(route)}
                className="flex items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-[var(--accent)] transition-colors group"
              >
                <span
                  className={cn(
                    "font-mono text-[10px] font-bold px-1.5 py-0.5 rounded min-w-[52px] text-center",
                    METHOD_COLORS[method] || "",
                  )}
                >
                  {method}
                </span>
                <code className="text-xs font-mono text-[var(--foreground)] flex-1 truncate">
                  {route.path}
                </code>
                {route.summary && (
                  <span className="text-[10px] text-[var(--muted-foreground)] truncate max-w-[200px] hidden sm:block">
                    {route.summary}
                  </span>
                )}
                <ChevronRight
                  size={14}
                  className="text-[var(--muted-foreground)] opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                />
              </button>
            );
          })}
        </div>
      ))}

      {Object.keys(filteredGroups).length === 0 && (
        <div className="text-center py-8 text-sm text-[var(--muted-foreground)]">
          No endpoints match &quot;{search}&quot;
        </div>
      )}
    </div>
  );
}
