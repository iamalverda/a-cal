# A-Cal REST API Reference

Base URL: `http://localhost:8000/api/a-cal`

All endpoints accept and return JSON. Authentication is via Bearer token
(if running with atom's auth layer) or unauthenticated (standalone mode).

---

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

---

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

### List Providers (by sub-account)
```
GET /providers?sub_account_id={id}
```
Response: `ProviderConnection[]`

### List All Providers
```
GET /providers/all
```
Response: `ProviderConnection[]`

### Update Provider Status
```
PATCH /providers/{provider_id}
```
Body:
```json
{ "status": "connected" }
```
Response: `ProviderConnection`

### Delete Provider
```
DELETE /providers/{provider_id}
```

---

## OAuth

### Start OAuth Flow
```
GET /providers/{provider_id}/oauth/start
```
Response:
```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/auth?...",
  "provider_id": "uuid",
  "provider_type": "google_calendar",
  "redirect_uri": "http://localhost:8000/api/a-cal/providers/{id}/oauth/callback"
}
```

### OAuth Callback
```
GET /providers/{provider_id}/oauth/callback?code={auth_code}&state={state}
```
Exchanges the authorization code for tokens, stores them, and redirects to
the frontend. Requires `A_CAL_GOOGLE_CLIENT_ID` / `A_CAL_MS_CLIENT_ID` and
matching secrets in environment variables.

---

## Unified Calendar

### Get Unified Calendar
```
GET /calendar/unified?days=7
```
Returns events from all sub-accounts, merged per sync rules.
Response: `UnifiedEvent[]`

### List Events
```
GET /calendar/events?days=30
```
Returns all events within the given time window (1–365 days).
Response: `UnifiedEvent[]`

### Create Event
```
POST /calendar/events
```
Body:
```json
{
  "title": "Team Standup",
  "start": "2026-07-13T09:00:00Z",
  "end": "2026-07-13T09:30:00Z",
  "description": "Weekly sync",
  "location": "Zoom",
  "source_sub_account_id": "uuid",
  "metadata": {}
}
```
Response: `UnifiedEvent`

### Update Event
```
PATCH /calendar/events/{event_id}
```
Body: partial event fields (`title`, `start`, `end`, `description`,
`location`, `metadata`)

Response: `UnifiedEvent`

### Delete Event
```
DELETE /calendar/events/{event_id}
```

---

## Sync

### Trigger Sync
```
POST /sync/trigger
```
Body:
```json
{ "sub_account_id": "uuid" }
```
Pulls events from connected providers via the sync engine. Fires
`on_sync_complete` plugin hook after completion.

Response:
```json
{
  "status": "ok",
  "synced": 12,
  "sub_account_id": "uuid"
}
```

### Sync Rules

#### Create Sync Rule
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

#### List Sync Rules
```
GET /sync-rules?sub_account_id={id}
```

---

## Email

### List Email Messages
```
GET /email/messages?sub_account_id={id}&limit=50
```
Fetches messages from connected email providers (IMAP/SMTP or Gmail).
Detects calendar invites automatically.

Response: `EmailMessage[]`
```json
[
  {
    "provider_message_id": "abc123",
    "provider_type": "imap_smtp",
    "provider_connection_id": "uuid",
    "subject": "Meeting tomorrow?",
    "from_address": "sarah@example.com",
    "to_addresses": ["me@example.com"],
    "received_at": "2026-07-12T10:00:00Z",
    "snippet": "Can we push to 3pm instead...",
    "has_calendar_invite": false,
    "labels": ["INBOX"]
  }
]
```

### Send Email
```
POST /email/send
```
Body:
```json
{
  "provider_connection_id": "uuid",
  "to": ["sarah@example.com"],
  "subject": "Re: Meeting tomorrow?",
  "body": "3pm works for me."
}
```

### Scan Emails for Schedule
```
POST /email/scan-schedule
```
Runs the email-to-schedule pipeline: reads recent emails, detects meeting
proposals and invites, extracts proposed times, cross-references with the
user's calendar to find conflicts, and returns actionable suggestions.

Privacy: email content is processed locally. LLM analysis (if enabled) uses
privacy-tiered routing to force email processing to local models.

Response:
```json
{
  "suggestions": [
    {
      "type": "create_event",
      "email_id": "abc123",
      "proposed_time": "2026-07-13T15:00:00Z",
      "title": "Meeting with Sarah",
      "conflicts": []
    },
    {
      "type": "conflict_warning",
      "email_id": "def456",
      "proposed_time": "2026-07-14T10:00:00Z",
      "conflicts": [{ "title": "Standup", "start": "..." }]
    }
  ],
  "detection": {
    "meeting_proposals": 3,
    "invites": 1,
    "reschedule_requests": 1
  }
}
```

---

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

---

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

---

## Self-Model Facts

### List Facts
```
GET /self-model/facts?category={category}
```
Returns all active facts, sorted by confidence (highest first). Optional
category filter.

### Search Facts
```
GET /self-model/facts/search?q={query}&limit=10
```
Full-text search across fact content.

### Edit Fact
```
PATCH /self-model/facts/{fact_id}
```
Body: `{ "content": "Corrected fact text" }`

User corrections update the fact content and reset confidence tracking.

### Delete Fact
```
DELETE /self-model/facts/{fact_id}
```

### Clear All Facts
```
DELETE /self-model/facts
```

### Export Facts
```
GET /self-model/export
```
Returns all facts as a downloadable JSON document.

---

## Nervous System (CAS)

### Overview
```
GET /nervous-system/overview
```
Complete snapshot: activation states, gate states, autonomic mode, CAS
agent list, and recent episodic memories.

### State
```
GET /nervous-system/state
```
Current nervous system activation and gate states.

### Agents
```
GET /nervous-system/agents
```
List of A-Cal specialist agents with their CAS augmentation mappings.

### CAS Agents
```
GET /nervous-system/cas-agents
```
List of 10 bio-mimetic CAS agent specs (thalamus gate, prefrontal cortex,
hippocampus, RAS, autonomic system, insula, cerebellum, basal ganglia,
claustrum, limbic bridge, vagal tone).

### Memories
```
GET /nervous-system/memories?limit=10
```
Recent episodic memories encoded by the nervous system.

### Route Signal
```
POST /nervous-system/route
```
Body: `{ "signal": "schedule_request" }`

Routes a signal through: thalamus gate → RAS → basal ganglia → conductor →
CAS modules → hippocampus.

### Assess User State
```
POST /nervous-system/assess-user-state
```
Body: `{ "events": [...] }`

Assesses the user's cognitive state from their calendar events.

### Verify Binding
```
POST /nervous-system/verify-binding
```
Body: `{ "events": [...], "sub_accounts": [...] }`

Verifies calendar binding between sub-accounts and events.

---

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
GET /swarm/negotiations/{negotiation_id}
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

---

## Marketplace

### List Items
```
GET /marketplace/items?item_type=agent_spec&tag=productivity
```

### Get Item
```
GET /marketplace/items/{item_id}
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
POST /marketplace/items/{item_id}/install
```

### List Installs
```
GET /marketplace/installs
```

### Remix Item
```
POST /marketplace/items/{item_id}/remix
```

### Get Remixes
```
GET /marketplace/items/{item_id}/remixes
```

### Get Remix Chain
```
GET /marketplace/items/{item_id}/remix-chain
```

### Rate Item
```
POST /marketplace/items/{item_id}/rate
```
Body: `{ "stars": 1-5 }`

---

## Developer

### Plugin Registry

```
GET /developer/plugins?plugin_type=agent&enabled_only=false
POST /developer/plugins
DELETE /developer/plugins/{plugin_id}
POST /developer/plugins/{plugin_id}/enable
POST /developer/plugins/{plugin_id}/disable
PATCH /developer/plugins/{plugin_id}/config
```

### Plugin Runtime

Manages Python plugins loaded from disk (`~/.a-cal/plugins/` or
`A_CAL_PLUGIN_DIR`). Runtime plugins fire hooks on events, conductor
responses, and sync operations.

#### List Runtime Plugins
```
GET /developer/plugins/runtime/list
```
Returns loaded plugins with hook badges, load errors, and enable/disable
status.

#### List Supported Hooks
```
GET /developer/plugins/runtime/hooks
```

#### Scan for Plugins
```
POST /developer/plugins/runtime/scan
```
Scans the plugin directory and loads any new `.py` files.

#### Reload Plugin
```
POST /developer/plugins/runtime/{plugin_id}/reload
```
Reloads a plugin from disk (bypasses stale bytecode cache).

#### Enable/Disable Runtime Plugin
```
POST /developer/plugins/runtime/{plugin_id}/enable
POST /developer/plugins/runtime/{plugin_id}/disable
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

---

## Health
```
GET /health
```
Response:
```json
{
  "status": "ok",
  "mode": "standalone",
  "version": "0.7.0",
  "database": "sqlite"
}
```

The `database` field reports the active backend: `sqlite` (default) or
`postgresql` (when `DATABASE_URL` is set). Use this to verify your
PostgreSQL configuration is active.

---

## TypeScript SDK

The SDK (`sdk/index.ts`) covers all 60+ REST endpoints. Import and use:

```typescript
import { api, swarmApi, marketplaceApi, developerApi } from "@a-cal/sdk";

// Sub-accounts
const subs = await api.listSubAccounts();
await api.createSubAccount({ name: "Work", kind: "calendar" });

// Calendar events
await api.createEvent({ title: "Standup", start: "...", end: "..." });
await api.updateEvent(eventId, { title: "Renamed" });
await api.deleteEvent(eventId);

// Sync
await api.triggerSync(subAccountId);

// Email
const messages = await api.listEmailMessages(subAccountId);
await api.sendEmail({ providerConnectionId, to, subject, body });
const suggestions = await api.scanEmailsForSchedule();

// Conductor chat
const result = await api.sendToConductor("Schedule a meeting tomorrow");

// Settings
await api.setLLMEnabled(true);
await api.setModelRouting({ global_provider: "ollama", global_model: "llama3.2" });
await api.setApiKeys({ openai: "sk-..." });

// Self-model facts
const facts = await api.listSelfModelFacts();
await api.editSelfModelFact(factId, { content: "Corrected" });
await api.exportSelfModel();

// Nervous system
const overview = await api.getNervousSystemOverview();
await api.routeNervousSystemSignal({ signal: "schedule_request" });

// OAuth
const oauth = await api.startOAuth(providerId);

// Marketplace
const items = await marketplaceApi.listItems("agent_spec");
await marketplaceApi.install(itemId);

// Developer
await developerApi.exportConfig();
await developerApi.createAgentSpec({ ... });
await developerApi.listRuntimePlugins();
await developerApi.reloadRuntimePlugin(pluginId);
```

---

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
