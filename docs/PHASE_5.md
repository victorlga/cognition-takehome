# Phase 5 — Integration Test & Demo Prep

> **Before starting, load the Devin Playbook `cognition-takehome-prompting-playbook` and follow it throughout this session.**

**Depends on:** PHASE_3 complete (verify via CHANGELOG.md entry "Remediated N issues") AND PHASE_4 complete (verify via CHANGELOG.md entry "Observability dashboard")

---

## Goal

End-to-end verification of the full pipeline. Prepare all demo artifacts for the Loom recording.

---

## Inputs to Read

1. `CHANGELOG.md` — read the entire file, especially Phases 1–4
2. `docs/TAKEHOME.md` — the full assignment spec (deliverables list)
3. `docs/PLAN.md` — master plan
4. `docs/ARCHITECTURE.md` — full architecture for README reference

---

## Architecture / Business Decisions Already Made

- Docker Compose is the deployment mechanism
- The system must be reproducible: `docker compose up` → working system
- README must be clear enough for a reviewer to reproduce
- Demo materials: screenshots, dashboard, project board, PR diffs

---

## Procedure

### Step 1: Clean Environment Test

```bash
# Stop any running containers
docker compose down -v

# Rebuild from scratch
docker compose up --build -d

# Wait for startup
sleep 5

# Verify health
curl http://localhost:8000/health
```

### Step 2: End-to-End Pipeline Test

Simulate the full workflow:

1. **Create a test issue** on the fork (or use an existing remediated issue)
2. **Move it to Planning** on the project board
3. **Verify** the orchestrator receives the webhook and spawns a planner session
4. **Check** the planner posts a plan as an issue comment
5. **Move to Building** → verify builder session spawns → PR opens
6. **Move to Reviewing** → verify reviewer session spawns → review posted
7. **Move to Done** → verify metrics update

If the full webhook flow isn't working end-to-end, document what works and what requires manual intervention. The demo should show the orchestrator in action even if some steps need a nudge.

### Step 3: Verify Dashboard with Real Data

1. Open `http://localhost:8000/dashboard` in a browser
2. Confirm metrics reflect the actual remediation work from Phase 3
3. Take screenshots:
   - Dashboard overview (full page)
   - Issues by status chart
   - Activity feed
4. Verify auto-refresh works

### Step 4: Verify GitHub Artifacts

1. **Project board**: All issues in correct columns
   ```bash
   gh project view <number> --owner victorlga
   ```
2. **PRs**: All remediation PRs merged
   ```bash
   gh pr list --repo victorlga/superset --state merged
   ```
3. **Issues**: Comment trails show planner → builder → reviewer flow
4. Take screenshots of:
   - Project board in Done state
   - A representative PR diff
   - Issue comment trail showing the flow

### Step 5: Write README

Update `README.md` in `cognition-takehome` with:

```markdown
# Vulnerability Remediation System

An event-driven system that uses the Devin API to automatically plan, fix,
review, and land security fixes on Apache Superset.

## Architecture
[Mermaid diagram from ARCHITECTURE.md]

## Quick Start
1. Clone this repo
2. Copy `.env.example` to `.env` and fill in secrets
3. `docker compose up --build`
4. Configure webhook on your GitHub repo to point to `<host>:8000/webhooks/github`
5. Move an issue to "Planning" on the project board

## How It Works
[Brief description of the kanban → Devin session flow]

## Dashboard
[Screenshot]

## Remediated Issues
[Table of issues with links to PRs]

## Tech Stack
[From ARCHITECTURE.md]

## Project Structure
[Directory tree]
```

### Step 6: Create `.env.example`

```bash
DEVIN_API_KEY=cog_your_key_here
DEVIN_ORG_ID=your_org_id
GITHUB_TOKEN=ghp_your_token_here
GITHUB_WEBHOOK_SECRET=your_webhook_secret
```

### Step 7: Final Checklist

- [ ] `docker compose up --build` works from a clean state
- [ ] Health check passes
- [ ] Webhook receives and processes events
- [ ] Dashboard shows real metrics
- [ ] All remediation PRs are merged on the fork
- [ ] Project board is in final state
- [ ] README is complete with setup instructions
- [ ] `.env.example` exists
- [ ] No secrets committed to the repo
- [ ] All screenshots captured for Loom

---

## Deliverables

- [ ] Verified end-to-end pipeline (documented what works, what needs manual steps)
- [ ] Updated `README.md` with setup instructions and architecture
- [ ] `.env.example` with placeholder values
- [ ] Screenshots: dashboard, project board, PR diffs, issue comments
- [ ] Clean `docker compose up` verified

---

## Test Plan & Verification

1. Fresh `docker compose up --build` starts cleanly
2. All health checks pass
3. Dashboard renders with real data
4. GitHub artifacts (PRs, issues, board) are in expected state
5. README is self-contained enough for a reviewer to understand the system

---

## Definition of Done

- System reproducible via `docker compose up`
- README complete
- All screenshots captured
- Pipeline verified end-to-end (or gaps documented)

---

## CHANGELOG Entry Template

```markdown
## [PHASE_5] — YYYY-MM-DD — Integration verified and demo materials prepared

**What changed:**
- Verified end-to-end pipeline
- Updated README.md with full documentation
- Created .env.example
- Captured all demo screenshots
- [documented any manual steps needed]

**Files touched:**
- `README.md` (updated)
- `.env.example` (new)
- `CHANGELOG.md` (appended this entry)

**How it was verified:**
- Fresh docker compose up works
- Dashboard shows real data
- All PRs merged on fork
- README reviewed for completeness

**What the next phase needs to know:**
- System is ready for the Loom recording
- Dashboard URL: http://localhost:8000/dashboard
- Screenshots stored at: [paths]
- Any caveats for the demo: [list]

**Open questions / known gaps:**
- [list any issues]
```
