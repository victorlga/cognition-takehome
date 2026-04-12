# Phase 6 — Loom Video & Final Polish

> **Before starting, load the Devin Playbook `cognition-takehome-prompting-playbook` and follow it throughout this session.**

**Depends on:** PHASE_5 complete (verify via CHANGELOG.md entry "Integration verified and demo materials prepared")

---

## Goal

Record the 5-minute Loom video presenting the system to a VP of Engineering + senior ICs. Submit the final deliverables.

---

## Inputs to Read

1. `CHANGELOG.md` — read the entire file, all phases
2. `docs/TAKEHOME.md` — deliverables list and submission link
3. `docs/PLAN.md` — for the narrative structure
4. `docs/ARCHITECTURE.md` — for the technical walkthrough
5. Phase 5 screenshots and demo materials

---

## Note

This phase is primarily **manual work for Victor**. Devin can help prepare talking points, review the script, and ensure all artifacts are ready, but the Loom recording itself is done by Victor.

---

## Video Structure (5 minutes total)

### Segment 1: What — Problem Framing (60 seconds)

**Talking points:**
- "Security vulnerabilities in large codebases are discovered faster than teams can fix them"
- "Apache Superset: 60k+ stars, complex Python/React codebase, active security issue backlog"
- "What if we could automate the entire remediation pipeline — from triage to tested fix?"
- "This is an event-driven vulnerability remediation system powered by the Devin API"

**On screen:** GitHub issue tracker showing the security issues, fork project board

### Segment 2: How — System Walkthrough (150 seconds)

**Talking points:**
- Architecture overview (show Mermaid diagram or simplified version)
- "The system polls for label changes on GitHub issues — zero webhook setup, just `docker compose up`"
- Demo the flow:
  1. Show an issue in Backlog
  2. Move to Planning → show the planner Devin session starting
  3. Show the remediation plan posted as an issue comment
  4. Move to Building → show the builder Devin session
  5. Show the PR with the fix + tests
  6. Show the reviewer Devin session approving
  7. Show the merged PR
- "All orchestrated by a lightweight FastAPI backend — here's the poller, the state machine, the Devin API client"
- Show the dashboard: "An engineering leader can see at a glance: N issues remediated, X% success rate, Y-hour median time-to-fix"
- "The system also runs periodic scans to discover new vulnerabilities automatically"

**On screen:** Live demo of the orchestrator, Devin sessions, PRs, dashboard

### Segment 3: Why — Why Devin (60 seconds)

**Talking points:**
- "Devin isn't just a code generator — it's a full engineering agent"
- "Each role in the pipeline — planner, builder, reviewer — is a Devin session with a specialized prompt"
- "Sessions can read code, understand context, write tests, open PRs, respond to review comments"
- "This is what 'Devin as a primitive' means: composable, parallelizable engineering sessions"
- "The orchestrator is ~500 lines of Python. The real power is in what Devin does with each session."

### Segment 4: When — Next Steps (30 seconds)

**Talking points:**
- "Next steps: expand to multiple repos, integrate with SAST pipelines, production hardening"
- "Add SLA tracking: 'all critical vulnerabilities remediated within 24 hours'"
- "Scale to enterprise: Devin fleet management, priority queuing, approval workflows"
- "This pattern generalizes: any event-driven engineering workflow can be built this way"

---

## Pre-Recording Checklist

- [ ] Docker Compose running, system healthy
- [ ] Dashboard showing real data from remediation work
- [ ] GitHub Project board in final state (items in Done)
- [ ] At least one issue ready to demo the live flow (or use a recording of a previous run)
- [ ] Browser tabs pre-opened:
  - Fork issues page
  - Project board
  - A representative PR
  - Dashboard
  - Architecture diagram
  - Devin session (if available)
- [ ] Screen recording software ready
- [ ] Talking points reviewed

---

## Submission Checklist

- [ ] Loom video recorded (≤ 5 minutes)
- [ ] Video covers: What, How, Why, When
- [ ] Solution repo: `github.com/victorlga/cognition-takehome`
  - [ ] README with setup instructions
  - [ ] Docker Compose works
  - [ ] All planning docs in `docs/`
- [ ] Fork: `github.com/victorlga/superset`
  - [ ] Issues created and remediated
  - [ ] PRs merged with tests
  - [ ] Project board visible
- [ ] Submit via: https://you.ashbyhq.com/cognition/assignment/7d73bea9-c7d7-417a-99a6-6138d6a37bdb

---

## Definition of Done

- Loom video submitted
- All deliverables accessible to the reviewers
- CHANGELOG complete with all phases documented

---

## CHANGELOG Entry Template

```markdown
## [PHASE_6] — YYYY-MM-DD — Loom video recorded and submitted

**What changed:**
- Recorded 5-minute Loom video
- Submitted via Ashby
- Final polish on README and docs

**Files touched:**
- `README.md` (final polish)
- `CHANGELOG.md` (appended this entry)

**How it was verified:**
- Video plays correctly, covers all 4 segments
- All links in submission are accessible
- Docker Compose verified one final time

**What the next phase needs to know:**
- N/A — this is the final phase

**Open questions / known gaps:**
- [any post-submission notes]
```
