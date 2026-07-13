# Changelog

All notable changes to A-Cal are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and this project adheres
to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Marketplace trust & moderation system
  - Content hashing (deterministic SHA-256 over item config) for tamper detection
  - Trust scoring (0-100) from ratings, verification status, and flag count
  - Flagging system: users can flag items; 3+ unresolved flags auto-marks as flagged
  - Verification system: moderators/admins can verify items
  - 5 new API endpoints: flag, get flags, resolve flag, verify, get trust info
  - Frontend trust badges (Verified / Flagged / Trust: NN) and flag button with
    reason form on marketplace item cards
  - TypeScript types: VerificationStatus, FlagRecord, trust fields on MarketplaceItem
  - 27 Python tests + 4 E2E tests for the trust system

### Fixed
- Remixed marketplace items now compute content hash (both in-memory and persistent
  store). Previously remixed items had empty content_hash fields.
- E2E email-depth test race condition: waitForResponse now filters for POST method
  only, preventing it from catching the initial GET settings load

## [0.1.0] — 2026-07-12

### Added
- Agentic calendar platform with conductor + federated swarm agent system
  - 6 specialist agents (conductor, schedule, sync, email, negotiate, self-model)
  - Keyword + LLM intent classification with plugin override support
  - Bio-mimetic nervous system (10 CAS modules: thalamus gate, RAS, basal
    ganglia, hippocampus, insula, etc.)
  - Hybrid mode: rule-based actions execute real calendar operations, then
    LLM crafts natural language response with anti-hallucination guardrails
- Sub-account model with 4 sync modes
  - Mirror + filter (default), intelligent merge, layered federation,
    per-sub-agent + merge
  - Per-sub-account configuration (not just global)
  - Sync rules with include/exclude/transform patterns
- Model routing (BYOK)
  - 12 providers: Ollama, OpenAI, Anthropic, Gemini, Azure, DeepSeek,
    Together, Groq, OpenRouter, Mistral, LM Studio, llama.cpp
  - Privacy-tiered routing forces email/self-model/negotiation to local
  - Global + per-task model overrides
- Email integration
  - OAuth for Gmail/Outlook, IMAP/SMTP for any provider
  - 3 depth levels: sync_notify, agent_mediated, full_two_way
  - Email-to-schedule pipeline with LLM-powered suggestions
- Interaction
  - Contextual command bar (Cmd+K)
  - Persistent conductor chat panel
  - Voice input via Web Speech API
  - Proactive suggestions with priority-tiered ranking
- Three skill modes (Simple / Pro / Developer) with progressive disclosure
- Developer Studio
  - Visual workflow builder with JSON export/import
  - Plugin system with 8 supported hooks and 8 example plugins
  - Agent spec editor (create custom specialists)
  - Config-as-code (full export/import)
  - API Explorer (browse 127 endpoints interactively)
  - TypeScript SDK covering all REST endpoints
- Community marketplace
  - Browse, search, install, remix, and rate shared configs
  - 6 item types: agent_spec, sync_rule_pack, negotiation_strategy,
    ui_theme, plugin_config, workflow
  - Provenance metadata and remix chains
  - Mode-tiered discovery (Simple sees curated, Pro sees all)
- User authentication
  - Session-based auth with PBKDF2 password hashing
  - Register, login, logout, /me endpoints
  - Multi-user data isolation (per-user_id filtering)
  - Demo auto-login for standalone/dev mode
- PWA support (installable, offline service worker, app manifest)
- Mobile responsive layout
- Docker self-hosting (docker compose up, PostgreSQL profile)
- CI/CD pipeline (GitHub Actions: Python tests, frontend build, E2E, lint)
- CalDAV integration (tested against Radicale)
- Calendar analytics (event counts, busy patterns, meeting distribution)
- Timezone-aware scheduling
- 4 workflow templates (daily briefing, conflict resolver, focus time
  protector, weekly review)

### Tested
- 829 Python tests passing (2 skipped)
- 79 E2E tests passing (Playwright)
- TypeScript typecheck clean
- Next.js build passes
- Ruff linting clean
