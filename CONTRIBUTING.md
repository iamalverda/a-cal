# Contributing to A-Cal

A-Cal is built to be customized. Whether you're fixing a bug, adding a feature,
building a plugin, or sharing a config pack, this guide will get you started.

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+ with pnpm
- SQLite (default) or PostgreSQL (optional)
- [Ollama](https://ollama.ai) for local LLM testing (optional)

### Clone and install

```bash
git clone <repo-url> a-cal
cd a-cal
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd web && pnpm install && cd ..
```

### Run the backend

```bash
.venv/bin/python -m a_cal.api.standalone
# serves at http://localhost:8000
```

### Run the frontend

```bash
cd web
pnpm dev
# serves at http://localhost:3456
```

Open http://localhost:3456 to see the full A-Cal interface. The frontend
proxies `/api/*` to the backend automatically.

### Run tests

```bash
# Python tests (829 passing)
.venv/bin/python -m pytest tests/ -q

# TypeScript typecheck
cd web && pnpm typecheck

# E2E tests (Playwright, 79 passing)
cd web && pnpm exec playwright test

# Linting
.venv/bin/ruff check a_cal/
```

### Docker

```bash
cp .env.example .env
docker compose up --build
# backend at :8000, frontend at :3456
```

For PostgreSQL instead of SQLite:

```bash
docker compose --profile postgres up --build
```

## Git workflow

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feat/your-feature
   ```
2. Use [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` new feature
   - `fix:` bug fix
   - `docs:` documentation only
   - `test:` test additions or corrections
   - `chore:` build, deps, config, etc.
3. Run tests before committing:
   ```bash
   .venv/bin/python -m pytest tests/ -q
   cd web && pnpm typecheck && pnpm exec playwright test
   ```
4. Never push directly to `main`. Open a pull request.
5. Never expose API keys, tokens, or secrets in code or logs.

## Code standards

### Python
- Target Python 3.11+
- Use `from __future__ import annotations` for forward references
- Never use `Any` — use `unknown` equivalents: `dict[str, object]` or specific types
- All new functions require docstrings
- Lint with `ruff check`
- Test with pytest

### TypeScript
- Never use `any` — use `unknown` and narrow with type guards
- All new functions require JSDoc comments
- Typecheck with `tsc --noEmit`
- Test with Playwright for E2E

## Building plugins

Plugins are Python files with a `Plugin` class that implements hooks. See
`plugins/README.md` for the full hook reference and `plugins/examples/` for
working examples.

```python
class Plugin:
    name = "My Plugin"
    plugin_type = "agent"
    enabled = True

    def on_event_created(self, event):
        """Called when a new event is created. Return modified event or None."""
        return None
```

Install by copying to `~/.a-cal/plugins/` and scanning from the UI or API.

## Building workflow configs

Workflows are JSON-defined automation chains. Build them visually in Developer
mode (Workflow Builder) or write JSON directly:

```json
{
  "name": "Daily briefing",
  "nodes": [
    { "id": "fetch", "type": "calendar.fetch", "params": { "days": 1 } },
    { "id": "summarize", "type": "llm.summarize", "params": { "prompt": "Summarize today's schedule" } },
    { "id": "notify", "type": "email.send", "params": {} }
  ],
  "edges": [["fetch", "summarize"], ["summarize", "notify"]]
}
```

## Sharing on the marketplace

1. Build a config (agent spec, sync rule pack, workflow, plugin config, UI theme)
2. Publish via the API or the Marketplace panel in Pro/Developer mode
3. Other users can browse, install, remix, and rate your config
4. Every item carries provenance metadata for auditability

## Architecture overview

A-Cal extends atom's Python/FastAPI backend with an additive `a_cal/` package:

```
a_cal/
  agents/         conductor, specialists, LLM service, nervous system
  api/            FastAPI routes (80+ endpoints)
  auth/           session-based auth (PBKDF2)
  db/             SQLAlchemy models, store, schema upgrades
  developer/      plugin runtime, agent CRUD, config I/O
  email/          IMAP/SMTP provider
  integrations/   atom, cal.com, zero-calendar bridges
  marketplace/    registry, persistent store, types
  providers/      Google, Outlook, CalDAV, IMAP/SMTP
  self_model/     extractor, store, settings, types
  settings/       model routing, modes, autonomy, email
  swarm/          federated negotiation coordinator
  sync/           engine, rules
  workflows/      models, runner, store
  analytics/      calendar analytics
```

The frontend is a Next.js app in `web/` with components for each major feature.

## License

A-Cal is AGPL-3.0-or-later. Contributions are accepted under the same license.
