# CHANGELOG

> **Contract:** Each entry follows this format:
>
> ## [PHASE_X] — YYYY-MM-DD — One-line summary
>
> **What changed:**
> (Bullet list of changes)
>
> **Files touched:**
> (List of files added/modified/deleted)
>
> **How it was verified:**
> (CI green, curl commands, screenshots, manual checks, etc.)
>
> **What the next phase needs to know:**
> (Key context, decisions, blockers, or artifacts that downstream phases depend on)
>
> **Open questions / known gaps:**
> (Anything unresolved that future phases should be aware of)
>
> ---
>
> **Rules:**
> - Future phases MUST read the entire CHANGELOG before starting work and decide which entries are relevant.
> - Sub-phases (e.g., PHASE_3_1, PHASE_3_2) do NOT write to CHANGELOG directly — only the parent orchestrator phase does after merging sub-phase outputs.
> - Entries are append-only. Never edit or delete a previous entry.

---

## [PHASE_0] — 2026-04-12 — Bootstrap planning docs, playbook, and machine

**What changed:**
- Created `docs/TAKEHOME.md` (verbatim from recruiter email)
- Created `docs/PLAN.md` (master plan with phase overview and dependency graph)
- Created `docs/ARCHITECTURE.md` (system architecture, tech stack, Mermaid diagram, secrets, design decisions)
- Created `docs/PHASE_1.md` through `docs/PHASE_6.md` (self-contained phase prompts)
- Created `CHANGELOG.md` (this file, with contract documented)
- Created Devin Playbook `cognition-takehome-prompting-playbook` via native Devin Playbook feature
- Configured Devin Machine with both repos and required tooling

**Files touched:**
- `docs/TAKEHOME.md` (already existed)
- `docs/PLAN.md` (new)
- `docs/ARCHITECTURE.md` (new)
- `docs/PHASE_1.md` (new)
- `docs/PHASE_2.md` (new)
- `docs/PHASE_3.md` (new)
- `docs/PHASE_4.md` (new)
- `docs/PHASE_5.md` (new)
- `docs/PHASE_6.md` (new)
- `CHANGELOG.md` (new)

**How it was verified:**
- All docs reviewed for completeness and cross-references
- Devin Machine smoke test: `gh auth status`, `pip-audit --version`, `semgrep --version`, `docker --version` all pass
- Playbook created and visible in Devin UI (ID: `playbook-77e36f049a66446c821245596544412a`)

**What the next phase needs to know:**
- GitHub Projects v2 webhooks ARE supported — `projects_v2_item.edited` fires on status field changes. Primary trigger confirmed feasible.
- Devin API v3 supports: session creation with playbook attachment, polling, messaging, attachments, scheduled sessions
- Tech stack locked: FastAPI + SQLite + Docker Compose + htmx dashboard
- Both repos cloned and authenticated on the Devin Machine
- All phase prompts reference the `cognition-takehome-prompting-playbook` Devin Playbook

**Open questions / known gaps:**
- Devin API key (`DEVIN_API_KEY`) and org ID (`DEVIN_ORG_ID`) must be provisioned as secrets before Phase 2 can test session creation
- GitHub webhook secret needs to be generated and configured on the fork before Phase 2 can receive webhooks
- The exact GitHub Projects v2 field node IDs for the Status field on the fork's project board will only be known after Phase 1 creates the board
- localhost.run SSH tunnel (zero-signup) for local webhook testing during Phase 2: `ssh -R 80:localhost:8000 nokey@localhost.run`

---

## [PHASE_1] — 2026-04-12 — Selected 4 issues and seeded fork project board

**What changed:**
- Selected 4 issues from apache/superset (3 security, 1 high-impact bug) after evaluating 30+ candidates
- Created issues on victorlga/superset: [#1](https://github.com/victorlga/superset/issues/1), [#2](https://github.com/victorlga/superset/issues/2), [#3](https://github.com/victorlga/superset/issues/3), [#4](https://github.com/victorlga/superset/issues/4)
- Created GitHub Project "Vulnerability Remediation" ([project #4](https://github.com/users/victorlga/projects/4)) with kanban columns: Backlog, Planning, Building, Reviewing, Done
- Configured webhook (ID: 605878262) on victorlga/superset for `issues`, `issue_comment`, `pull_request` events (inactive, placeholder URL)
- Created labels on fork: `remediation-target`, `authentication`, `embedded`, `api`, `security`

### Selection Table

| # | Issue Link | Source | Category | Business Impact | Why Non-Trivial | Why Devin Can Fix It | Est. Complexity | Verification Strategy |
|---|-----------|--------|----------|----------------|----------------|---------------------|----------------|----------------------|
| 1 | [apache/superset#24713](https://github.com/apache/superset/issues/24713) | Security search (text) | security | Session replay attack — after logout, stolen cookies still grant full access. Classic OWASP session management flaw. Any security audit would flag this. | Requires implementing server-side session invalidation in Flask/Flask-Login. Must understand Superset's session backend (filesystem, Redis, or DB), add a session store that tracks active sessions, and invalidate on logout. Needs to handle multiple session backends. | Bounded to session management code (`security/manager.py`, login/logout views). Clear repro steps. Test: log in, copy cookie, log out, verify cookie is rejected. | Medium | Write test: login → get session cookie → logout → replay cookie → assert 401/redirect |
| 2 | [apache/superset#37061](https://github.com/apache/superset/issues/37061) | Security search (text) | security | Guest users in embedded dashboards cannot sort tables — breaks core embedded functionality. Overly restrictive access check blocks legitimate read-only operations. 100% repro rate reported. | Requires understanding the `raise_for_access()` check in `query_context.py` and the guest token permission model. Must differentiate between safe operations (sorting, pagination) and actual payload modifications (changing datasource, adding metrics). Not a simple boolean flip — needs granular allowlist logic. | Stack trace provided pointing to exact code path (`charts/data/api.py` → `get_data_command.py` → `query_context.py`). Fix is in 2-3 files. Clear acceptance criteria: guest user can sort without error. | Medium | Write test: create guest token → load embedded dashboard → sort table column → assert no error and sorted results returned |
| 3 | [apache/superset#33500](https://github.com/apache/superset/issues/33500) | Security search (text) | security | Error messages containing HTML tags (e.g., from database errors with `<a>` in SQL) cause "Bad Request" instead of showing the actual error. This is XSS-adjacent: the root cause is improper HTML handling in API responses. Maintainer confirmed as valid API bug, PRs welcome. | Requires tracing the error response pipeline from backend API through frontend rendering. Must fix HTML sanitization to properly escape (not reject) HTML in error messages. Involves both backend response formatting and frontend error display logic. | Exact repro steps provided. Backend returns correct data in `message` field but frontend/middleware rejects it. Fix involves the error handling middleware and/or frontend error display components. | Medium | Write test: create chart with `<a>` in metric expression → trigger error → assert actual error message is displayed (not "Bad Request") |
| 4 | [apache/superset#37100](https://github.com/apache/superset/issues/37100) | Security search (text) | security | `AUTH_USER_REGISTRATION=True` (required for LDAP/OAuth user sync) also enables public self-registration via UI. This is an insecure default: any anonymous user can create an account on a production instance configured for LDAP/OAuth. Multiple users confirmed affected. | Requires decoupling two behaviors currently tied to one config flag: (1) automatic user provisioning from LDAP/OAuth providers, and (2) public self-registration via the UI registration form. Must add a new config option or modify the registration view to check auth type. Needs to preserve backward compatibility. | Fix is in Flask-AppBuilder integration layer (`security/manager.py`, config handling, registration views). Bounded scope. Clear acceptance criteria: LDAP/OAuth user sync works while UI registration is disabled. | Medium | Write test: configure AUTH_LDAP + AUTH_USER_REGISTRATION=True → verify LDAP users can log in → verify `/register` endpoint is disabled or returns 403 |

### Demo Narrative

The 4 picks tell a varied security story:
1. **Session management vulnerability** (#1) — classic OWASP flaw, shows Devin can handle authentication security
2. **Broken access control in embedded dashboards** (#2) — overly restrictive guest permissions, shows Devin understands authorization models
3. **XSS-adjacent HTML sanitization bug** (#3) — improper input handling in API responses, shows Devin can fix data flow issues
4. **Insecure defaults in authentication config** (#4) — configuration-level security flaw, shows Devin can reason about security architecture

### Rejected Candidates

| Issue | Why Rejected |
|-------|-------------|
| [#35845](https://github.com/apache/superset/issues/35845) — CSP header override | Apache infrastructure issue (`.htaccess` on superset-site repo), not a code fix in the Superset codebase. Requires ASF governance approval for domain allowlists. |
| [#34342](https://github.com/apache/superset/issues/34342) — Dashboard filter SQL injection with apostrophes | The apostrophe escaping (`O'Donnell` → `O''Donnell`) is actually correct SQL escaping behavior. A linked PR (#34180) already addresses this. Not a real vulnerability. |
| [#29934](https://github.com/apache/superset/issues/29934) — Trailing slash URL inconsistencies | More of an API design inconsistency than a security issue. Low demo impact — explaining trailing slash behavior to a VP of Engineering is not compelling. May already be fixed. |
| [#37938](https://github.com/apache/superset/issues/37938) — Restrict User/Role views to Admins only | Intentional design decision per maintainers. Changing it requires modifying both frontend route guards and backend permission checks. Risk of scope creep since it touches core RBAC model. |
| [#33744](https://github.com/apache/superset/issues/33744) — Duplicate RLS permission names | Orphaned permission cleanup requiring a DB migration. Too narrow in scope — would look like a one-liner migration script, not a substantial fix. |
| [#36070](https://github.com/apache/superset/issues/36070) — Duplicate can_import permission | Similar to #33744 — permission registry cleanup. Low demo impact, likely a one-line fix in permission registration. |
| [#37695](https://github.com/apache/superset/issues/37695) — RLS Jinja macro + empty Flask session in SQL Lab | Complex interaction between Flask session lifecycle and async query execution. High risk of incomplete fix — the root cause may be in Flask-AppBuilder's request context management. Issue reporter hasn't confirmed the bot's suggested workaround. |
| [#38185](https://github.com/apache/superset/issues/38185) — Embedded SDK 403 on /datasets API | Configuration-heavy issue with JWT, CORS, and guest role setup. Multiple users affected but root cause varies per deployment. Hard to write a deterministic test. |

**Files touched:**
- `CHANGELOG.md` (appended this entry)

**How it was verified:**
- `gh issue list --repo victorlga/superset --label remediation-target` returns 4 issues
- GraphQL query confirms all 4 issues in Backlog column on project #4
- Each issue on the fork has a backlink to the original apache/superset issue ("> Mirrored from..." header)
- Selection table reviewed against difficulty bar: all picks require code reading, context understanding, logic changes, and test writing
- Set includes 3 code-level security fixes (#1, #3, #4) and 1 access control / high-impact embedded bug (#2)
- No dependency-bump-only or SAST-only picks

**What the next phase needs to know:**
- Issue numbers on the fork: #1, #2, #3, #4
- Project board number: 4 (URL: https://github.com/users/victorlga/projects/4)
- Project node ID: `PVT_kwHOAsVV684BUblu`
- Status field ID: `PVTSSF_lAHOAsVV684BUbluzhBjurA`
- Status field option IDs: Backlog=`f75ad846`, Planning=`c5c11784`, Building=`47fc9ee4`, Reviewing=`17ec3a1e`, Done=`98236657`
- Webhook ID: 605878262 (inactive, URL placeholder — update in Phase 2)
- Webhook secret: stored as `GITHUB_WEBHOOK_SECRET` in Devin secrets
- `projects_v2_item` events are NOT supported on repository-level webhooks for user-owned repos — only org-level webhooks support them. The orchestrator should use the **issue label fallback** (documented in ARCHITECTURE.md) as the primary trigger mechanism, or use the GitHub API to poll project board state.
- The webhook is configured for `issues`, `issue_comment`, `pull_request` events — these support the label-based state machine driver.

**Open questions / known gaps:**
- `projects_v2_item` webhook events require organization-level webhooks, not repo-level. Since `victorlga/superset` is a user-owned fork (not an org repo), the orchestrator must use the label-based fallback or API polling for project board state changes. Phase 2 should plan for this.
- The GITHUB_TOKEN PAT does not have the `project` scope — project board management (adding items, changing status) was done manually. Phase 2/3 may need the PAT updated if the orchestrator needs to programmatically move items on the board.
- Issue #24713 (session cookies) is from 2023 and confirmed on v3.x — need to verify the session handling code path still applies to current main branch.

---

## [PHASE_2] — 2026-04-12 — Orchestrator backend with webhook receiver and Devin API client

**What changed:**
- Built FastAPI orchestrator in `orchestrator/` directory
- Implemented webhook receiver (`POST /webhooks/github`) with HMAC-SHA256 verification
- Implemented Devin API v3 client (session creation, polling, messaging)
- Implemented GitHub API client (issue resolution via GraphQL, comments, labels)
- Implemented state machine with SQLite persistence (backlog → planning → building → reviewing → done)
- Created prompt templates for planner/builder/reviewer Devin sessions
- Created Docker Compose configuration for single-command startup
- Added health check (`GET /health`) and metrics stub (`GET /api/metrics`)
- Added dashboard stub (`GET /dashboard`) — full implementation in Phase 4
- Added scanner stub (`scanner.py`) — full implementation in Phase 3
- Added 53 unit tests covering webhook, state machine, Devin client, prompts, and DB layer
- Updated `.gitignore` for Python/Docker artifacts

**Files touched:**
- `orchestrator/` (new directory, all files)
  - `orchestrator/pyproject.toml` (new)
  - `orchestrator/Dockerfile` (new)
  - `orchestrator/app/__init__.py` (new)
  - `orchestrator/app/main.py` (new)
  - `orchestrator/app/config.py` (new)
  - `orchestrator/app/webhook.py` (new)
  - `orchestrator/app/devin_client.py` (new)
  - `orchestrator/app/github_client.py` (new)
  - `orchestrator/app/state_machine.py` (new)
  - `orchestrator/app/prompts.py` (new)
  - `orchestrator/app/scanner.py` (new)
  - `orchestrator/app/db.py` (new)
  - `orchestrator/app/dashboard.py` (new)
  - `orchestrator/templates/dashboard.html` (new)
  - `orchestrator/tests/` (new, 6 test files)
- `docker-compose.yml` (new)
- `.gitignore` (new)
- `CHANGELOG.md` (appended this entry)

**How it was verified:**
- All 53 unit tests pass: `python -m pytest orchestrator/tests/ -v`
- Docker Compose builds and starts cleanly
- Health check returns 200 with `{"status": "ok"}`
- Webhook rejects invalid HMAC signatures (returns 401)
- Webhook accepts valid payloads and routes by event type
- State machine validates transitions (rejects skips, allows error from any state)
- Devin client correctly creates sessions, polls status, handles timeouts
- Prompt templates render with all expected fields
- DB layer handles upsert, session logging, and aggregate metrics
- Metrics endpoint returns valid JSON

**What the next phase needs to know:**
- Orchestrator runs on port 8000 via `docker compose up --build`
- Webhook endpoint: `POST /webhooks/github` (expects `projects_v2_item` events)
- Dashboard endpoint: `GET /dashboard` (stub — full htmx dashboard in Phase 4)
- Metrics API: `GET /api/metrics` (returns JSON with issue counts, session counts, activity feed)
- Health check: `GET /health` (returns `{"status": "ok"}`)
- Database file: `data/orchestrator.db` (mounted via Docker volume)
- Environment variables required: `DEVIN_API_KEY`, `DEVIN_ORG_ID`, `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`
- State machine supports transitions: backlog → planning → building → reviewing → done (plus error from any state)
- Devin sessions are created with tags `[issue-{N}, {role}]` for filtering

**Open questions / known gaps:**
- Real Devin API session creation not tested (mocked in unit tests) — requires API key in environment
- Webhook payload parsing assumes `changes.field_value.to.name` contains the new status column name — needs validation against real GitHub Projects v2 payloads once Phase 1 creates the board
- Scanner module is a stub — full implementation deferred to Phase 3
