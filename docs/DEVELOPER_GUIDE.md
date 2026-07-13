# A-Cal Developer Guide

This guide covers everything available in Developer mode: the REST API, the
TypeScript SDK, the plugin system, visual workflows, agent spec editing,
config-as-code, and the marketplace.

## Enabling Developer mode

Switch to Developer mode from the sidebar mode selector. Developer mode
unlocks all panels: API Explorer, Plugin Runtime, Agent Spec Editor, Workflow
Builder, Config Import/Export, and the full Marketplace.

## REST API

Base URL: `http://localhost:8000/api/a-cal`

All endpoints accept and return JSON. In standalone mode, authentication is
optional (a demo user is auto-created). See `docs/API_REFERENCE.md` for the
full endpoint list (80+ routes).

### Key endpoints

| Area | Method | Path | Description |
|------|--------|------|-------------|
| Conductor | POST | `/conductor/chat` | Send a message to the conductor agent |
| Sub-accounts | GET/POST | `/sub-accounts` | List or create sub-accounts |
| Sub-accounts | PATCH/DELETE | `/sub-accounts/{id}` | Update or delete |
| Providers | GET/POST | `/providers` | List or create provider connections |
| Calendar | GET/POST | `/events` | List or create events |
| Calendar | PATCH/DELETE | `/events/{id}` | Update or delete events |
| Sync | POST | `/sync/{sub_id}` | Trigger a sync for a sub-account |
| Sync rules | GET/POST | `/sub-accounts/{id}/sync-rules` | List or create sync rules |
| Email | POST | `/email/scan` | Scan inbox for scheduling items |
| Email | POST | `/email/scan-schedule` | Scan with depth-gated suggestions |
| Swarm | POST | `/swarm/negotiate` | Start a negotiation between sub-agents |
| Swarm | POST | `/swarm/detect-conflicts` | Detect scheduling conflicts |
| Settings | GET/PUT | `/settings/model-routing` | Get or set model routing config |
| Settings | GET/PUT | `/settings/mode` | Get or set skill mode |
| Settings | GET/PUT | `/settings/self-model` | Get or set self-model depth + privacy |
| Settings | GET/PUT | `/settings/autonomy` | Get or set agent autonomy level |
| Marketplace | GET | `/marketplace/items` | Browse shared configs |
| Marketplace | POST | `/marketplace/items` | Publish a config |
| Marketplace | POST | `/marketplace/items/{id}/install` | Install a config |
| Marketplace | POST | `/marketplace/items/{id}/remix` | Remix a config |
| Developer | GET | `/developer/plugins` | List registered plugins |
| Developer | POST | `/developer/plugins/runtime/scan` | Scan plugin directory |
| Developer | GET/POST | `/developer/agent-specs` | List or create agent specs |
| Developer | POST | `/developer/export` | Export full config as JSON |
| Developer | POST | `/developer/import` | Import config from JSON |

Use the API Explorer panel in Developer mode to browse and test all endpoints
interactively.

## TypeScript SDK

```bash
pnpm add @a-cal/sdk
```

```typescript
import { ACalClient } from "@a-cal/sdk";

const client = new ACalClient({
  baseUrl: "http://localhost:8000/api/a-cal",
});

// Talk to the conductor
const result = await client.conductor.chat("Schedule lunch tomorrow at noon");

// Manage sub-accounts
const subs = await client.subAccounts.list();
await client.subAccounts.create({ name: "Work Google", kind: "calendar" });

// Configure model routing
await client.settings.setLLMEnabled(true);
await client.settings.setApiKeys({ openai: "sk-..." });
await client.settings.setModelRouting({
  global_provider: "openai",
  global_model: "gpt-4o",
  privacy_force_local: true,
});

// Browse marketplace
const items = await client.marketplace.list("agent_spec");
await client.marketplace.install(items[0].id);

// Developer: export/import config
const config = await client.developer.exportConfig();
```

See `sdk/README.md` for the full API surface.

## Plugin system

Plugins are Python files with a `Plugin` class. They run in-process and hook
into the conductor, sync engine, and event lifecycle.

### Hooks

| Hook | When it fires | Return value |
|------|--------------|-------------|
| `on_event_created(event)` | After an event is created | Modified event dict or None |
| `on_event_updated(event)` | After an event is updated | Modified event dict or None |
| `on_event_deleted(event_id)` | After an event is deleted | None |
| `on_sync_complete(sub_account_id, events)` | After a provider sync finishes | None |
| `on_intent_classified(message, intent)` | After conductor classifies intent | Override intent string or None |
| `on_conductor_response(response, context)` | Before conductor returns response | Transformed response string or None |
| `get_agent_spec()` | When loading agent specs | Agent spec dict or list of dicts |
| `get_sync_rules()` | When loading sync rules | Sync rule dict or list of dicts |

### Example plugin

```python
class Plugin:
    name = "Focus Time Protector"
    plugin_type = "agent"
    enabled = True

    def on_event_created(self, event):
        title = (event.get("title") or "").lower()
        if "focus" in title or "deep work" in title:
            metadata = event.get("metadata") or {}
            metadata["protected"] = True
            event["metadata"] = metadata
            return event
        return None
```

### Installing plugins

1. Copy `.py` files to `~/.a-cal/plugins/` (or your `A_CAL_PLUGIN_DIR`)
2. Open Developer mode and click "Scan Directory" in Runtime Plugins
3. Or call the API: `POST /api/a-cal/developer/plugins/runtime/scan`
4. Enable/disable plugins from the UI or API without removing files

See `plugins/examples/` for 5 working examples covering all hook types.

## Visual workflow builder

Workflows are automation chains that connect calendar events, LLM calls, email,
and sync operations. Build them visually in Developer mode or write JSON.

### Workflow JSON

```json
{
  "name": "Morning briefing",
  "description": "Summarize today's schedule and email me",
  "nodes": [
    { "id": "fetch", "type": "calendar.fetch", "params": { "days": 1 } },
    { "id": "summarize", "type": "llm.summarize", "params": { "prompt": "Summarize today's meetings" } },
    { "id": "notify", "type": "email.send", "params": { "subject": "Your day ahead" } }
  ],
  "edges": [["fetch", "summarize"], ["summarize", "notify"]]
}
```

### Workflow node types

| Type | Description |
|------|-------------|
| `calendar.fetch` | Fetch events for a date range |
| `calendar.create` | Create a new event |
| `llm.summarize` | Send text to the LLM for summarization |
| `llm.generate` | Generate text from a prompt |
| `email.send` | Send an email |
| `sync.trigger` | Trigger a sub-account sync |
| `filter` | Filter events by criteria |
| `transform` | Transform event data |

## Agent spec editor

Agent specs define the specialist agents the conductor can route to. Each spec
includes a system prompt, tools, cognitive tier, privacy settings, and
capabilities.

```json
{
  "name": "focus_protector",
  "display_name": "Focus Protector",
  "description": "Protects deep work time from interruptions",
  "system_prompt": "You are a focus time specialist...",
  "tools": ["calendar.read", "calendar.update"],
  "default_tier": "standard",
  "can_negotiate": true,
  "privacy_force_local": false,
  "capabilities": ["focus_detection", "conflict_resolution"]
}
```

Create and manage agent specs via the API or the Agent Spec Editor panel.

## Config-as-code

Export your full configuration as JSON and import it on another instance.
This includes sub-accounts, sync rules, agent specs, model routing, self-model
settings, and marketplace installs.

```bash
# Export
curl http://localhost:8000/api/a-cal/developer/export > my-acal-config.json

# Import
curl -X POST http://localhost:8000/api/a-cal/developer/import \
  -H "Content-Type: application/json" \
  -d @my-acal-config.json
```

## Marketplace

Share your configs with the community:

1. Build something useful (agent spec, sync rule pack, workflow, plugin config)
2. Publish via `POST /api/a-cal/marketplace/items` or the Marketplace panel
3. Other users browse, install, remix, and rate your work
4. Every item includes provenance metadata for auditability

### Item types

| Type | Description |
|------|-------------|
| `agent_spec` | Custom agent configuration |
| `sync_rule_pack` | Collection of sync rules |
| `negotiation_strategy` | Swarm negotiation parameters |
| `ui_theme` | Visual customization |
| `plugin_config` | Plugin configuration |
| `workflow` | Automation chain |

### Remixing

Any marketplace item can be remixed. The remix creates a new item that
references the original, building a provenance chain. Users can see the full
remix tree to understand how a config evolved.

## Model routing

Configure which LLM provider handles which tasks. Privacy-tiered routing
forces email content, self-model reasoning, and negotiation to always run on
local models.

### Supported providers

| Provider | Type | API key needed |
|----------|------|----------------|
| Ollama | Local | No |
| OpenAI | Cloud | Yes |
| Anthropic | Cloud | Yes |
| Google Gemini | Cloud | Yes |
| Azure OpenAI | Cloud | Yes |
| DeepSeek | Cloud | Yes |
| Together | Cloud | Yes |
| Groq | Cloud | Yes |
| OpenRouter | Cloud | Yes |
| Mistral | Cloud | Yes |
| LM Studio | Local | No |
| llama.cpp | Local | No |

### Per-task routing

In Pro/Developer mode, assign different models to different tasks:

```json
{
  "global_provider": "ollama",
  "global_model": "llama3.2",
  "privacy_force_local": true,
  "per_task": {
    "sync": { "provider": "ollama", "model": "llama3.2" },
    "schedule": { "provider": "openai", "model": "gpt-4o" },
    "email": { "provider": "ollama", "model": "llama3.2" },
    "negotiate": { "provider": "ollama", "model": "llama3.2" },
    "self_model": { "provider": "ollama", "model": "llama3.2" }
  }
}
```
