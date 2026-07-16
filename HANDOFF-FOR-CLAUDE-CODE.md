# Handoff for Claude Code — A-Cal Hardened Launch (Post-Merge)

> Written by Codex on 2026-07-15, after merging PR #5 to `origin/main`.
> The previous handoff (`HANDOFF-FOR-CODEX.md`) gave Codex a security/hardening
> work list. This handoff reports what was done, asks you to verify it, and
> identifies what remains to get the project fully operational.

---

## 0. Context

A-Cal is an agentic, self-hostable calendar + email platform. Backend: Python
3.11 / FastAPI / SQLAlchemy / SQLite|Postgres in `a_cal/`. Frontend: Next.js 15
/ React 19 in `web/`. Repo root: `/Users/christophervaughn/Documents/A-Cal/a-cal`.

All work from the prior handoff's Work Items (P0-1 through P3-2) was already
completed in earlier commits. This handoff covers the **security hardening and
E2E CI fix** that Codex did on top of that, merged via PR #5.

**Current baseline (all on `origin/main`, commit `89827a4`):**
- `python -m pytest tests/ -q` → **996 passed, 9 skipped, 0 failed**
- `ruff check a_cal/ tests/` → **clean**
- `cd web && pnpm typecheck && pnpm build` → **clean**
- `cd web && pnpm test:e2e` (CI) → **82 passed, 0 failed**
- GitHub Actions CI: **all 5 jobs green** (Python Tests, Python Lint, Frontend
  Build + Typecheck, Frontend Typecheck, E2E Tests)

---

## 1. What Codex Did (verify all of this)

### 1.1 Auth wall (`a_cal/auth/session.py`)
- Added `AuthMiddleware` (pure-ASGI, ordered after `SessionMiddleware`) that
  401s any path not in `_PUBLIC_PATHS` when there's no session cookie. Public
  paths: `/health`, `/docs`, `/openapi.json`, `/redoc`, auth endpoints
  (register/login/logout/me/demo-login), public booking, OAuth callbacks,
  marketplace browse.
- The contextvar default stays `"local-dev-user"` (reverting it to `None` broke
  ~60 tests). The **wall** is the gate, not the contextvar.
- `get_current_user_id()` raises `HTTPException(401)` when called as a
  dependency and no user is resolved.
- **Verify:** `tests/test_auth_wall.py` (12 tests) covers 401 without session,
  public path access, post-login access, lockout escalation, register cap,
  secret enforcement refusal.

### 1.2 Session secret enforcement (`a_cal/auth/session.py` + `a_cal/api/standalone.py`)
- `assert_secure_session_secret()` runs in a FastAPI lifespan (`_lifespan`).
  Refuses boot with the public dev default unless
  `A_CAL_ALLOW_INSECURE_DEV_SECRET=1`.
- Cookie `secure` flag derives from `A_CAL_BASE_URL` (HTTPS → secure cookie).
- **Verify:** boot the app with the dev secret and no allow flag → RuntimeError.
  With a real secret or the allow flag → boots fine.

### 1.3 Rate limiting — DB-backed, no new dependency (`a_cal/auth/session.py` + `a_cal/db/models.py`)
- `AuthAttempt` model (`a_cal_auth_attempts` table) tracks failed logins and
  registrations by key (email for login, IP for register).
- Email-keyed escalating login lockout: no lockout until 5 failures, then
  doubling lockout windows (60s, 120s, 240s, ...).
- Per-IP register cap: configurable via `A_CAL_REGISTER_MAX_PER_IP` (default 5)
  and `A_CAL_REGISTER_WINDOW` (default 24h).
- **Verify:** `tests/test_auth_wall.py` tests lockout escalation, lock after
  repeated failures, counter reset on success, register cap enforcement.

### 1.4 OAuth state — stateless HMAC (`a_cal/providers/oauth.py`)
- Replaced the in-memory `_state_store` dict with stateless HMAC tokens
  (`sign_state` / `validate_state`). Format: `base64url(payload).base64url(hmac)`,
  signed with the session secret, constant-time compare.
- Survives restarts and works across multiple workers (the old in-memory store
  broke both).
- **Verify:** `tests/test_oauth.py` uses `sign_state` for state generation.

### 1.5 Demo-login gating (`a_cal/api/standalone.py`)
- The `/api/a-cal/auth/demo-login` endpoint is only mounted when
  `A_CAL_ENABLE_DEMO=1`. Off by default.

### 1.6 Demo sub-account seeding (`a_cal/api/standalone.py`)
- `_seed_demo_sub_accounts()` seeds four default sub-accounts (Main Calendar,
  Work Google, Personal, Email Inbox) when a demo user is first created.
  UUID-based IDs to avoid colliding with `local-dev-user`'s hardcoded IDs.
- This was needed because the demo user gets a fresh empty account; E2E tests
  expect the sidebar to show sub-accounts.

### 1.7 SQLite busy_timeout (`a_cal/db/models.py`)
- Added `PRAGMA busy_timeout=5000` alongside the existing `PRAGMA journal_mode=WAL`
  in the event listener. Concurrent writers now wait up to 5s instead of
  immediately throwing "database is locked".

### 1.8 Schema upgrade — dialect-aware (`a_cal/db/schema_upgrade.py`)
- `_column_exists()` now uses `inspect(conn).get_columns()` instead of
  `has_column()` (which doesn't exist in SQLAlchemy 2.0.51). Works on both
  SQLite and Postgres.

### 1.9 Postgres migration entrypoint (`scripts/migrate-and-start.sh` + `Dockerfile.backend`)
- Container entrypoint runs `alembic upgrade head` when `DATABASE_URL` is set
  (Postgres), then starts the app. SQLite dev mode skips Alembic and relies
  on `create_all` + `upgrade_schema`.
- Dockerfile.backend CMD now calls the script.

### 1.10 Env var canonicalization (`docker-compose.yml`, `.env.example`, `README.md`)
- All env vars canonicalized to `A_CAL_*` prefix:
  `A_CAL_GOOGLE_CLIENT_ID`, `A_CAL_MS_CLIENT_ID` (was `GOOGLE_CLIENT_ID` /
  `OUTLOOK_CLIENT_ID`), `A_CAL_BASE_URL`, `A_CAL_FRONTEND_URL`,
  `A_CAL_SESSION_SECRET`, `A_CAL_ENABLE_DEMO`, `A_CAL_CORS_ORIGINS`,
  `A_CAL_REGISTER_MAX_PER_IP`.

### 1.11 Port/host (`a_cal/api/standalone.py`)
- `__main__` uses `A_CAL_PORT` / `A_CAL_HOST` env vars instead of hardcoded 8000.

### 1.12 E2E CI fix (`.github/workflows/ci.yml` + `web/playwright.config.ts`)
- Playwright webServer command was hardcoded to `.venv/bin/python`, which
  doesn't exist in CI. Changed to `python` when `CI` is set, `.venv/bin/python`
  locally.
- Added `A_CAL_ALLOW_INSECURE_DEV_SECRET=1`, `A_CAL_ENABLE_DEMO=1`,
  `A_CAL_REGISTER_MAX_PER_IP=100000` to the E2E CI env.

### 1.13 Frontend auth gating (`web/app/page.tsx`)
- `loadRealData()` effect was firing on mount before demo-login completed,
  so protected API calls got 401 and the UI stayed empty. Gated the effect on
  auth state (`user`, `authLoading`, `backendDown`).

### 1.14 E2E test authentication (`web/tests/e2e/*.spec.ts`)
- Tests that hit protected API endpoints directly (email-scan-depth,
  proactive-suggestions) now authenticate via demo-login first.
- UI tests that race with auth (sub-accounts, sync-rules, email-depth) now
  wait for the Conductor text before proceeding.

---

## 2. What Remains to Get Fully Operational

### 🔴 Items only the user (Chris) can do

1. **Generate and set `A_CAL_SESSION_SECRET`** for production. The app refuses
   to boot with the dev secret. Generate with:
   `python -c "import secrets;print(secrets.token_urlsafe(48))"`
   Put it in `.env` or your hosting platform's env vars. This is the single
   most important production step.

2. **Set OAuth credentials** (`A_CAL_GOOGLE_CLIENT_ID`, `A_CAL_GOOGLE_CLIENT_SECRET`,
   `A_CAL_MS_CLIENT_ID`, `A_CAL_MS_CLIENT_SECRET`) in `.env` if you want real
   calendar/email sync. Without these, OAuth login buttons appear but silently
   stay unconfigured.

3. **Set `A_CAL_CORS_ORIGINS`** to your real frontend domain(s) in production.
   Default is localhost only.

4. **Set `A_CAL_BASE_URL` and `A_CAL_FRONTEND_URL`** to your real domains in
   production. OAuth redirect URIs and the cookie `Secure` flag depend on these.

5. **Choose database backend.** SQLite is fine for single-user/low traffic.
   For real multi-user concurrency, use Postgres:
   `docker compose --profile postgres up --build` with `DATABASE_URL` set.
   The migrate-and-start entrypoint handles alembic automatically.

6. **Decide on `A_CAL_ENABLE_DEMO`.** Set to `1` only if you want the demo-login
   backdoor. Off by default (correct for production).

7. **Decide on `A_CAL_ENABLE_PLUGINS`.** Plugins run arbitrary Python in-process.
   Only enable for trusted single-operator deployments. Off by default.

### 🟠 Code/infra work Claude Code should evaluate

1. **Single-worker uvicorn.** The app still runs `uvicorn.run(app, ...)` with
   no `--workers` flag. For production, consider running behind gunicorn with
   uvicorn workers, or a reverse proxy. The stateless OAuth state (fixed) and
   DB-backed rate limiting (fixed) are now worker-safe, so this is purely an
   ops/config change, not a code blocker.

2. **Oversized files still over the 800-line project rule:**
   - `a_cal/db/store.py` — 1946 lines
   - `a_cal/agents/standalone_responses.py` — 1359 lines
   - `web/components/email-panel.tsx` — 1849 lines
   - `web/components/settings-panel.tsx` — 1607 lines
   - `web/lib/api.ts` — 1469 lines
   - `web/components/calendar-view.tsx` — 1022 lines
   The previous handoff's P2-3 (split oversized files) was partially done —
   `standalone_data.py`, `agent_routes.py`, and routes were split, but the
   above remain. Evaluate whether splitting these is worth the churn vs.
   leaving them as stable working code.

3. **Alembic migration coverage.** There are only 3 migration files
   (`alembic/versions/0001-0003`). Recent model additions (e.g. `AuthAttempt`
   table, any new columns from the isolation/hardening work) rely on
   `create_all` + `upgrade_schema` for SQLite and may not have corresponding
   Alembic migrations. If deploying to Postgres, verify that `alembic upgrade
   head` creates all tables. Consider generating a migration that captures the
   current schema state: `alembic revision --autogenerate -m "sync schema"`.

4. **Frontend Dockerfile bakes `A_CAL_API_URL` at build time?** The
   `next.config.mjs` rewrites read `process.env.A_CAL_API_URL` at runtime
   (server-side), so the Docker frontend should work with
   `A_CAL_API_URL=http://backend:8000`. But verify this actually resolves at
   runtime in the container — Next.js `rewrites()` runs server-side, so it
   should be fine. Flag if not.

5. **No HTTPS/TLS termination.** The app sets cookie `secure` based on
   `A_CAL_BASE_URL`, but there's no TLS config in the Dockerfiles. Production
   needs a reverse proxy (nginx, Caddy, Cloudflare) for HTTPS. This is an ops
   concern, not a code fix.

6. **E2E test for auth wall in CI.** The Python `test_auth_wall.py` covers the
   auth wall at the unit level, but there's no E2E test that verifies a
   browser-side user hitting a protected route without a session gets the
   login panel (the `auth-flow.spec.ts` tests cover login/logout, but not the
   "protected route 401 → login panel" flow specifically). Consider adding one.

### 🟡 Nice-to-haves (low priority)

1. **Node.js version in CI.** GitHub Actions warns that Node 20 actions are
   deprecated and forces Node 24. The CI workflows use `actions/checkout@v4`,
   `actions/setup-node@v4`, etc. which target Node 20. Update to newer action
   versions or accept the forced Node 24.

2. **Frontend Dockerfile uses `node:20-slim`** while CI uses Node 22.
   Align these for consistency.

3. **`web/Dockerfile` installs with `pnpm install --frozen-lockfile || pnpm
   install`** — the fallback to non-frozen install hides lockfile drift.
   Consider making the lockfile mandatory.

---

## 3. Suggested Next Steps (in order)

1. **Verify the hardening** — read `a_cal/auth/session.py` (auth wall,
   lockout, secret enforcement), `a_cal/providers/oauth.py` (stateless state),
   `a_cal/api/standalone.py` (lifespan, demo gating, seeding). Run the test
   suite. Boot the app without the allow flag to confirm the secret refusal.

2. **Check Alembic migration coverage** — run `alembic revision --autogenerate`
   against a fresh SQLite DB and see if it produces an empty migration (meaning
   migrations are in sync) or a diff (meaning there are unmigrated tables/
   columns). If there's a diff, create the migration.

3. **Decide on oversized file splits** — the store.py (1946 lines) and
   standalone_responses.py (1359 lines) are the biggest offenders. Evaluate
   whether splitting them now is worth the risk vs. leaving them as stable
   working code that's already tested.

4. **Add a production-readiness checklist** to the README — the items in
   section 2.1 (secret, OAuth, CORS, URLs, database, demo, plugins) as a
   concrete pre-launch checklist.

5. **Complete any of the 🟠 items** above that you judge worth doing.

---

## 4. Conventions (from `CLAUDE.md`, still in force)

- `.venv/bin/python -m pytest tests/ -q` is the test command.
- `cd web && pnpm typecheck && pnpm build` is the frontend check.
- `ruff check a_cal/ tests/` for linting.
- Conventional Commits for all git operations.
- `origin/main` is protected — create a feature branch, push, open a PR.
- The user (Chris/iamalverda) has write access and can approve PRs.
- The venv is at `.venv/` (system `python` is not on PATH).
- Tests share a single in-memory SQLite DB (module-level engine singleton), so
  test ordering matters. The register cap must stay high in conftest
  (`A_CAL_REGISTER_MAX_PER_IP=100000`) to avoid cross-test 429s.
- `A_CAL_ALLOW_INSECURE_DEV_SECRET=1` and `A_CAL_ENABLE_DEMO=1` are set in
  `tests/conftest.py` for the test suite.

---

## 5. Key Files to Read

| File | What's there |
|------|-------------|
| `a_cal/auth/session.py` | AuthMiddleware, lockout, secret enforcement, register cap |
| `a_cal/api/standalone.py` | Lifespan, demo gating, demo seeding, CORS, port/host |
| `a_cal/providers/oauth.py` | Stateless HMAC OAuth state |
| `a_cal/db/models.py` | AuthAttempt model, busy_timeout pragma |
| `a_cal/db/schema_upgrade.py` | Dialect-aware column existence check |
| `scripts/migrate-and-start.sh` | Postgres alembic entrypoint |
| `.github/workflows/ci.yml` | CI with E2E env vars |
| `web/playwright.config.ts` | Portable python command for webServer |
| `web/app/page.tsx` | Auth-gated data loading |
| `tests/test_auth_wall.py` | 12 tests covering the auth wall |
| `tests/_authclient.py` | Shared authenticated TestClient helper |
| `tests/conftest.py` | Test env vars, authed_client fixture |
| `docker-compose.yml` | Canonical A_CAL_* env vars |
| `.env.example` | Production config reference |
