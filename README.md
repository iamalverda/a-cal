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
organized as a nervous system coordinator. Users talk to the conductor in
plain language; the conductor dispatches to specialists and makes real changes.

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
- Config-as-code (export/import full config as JSON)
- Agent spec CRUD (create custom agents beyond the 6 built-ins)
- Visual workflow builder (chain agent steps, export/import)
- Full REST API (`/api/a-cal/*`)

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
    conductor.py          # Intent classification + routing + LLM dispatch
    specs.py              # 6 built-in agent specs (conductor + 5 specialists)
    cas_specs.py          # 10 CAS bio-mimetic agent specs
    nervous_system.py     # Nervous system coordinator (signal routing)
    standalone_responses.py  # Rule-based responses without an LLM
    llm_service.py        # Standalone LLM service (Ollama, OpenAI, etc.)
    registry.py           # Agent registry
  api/
    standalone.py         # FastAPI app mounting all routers
    agent_routes.py       # Conductor chat, settings, self-model facts
    standalone_data.py    # Sub-accounts, providers, sync, calendar view
    oauth_routes.py       # OAuth start/callback for Google/Outlook/Gmail
    swarm_routes.py       # Federated swarm negotiation endpoints
    marketplace_routes.py # Marketplace browse/install/remix/rate
    developer_routes.py   # Plugins, agent CRUD, config export/import
    routes.py             # Production routes (with atom's database)
  db/
    store.py              # SQLite-backed persistent store (all entities)
    models.py             # SQLAlchemy models
  self_model/
    types.py              # Depth hierarchy, fact categories, privacy tiers
    store.py              # JSON-based fact storage (LanceDB in full deployment)
    extractor.py          # Depth-gated fact extraction from events/emails
    model.py              # SelfModel — context injection, enrichment, export
    settings.py           # User-controlled settings (depth, toggles, privacy)
  sync/
    engine.py             # Four sync modes
    rules.py              # Include/exclude/transform rule evaluation
  providers/
    base.py               # CalendarProvider/EmailProvider ABCs + DTOs
    factory.py            # Build a live provider from a connection
    google_provider.py    # Google Calendar (via OAuth)
    outlook_provider.py   # Microsoft Outlook (via OAuth)
    caldav_provider.py    # Any CalDAV server (Radicale, Nextcloud, ...)
    gmail_provider.py     # Gmail (via OAuth)
    oauth.py              # OAuth flow helpers
  email/
    imap_smtp_provider.py # Any email provider via stdlib IMAP/SMTP
  marketplace/
    store.py              # In-memory marketplace store
    types.py              # MarketplaceItem, Provenance, InstallRecord
  developer/
    plugins.py            # Plugin system (PluginBase + PluginRegistry)
    config_io.py          # Config export/import with schema versioning
    agent_crud.py         # Custom agent spec CRUD
  settings/
    modes.py              # Simple/Pro/Developer skill mode configs
    model_routing.py      # Model routing config (12 providers)
  integrations/
    atom_bridge.py        # Runtime atom detection + adapter bridge
  swarm/
    coordinator.py        # Swarm negotiation loop
    protocol.py           # Message types, states, priority system

web/
  app/page.tsx            # Main page (loads all panels)
  components/
    calendar-view.tsx     # Unified calendar timeline
    conductor-panel.tsx   # Chat interface for talking to agents
    settings-panel.tsx    # Model routing, self-model, connections, privacy
    sub-account-sidebar.tsx  # Sub-account management
    email-panel.tsx       # Inbox, compose, invite detection
    marketplace-panel.tsx # Browse, search, install, remix
    developer-panel.tsx   # Plugins, agent specs, config export/import
    workflow-builder.tsx  # Visual workflow composition
    swarm-panel.tsx       # Negotiation history and audit trail
    nervous-system-panel.tsx  # CAS module overview and signal routing
  lib/api.ts              # Full API client (all backend endpoints)
  types/index.ts          # TypeScript types mirroring Python models
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

---

## Optional Dependencies

- `caldav` + `icalendar` — for CalDAV provider support (`pip install a-cal[caldav]`)
- `httpx` — for OAuth token exchange and HTTP-based provider calls
- `ollama` — for local model serving (install separately via [ollama.ai](https://ollama.ai))

---

## Project Status

413 passing tests. 57 Python files, 21 TypeScript files. Frontend build
passes (152 kB first load). Standalone server runs all endpoints without atom.
Conductor routes natural language across all 5 intents with real calendar
operations. Self-model extractor learns from synced events. Natural-language
account creation works end-to-end.

See `outputs/A-Cal_end_goal.md` in the workspace root for the full product
charter and design decisions.

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).
