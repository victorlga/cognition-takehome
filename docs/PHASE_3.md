# Phase 3 — Issue Remediation (Orchestrator Phase)

> **Before starting, load the Devin Playbook `cognition-takehome-prompting-playbook` and follow it throughout this session.**

**Depends on:** PHASE_1 complete (verify via CHANGELOG.md entry containing issue numbers) AND PHASE_2 complete (verify via CHANGELOG.md entry "Orchestrator backend")

---

## Goal

Drive each seeded issue through the full remediation pipeline (Backlog → Planning → Building → Reviewing → Done) using `state:*` label transitions, the orchestrator, and Devin sessions. This is an **orchestrator phase** that coordinates sub-phases.

---

## Inputs to Read

1. `CHANGELOG.md` — read the entire file. Specifically:
   - PHASE_1 entry: issue numbers on the fork, webhook configuration
   - PHASE_2 entry: orchestrator endpoints, database location
   - PHASE_2_FIX entry: label-based state machine driver, `state:*` label mapping
2. `docs/TAKEHOME.md` — the full assignment spec
3. `docs/PLAN.md` — master plan
4. `docs/ARCHITECTURE.md` — prompt templates, state machine design, label-to-status mapping

---

## Architecture / Business Decisions Already Made

- Each issue is an **independent remediation** on its own branch
- Sub-phases can run in **parallel** (no shared mutable state during execution)
- The orchestrator manages the Devin session lifecycle
- Planner → Builder → Reviewer pipeline per issue
- PRs target `main` on `victorlga/superset`
- Branch naming: `fix/{issue_number}-{slug}`
- State transitions are driven by **`state:*` labels** on issues (not GitHub Projects v2 board columns)
- The webhook fires on `issues` events with `labeled` action; the orchestrator extracts the target status from the label name

---

## Label-to-Status Mapping

| Label Applied | Status Transition | Devin Session Spawned |
|---|---|---|
| `state:planning` | Backlog → Planning | Planner session |
| `state:building` | Planning → Building | Builder session |
| `state:reviewing` | Building → Reviewing | Reviewer session |
| `state:done` | Reviewing → Done | *(none — human merge)* |

---

## Procedure

### Step 1: Verify Prerequisites

```bash
# Confirm orchestrator is running
curl http://localhost:8000/health

# Confirm issues exist on fork
gh issue list --repo victorlga/superset --label remediation-target

# Confirm state:* labels exist on the fork
gh label list --repo victorlga/superset | grep "state:"
```

### Step 2: Start the Pipeline

For each issue, the orchestrator drives the flow. You can either:

**Option A: Use the orchestrator end-to-end** — Apply the `state:planning` label to the issue on `victorlga/superset`. The webhook fires, the orchestrator spawns a planner Devin session. Monitor and advance through each stage by applying the next `state:*` label.

**Option B: Manual orchestration with Devin API** — If the orchestrator has bugs, fall back to manually creating Devin sessions via the API or via separate Devin session prompts. Document what worked and what didn't.

### Step 3: For Each Issue — Planning Stage

1. Apply the `state:planning` label to the issue
2. The orchestrator (or you manually) spawns a **Planner Devin session** with the planner prompt from `ARCHITECTURE.md`
3. Wait for the planner to post a remediation plan as an issue comment
4. Review the plan for sanity. If it looks reasonable, proceed. If not, send a message to the planner session requesting revisions.

### Step 4: For Each Issue — Building Stage

1. Apply the `state:building` label to the issue (this signals plan approval)
2. The orchestrator spawns a **Builder Devin session** with the builder prompt
3. Wait for the builder to open a PR on `victorlga/superset`
4. Verify the PR:
   - Has a clear description referencing the issue
   - Includes code changes (not just dependency bumps, unless that was the plan)
   - Includes new or updated tests
   - CI passes (or at least the relevant test files pass locally)

### Step 5: For Each Issue — Reviewing Stage

1. Apply the `state:reviewing` label to the issue
2. The orchestrator spawns a **Reviewer Devin session** with the reviewer prompt
3. Wait for the reviewer to post review comments
4. If changes are requested, the reviewer should iterate with the builder (or a new builder session is spawned)
5. Loop until CI is green and the review is approved

### Step 6: For Each Issue — Completion

1. Human (Victor) merges the PR
2. Apply the `state:done` label to the issue
3. The orchestrator logs completion metrics

### Step 7: Handle Failures

If any Devin session fails or produces an unsatisfactory result:
1. Check the session logs and messages
2. If the issue is too complex, simplify the plan and retry
3. If the issue is fundamentally infeasible, skip it and note in the CHANGELOG
4. The goal is 3–5 successfully remediated issues, not a 100% success rate

### Step 8: Spawn Sub-Phase Prompts (if parallelizing)

If running issues in parallel, create sub-phase files:

- `docs/PHASE_3_1.md` — Remediation for issue #A
- `docs/PHASE_3_2.md` — Remediation for issue #B
- `docs/PHASE_3_3.md` — Remediation for issue #C
- etc.

Each sub-phase prompt follows this template:

```markdown
# Phase 3.N — Remediate Issue #X: <title>

> Before starting, load the Devin Playbook `cognition-takehome-prompting-playbook`.

## Goal
Fix issue #X on victorlga/superset.

## Issue Details
- URL: <fork issue URL>
- Original: <apache/superset issue URL>
- Category: <security / high-impact bug / dependency / SAST>
- Description: <brief summary>

## Remediation Plan
<paste the planner's approved plan here>

## Instructions
1. Clone victorlga/superset, checkout a new branch: fix/X-slug
2. Implement the remediation plan step by step
3. Write or update tests to verify the fix
4. Run the relevant test suite locally
5. Open a PR against main with a description referencing issue #X
6. Ensure CI passes

## Definition of Done
- PR open with passing tests
- Issue comment with PR URL
- Code review approved
```

**Important:** Sub-phases do NOT write to CHANGELOG.md. Only this orchestrator phase does, after all sub-phases complete.

---

## Deliverables

- [ ] One merged PR per remediated issue on `victorlga/superset`
- [ ] Issue comments showing the planner → builder → reviewer flow
- [ ] All issues labeled `state:done` upon completion (or documented reason for skip)
- [ ] Sub-phase files (if parallelized): `docs/PHASE_3_1.md`, etc.
- [ ] CHANGELOG entry summarizing all remediations

---

## Test Plan & Verification

For each remediated issue:
1. PR is merged to `main` on `victorlga/superset`
2. The PR includes tests that verify the fix
3. CI passes on the PR (or relevant tests pass locally)
4. The issue comment trail shows planner → builder → reviewer flow
5. The issue has the `state:done` label applied

---

## Definition of Done

- At least 3 issues successfully remediated with merged PRs
- Each PR has passing tests
- All remediated issues labeled `state:done`
- The remediation set tells a varied, demo-worthy story

---

## CHANGELOG Entry Template

```markdown
## [PHASE_3] — YYYY-MM-DD — Remediated N issues on victorlga/superset

**What changed:**
- Issue #A: <title> — <one-line summary of fix> (PR #X)
- Issue #B: <title> — <one-line summary of fix> (PR #Y)
- Issue #C: <title> — <one-line summary of fix> (PR #Z)
- [additional issues...]

**Files touched:**
- `docs/PHASE_3_1.md` through `docs/PHASE_3_N.md` (sub-phase prompts)
- `CHANGELOG.md` (appended this entry)

**How it was verified:**
- All PRs merged with passing tests
- Each issue labeled `state:done`
- Each issue has a comment trail showing the planner/builder/reviewer flow

**What the next phase needs to know:**
- PR URLs: #X, #Y, #Z
- Any issues that were skipped and why
- Orchestrator performance observations (did webhooks work? session success rate?)

**Open questions / known gaps:**
- [list any issues]
```
