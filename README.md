# A-Cal

> The agentic calendar platform that gives users superpowers over their time.
> One identity, many linked accounts, agents that act on your behalf, and
> total control over how it all works — from beginner to developer.

A-Cal is what happens when Calendly, Motion, and a personal AI chief of staff
merge into one self-hostable, fully customizable platform. It unifies multiple
calendar and email accounts under a single identity with a sub-account
hierarchy, puts agents in charge of sync, scheduling, email, negotiation, and
self-awareness, and lets the user control everything — from which model runs
which task to how conflicts between sub-accounts are resolved.

**The differentiator isn't any single feature. It's the combination: unified
identity across providers + agentic control + total customization + community,
all runnable on a local model or any cloud provider you choose.**

---

## Features

### Sub-Account Hierarchy
One A-Cal identity owns many sub-accounts. Each sub-account groups one or more
provider connections (Google Calendar, Outlook, CalDAV, Gmail, IMAP/SMTP).
A "main" sub-account is the composite conductor view; non-main sub-accounts
are the linked provider groupings. Users control sync mode, agent autonomy,
and what flows to the main calendar per sub-account.

### Agent System
A conductor agent routes natural-language requests to 5 specialist agents
(schedule, sync, email, negotiate, self-model), augmented by 10 bio-mimetic
CAS modules (thalamus gate, RAS, basal ganglia, hippocampus, insula, etc.)
organized as a nervous system coordinator. The conductor runs in hybrid mode:
rule-based actions execute real calendar operations, then the LLM (if enabled)
crafts a natural-language response with that context. Works standalone without
any LLM, or with any provider.

### Self-Model
A-Cal learns about the user at a depth they choose (pattern memory, attention/
intent, longitudinal identity). Everything the self-model knows is transparent,
correctable, and deletable. Facts carry provenance, confidence scores, and
privacy tiers. The extractor automatically learns from synced events — busy
times, meeting patterns, energy patterns, relationships, and more.

### Federated Swarm Negotiation
When two sub-accounts conflict over a time slot, their agents negotiate:
probe → propose → accept/reject/concede → resolve/escalate. Priority levels,
alternative slot proposals, and full audit trails. The user can watch
negotiations unfold in real time.

### Model Routing (BYOK)
Run on a local model (Ollama, llama.cpp, LM Studio) or any cloud provider
(OpenAI, Anthropic, Google, Azure, Deepseek, Together, Groq, OpenRouter,
Mistral). Privacy-tiered routing forces email content, self-model reasoning,
and negotiation to always run on local models — enforced structurally, not
toggled in settings.

### Sync Engine — Four Modes
- **Mirror + Filter** (default) — mirror every event, apply include/exclude rules
- **Intelligent Merge** — deduplicate, resolve conflicts, surface most relevant
- **Layered Federation** — each sub stays autonomous; main view is read-only composite
- **Per-Sub-Agent** — each sub gets its own agent; conductor merges outputs

### Skill Modes
- **Simple** — clean calendar + chat bar. Beginners see nothing overwhelming.
- **Pro** — power users get granular sync modes, model routing, marketplace, workflows.
- **Developer** — full API/SDK, plugin system, agent spec editor, config-as-code, visual builder.

Modes are additive and reversible — switching doesn't lose settings.

### Community Marketplace
Browse, search, install, remix, and rate shared configs: agent specs, sync
rule packs, negotiation strategies, UI themes, and plugin configs. Every item
includes provenance metadata so users can audit what a config does before
installing.

### Developer Layer
- Plugin system (register/unregister/enable/disable/configure)
- Plugin runtime (load Python plugins from disk, fire hooks on events/conductor/sync)
- Config-as-code (export/import full config as JSON)
- Agent spec CRUD (create custom agents beyond the 6 built-ins)
- Visual workflow builder (chain agent steps, export/import)
- Full REST API (`/api/a-cal/*`) and TypeScript SDK

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+ with pnpm
- SQLite (included with Python) or PostgreSQL

### Backend

```bash
cd a-cal
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m a_cal.api.standalone
# → serves at http://localhost:8000
```

### Frontend

```bash
cd a-cal/web
pnpm install
pnpm dev
# → serves at http://localhost:3456
```

Open http://localhost:3456 to see the full A-Cal interface.

### Docker

```bash
cd a-cal
cp .env.example .env  # edit with your OAuth credentials
docker compose up --build
# → backend at http://localhost:8000, frontend at http://localhost:3456
```

The `a-cal-data` volume persists the SQLite database across container restarts.

#### PostgreSQL (optional)

```bash
# Start with PostgreSQL instead of SQLite:
docker compose --profile postgres up --build
```

This starts a PostgreSQL 16 container and sets `DATABASE_URL` automatically.
The `a-cal-postgres` volume persists data across restarts. The backend image
includes `psycopg2-binary` and `alembic` for production use.

### Run Tests

```bash
# Backend tests
.venv/bin/python -m pytest tests/ -q

# Frontend typecheck
cd web && npx tsc --noEmit

# Frontend build
cd web && npx next build
```

---

## Architecture

```
a_cal/
  agents/
    conductor.py           # Intent classification + routing + LLM dispatch
    specs.py               # 6 built-in agent specs (conductor + 5 specialists)
    cas_specs.py           # 10 CAS bio-mimetic agent specs
    nervous_system.py      # Nervous system coordinator (signal routing)
    llm_service.py         # LLM service (hybrid mode, any provider)
    email_scheduler.py     # Email-to-schedule detection (invites, conflicts)
    standalone_responses.py  # Standalone LLM response generation
    registry.py            # Agent registry and lookup
  api/
    standalone.py          # FastAPI app entry point (configurable CORS)
    standalone_data.py     # Data/sync routes (sub-accounts, events, email)
    agent_routes.py        # Conductor, settings, self-model, nervous system
    developer_routes.py    # Plugin runtime, agent specs, config export/import
    marketplace_routes.py  # Marketplace browse/search/install/remix
    swarm_routes.py        # Swarm negotiation endpoints
    oauth_routes.py        # OAuth start/callback flows
  db/
    store.py               # SQLite persistent store (settings, model routing)
    models.py              # SQLAlchemy models (SubAccount, Provider, SyncRule)
  providers/
    base.py                # Provider ABC
    google_provider.py     # Google Calendar (via OAuth)
    outlook_provider.py    # Outlook (via OAuth)
    caldav_provider.py     # Any CalDAV server (Radicale, Nextcloud, ...)
    gmail_provider.py      # Gmail (via OAuth)
    factory.py             # Provider factory
    oauth.py               # OAuth flow helpers
  email/
    imap_smtp_provider.py  # Any email provider via stdlib IMAP/SMTP
  self_model/
    model.py               # Self-model logic and fact management
    extractor.py           # Auto-learning from synced events
    store.py               # JSON file-based fact storage
    types.py               # Fact categories, depth tiers, privacy levels
    settings.py            # Self-model depth and category settings
  marketplace/
    store.py               # In-memory marketplace store
    persistent_store.py    # SQLAlchemy-backed marketplace store
    types.py               # MarketplaceItem, Provenance, InstallRecord
  developer/
    plugins.py             # Plugin system (PluginBase + PluginRegistry)
    plugin_runtime.py      # Plugin runtime (load from disk, fire hooks, reload)
    config_io.py           # Config export/import with schema versioning
    agent_crud.py          # Custom agent spec CRUD
  settings/
    modes.py               # Simple/Pro/Developer skill mode configs
    model_routing.py       # Model routing config (12 providers, privacy tiers)
  sync/
    engine.py              # Four-mode sync engine
    rules.py               # Sync rule evaluation
  integrations/
    atom_bridge.py         # Runtime atom detection + adapter bridge
  swarm/
    coordinator.py         # Swarm negotiation loop
    protocol.py            # Message types, states, priority system

web/
  app/
    page.tsx               # Main page (loads all panels)
    layout.tsx             # Root layout
  components/
    calendar-view.tsx      # Unified calendar timeline
    conductor-panel.tsx    # Chat interface for talking to agents
    settings-panel.tsx     # Model routing, self-model, connections, privacy
    sub-account-sidebar.tsx   # Sub-account management
    add-account-wizard.tsx    # Sub-account creation wizard
    email-panel.tsx        # Inbox, compose, invite detection, schedule scan
    marketplace-panel.tsx  # Browse, search, install, remix
    developer-panel.tsx    # Plugins, agent specs, config, runtime plugins
    workflow-builder.tsx   # Visual workflow composition
    swarm-panel.tsx        # Negotiation history and audit trail
    nervous-system-panel.tsx  # CAS module overview and signal routing
    ui/                    # Shared UI primitives (badge, button, input, select, switch)
  lib/
    api.ts                 # Full API client (all backend endpoints)
    mock-data.ts           # Fallback mock data for offline frontend
    utils.ts               # Shared utilities
  types/
    index.ts               # TypeScript types mirroring Python models

sdk/
  index.ts                 # Full TypeScript SDK (60+ endpoints)
  package.json             # SDK package metadata

plugins/
  examples/                # 5 example plugins (event_tagger, conflict_notifier,
                           #   response_enhancer, custom_agent, sync_rules_pack)
  README.md                # Plugin development guide with hook reference
```

---

## How It Works

1. **Connect your accounts.** Type "connect my work Google and personal Outlook"
   in the conductor chat. A-Cal creates sub-accounts, links the providers, and
   mirrors events onto the main calendar.

2. **Talk to your agents.** "Schedule a 30-minute meeting with Sarah tomorrow
   afternoon." "What events do I have today?" "Find a free slot next week."
   The conductor routes to the right specialist and makes real changes.

3. **Control your privacy.** Email content, self-model reasoning, and
   negotiation always run on local models. Calendar sync and scheduling can
   use cloud models if you choose. See exactly what the self-model knows and
   correct or delete any fact.

4. **Customize everything.** Switch to Pro mode for granular sync modes and
   model routing. Switch to Developer mode for the full API, plugin system,
   and visual workflow builder. Share your configs on the marketplace.

5. **Run it anywhere.** Local model via Ollama for complete privacy, or any
   cloud provider with your own API key. Self-host on your own server or run
   on atom's managed infrastructure.

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `A_CAL_BASE_URL` | `http://localhost:8000` | Backend URL (for OAuth callbacks) |
| `A_CAL_FRONTEND_URL` | `http://localhost:3456` | Frontend URL (for OAuth redirects) |
| `A_CAL_CORS_ORIGINS` | localhost dev origins | Comma-separated allowed CORS origins (set to your real frontend origin for production) |
| `A_CAL_PLUGIN_DIR` | `~/.a-cal/plugins` | Directory for plugin Python files |
| `A_CAL_SESSION_SECRET` | dev secret (insecure) | **Required for production** — the server refuses to boot with the public dev default. Generate with `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `A_CAL_ALLOW_INSECURE_DEV_SECRET` | unset | Set to `1` to opt in to the dev secret (tests/local dev only; never in production) |
| `A_CAL_ENABLE_DEMO` | unset (off) | Set to `1` to mount the demo-login route (known-credential backdoor; local dev only) |
| `A_CAL_REGISTER_MAX_PER_IP` | `10` | Per-IP signup cap per `A_CAL_REGISTER_WINDOW_HOURS`; `0` or negative disables it |
| `A_CAL_REGISTER_WINDOW_HOURS` | `1` | Rolling window for the per-IP registration cap |
| `A_CAL_ENABLE_PLUGINS` | unset (off) | Set to `1` to enable the in-process plugin runtime (self-host, single-operator only) |
| `A_CAL_GOOGLE_CLIENT_ID` | — | Google OAuth client ID |
| `A_CAL_GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |
| `A_CAL_MS_CLIENT_ID` | — | Microsoft OAuth client ID |
| `A_CAL_MS_CLIENT_SECRET` | — | Microsoft OAuth client secret |
| `DATABASE_URL` | SQLite local | PostgreSQL URL for multi-user deployment |

### OAuth Setup
1. Register an app in [Google Cloud Console](https://console.cloud.google.com/)
   and/or [Azure Portal](https://portal.azure.com/)
2. Set the redirect URI to `{A_CAL_BASE_URL}/api/a-cal/providers/{id}/oauth/callback`
3. Set the client ID and secret via environment variables or in Developer mode
4. Click "Authorize" next to each provider in Settings → Connections

### Local Model Setup
1. Install [Ollama](https://ollama.ai)
2. Pull a model: `ollama pull llama3.2`
3. In A-Cal Settings → Model Routing, select Ollama as the provider
4. Toggle "Enable AI responses" to activate real LLM-powered agent responses

### Plugin Development
> Plugins run arbitrary Python code in-process. The runtime is gated behind
> `A_CAL_ENABLE_PLUGINS=1` (default off) for multi-tenant safety. Set this
> flag only in self-hosted, single-operator deployments.

1. Create a `.py` file in `~/.a-cal/plugins/` (or your `A_CAL_PLUGIN_DIR`)
2. Define a `Plugin` class with at least one supported hook:
   - `on_event_created`, `on_event_updated`, `on_event_deleted`
   - `on_sync_complete`, `on_intent_classified`, `on_conductor_response`
3. See `plugins/examples/` for working examples and `plugins/README.md` for
   the full hook reference

---

## Optional Dependencies

- `caldav` + `icalendar` — for CalDAV provider support (`pip install a-cal[caldav]`)
- `postgres` — for PostgreSQL backend (`pip install a-cal[postgres]`, includes `psycopg2-binary`)
- `migrations` — for Alembic database migrations (`pip install a-cal[migrations]`)
- `httpx` — for OAuth token exchange and HTTP-based provider calls
- `ollama` — for local model serving (install separately via [ollama.ai](https://ollama.ai))

---

## Project Status

854 passing tests (Python), 83 E2E tests (Playwright). 77 Python source files
(18.6k+ lines), 52 TypeScript/TSX files (13.1k+ lines). Frontend build passes,
TypeScript typecheck clean. Standalone server runs all 127 endpoints without
atom. PostgreSQL production support via `DATABASE_URL` with native JSONB,
Alembic migrations, and Docker Compose `--profile postgres`. Conductor routes
natural language across all 5 intents with real calendar operations. Self-model
extractor learns from synced events. Federated swarm negotiation resolves
sub-account conflicts with full audit trails. IMAP/SMTP email provider for any
email server. Docker self-hosting via `docker compose up`. 5 example plugins
with full hook coverage. SDK covers all 127 REST endpoints.

### Security

Before exposing A-Cal to real users:

1. **Set `A_CAL_SESSION_SECRET`** — the built-in dev secret allows session
   cookie forgery. Generate one with
   `python -c "import secrets;print(secrets.token_urlsafe(48))"` and set it
   in your `.env` or environment.
2. **Leave `A_CAL_ENABLE_PLUGINS` unset** unless you are the sole operator.
   Plugins run arbitrary Python in the server process — never enable them on
   a shared multi-tenant deployment.
3. **Use HTTPS** behind a reverse proxy in production.

### Remaining for production
- Real OAuth credentials (Google/Outlook client ID + secret)
- LLM API keys for cloud model routing (or use local Ollama)
- Community marketplace hosted registry (local file-based registry is ready)
- SDK npm publishing (npm org/account needed)

See `outputs/A-Cal_end_goal.md` in the workspace root for the full product
charter and design decisions.

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).

## Additional Documentation

- [Contributing Guide](CONTRIBUTING.md) — setup, code standards, git workflow, plugin development
- [Developer Guide](docs/DEVELOPER_GUIDE.md) — API, SDK, plugins, workflows, agent specs, marketplace
- [API Reference](docs/API_REFERENCE.md) — full REST endpoint documentation
- [SDK README](sdk/README.md) — TypeScript SDK usage and API surface
- [Plugin Examples](plugins/README.md) — hook reference and working plugin examples
- [Product Charter](outputs/A-Cal_end_goal.md) — full design vision and architectural decisions
