# Handoff for Claude Code — A-Cal Second-Eyes Review

> Written by Codex on 2026-07-13.
> Purpose: hand off the A-Cal project for an independent review pass.
> You are asked to act as a second set of eyes, not to start over.

---

## What This Project Is

A-Cal is an agentic, self-hostable calendar + email platform. The elevator
pitch: Calendly + Motion + a personal AI chief of staff, merged into one
customizable platform that unifies fragmented calendar/email accounts under a
single identity and puts agents in charge of sync, scheduling, email,
negotiation, and self-awareness.

The full product charter lives at [outputs/A-Cal_end_goal.md](../outputs/A-Cal_end_goal.md)
(workspace root) and the integration architecture at
[outputs/A-Cal_integration_architecture.md](../outputs/A-Cal_integration_architecture.md).
Read those for the design vision and the 9 brainstorming decisions that shaped
the architecture. The [README.md](README.md) in this directory is the canonical
feature/architecture summary and is kept up to date with test counts.

The workspace root (`/Users/christophervaughn/Documents/A-Cal`) also contains
several reference projects that were studied and partially integrated: `atom`
(intent classification + model serving + encrypted storage, now actively
bridged), `cal.com`, `zero-calendar`, `khal`, `Etar-Calendar`, `Radicale`,
`rencal`, `weektodo`, `someday`, and `calendar`. Only `a-cal/` is the product;
the others are reference material or integration targets.

---

## Current State at a Glance

- **Repository:** `a-cal/` is a git repo (this directory). The workspace root
  is **not** a git repo.
- **Branch:** `feat/unified-email-inbox` (6 commits ahead of `main`). All
  recent phase work lives here and has not been merged or pushed.
- **main** sits at `21f3f8d docs: add unreleased changelog entry for trust &
  moderation system`.
- **HEAD** sits at `cef4789 feat: team & payments + developer platform
  (Phase 5 & 6)`.
- **Working tree:** clean. Nothing uncommitted.
- **Backend:** Python 3.11+, FastAPI, SQLAlchemy, SQLite (default) or
  PostgreSQL. ~77 source files, ~18.6k lines.
- **Frontend:** Next.js 15 + React 19 + Tailwind 4 + lucide-react +
  framer-motion. 23 panel components, ~13.1k lines of TS/TSX.
- **SDK:** TypeScript SDK at `sdk/index.ts` covering the REST API.
- **Tests:** ~953 Python pytest tests passing (per commit message), 20 E2E
  Playwright specs. Commit messages report "typecheck clean, build clean."
- **Docker:** `docker compose up --build` runs backend + frontend; `--profile
  postgres` adds PostgreSQL 16.
- **Version:** 0.7.0 (in `pyproject.toml`).

### Run it

Backend:
```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m a_cal.api.standalone   # http://localhost:8000
```

Frontend:
```bash
cd web && pnpm install && pnpm dev          # http://localhost:3456
```

Tests:
```bash
.venv/bin/python -m pytest tests/ -q       # backend
cd web && npx tsc --noEmit                 # typecheck
cd web && npx next build                   # build
cd web && npx playwright test              # E2E
```

---

## What Has Been Done So Far (by Phase)

The commit history tells the story. Everything below is already implemented and
committed on `feat/unified-email-inbox`.

### Foundation (pre-phase, on main)
- Conductor + 5 specialist agents + 10 bio-mimetic CAS modules wired through a
  Nervous System Coordinator (`a_cal/agents/`).
- Sub-account hierarchy with 4 sync modes (mirror+filter default, intelligent
  merge, layered federation, per-sub-agent) — `a_cal/sync/engine.py`.
- Model routing (BYOK) across 12 providers with privacy-tiered forcing
  (email/self-model/negotiation always local) — `a_cal/settings/model_routing.py`.
- Self-model with depth tiers, auto-extraction from synced events, fact CRUD
  — `a_cal/self_model/`.
- Federated swarm negotiation with audit trails — `a_cal/swarm/`.
- User authentication (session-based, PBKDF2), multi-user data isolation.
- Marketplace (browse/search/install/remix/rate, trust & moderation, content
  hashing, flagging, verification) — `a_cal/marketplace/`.
- Developer Studio: plugin system + runtime, agent spec CRUD, config
  export/import, visual workflow builder, API Explorer, GraphQL.
- Three skill modes (Simple / Pro / Developer) with progressive disclosure.
- PWA support, mobile responsive layout, voice input (Web Speech API),
  contextual command bar (Cmd+K), proactive suggestions.
- atom integration bridge (auto-detect, encrypted token storage, LLM service,
  intent classifier) — `a_cal/integrations/atom_bridge.py`.
- CalDAV provider (tested against Radicale), IMAP/SMTP email provider (stdlib).
- Calendar analytics, Docker self-hosting, CI/CD (GitHub Actions), ruff lint.
- Marketplace trust & moderation system (content hashing, trust scoring,
  flagging, verification, frontend badges).

### Phase 1 & 2 — `23d84ef`
- Email attachments + scheduling/booking system.
- Booking routes, event type creation, scheduling flow.

### Phase 3 & 4 — `371ba9b`
- Calendar improvements: all-day events, recurrence rules, attendees with
  status badges, event color coding, inline edit/delete, NewEventModal with
  all-day toggle + recurrence dropdown + color picker + attendees input.
  Schema upgrade handles the new columns on existing databases.
- Advanced email: labels, filters, snooze, scheduled send, templates, vacation
  responder, AI summarization (LLM with extractive fallback). Frontend gets
  labels sidebar, snooze presets, AI summarize button, template picker,
  scheduled send picker, snoozed folder, email settings modal, keyboard
  shortcuts (j/k/s/e/r/c).

### Phase 5 & 6 — `cef4789` (HEAD)
- Team & Payments: team CRUD + member management, round-robin assignment,
  collective scheduling, routing forms (cal.com-style), webhooks with
  HMAC-SHA256 signed delivery + history, Stripe payment integration
  (PaymentService with mock fallback), paid event types, payment intent
  create/confirm, paid booking flow returns pending_payment, workflow trigger
  config, booking lifecycle webhook dispatch.
- Developer & Platform: GraphQL read-only query API with field projection +
  aliases, schema introspection, public booking page embed routes (iframe +
  popup + text link), custom domain config endpoint, PWA manifest.
- Frontend: TeamsPanel (tabbed: teams/routing forms/webhooks/payments/triggers),
  PlatformPanel (custom domain, embed snippet generator, GraphQL explorer),
  GraphQLExplorer (interactive query runner + schema display). 39 new tests.

### Recent standalone-provider work (also on this branch)
- `09bc6fd` standalone Google Calendar + Gmail providers with direct API calls.
- `6fdaeb8` unified multi-account email inbox with Gmail-class features.
- `d1c4bc7` auto-load `.env` on startup + fix OAuth env var names.

---

## What Remains / Known Gaps

These are called out in the README and charter, not hidden:

1. **Real OAuth credentials.** The OAuth flow code is complete (start, callback,
   token exchange, state validation in `a_cal/providers/oauth_routes.py`), but
   it requires user-provided Google/Microsoft client ID + secret (env vars in
   `.env`). No live provider has been tested end-to-end with real credentials.
2. **LLM API keys for cloud routing.** Local Ollama works; cloud providers need
   user API keys. Privacy-tiered routing is enforced structurally.
3. **Marketplace hosted registry.** Local file-based registry is ready; a
   hosted/remote registry is not deployed.
4. **SDK npm publishing.** The SDK is complete but not published (needs an npm
   org/account).
5. **Merge to main.** The 6 phase commits on `feat/unified-email-inbox` have not
   been merged or pushed. There are also several stale feature branches
   (`feat/ci-cd-and-linting`, `feat/docs-and-e2e-tests`,
   `feat/marketplace-trust-system`, etc.) that appear to already be merged into
   the current branch's history — worth confirming before cleanup.

---

## Architecture Map (where things live)

```
a_cal/
  agents/        conductor, 5 specialist specs, 10 CAS modules, nervous system,
                  LLM service, email scheduler, standalone responses, registry
  api/           standalone.py (FastAPI entry), routes split by domain:
                  standalone_data, agent_routes, booking_routes, developer_routes,
                  marketplace_routes, swarm_routes, oauth_routes, analytics_routes,
                  graphql_routes, team_routes
  auth/          session-based auth (PBKDF2)
  db/            models.py (SQLAlchemy), store.py (SQLite/PG), schema_upgrade.py
  developer/     plugins, plugin_runtime, config_io, agent_crud
  email/         imap_smtp_provider (stdlib, any provider)
  integrations/  atom_bridge, calcom_bridge, zero_calendar_bridge, payments,
                  webhooks, mount
  marketplace/   store, persistent_store, registry, trust, types
  providers/     base (ABC), google, outlook, caldav, gmail, imap_smtp, factory,
                  oauth, oauth_api
  self_model/    model, extractor, store, types, settings
  settings/      modes, model_routing, autonomy, email
  swarm/         coordinator, protocol
  sync/          engine (4 modes), rules
  workflows/     models, runner, store
alembic/         3 migration versions (sub_accounts, additional_tables, user_id)
web/             Next.js app, 23 components, lib/api.ts (full client), types/
sdk/             TypeScript SDK
plugins/examples/ 8 example plugins across 8 hooks
docs/            API_REFERENCE, DEVELOPER_GUIDE, FEATURE_AUDIT (cal.com/Gmail/Calendly gap analysis)
tests/           ~51 Python test files, conftest.py
```

---

## What I'm Asking You (Claude Code) to Do

Be my second set of eyes. Specifically:

1. **Read the charter** at `../outputs/A-Cal_end_goal.md` and the integration
   architecture at `../outputs/A-Cal_integration_architecture.md` to
   understand the goal and the 9 design decisions. Read the `README.md` and
   `docs/FEATURE_AUDIT.md` for the current feature inventory and gap analysis
   against Calendly/Gmail/cal.com.

2. **Audit the code on `feat/unified-email-inbox`** for correctness and
   consistency. Pay attention to:
   - The Phase 5 & 6 work (the most recent, largest commit) — team routes,
     payments, webhooks, GraphQL, embed routes. Check for schema/DB drift,
     store/query correctness, and whether the schema upgrade path handles
     existing databases.
   - The Phase 3 & 4 work — new CalendarEvent columns and the email label/
     filter/snooze/scheduled-send/template/vacation models.
   - Provider correctness: the standalone Google/Gmail providers and the
     IMAP/SMTP provider. OAuth flow integrity and secret handling.
   - Privacy-tiered model routing: confirm email/self-model/negotiation are
     structurally forced to local and cannot be bypassed via settings.
   - Multi-user isolation: confirm `user_id` filtering is consistently applied
     across all store queries (the README claims this).

3. **Run the tests** to verify the "953 passing" claim and that the frontend
   typecheck + build are actually clean:
   ```bash
   .venv/bin/python -m pytest tests/ -q
   cd web && npx tsc --noEmit && npx next build
   ```
   Report any failures with file/line references.

4. **Flag risks**, ordered by severity: bugs, behavioral regressions, security
   issues (especially around secrets/OAuth/session handling), missing tests,
   and anything that diverges from the charter's design principles
   (beginner-safe/privacy-structural/user-owns-self-model).

5. **Note anything that looks unfinished or inconsistent** between the
   README's claims and the actual code — e.g., endpoints that exist but aren't
   wired into the frontend, or frontend components calling endpoints that
   don't exist.

Do not reformat, refactor, or merge anything. This is a review pass. If you
find issues, list them with file/line references and severity. If you want to
fix something, ask first.

---

## Conventions to Respect

- Use `pnpm` for frontend package management; `pip`/`pyproject.toml` for backend.
- Run `pnpm test` (E2E) and `pytest` after any TypeScript/Python change.
- Conventional Commits for all git operations. Never push to `main` directly.
- No `any` types in TypeScript — use `unknown` and narrow. JSDoc on new
  functions. No secrets in code or logs. Never `rm -rf`.
- Keep changes scoped to `a_cal/`, `web/`, `sdk/`, `tests/`, `docs/`,
  `plugins/`, `alembic/` within this directory. Do not modify the sibling
  reference projects unless explicitly asked.

---

## Quick File Pointers

- Product charter + design decisions: `../outputs/A-Cal_end_goal.md`
- Integration topology: `../outputs/A-Cal_integration_architecture.md`
- Feature gap analysis vs Calendly/Gmail/cal.com: `docs/FEATURE_AUDIT.md`
- API reference (all endpoints): `docs/API_REFERENCE.md`
- Developer guide (plugins, SDK, workflows, marketplace): `docs/DEVELOPER_GUIDE.md`
- Backend entry point: `a_cal/api/standalone.py`
- Conductor (the brain): `a_cal/agents/conductor.py`
- Nervous system (CAS routing): `a_cal/agents/nervous_system.py`
- DB models: `a_cal/db/models.py` — store: `a_cal/db/store.py`
- Frontend API client: `web/lib/api.ts` — types: `web/types/index.ts`
- Main page (loads all panels): `web/app/page.tsx`
- Environment template: `.env.example`
