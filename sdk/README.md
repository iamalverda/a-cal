# @a-cal/sdk

TypeScript SDK for the A-Cal agentic calendar platform.

## Installation

```bash
pnpm add @a-cal/sdk
# or
npm install @a-cal/sdk
```

## Quick Start

```typescript
import { ACalClient } from "@a-cal/sdk";

const client = new ACalClient({
  baseUrl: "http://localhost:8000/api/a-cal",
  apiKey: "your-api-key", // optional, for authenticated deployments
});

// Talk to the conductor agent
const result = await client.conductor.chat("Schedule lunch tomorrow at noon");
console.log(result.response);

// Manage sub-accounts
const subs = await client.subAccounts.list();
await client.subAccounts.create({ name: "Work Google", kind: "calendar" });

// Enable AI agents with your model provider
await client.settings.setLLMEnabled(true);
await client.settings.setApiKeys({ openai: "sk-..." });
await client.settings.setModelRouting({
  global_provider: "openai",
  global_model: "gpt-4o",
  privacy_force_local: true,
});

// Check if Ollama is available (for local models)
const ollama = await client.settings.getOllamaStatus();
if (ollama.available) {
  console.log("Available models:", ollama.models);
}

// Browse the marketplace
const items = await client.marketplace.list("agent_spec");
await client.marketplace.install(items[0].id);

// Developer: export/import full config
const config = await client.developer.exportConfig();
await client.developer.importConfig(config);

// Swarm: detect scheduling conflicts
const conflicts = await client.swarm.detectConflicts(events);
```

## API Surface

| Namespace | Methods |
|-----------|---------|
| `subAccounts` | list, create, update, delete |
| `providers` | list, listAll, create |
| `calendar` | unified |
| `conductor` | chat |
| `agents` | list |
| `settings` | getMode, setMode, getModelRouting, setModelRouting, getLLMEnabled, setLLMEnabled, getOllamaStatus, getApiKeys, setApiKeys, getSelfModel, setSelfModel |
| `swarm` | negotiate, list, get, detectConflicts |
| `marketplace` | list, get, search, publish, install, listInstalls, remix, getRemixes, getRemixChain, rate |
| `developer` | listPlugins, registerPlugin, deletePlugin, enablePlugin, disablePlugin, updatePluginConfig, listAgentSpecs, createAgentSpec, updateAgentSpec, deleteAgentSpec, exportConfig, importConfig |

## License

AGPL-3.0-or-later
