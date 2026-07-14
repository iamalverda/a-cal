# Handoff for Codex / Claude Code — A-Cal Store Consolidation & File Splitting

> Written by Codex on 2026-07-14, after completing the cleanup & hardening
> PR (#3). This document covers the deferred P2-3, P2-4, and P3-2 work items
> from the original `HANDOFF-FOR-CODEX.md`. It is deliberately verbose: the
> goal is to give whoever picks this up (Codex on a fresh context, or Claude
> Code) enough architectural understanding to execute confidently without
> re-deriving the analysis.

---

## 0. Where things stand right now

**Branch:** `fix/cleanup-and-hardening` — PR #3 is open against `main`.
The PR contains 14 commits: 9 from `main` (including the security fix
`4350e83`) plus 5 from the cleanup pass (P0 fixes, P1 isolation tests,
P1 security hardening, P2 dead-code removal + lint, P3-1 GraphQL depth
limit). The PR is ready to merge; the work below should go in a **separate
PR** to keep review scope manageable.

**Baseline to preserve:**
```
ruff check a_cal/ tests/         → All checks passed
.venv/bin/python -m pytest tests/ -q  → 982 passed, 9 skipped
                                         (2 pre-existing date-dependent failures:
                                          test_event_actions.py::TestListEventsResponse::test_conductor_lists_events_via_chat
                                          test_timezone.py::TestConductorTimezone::test_event_near_utc_midnight_shows_as_today_in_local_tz)
cd web && npx tsc --noEmit        → clean
```

**Pre-existing test failures — DO NOT try to fix these.** Both fail because
the tests create events relative to "now" and assert the conductor's natural
language response contains the event title. When the current time falls near
a day boundary or on a day where the conductor's phrasing changes, the
assertion breaks. They fail identically on the original `main` before any of
our changes. They are not caused by the refactor work and should be left
alone (or fixed in a separate dedicated PR if desired).

**Conventions (from AGENTS.md + CLAUDE.md, still in force):**
- `pnpm` for frontend, `pip`/`pyproject.toml` for backend.
- Conventional Commits. Never push to `main` directly (protected). Open a PR.
- No `any` in TS (use `unknown` + narrow). JSDoc on new functions.
- Never `rm -rf` on any directory. No secrets in code/logs.
- Keep changes scoped to `a_cal/`, `web/`, `sdk/`, `tests/`, `docs/`,
  `plugins/`, `alembic/` within this repo. Do not touch sibling reference
  projects in the parent workspace.
- Run `ruff check a_cal/ tests/` and `.venv/bin/python -m pytest tests/ -q`
  after every change. Run `cd web && npx tsc --noEmit` if you touch any TS.

---

## 1. The Problem: Store Singleton Proliferation (P2-4 + P3-2)

### What's happening

Seven modules across the codebase each instantiate their own
`PersistentStore()` at module load time (i.e., when the file is first
imported). In production, these all point at the same SQLite file (or
Postgres DB), so they share data — but they create **separate SQLAlchemy
engine and session instances**, which is wasteful and can cause subtle
issues if the DB path changes after import.

In tests, this is actively painful. Every test that needs an in-memory store
must monkeypatch each module's singleton individually. Miss one, and that
module silently uses the file-based production store (or a stale in-memory
one from a previous test), leading to cross-test data leakage that is
extremely hard to debug.

### The seven singletons (the full inventory)

Here is every module-level `PersistentStore` instance in the codebase, with
the variable name used and the line where it's created:

| Module | Variable | Line | Notes |
|--------|----------|------|-------|
| `a_cal/api/standalone_data.py` | `_store` | 173 | Sub-accounts, providers, calendar, email endpoints |
| `a_cal/api/booking_routes.py` | `_db` | 94 | Booking pages, event-type extensions |
| `a_cal/api/team_routes.py` | `_db` | 28 | Teams, routing forms, webhooks, payments |
| `a_cal/api/analytics_routes.py` | `_db` | 36 | Calendar analytics, event-type CRUD |
| `a_cal/api/graphql_routes.py` | `_db` | 31 | GraphQL query resolvers |
| `a_cal/api/oauth_routes.py` | `_store` | 43 | OAuth start/callback flows |
| `a_cal/integrations/webhooks.py` | `_store` | 23 | Webhook dispatch + delivery recording |

Four modules use the name `_db`; three use `_store`. They are all the same
class (`PersistentStore`). The naming inconsistency is P3-2.

### The special case: `agent_routes.py`

`a_cal/api/agent_routes.py` has a **different** pattern. It defines a
wrapper class `_SettingsStore` that holds a `PersistentStore` internally:

```python
class _SettingsStore:
    def __init__(self) -> None:
        self._db = _DBStore()          # _DBStore is an alias for PersistentStore
        self._conductors: dict[str, ACalConductor] = {}
        self._registries: dict[str, AgentRegistry] = {}
```

The module-level singleton is `_store = _SettingsStore()`, and the
`PersistentStore` inside it is `_store._db`. Tests patch
`agent_routes._store._db` to swap the database. This nested structure means
the consolidation needs to handle this module differently — the `_SettingsStore`
wrapper provides conductor caching and registry management on top of the raw
store, so we can't just replace it with a bare `PersistentStore`.

### The other special cases (NOT part of this consolidation)

- **`developer_routes.py`** creates per-user `AgentSpecStore` and
  `WorkflowStore` instances lazily via `_get_agent_store(user_id)` and
  `_get_workflow_store(user_id)`. Each wraps a fresh `PersistentStore()`.
  This is a different pattern (per-user, lazy) and is NOT part of the
  consolidation. Leave it alone.

- **`marketplace_routes.py`** uses a `_get_store()` lazy accessor that
  returns either `PersistentMarketplaceStore` or `MarketplaceStore`
  depending on whether atom is detected. This is a **different class**, not
  `PersistentStore`. It already has the lazy-accessor pattern we're moving
  toward, which is a good sign. Leave it alone.

### How tests patch today (the pain point, concretely)

**`tests/test_http_isolation.py`** — the `_patch_stores()` helper patches 7
singletons (including the nested `agent_routes._store._db`):

```python
def _patch_stores(db: PersistentStore) -> dict:
    originals = {
        "standalone_data": standalone_data._store,
        "booking": booking_routes._db,
        "analytics": analytics_routes._db,
        "team": team_routes._db,
        "graphql": graphql_routes._db,
        "oauth": oauth_routes._store,
        "agent_store_db": agent_routes._store._db,
    }
    standalone_data._store = db
    booking_routes._db = db
    analytics_routes._db = db
    team_routes._db = db
    graphql_routes._db = db
    oauth_routes._store = db
    agent_routes._store._db = db
    return originals
```

**`tests/test_phase5_phase6.py`** — the `_clean_db` fixture patches 6
singletons (no oauth or agent_routes in this file):

```python
booking_routes._db = db
analytics_routes._db = db
team_routes._db = db
graphql_routes._db = db
webhook_mod._store = db
standalone_data._store = db
```

**`tests/test_booking_api.py`** — patches 2 singletons:

```python
booking_routes._db = db
analytics_routes._db = db
```

Every new test file that needs an in-memory store must know this full list
and patch all of them. If someone adds a new route module with its own
`PersistentStore()`, every existing test fixture silently breaks (the new
module won't be patched and will read/write the wrong database).

### The fix

Create a single shared store module that all route modules import from.
Tests patch that one module. One seam, one place to configure, one place to
test.

**New file: `a_cal/api/store.py`**

```python
"""Shared PersistentStore singleton for all A-Cal route modules.

Importing this module gives every route module the same store instance,
which means tests only need to patch one location (`a_cal.api.store._store`)
to swap the database for an in-memory instance.

In production, the store uses SQLite (default) or PostgreSQL (when
configured via environment variables). In tests, the `A_CAL_DB_PATH=:memory:`
env var (set in conftest.py) makes it use an in-memory SQLite database.
"""
from __future__ import annotations

from a_cal.db.store import PersistentStore

# Single shared instance. All route modules import this, never instantiate
# their own PersistentStore().
_store = PersistentStore()


def get_store() -> PersistentStore:
    """Return the shared PersistentStore instance.

    Tests patch `a_cal.api.store._store` to swap the database. Route modules
    should either import `_store` directly (for module-level use) or call
    this function (for use inside route handlers where a fresh reference is
    clearer).
    """
    return _store
```

**Then, in each of the 7 route modules, replace:**

```python
from a_cal.db.store import PersistentStore
# ...
_db = PersistentStore()      # or _store = PersistentStore()
```

**with:**

```python
from a_cal.api.store import _store
# For modules that used _db, alias it for minimal churn:
# _db = _store    ← DO NOT do this; we want to standardize on _store
```

Instead, do a find-replace within each module: every reference to `_db`
becomes `_store`. This is the P3-2 naming standardization, done as part of
the same pass. The name `_store` is chosen over `_db` because:
- It's more descriptive (it's a store object, not a raw database connection).
- More modules already use `_store` (3 of 7) than `_db` (4 of 7), so it's
  the lower-churn direction — wait, actually `_db` is used by 4 and `_store`
  by 3. The difference is one module. Pick `_store` because it reads better
  and the churn difference is negligible.

**For `agent_routes.py` specifically:**

The `_SettingsStore` wrapper needs to use the shared store instead of
creating its own. Change:

```python
class _SettingsStore:
    def __init__(self) -> None:
        self._db = _DBStore()
```

to:

```python
from a_cal.api.store import _store as _shared_store

class _SettingsStore:
    def __init__(self) -> None:
        self._db = _shared_store
```

This way `agent_routes._store._db` still works (the attribute name doesn't
change), but it points at the shared instance. Tests that patch
`agent_routes._store._db` can instead patch `a_cal.api.store._store` and it
will propagate everywhere.

**For `webhooks.py`:**

Replace `_store = PersistentStore()` with `from a_cal.api.store import _store`.

### Updating test fixtures

After the consolidation, test fixtures simplify dramatically. Instead of
patching 7 module-level singletons, they patch one:

```python
@pytest.fixture(autouse=True)
def _clean_db():
    from a_cal.api import store as store_mod
    db = PersistentStore(in_memory=True)
    original = store_mod._store
    store_mod._store = db
    # Also update agent_routes._store._db since it grabbed the old reference
    from a_cal.api import agent_routes
    agent_routes._store._db = db
    yield db
    store_mod._store = original
    agent_routes._store._db = original
```

Wait — there's a subtlety. `_SettingsStore.__init__` grabs `_shared_store`
at construction time and stores it as `self._db`. If we later patch
`store_mod._store`, the `_SettingsStore` instance already holds the old
reference. So we still need to update `agent_routes._store._db` in the
fixture. This is an improvement (2 patches instead of 7) but not as clean
as 1.

**Alternative for agent_routes:** Instead of grabbing the shared store in
`__init__`, make `_SettingsStore` read from the shared module on each
access:

```python
class _SettingsStore:
    @property
    def _db(self):
        from a_cal.api.store import _store
        return _store
```

This way patching `a_cal.api.store._store` automatically propagates to
`agent_routes._store._db` without any extra fixture work. The property
approach adds a tiny import-and-lookup overhead on every settings access,
but settings access is not hot-path code (it's API-call-frequency, not
per-request).

**Recommended approach:** Use the `@property` trick for `_SettingsStore._db`.
This gets us down to **one patch in every test fixture**: just
`store_mod._store = db`. That's the ideal end state.

### Execution order for P2-4/P3-2

1. Create `a_cal/api/store.py` with the shared singleton + `get_store()`.
2. Update `agent_routes.py`: change `_SettingsStore._db` from a direct
   attribute to a `@property` that reads from `a_cal.api.store`. Remove the
   `_DBStore()` instantiation in `__init__`.
3. Update the 6 remaining modules: replace their `PersistentStore()` with
   `from a_cal.api.store import _store`, and rename all `_db` → `_store`
   within each module.
4. Update `webhooks.py`: same as step 3.
5. Update test fixtures in `test_http_isolation.py`, `test_phase5_phase6.py`,
   and `test_booking_api.py` to patch only `a_cal.api.store._store`.
6. Run `ruff check a_cal/ tests/` + full pytest + tsc.
7. Commit as `refactor: consolidate store singletons into shared module, standardize naming`.

### Files touched (P2-4/P3-2)

**New:** `a_cal/api/store.py`
**Modified source (7):** `standalone_data.py`, `booking_routes.py`,
`team_routes.py`, `analytics_routes.py`, `graphql_routes.py`,
`oauth_routes.py`, `a_cal/integrations/webhooks.py`
**Modified special (1):** `agent_routes.py` (the `_SettingsStore` property change)
**Modified tests (3):** `test_http_isolation.py`, `test_phase5_phase6.py`,
`test_booking_api.py`

Total: 1 new + 11 modified = 12 files. Each source file diff is small
(import swap + variable rename). The test fixture diffs are where the line
count drops the most (7-patch blocks → 1-patch blocks).

---

## 2. The Plan: File Splitting (P2-3, selective)

### What we're splitting and what we're not

| File | Lines | Verdict | Rationale |
|------|-------|---------|-----------|
| `a_cal/api/standalone_data.py` | 1231 | **SPLIT** | Clear domain boundaries, natural router decomposition |
| `a_cal/api/agent_routes.py` | 868 | **SPLIT** | Barely over limit; easy to split settings vs nervous-system |
| `a_cal/db/store.py` | 1936 | **DEFER** | One class, stable, no merge conflicts; mixin pattern not used elsewhere |
| `a_cal/agents/standalone_responses.py` | 1359 | **DEFER** | Agent logic with semantic boundaries; high risk of subtle behavior change |

### P2-3a: Split `standalone_data.py` (1231 → 4 files)

This file defines one `APIRouter(prefix="/api/a-cal")` with 45 endpoints
across 5 domain areas. The split is along those domain lines.

**Current structure (by endpoint group):**

```
Lines 177-227   : Sub-accounts (5 endpoints)
Lines 229-300   : Providers (5 endpoints)
Lines 302-388   : Sync trigger (1 endpoint, large async function)
Lines 390-597   : Calendar + sync-rules (7 endpoints)
Lines 598-1231  : Email (24 endpoints: messages, accounts, star, read,
                  delete, search, folders, send, labels, filters, snooze,
                  schedule, vacation, templates, summarize)
```

**Proposed split:**

| New file | Contents | Approx lines | Endpoints |
|----------|----------|--------------|-----------|
| `a_cal/api/sub_account_routes.py` | Sub-account + provider + sync endpoints + their Pydantic models | ~300 | 11 |
| `a_cal/api/calendar_routes.py` | Calendar event CRUD + sync-rules + their models | ~250 | 7 |
| `a_cal/api/email_routes.py` | All email endpoints + their models | ~550 | 24 |
| `a_cal/api/standalone_data.py` | Router composition only: imports the 3 sub-routers, creates the parent router, includes them | ~30 | 0 |

**How to preserve the public import path:**

`standalone.py` imports the router from `standalone_data`:

```python
from a_cal.api.standalone_data import router as standalone_data_router
```

After the split, `standalone_data.py` keeps the same `router` variable but
composes it from sub-routers:

```python
from a_cal.api.sub_account_routes import router as _sub_router
from a_cal.api.calendar_routes import router as _calendar_router
from a_cal.api.email_routes import router as _email_router

router = APIRouter(prefix="/api/a-cal", tags=["a-cal-data"])
router.include_router(_sub_router)
router.include_router(_calendar_router)
router.include_router(_email_router)
```

This way `standalone.py` doesn't change at all. The `router` object it
imports has the same prefix and includes all the same endpoints.

**Important:** All sub-routers should use `APIRouter()` **without** a prefix
(the prefix is on the parent). Or they can use the same prefix — FastAPI
handles overlapping prefixes by concatenating, so if both parent and child
have `prefix="/api/a-cal"`, you'd get `/api/a-cal/api/a-cal/...` which is
wrong. **Use no prefix on sub-routers; the parent provides it.**

Actually, let me be precise: `APIRouter.include_router()` **does not
concatenate** prefixes in the way you might expect. If the parent has
`prefix="/api/a-cal"` and you `include_router(child)` where child has no
prefix, the child's routes get the parent's prefix. If the child also has
`prefix="/api/a-cal"`, the child's routes get **both** prefixes, resulting
in `/api/a-cal/api/a-cal/...`. So: **sub-routers must have no prefix.**

**The `_store` reference:** After P2-4 is done, each sub-module imports
`from a_cal.api.store import _store` and uses it directly. No store
instantiation in the sub-modules.

**The `_fire_plugin_hook` helper:** This is defined in `standalone_data.py`
and used by calendar endpoints. Move it to `calendar_routes.py` (or to a
small `a_cal/api/_helpers.py` if both calendar and email use it — check
first).

**Pydantic models:** Each sub-module takes its own models with it. The
models are defined right above the endpoints that use them, so they move
naturally.

### P2-3b: Split `agent_routes.py` (868 → 2 files)

This file has two clearly separable concerns:

```
Lines 1-210   : _SettingsStore class + settings endpoints (mode, routing,
                autonomy, timezone, email, self-model, api-keys, ollama,
                backend-mode, atom-status, llm-enabled, preload-model)
Lines 260-285 : Conductor chat endpoint
Lines 285-345 : Email scan-schedule endpoint
Lines 346-868 : Nervous system endpoints (overview, agents, state, route,
                memories, assess-user-state, verify-binding, cas-agents)
```

**Proposed split:**

| New file | Contents | Approx lines |
|----------|----------|--------------|
| `a_cal/api/agent_routes.py` | `_SettingsStore`, conductor chat, settings endpoints, self-model endpoints | ~550 |
| `a_cal/api/nervous_system_routes.py` | All `/nervous-system/*` endpoints + their models | ~320 |

`standalone.py` adds one `include_router` call for the new nervous-system
router. The existing `agent_router` import stays the same (just fewer
endpoints in it).

### What we're deferring and why

**`store.py` (1936 lines):** This is a single class (`PersistentStore`)
with ~70 methods organized by domain. The handoff suggests splitting it
into mixins (CalendarMixin, EmailMixin, TeamsMixin, etc.) composed into
`PersistentStore`. This is architecturally clean but:
- The mixin pattern is not used anywhere else in this codebase. Introducing
  it for one class adds a pattern that future contributors must learn.
- The file is stable — it rarely changes, and when it does, the changes are
  to one domain section at a time (no merge conflicts in practice).
- The risk of a subtle behavior change during the split is non-trivial
  (e.g., a helper method that's used across domains, a `self._session()`
  call that assumes a specific class hierarchy).
- Modern editors handle 2000-line files fine with symbol search and code
  folding.

The cost-benefit doesn't justify it right now. If the file grows past 2500
lines or starts causing merge conflicts, revisit.

**`standalone_responses.py` (1359 lines):** This is agent response
generation logic. The boundaries between sections are semantic (how the
conductor phrases things, what context it considers), not structural (which
endpoints or data models it touches). A mechanical split risks introducing
subtle behavioral changes in the conductor's responses, which are hard to
catch with tests (the response text is natural language, and the existing
tests only assert on substrings). Defer indefinitely unless there's a
specific need.

---

## 3. Suggested PR structure

Do all of this on a new branch `refactor/store-consolidation-and-file-split`
created from `main` (after PR #3 merges) or from `fix/cleanup-and-hardening`
(if PR #3 hasn't merged yet — the changes are independent).

**Commit 1:** `refactor: consolidate store singletons into shared module, standardize naming`
- P2-4 + P3-2. Create `a_cal/api/store.py`, update 7 route modules +
  agent_routes, update 3 test fixtures.
- Verify: ruff clean, pytest green (same 982+9+2 numbers), tsc clean.

**Commit 2:** `refactor: split standalone_data.py into sub-account, calendar, and email route modules`
- P2-3a. Create 3 new sub-modules, reduce `standalone_data.py` to router
  composition.
- Verify: ruff clean, pytest green, tsc clean.

**Commit 3:** `refactor: split nervous-system routes out of agent_routes.py`
- P2-3b. Create `nervous_system_routes.py`, update `standalone.py` to
  include it.
- Verify: ruff clean, pytest green, tsc clean.

**Open PR:** `refactor: consolidate store singletons and split oversized route files`
- Body should reference this handoff doc and PR #3.

---

## 4. Verification checklist (run after each commit)

```bash
# Lint
ruff check a_cal/ tests/

# Backend tests (expect: 982 passed, 9 skipped, 2 failed [pre-existing])
.venv/bin/python -m pytest tests/ -q

# Frontend typecheck (only if TS files touched — these refactors are Python-only)
cd web && npx tsc --noEmit
```

If the test count changes (other than the 2 pre-existing failures), something
went wrong. The refactor is pure mechanical — no new tests, no removed tests,
no behavior changes. If a test starts failing that wasn't failing before,
it's almost certainly a store patching issue (a module that's still using
its own `PersistentStore()` instead of the shared one).

**Debugging tip:** If you get cross-test data leakage (test A's data appears
in test B), grep for any remaining `PersistentStore()` instantiations in
`a_cal/` that you missed:

```bash
rg "PersistentStore\(\)" a_cal/ --type py -g '!a_cal/api/store.py' -g '!test*'
```

The only results should be in `developer_routes.py` (per-user lazy stores,
intentionally separate) and `marketplace_routes.py` (different store class,
intentionally separate). If you see any others, that's a missed module.

---

## 5. Key file map (quick reference)

```
a_cal/api/
  standalone.py              — app factory, includes all routers (lines 124-134)
  store.py                   — NEW: shared PersistentStore singleton
  standalone_data.py         — 1231 lines → split into 3 sub-modules + composition stub
  sub_account_routes.py      — NEW: sub-account + provider + sync endpoints
  calendar_routes.py         — NEW: calendar event + sync-rule endpoints
  email_routes.py            — NEW: all email endpoints
  agent_routes.py            — 868 lines → settings + conductor stay here
  nervous_system_routes.py   — NEW: nervous-system endpoints split from agent_routes
  booking_routes.py          — _db → _store (from shared module)
  team_routes.py             — _db → _store (from shared module)
  analytics_routes.py        — _db → _store (from shared module)
  graphql_routes.py          — _db → _store (from shared module)
  oauth_routes.py            — _store (from shared module, no rename needed)
  developer_routes.py        — NOT TOUCHED (per-user lazy stores)
  marketplace_routes.py      — NOT TOUCHED (different store class)

a_cal/integrations/
  webhooks.py                — _store (from shared module, no rename needed)

a_cal/db/
  store.py                   — NOT TOUCHED (1936 lines, deferred)

a_cal/agents/
  standalone_responses.py    — NOT TOUCHED (1359 lines, deferred)

tests/
  test_http_isolation.py     — simplify _patch_stores() to patch one location
  test_phase5_phase6.py      — simplify _clean_db fixture to patch one location
  test_booking_api.py        — simplify fixture to patch one location
```

---

## 6. What's strong (don't break these)

- **The `user_id` scoping pattern** in `PersistentStore` — every query
  method filters by `user_id` (now effective after the AuthMiddleware fix
  in `4350e83`). The store consolidation must not change any query logic.
- **The `_session()` context manager** — `PersistentStore._session()` yields
  a SQLAlchemy session and handles commit/rollback. All store methods use
  it. The consolidation only changes who holds the `PersistentStore`
  instance, not how it works internally.
- **The router composition in `standalone.py`** — 11 routers included in a
  specific order. The file split must not change this order or the set of
  routers (except adding the new `nervous_system_router`).
- **The test count** — 982 passed is the baseline. The refactor must not
  add or remove tests. If the count changes, investigate before proceeding.
