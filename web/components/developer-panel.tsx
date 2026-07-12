"use client";

/** Developer panel — plugins, custom agents, and config-as-code.

Visible in Developer mode only. Shows registered plugins, custom agent
specs (beyond the 6 built-ins), and config export/import controls.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { developerApi } from "@/lib/api";
import type { Plugin, AgentSpec } from "@/types";
import type { RuntimePlugin } from "@/types";
import { Button } from "@/components/ui/button";
import { Upload, Download, ScanLine, RefreshCw, Loader2, AlertCircle, Code2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";

const PLUGIN_TYPE_LABELS: Record<string, string> = {
  agent: "Agent",
  provider: "Provider",
  sync_rule: "Sync Rule",
  ui_component: "UI Component",
};

export function DeveloperPanel() {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [agents, setAgents] = useState<AgentSpec[]>([]);
  const [loading, setLoading] = useState(true);
  const [exportData, setExportData] = useState<string | null>(null);
  const [runtimePlugins, setRuntimePlugins] = useState<RuntimePlugin[]>([]);
  const [runtimeLoading, setRuntimeLoading] = useState(false);
  const [supportedHooks, setSupportedHooks] = useState<string[]>([]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [pluginData, agentData] = await Promise.all([
        developerApi.listPlugins(),
        developerApi.listAgentSpecs(),
      ]);
      setPlugins(pluginData);
      setAgents(agentData);
    } catch {
      setPlugins([]);
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRuntimePlugins = useCallback(async () => {
    setRuntimeLoading(true);
    try {
      const [pluginList, hooksResp] = await Promise.all([
        developerApi.listRuntimePlugins(),
        developerApi.listRuntimeHooks(),
      ]);
      setRuntimePlugins(pluginList);
      setSupportedHooks(hooksResp.hooks);
    } catch {
      setRuntimePlugins([]);
    } finally {
      setRuntimeLoading(false);
    }
  }, []);

  const handleScanRuntime = async () => {
    setRuntimeLoading(true);
    try {
      const result = await developerApi.scanRuntimePlugins();
      setRuntimePlugins(result.plugins);
    } catch {
      setRuntimePlugins([]);
    } finally {
      setRuntimeLoading(false);
    }
  };

  const handleToggleRuntimePlugin = async (plugin: RuntimePlugin, enable: boolean) => {
    try {
      if (enable) {
        await developerApi.enableRuntimePlugin(plugin.id);
      } else {
        await developerApi.disableRuntimePlugin(plugin.id);
      }
      loadRuntimePlugins();
    } catch (e) {
      console.error("runtime toggle failed", e);
    }
  };

  const handleReloadRuntimePlugin = async (pluginId: string) => {
    try {
      await developerApi.reloadRuntimePlugin(pluginId);
      loadRuntimePlugins();
    } catch (e) {
      console.error("runtime reload failed", e);
    }
  };

  useEffect(() => {
    loadData();
    loadRuntimePlugins();
  }, [loadData, loadRuntimePlugins]);

  const handleTogglePlugin = async (plugin: Plugin, enable: boolean) => {
    try {
      if (enable) {
        await developerApi.enablePlugin(plugin.id);
      } else {
        await developerApi.disablePlugin(plugin.id);
      }
      loadData();
    } catch (e) {
      console.error("toggle failed", e);
    }
  };

  const handleExport = async () => {
    try {
      const config = await developerApi.exportConfig();
      setExportData(JSON.stringify(config, null, 2));
    } catch (e) {
      console.error("export failed", e);
    }
  };

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importResult, setImportResult] = useState<string | null>(null);

  const handleImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const config = JSON.parse(text);
      const result = await developerApi.importConfig(config);
      setImportResult(`Imported: ${result.imported ?? "OK"} items`);
      loadData();
    } catch (e) {
      setImportResult(`Import failed: ${e instanceof Error ? e.message : "unknown error"}`);
    }
  };

  const handleDownloadExport = () => {
    if (!exportData) return;
    const blob = new Blob([exportData], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "a-cal-config.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleDeleteAgent = async (name: string) => {
    try {
      await developerApi.deleteAgentSpec(name);
      loadData();
    } catch (e) {
      console.error("delete failed", e);
    }
  };

  const builtInAgents = agents.filter(
    (a) => a.name.startsWith("a_cal_") && !a.name.includes("custom")
  );
  const customAgents = agents.filter(
    (a) => !a.name.startsWith("a_cal_") || a.name.includes("custom")
  );

  return (
    <div className="flex flex-col gap-6 p-4">
      {/* Plugins section */}
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium">Plugins</h2>
        {loading && <p className="text-sm text-muted-foreground">Loading...</p>}
        {!loading && plugins.length === 0 && (
          <p className="text-sm text-muted-foreground">No plugins registered.</p>
        )}
        <div className="grid gap-2">
          {plugins.map((plugin) => (
            <div
              key={plugin.id}
              className="rounded-lg border border-border p-3 flex items-center justify-between gap-3"
            >
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{plugin.name}</span>
                  <Badge variant="secondary" className="text-xs">
                    {PLUGIN_TYPE_LABELS[plugin.plugin_type] ?? plugin.plugin_type}
                  </Badge>
                  <Badge variant="outline" className="text-xs">v{plugin.version}</Badge>
                </div>
                <span className="text-xs text-muted-foreground">{plugin.description}</span>
              </div>
              <Switch
                checked={plugin.enabled}
                onCheckedChange={(checked) => handleTogglePlugin(plugin, checked)}
              />
            </div>
          ))}
        </div>
      </section>

      {/* Runtime plugins section (loaded code from ~/.a-cal/plugins/) */}
      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium">Runtime Plugins</h2>
          <Button variant="outline" size="sm" onClick={handleScanRuntime} disabled={runtimeLoading}>
            {runtimeLoading ? <Loader2 size={14} className="animate-spin" /> : <ScanLine size={14} />}
            Scan Directory
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Plugins loaded from <code className="text-xs">~/.a-cal/plugins/</code>. Each file must define a <code className="text-xs">Plugin</code> class with at least one supported hook.
        </p>
        {supportedHooks.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {supportedHooks.map((hook) => (
              <Badge key={hook} variant="outline" className="text-[10px] font-mono py-0">
                {hook}
              </Badge>
            ))}
          </div>
        )}
        {runtimeLoading && runtimePlugins.length === 0 && (
          <p className="text-sm text-muted-foreground">Scanning...</p>
        )}
        {!runtimeLoading && runtimePlugins.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No plugins loaded. Drop a .py file in ~/.a-cal/plugins/ and click Scan.
          </p>
        )}
        <div className="grid gap-2">
          {runtimePlugins.map((plugin) => (
            <div
              key={plugin.id}
              className="rounded-lg border border-border p-3 flex items-center justify-between gap-3"
            >
              <div className="flex flex-col gap-1 min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Code2 size={14} className="shrink-0 text-muted-foreground" />
                  <span className="text-sm font-medium truncate">{plugin.name}</span>
                  <Badge variant="secondary" className="text-xs shrink-0">
                    {plugin.plugin_type}
                  </Badge>
                  {plugin.load_error && (
                    <Badge variant="destructive" className="text-xs shrink-0">
                      <AlertCircle size={10} className="mr-1" />
                      Error
                    </Badge>
                  )}
                </div>
                {plugin.load_error ? (
                  <span className="text-xs text-red-500 font-mono truncate">{plugin.load_error}</span>
                ) : (
                  <div className="flex flex-wrap gap-1">
                    {plugin.hooks.map((hook) => (
                      <Badge key={hook} variant="outline" className="text-[10px] font-mono py-0">
                        {hook}
                      </Badge>
                    ))}
                  </div>
                )}
                <span className="text-[10px] text-muted-foreground truncate">{plugin.file_path}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {!plugin.load_error && (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleReloadRuntimePlugin(plugin.id)}
                      title="Reload from disk"
                    >
                      <RefreshCw size={12} />
                    </Button>
                    <Switch
                      checked={plugin.enabled}
                      onCheckedChange={(checked) => handleToggleRuntimePlugin(plugin, checked)}
                    />
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Agent specs section */}
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium">Agent Specs</h2>
        <div className="grid gap-2">
          {builtInAgents.map((agent) => (
            <div
              key={agent.name}
              className="rounded-lg border border-border p-3 flex items-center justify-between gap-3"
            >
              <div className="flex flex-col gap-1">
                <span className="text-sm font-medium">{agent.display_name}</span>
                <span className="text-xs text-muted-foreground">{agent.description}</span>
              </div>
              <Badge variant="outline" className="text-xs">Built-in</Badge>
            </div>
          ))}
          {customAgents.map((agent) => (
            <div
              key={agent.name}
              className="rounded-lg border border-border p-3 flex items-center justify-between gap-3"
            >
              <div className="flex flex-col gap-1">
                <span className="text-sm font-medium">{agent.display_name}</span>
                <span className="text-xs text-muted-foreground">{agent.description}</span>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="secondary" className="text-xs">Custom</Badge>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => handleDeleteAgent(agent.name)}
                >
                  Delete
                </Button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Config-as-code section */}
      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium">Config-as-Code</h2>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={handleExport}>
              <Download size={14} />
              Export
            </Button>
            <Button variant="outline" size="sm" onClick={() => fileInputRef.current?.click()}>
              <Upload size={14} />
              Import
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/json"
              onChange={handleImport}
              className="hidden"
            />
          </div>
        </div>
        {importResult && (
          <div className="text-xs rounded-md border border-border p-2 bg-muted/30">
            {importResult}
          </div>
        )}
        {exportData && (
          <>
            <pre className="text-xs font-mono rounded-lg border border-border p-3 overflow-auto max-h-96 bg-muted/50">
              {exportData}
            </pre>
            <Button variant="ghost" size="sm" onClick={handleDownloadExport} className="w-fit">
              <Download size={14} />
              Download as file
            </Button>
          </>
        )}
      </section>
    </div>
  );
}
