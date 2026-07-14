# Codex's Architectural Understanding — A-Cal API Refactor

> Written by Codex on 2026-07-14. This is my working understanding of the
> A-Cal API layer, the store singleton pattern, and the file-splitting
> strategy. It exists so that a future handoff to Claude Code (or back to
> Codex) has the full mental model — not just a task list, but the *why*
> behind every decision. If you understand the concepts below, you can
> re-derive every implementation step from first principles.

---

## 1. How the A-Cal API Layer Is Assembled

### The mounting chain

The running application is assembled in `a_cal/api/standalone.py`. That file
imports ~12 routers from sibling modules and calls `app.include_router(...)`
for each one. Each router is a FastAPI `APIRouter` with its own prefix and
tags:

```
standalone.py
  ├── agent_router        (prefix="/api/a-cal", tags=["a-cal-agents"])
  ├── standalone_data_router (prefix="/api/a-cal", tags=["a-cal-data"])
  ├── oauth_router        (prefix="/api/a-cal/oauth", tags=["oauth"])
  ├── analytics_router    (prefix="/api/a-cal", tags=["analytics"])
  ├── booking_router      (prefix="/api/a-cal", tags=["booking"])
  ├── team_router         (prefix="/api/a-cal", tags=["team"])
  ├── graphql_router      (prefix="/graphql", tags=["graphql"])
  └── ... (swarm, marketplace, developer, auth)
```

The key insight: **every route module owns a module-level `router` object,
and `standalone.py` is the single composition point that mounts them all.**
This means a route module's `router` is its public interface — tests and
mount code import `from a_cal.api.<module> import router`, and nothing else
about the module's internal structure is part of the contract.

### The atom deployment path

There's a second mounting path in `a_cal/integrations/mount.py` (the "atom"
deployment). It also imports `standalone_data.router`. The old `routes.py`
file (deleted in an earlier P0-2 fix) was a stale duplicate that was never
mounted in standalone mode. The split must preserve the `standalone_data.router`
export so both deployment paths keep working without changes.

---

## 2. The PersistentStore Singleton Pattern

### Why it exists

`PersistentStore` (in `a_cal/db/store.py`) is the data access layer — it
wraps SQLite (default) or PostgreSQL and exposes methods like
`create_sub_account`, `get_unified_calendar`, `list_providers`, etc.

Before P2-4, every route module instantiated its own store at import time:

```python
# old pattern — each module had its own instance
_store = PersistentStore()  # in standalone_data.py
_db = PersistentStore()     # in booking_routes.py (different name!)
_db = PersistentStore()     # in team_routes.py
```

These all pointed at the same database file, so they were functionally
equivalent. But tests needed to monkeypatch each one separately — a 5-way
patch in `test_phase5_phase6.py` and a 7-way patch in `test_http_isolation.py`.
Missing one patch meant a test would silently use the wrong database,
causing cross-test pollution or false passes.

### The P2-4/P3-2 solution (already committed as `fe74b11`)

We created `a_cal/api/store.py`:

```python
from a_cal.db.store import PersistentStore
_store = PersistentStore()

def get_store() -> PersistentStore:
    return _store
```

Every route module now does `from a_cal.api.store import _store` instead of
instantiating its own. Naming was standardized to `_store` everywhere (was
mixed `_db`/`_store`).

### The Python import-binding trap (critical for the file split)

Here's the subtlety that determines how we patch things in tests:

```python
# In sub_account_routes.py:
from a_cal.api.store import _store   # creates a LOCAL binding
```

This `from X import Y` statement creates a **new name binding** in
`sub_account_routes`'s module namespace. It does NOT create a live reference
that tracks changes to `a_cal.api.store._store`. So if a test does:

```python
import a_cal.api.store as store_mod
store_mod._store = new_db  # swaps the shared instance
```

...the sub-modules' local `_store` bindings **do not change**. They still
point at the old `PersistentStore` instance. This is why the test fixtures
must patch each module's `_store` individually, even though they all
originally came from the same source.

The `get_store()` function was added as an alternative for future use —
calling `get_store()` at runtime would always read the current
`a_cal.api.store._store`, making a single patch point sufficient. But the
current route modules import `_store` at module level (for brevity and
because the handlers reference it as a bare name), so we still need
per-module patching in tests. This is a known trade-off documented here
so nobody mistakes it for a bug.

### The agent_routes.py property trick

`agent_routes.py` has a `_SettingsStore` class that used to hold a direct
`_db` attribute. We turned it into a `@property` that reads from
`a_cal.api.store._store` at access time:

```python
@property
def _db(self) -> _DBStore:
    from a_cal.api import store as _store_mod
    return _store_mod._store
```

This means patching `a_cal.api.store._store` automatically affects
`_SettingsStore._db` — no separate patch needed. This is the one place
where we avoided the local-binding trap by deferring the lookup to
access time.

---

## 3. FastAPI Router Composition — How Prefixes Work

### The pattern we use for file splitting

FastAPI's `APIRouter.include_router()` lets a parent router include a
child router. The child's routes inherit the parent's prefix. This is the
mechanism that lets us split a big file into smaller ones without changing
any URL paths.

**Parent (composition stub):**
```python
router = APIRouter(prefix="/api/a-cal", tags=["a-cal-data"])
router.include_router(_sub_router)
router.include_router(_calendar_router)
router.include_router(_email_router)
```

**Child (sub-router):**
```python
router = APIRouter(tags=["a-cal-data"])  # NO prefix!
```

The child defines routes like `@router.get("/sub-accounts")`, and when the
parent includes it, the final path becomes `/api/a-cal/sub-accounts`.

### The double-prefix trap

If a child router had `APIRouter(prefix="/api/a-cal", ...)` AND the parent
also had `prefix="/api/a-cal"`, the final path would be
`/api/a-cal/api/a-cal/sub-accounts` — double-prefixed. This is why **sub-
routers must NOT have a prefix**. The prefix lives only on the parent.

### When a sub-router is mounted directly (not via a parent)

For `nervous_system_routes.py` (P2-3b), we're NOT using a composition stub.
The nervous-system routes are extracted from `agent_routes.py` and mounted
directly in `standalone.py`. In this case, the new module's router **must**
carry its own prefix (`prefix="/api/a-cal"`) because there's no parent
router to inherit it from.

---

## 4. The File Splitting Plan (P2-3)

### Project rule: 800 lines max per file

Four files exceed this limit:
- `a_cal/db/store.py` — 1936 lines (not in scope for this PR)
- `a_cal/agents/standalone_responses.py` — 1359 lines (not in scope)
- `a_cal/api/standalone_data.py` — 1230 lines (P2-3a, this PR)
- `a_cal/api/agent_routes.py` — 877 lines (P2-3b, this PR)

### P2-3a: Split `standalone_data.py` → 3 sub-modules + composition stub

**Original structure (1230 lines):**
- Lines 1-48: imports, router, `_fire_plugin_hook` helper
- Lines 50-172: Pydantic models (8 model classes)
- Line 169: `from a_cal.api.store import _store`
- Lines 174-594: sub-account + provider + sync + calendar + sync-rule endpoints
- Lines 595-1231: email endpoints + Phase 4 advanced email models

**Target structure:**

| New file | Contents | Router prefix |
|---|---|---|
| `_helpers.py` | `_fire_plugin_hook()` shared helper | n/a (no router) |
| `sub_account_routes.py` | SubAccount/Provider/SyncRule models + endpoints | none (child) |
| `calendar_routes.py` | UnifiedEvent/EventCreate/EventUpdate + calendar endpoints + `_event_to_response` | none (child) |
| `email_routes.py` | Attachment/Email/Account/Label/Filter/Snooze/Schedule/Template/Vacation models + all email endpoints | none (child) |
| `standalone_data.py` (rewritten) | Composition stub: imports 3 sub-routers, includes them under `prefix="/api/a-cal"` | `/api/a-cal` (parent) |

**The composition stub:**
```python
"""Composition stub — real routes live in sub-modules."""
from fastapi import APIRouter
from a_cal.api.sub_account_routes import router as _sub_router
from a_cal.api.calendar_routes import router as _calendar_router
from a_cal.api.email_routes import router as _email_router

router = APIRouter(prefix="/api/a-cal", tags=["a-cal-data"])
router.include_router(_sub_router)
router.include_router(_calendar_router)
router.include_router(_email_router)
```

The `router` export is preserved, so every file that does
`from a_cal.api.standalone_data import router` keeps working unchanged.

### P2-3b: Split `agent_routes.py` → extract nervous-system routes

**Original structure (877 lines):**
- Lines 1-788: settings store, conductor setup, settings/conductor endpoints
- Lines 789-877: nervous system coordinator singleton + 8 endpoints

**Target:**
- `agent_routes.py` keeps settings + conductor endpoints (lines 1-788)
- `nervous_system_routes.py` gets the 8 nervous-system endpoints + their
  request models (NSRouteRequest, NSUserStateRequest, NSBindingRequest) +
  the `_get_nervous_system()` singleton function
- `agent_routes.py` imports `_get_nervous_system` back from the new module
  (it's used at line 136 when constructing a conductor)
- `nervous_system_routes.py` has its own `router = APIRouter(prefix="/api/a-cal", tags=["a-cal-agents"])`
  and is mounted directly in `standalone.py`

**What moves to `nervous_system_routes.py`:**
- `from a_cal.agents.nervous_system import NervousSystemCoordinator, SystemState`
- `from a_cal.agents.cas_specs import CAS_AGENTS, CAS_AGENTS_BY_NAME`
- `_nervous_system` global + `_get_nervous_system()` function
- `NSRouteRequest`, `NSUserStateRequest`, `NSBindingRequest` models
- 8 endpoints: `ns_overview`, `ns_agents`, `ns_state`, `ns_route`,
  `ns_memories`, `ns_assess_user_state`, `ns_verify_binding`, `ns_cas_agents`

**What stays in `agent_routes.py`:**
- Everything else, plus `from a_cal.api.nervous_system_routes import _get_nervous_system`
  (replacing the inline definition)

---

## 5. Test Fixture Implications

### Which test files need changes for P2-3a

Two test files patch `standalone_data._store` directly:

**`tests/test_http_isolation.py`** — `_patch_stores()` function:
- Currently patches `standalone_data._store`
- After split: must patch `sub_account_routes._store`,
  `calendar_routes._store`, `email_routes._store` instead
- Also needs to import the three new sub-modules

**`tests/test_phase5_phase6.py`** — `_clean_db()` function:
- Same pattern: replace `standalone_data._store` with the three sub-module patches

### What does NOT need to change

Files that only import `from a_cal.api.standalone_data import router` are
unaffected because the composition stub still exports `router`. This
includes: `test_email_endpoints.py`, `test_standalone_data.py`,
`test_sync_rules_api.py`, `test_event_actions.py`, `test_oauth.py`,
`test_connect_and_self_model.py`, `test_phase3_phase4.py`,
`test_caldav_integration.py`, `test_atom_bridge.py`,
`a_cal/integrations/mount.py`, and `a_cal/api/standalone.py`.

### The agent_routes.py import fix

`agent_routes.py:312` has:
```python
from a_cal.api.standalone_data import _store as data_store
```
After the split, `standalone_data.py` is a composition stub with no `_store`.
This line must change to:
```python
from a_cal.api.store import _store as data_store
```

---

## 6. Verification Protocol

After every code change, run this block:

```bash
.venv/bin/python -m pytest tests/ -q
ruff check a_cal/ tests/
cd web && npx tsc --noEmit
```

The baseline is **984 passed, 9 skipped, 0 failed** (as of the P2-4 commit).
Ruff must be clean. tsc must be clean (next build is optional for pure
backend refactors but should be run before opening the PR).

If any pre-existing date-dependent tests fail, re-run them individually to
confirm they're flaky, not caused by our changes.

---

## 7. Conventions Summary

- Conventional Commits (`refactor:`, `feat:`, `fix:`, `docs:`)
- Never push to `origin/main` (protected) — open a PR
- `pnpm` for frontend, `pip`/`pyproject.toml` for backend
- No `any` in TS (use `unknown` + narrow)
- JSDoc/docstrings on new functions
- Never `rm -rf`
- Never expose secrets in code or logs
- Keep changes scoped to `a_cal/`, `web/`, `sdk/`, `tests/`, `docs/`,
  `plugins/`, `alembic/`
