# Handoff for Claude Code — Remaining Oversized File Splits

> Written by Codex on 2026-07-14. This handoff covers the two remaining
> files that exceed the 800-line project rule. **Read
> [CODEX-UNDERSTANDING.md](CODEX-UNDERSTANDING.md) first** — it explains the
> API layer architecture, the store singleton pattern, FastAPI router
> composition, and the Python import-binding semantics you need to
> understand before touching these files.
>
> **Branch:** `refactor/store-consolidation-and-file-split` (PR #4 against
> `fix/cleanup-and-hardening`). Create a new branch from this one or from
> `main` after PR #4 merges — your call, but keep it off `origin/main`.

---

## What Codex Already Did (do NOT redo)

Three commits on `refactor/store-consolidation-and-file-split`:

1. **`fe74b11`** — P2-4/P3-2: consolidated 7 per-module `PersistentStore()`
   instances into a single `a_cal/api/store.py` singleton; standardized all
   naming to `_store` (was mixed `_db`/`_store`).

2. **`731f24f`** — P2-3a: split `standalone_data.py` (1230 lines) into
   `sub_account_routes.py`, `calendar_routes.py`, `email_routes.py`, and
   `_helpers.py`, composed under a 30-line composition stub.

3. **`0e9e266`** — P2-3b: extracted 8 nervous-system endpoints from
   `agent_routes.py` (877 -> 787 lines) into `nervous_system_routes.py`.

**Baseline:** 984 passed, 9 skipped, ruff clean, tsc clean. Preserve this.

---

## What's Left: Two Oversized Files

| File | Lines | Limit | Over by |
|---|---|---|---|
| `a_cal/db/store.py` | 1936 | 800 | 1136 |
| `a_cal/agents/standalone_responses.py` | 1359 | 800 | 559 |

**Do these one at a time.** Commit + verify (ruff + pytest + tsc) after each
split before starting the next. If the first split breaks something, you
don't want to also be debugging the second.

---

## File 1: `a_cal/db/store.py` (1936 lines)

### What this file is

`PersistentStore` is the data access layer — a single class that wraps
SQLAlchemy ORM models and exposes ~70 methods organized by domain. It's
the backend for every route module and the workflow/self-model systems.

### The public interface contract

Every caller does one of:
```python
from a_cal.db.store import PersistentStore          # instantiate directly
from a_cal.api.store import _store                    # shared singleton (for routes)
```

The `PersistentStore` class is the interface. Callers call methods like
`store.create_sub_account(...)`, `store.list_providers(...)`, etc. The
split must preserve every public method name and signature on the
`PersistentStore` class.

### Recommended approach: mixin classes

Split domain methods into mixin classes, then compose them:

```python
# a_cal/db/store_mixins/_sub_account.py
class SubAccountMixin:
    def list_sub_accounts(self) -> list[dict[str, Any]]: ...
    def create_sub_account(self, data: dict[str, Any]) -> dict[str, Any]: ...
    # ...

# a_cal/db/store.py (rewritten, ~200 lines)
from a_cal.db.store_mixins._sub_account import SubAccountMixin
from a_cal.db.store_mixins._provider import ProviderMixin
# ...

class PersistentStore(SubAccountMixin, ProviderMixin, CalendarMixin, ...):
    def __init__(self, in_memory=False): ...
    def _seed_if_empty(self): ...
    def _session(self): ...
```

**Why mixins and not composition?** Every call site does
`store.list_sub_accounts()`. With composition you'd need
`store.sub_accounts.list()` or a pass-through proxy layer. Mixins keep the
flat method namespace, so zero callers change.

### Domain section map (line numbers in the current file)

| Domain | Lines | Approx size | Suggested mixin file |
|---|---|---|---|
| Module imports + serialize helpers | 1-158 | 158 | stays in `store.py` |
| `PersistentStore` class def + `__init__` + `_seed_if_empty` + `_session` | 159-383 | 224 | stays in `store.py` |
| Sub-accounts | 384-446 | 62 | `_sub_account.py` |
| Providers | 447-595 | 148 | `_provider.py` |
| Calendar events | 596-748 | 152 | `_calendar.py` |
| Sync rules | 749-790 | 41 | `_sync_rules.py` (or fold into `_sub_account.py`) |
| Settings | 791-818 | 27 | `_settings.py` |
| API keys | 819-839 | 20 | stays with `_settings.py` |
| Self-model facts | 840-899 | 59 | `_self_model.py` |
| Negotiations | 900-934 | 34 | `_negotiations.py` (or fold into `_self_model.py`) |
| Event types | 935-1111 | 176 | `_event_types.py` |
| Bookings | 1112-1234 | 122 | `_bookings.py` |
| Email labels | 1235-1266 | 31 | `_email.py` |
| Email filters | 1267-1314 | 47 | `_email.py` |
| Email snooze | 1315-1362 | 47 | `_email.py` |
| Scheduled emails | 1363-1427 | 64 | `_email.py` |
| Email templates | 1428-1512 | 84 | `_email.py` |
| Teams | 1513-1581 | 68 | `_teams.py` |
| Team members | 1582-1690 | 108 | `_teams.py` |
| Routing forms | 1691-1758 | 67 | `_routing.py` (or fold into `_teams.py`) |
| Webhooks | 1759-1936 | 177 | `_webhooks.py` |

All email sections (lines 1235-1512) should go into one `_email.py` mixin
(~273 lines) rather than being split further — they're tightly related and
individually small.

### Critical details

1. **`_seed_if_empty` is large** (lines 180-379, ~200 lines). It seeds demo
   data on first run. It belongs in `store.py` because it touches every
   domain. If it makes `store.py` too big after the split, extract it into
   `_seed.py` as a standalone function that takes a `PersistentStore`
   instance.

2. **Serialize helpers** (`_serialize_sub_account`, `_serialize_provider`,
   `_serialize_sync_rule`, `_serialize_event`, `_serialize_event_type` at
   lines 58-158) are module-level functions used by the mixin methods. Move
   each helper into the mixin file that uses it. If a helper is shared across
   mixins, put it in `store.py` or a `_serialize.py` module.

3. **`_uid()` function** (line 45) is called by every method that does
   user-scoping. Mixins need access to it. Either keep it in `store.py` and
   have mixins import it, or move it to a small `_utils.py`:
   ```python
   from a_cal.db.store_utils import _uid
   ```

4. **`_session()` method** is called by every mixin method. It's an
   instance method on `PersistentStore`, so mixins inherit it
   automatically — no change needed.

5. **Import of ORM models** (lines 14-37) is needed by every mixin. Each
   mixin file should import what it uses from `a_cal.db.models`:
   ```python
   from a_cal.db.models import SubAccount, ProviderConnection, ...
   ```

6. **Test impact:** Tests instantiate `PersistentStore(in_memory=True)`
   directly. They don't care about the internal structure — as long as the
   class exposes the same methods, all 984 tests pass unchanged. This is the
   beauty of the mixin approach.

### Suggested file structure

```
a_cal/db/
  store.py          (~250 lines: class def, __init__, _seed_if_empty, _session)
  store_utils.py    (~20 lines: _uid, USER_ID)
  store_mixins/
    __init__.py
    _sub_account.py  (~80 lines: SubAccountMixin + _serialize_sub_account)
    _provider.py     (~160 lines: ProviderMixin + _serialize_provider)
    _calendar.py     (~160 lines: CalendarMixin + _serialize_event)
    _sync_rules.py   (~50 lines: SyncRuleMixin + _serialize_sync_rule)
    _settings.py     (~55 lines: SettingsMixin + ApiKeyMixin)
    _self_model.py   (~100 lines: SelfModelMixin + NegotiationMixin)
    _event_types.py  (~190 lines: EventTypeMixin + _serialize_event_type)
    _bookings.py     (~130 lines: BookingMixin)
    _email.py        (~280 lines: EmailMixin)
    _teams.py        (~180 lines: TeamMixin + TeamMemberMixin)
    _webhooks.py      (~185 lines: WebhookMixin)
```

### Verification

```bash
.venv/bin/python -m pytest tests/ -q          # expect 984 passed, 9 skipped
ruff check a_cal/ tests/                        # expect clean
cd web && npx tsc --noEmit                      # expect clean
```

---

## File 2: `a_cal/agents/standalone_responses.py` (1359 lines)

### What this file is

A collection of pure-Python response generators that produce useful,
interactive responses when no LLM is available (standalone mode). The
conductor calls `generate_standalone_response()` as its fallback.

### The public interface contract

**Production code imports:**
- `a_cal/agents/conductor.py:36` — `from a_cal.agents.standalone_responses import generate_standalone_response`

**Test code imports:**
- `tests/test_event_actions.py:19` — `generate_standalone_response`, `_detect_event_action`
- `tests/test_event_actions.py:311,331,353` — `_handle_list_events`
- `tests/test_connect_and_self_model.py:17` — `_parse_connect_request`, `generate_sync_response`, `generate_standalone_response`
- `tests/test_self_model_integration.py:18` — `_extract_self_model_prefs`, `_rank_slots_by_prefs`, `generate_schedule_response`, `_handle_create_event`

The cleanest approach: extract sub-modules and have `standalone_responses.py`
re-export everything so existing imports keep working. But it's even
cleaner to update the test imports to point at the new sub-modules. Your
choice — both work, but re-exporting is lower risk for the first pass.

### Function map (line numbers in the current file)

| Group | Lines | Functions | Suggested module |
|---|---|---|---|
| Parsing helpers | 28-233 | `_parse_datetime`, `_parse_duration`, `_parse_time_preference`, `_parse_specific_time`, `_parse_event_title`, `_detect_event_action` | `_parsing.py` (~205 lines) |
| Self-model + slot helpers | 235-417 | `_extract_self_model_prefs`, `_rank_slots_by_prefs`, `_find_free_slots` | `_slots.py` (~182 lines) |
| Event handlers | 418-800 | `_handle_create_event`, `_handle_reschedule_event`, `_handle_delete_event`, `_handle_list_events` | `_event_handlers.py` (~382 lines) |
| Generate functions | 801-1359 | `generate_schedule_response`, `_parse_connect_request`, `generate_sync_response`, `generate_email_response`, `generate_negotiate_response`, `generate_self_model_response`, `generate_chat_response`, `generate_standalone_response` | stays in `standalone_responses.py` (~558 lines) |

Wait — that leaves `standalone_responses.py` at 558 lines, which is under
800. But the event handlers at 382 are also fine. The parsing module at 205
and slots at 182 are small. This split produces four files all well under
the limit.

### Suggested file structure

```
a_cal/agents/
  standalone_responses.py  (~560 lines: all generate_* functions + re-exports)
  _parsing.py              (~205 lines: _parse_* and _detect_event_action)
  _slots.py                (~182 lines: _extract_self_model_prefs, _rank_slots_by_prefs, _find_free_slots)
  _event_handlers.py       (~382 lines: _handle_create_event, _handle_reschedule_event, _handle_delete_event, _handle_list_events)
```

### Critical details

1. **Inter-module dependencies:** The `generate_*` functions in
   `standalone_responses.py` call the parsing, slot, and event-handler
   functions. After extraction, `standalone_responses.py` must import them:
   ```python
   from a_cal.agents._parsing import _detect_event_action, _parse_datetime, ...
   from a_cal.agents._slots import _extract_self_model_prefs, _rank_slots_by_prefs, ...
   from a_cal.agents._event_handlers import _handle_create_event, _handle_list_events, ...
   ```

2. **`_event_handlers.py` depends on `_parsing.py` and `_slots.py`:**
   `_handle_create_event` calls `_parse_datetime`, `_parse_event_title`,
   `_parse_duration`, `_rank_slots_by_prefs`, `_find_free_slots`, etc. So
   `_event_handlers.py` imports from both `_parsing.py` and `_slots.py`.

3. **`TYPE_CHECKING` import:** The module uses
   `from typing import TYPE_CHECKING` with `if TYPE_CHECKING:` to import
   `IntentType` and `RoutingDecision` from `conductor.py` (avoids circular
   import). Keep this in `standalone_responses.py` since the `generate_*`
   functions type-hint `RoutingDecision`. The sub-modules don't need it
   (they work with plain dicts and strings).

4. **Re-export strategy:** To avoid touching test imports, add re-exports at
   the bottom of `standalone_responses.py`:
   ```python
   # Re-export for backward compatibility with test imports
   from a_cal.agents._parsing import _detect_event_action, _parse_connect_request
   from a_cal.agents._slots import _extract_self_model_prefs, _rank_slots_by_prefs
   from a_cal.agents._event_handlers import _handle_create_event, _handle_list_events
   from a_cal.agents._parsing import _parse_connect_request
   ```
   Or update the test imports directly — cleaner, but more files to touch.

5. **`generate_schedule_response` dispatches to event handlers:** It calls
   `_detect_event_action`, `_extract_self_model_prefs`,
   `_handle_list_events`, `_handle_create_event`, etc. After extraction,
   these are imported at the top of `standalone_responses.py`.

### Verification

Same as File 1:
```bash
.venv/bin/python -m pytest tests/ -q
ruff check a_cal/ tests/
cd web && npx tsc --noEmit
```

---

## Execution Order

1. **Split `store.py` first** — it's the bigger file and the higher-risk
   change (every route module depends on it). Do it, verify, commit.
2. **Split `standalone_responses.py` second** — lower risk (only conductor
   + tests depend on it), and you'll have confidence from the first split.
3. **Push and update PR #4** (or open a new PR if #4 has merged).

## Conventions (unchanged)

- Conventional Commits (`refactor:` prefix for these)
- Never push to `origin/main` (protected)
- `pnpm` for frontend, `pip`/`pyproject.toml` for backend
- No `any` in TS; JSDoc/docstrings on new functions
- Never `rm -rf`, never expose secrets
- Run `ruff check a_cal/ tests/` and `pytest tests/ -q` after every change
