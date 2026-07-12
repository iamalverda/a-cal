# A-Cal REST API Reference

Base URL: `http://localhost:8000/api/a-cal`

All endpoints accept and return JSON. Authentication is via Bearer token
(if running with atom's auth layer) or unauthenticated (standalone mode).

## Sub-Accounts

### Create Sub-Account
```
POST /sub-accounts
```
Body:
```json
{
  "name": "Work Google",
  "kind": "calendar",
  "sync_mode": "mirror_filter",
  "is_main": false,
  "agent_enabled": true
}
```
Response: `SubAccount`

### List Sub-Accounts
```
GET /sub-accounts
```
Response: `SubAccount[]`

### Update Sub-Account
```
PATCH /sub-accounts/{sub_id}
```
Body: partial `SubAccount` fields

### Delete Sub-Account
```
DELETE /sub-accounts/{sub_id}
```

## Provider Connections

### Create Provider Connection
```
POST /providers
```
Body:
```json
{
  "sub_account_id": "uuid",
  "provider_type": "google_calendar",
  "provider_account_id": "user@gmail.com",
  "display_name": "Work Calendar"
}
```
Response: `ProviderConnection`

### List Providers
```
GET /providers?sub_account_id={id}
```
Response: `ProviderConnection[]`

### List All Providers
```
GET /providers/all
```
Response: `ProviderConnection[]`

## Unified Calendar

### Get Unified Calendar
```
GET /calendar/unified?days=7
```
Returns events from all sub-accounts, merged per sync rules.
Response: `UnifiedEvent[]`

## Sync Rules

### Create Sync Rule
```
POST /sync-rules
```
Body:
```json
{
  "sub_account_id": "uuid",
  "rule_type": "include",
  "rule_config": { "pattern": ".*meeting.*" },
  "priority": 1
}
```

### List Sync Rules
```
GET /sync-rules?sub_account_id={id}
```

## Conductor (Agent Chat)

### Send Message to Conductor
```
POST /conductor/chat
```
Body:
```json
{ "message": "Move my 3pm to tomorrow" }
```
Response:
```json
{
  "response": "I'll move your 3pm meeting...",
  "agent": "a_cal_schedule",
  "routing_decision": { ... },
  "actions_taken": [...]
}
```

### List Agents
```
GET /agents
```
Response: `AgentSpec[]`

## Settings

### Skill Mode
```
GET /settings/mode
POST /settings/mode
```
Body (POST): `{ "mode": "simple" | "pro" | "developer" }`

### Model Routing
```
GET /settings/model-routing
POST /settings/model-routing
```
Body (POST):
```json
{
  "global_provider": "ollama",
  "global_model": "llama3.2",
  "per_task_overrides": {},
  "privacy_force_local": true
}
```

### LLM Enabled
```
GET /settings/llm-enabled
POST /settings/llm-enabled
```
Body (POST): `{ "enabled": true }`

When `false`, the conductor returns routing-only responses (no LLM calls).

### Ollama Status
```
GET /settings/ollama-status
```
Response:
```json
{
  "available": true,
  "models": ["llama3.2:8b", "mistral:7b", ...]
}
```

### API Keys
```
GET /settings/api-keys
POST /settings/api-keys
```
Body (POST): `{ "keys": { "openai": "sk-...", "anthropic": "sk-ant-..." } }`

API keys are masked on GET (returned as `"***"`). Keys are never logged.

### Self-Model Settings
```
GET /settings/self-model
POST /settings/self-model
```
Body (POST):
```json
{
  "depth": "pattern_memory" | "attention_intent" | "longitudinal_identity",
  "enabled_categories": {},
  "cloud_sync_enabled": false,
  "proactive_suggestions_enabled": false,
  "feed_into_calendar_view": true,
  "feed_into_agents": true
}
```

## Swarm Negotiation

### Negotiate
```
POST /swarm/negotiate
```
Body:
```json
{
  "claim_a": { "sub_account_id": "...", "priority": "high", "can_move": false },
  "claim_b": { "sub_account_id": "...", "priority": "low", "can_move": true }
}
```

### List Negotiations
```
GET /swarm/negotiations
```

### Get Negotiation
```
GET /swarm/negotiations/{id}
```

### Detect Conflicts
```
POST /swarm/detect-conflicts
```
Body:
```json
{
  "events": [
    { "title": "Team Standup", "source_sub_account_id": "...", "start": "...", "end": "..." }
  ]
}
```

## Marketplace

### List Items
```
GET /marketplace/items?item_type=agent_spec&tag=productivity
```

### Get Item
```
GET /marketplace/items/{id}
```

### Search
```
GET /marketplace/search?q=focus
```

### Publish Item
```
POST /marketplace/items
```
Body: `MarketplaceItem` with `provenance` metadata

### Install Item
```
POST /marketplace/items/{id}/install
```

### List Installs
```
GET /marketplace/installs
```

### Remix Item
```
POST /marketplace/items/{id}/remix
```

### Get Remixes
```
GET /marketplace/items/{id}/remixes
```

### Get Remix Chain
```
GET /marketplace/items/{id}/remix-chain
```

### Rate Item
```
POST /marketplace/items/{id}/rate
```
Body: `{ "stars": 1-5 }`

## Developer

### Plugins
```
GET /developer/plugins?plugin_type=agent
POST /developer/plugins
DELETE /developer/plugins/{id}
POST /developer/plugins/{id}/enable
POST /developer/plugins/{id}/disable
PATCH /developer/plugins/{id}/config
```

### Agent Specs
```
GET /developer/agents
POST /developer/agents
PATCH /developer/agents/{name}
DELETE /developer/agents/{name}
```

### Config Export/Import
```
POST /developer/config/export
POST /developer/config/import
```

## Health
```
GET /health
```
Response: `{ "status": "ok", "version": "0.5.0" }`

## TypeScript SDK

The frontend's `web/lib/api.ts` serves as the TypeScript SDK. Import and use:

```typescript
import { api, swarmApi, marketplaceApi, developerApi } from "@a-cal/sdk";

// Sub-accounts
const subs = await api.listSubAccounts();
await api.createSubAccount({ name: "Work", kind: "calendar" });

// Conductor chat
const result = await api.sendToConductor("Schedule a meeting tomorrow");

// Settings
await api.setLLMEnabled(true);
await api.setModelRouting({ global_provider: "ollama", global_model: "llama3.2", ... });
await api.setApiKeys({ openai: "sk-..." });

// Marketplace
const items = await marketplaceApi.listItems("agent_spec");
await marketplaceApi.install(itemId);

// Developer
await developerApi.exportConfig();
await developerApi.createAgentSpec({ ... });
```

## Error Handling

All endpoints return standard HTTP status codes:
- `200` — success
- `400` — bad request (validation error)
- `404` — not found
- `500` — server error

Error response body:
```json
{ "detail": "Error message" }
```
