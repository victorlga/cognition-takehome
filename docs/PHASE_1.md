# Phase 1 — Issue Selection & Seeding

> **Before starting, load the Devin Playbook `cognition-takehome-prompting-playbook` and follow it throughout this session.**

**Depends on:** PHASE_0 complete (verify via CHANGELOG.md entry "Bootstrap planning docs, playbook, machine, and wikis")

---

## Goal

Select 3–5 high-quality security issues and high-impact bugs from Apache Superset's issue tracker and seed them onto the fork (`victorlga/superset`). Create a GitHub Project board (kanban) to track their remediation.

---

## Inputs to Read

1. `CHANGELOG.md` — read the entire file to understand prior work
2. `docs/TAKEHOME.md` — the full assignment spec
3. `docs/PLAN.md` — master plan and phase overview
4. `docs/ARCHITECTURE.md` — system architecture and design decisions

---

## Architecture / Business Decisions Already Made

- The system is framed as a **Vulnerability Remediation System**, but "vulnerability" is interpreted broadly: anything a security-minded engineering org would want fixed
- Issues will be tracked on a **GitHub Projects v2 kanban board** on the fork
- The board has columns: **Backlog, Planning, Building, Reviewing, Done**
- The board drives the orchestrator via `projects_v2_item` webhooks
- The demo audience is a VP of Engineering + senior ICs — **technical depth + business impact matter**
- **The remediated issues are the on-screen proof that the system works.** Trivial picks tank the entire demo.

---

## Tech Stack

- GitHub CLI (`gh`) for issue/project management
- GitHub API (REST + GraphQL) for project board operations
- `pip-audit`, `bandit`, `semgrep`, `npm audit` for supplementary scanning

---

## Procedure

### Step 1: Primary Source — Apache Superset Issue Tracker

Browse open issues at `https://github.com/apache/superset/issues`. Search in this priority order, and stop as soon as you have enough viable candidates:

#### 1a. Security-labeled issues first

Search for issues with labels: `security`, `area:security`, and any other security-flavored labels.

```bash
gh issue list --repo apache/superset --label security --state open --limit 50
gh issue list --repo apache/superset --label "area:security" --state open --limit 50
```

For each candidate, read the issue body carefully. Evaluate against the filters below.

#### 1b. Fallback: Bug-labeled issues with security/reliability implications

If security-labeled issues are too few, too stale, or too hard to verify:

```bash
gh issue list --repo apache/superset --label bug --state open --limit 100 --json number,title,labels,createdAt
```

Prioritize bugs with security or reliability implications:
- Auth/authz issues
- Data integrity bugs
- Input handling / validation issues
- Access control problems
- Crashes on untrusted input
- Race conditions
- SQL injection vectors
- XSS in dashboard rendering

#### 1c. Last resort: Substantive functional bugs

Plain functional bugs are acceptable if they are substantive and clearly showcase Devin's ability to read code, reason about it, and produce a tested fix. Frame them honestly in the issue body as "high-impact bugs the system also handles."

### Step 2: Secondary Sources (supplement only)

Use these ONLY to supplement if the issue tracker is thin, or to add variety:

#### 2a. Recently closed security advisories
```bash
# Browse https://github.com/apache/superset/security/advisories for inspiration
```

#### 2b. Dependency CVEs
```bash
# Clone the fork and run audits
cd ~/repos/superset
pip-audit -r requirements/base.txt 2>&1 | head -50
npm audit --prefix superset-frontend 2>&1 | head -50
```

**Important:** Dependency CVEs are **low-priority filler**. A pile of `requirements.txt` version bumps will undersell the system. At most ONE dependency fix is allowed, and only if the bump genuinely requires code adaptation (API changed, deprecated call, etc.).

#### 2c. Static analysis
```bash
bandit -r superset/ -ll 2>&1 | head -50
semgrep --config auto superset/ 2>&1 | head -50
```

Again, treat these as supplement only. SAST findings are acceptable as at most one of the picks.

### Step 3: Apply Selection Filters

From the candidate pool, select 3–5 issues that satisfy **ALL** of these filters:

1. **Security-relevant or high-impact bug** — XSS/CSRF/SQLi, auth/authz bugs, secrets handling, unsafe deserialization, missing input validation, insecure defaults, broken access checks, or substantive correctness bugs that an engineering leader would care about.

2. **Non-trivial enough to showcase Devin's power.** This is critical:
   - Each pick should require Devin to actually read code, understand context, write or modify logic, and produce a real test.
   - Dependency-bump-only fixes are allowed as **at most one** of the picks, and only if the bump genuinely requires code adaptation.
   - If a CVE can be fixed by a one-line version bump with no code reading, it does **not** qualify on its own.

3. **Devin-sized** — Fixable by a single Devin session in roughly 1–2 hours of compute, with a bounded blast radius (a handful of files). Hard upper bound, not a target — err toward meatier issues that still fit.

4. **Verifiable** — Has a reproducible symptom, a failing test that can be written, or a clear acceptance criterion from the issue body.

5. **Demo-worthy as a set.** Together, the picks should tell a varied story for the Loom:
   - At least one real code-level security fix (input validation, auth check, injection fix)
   - At least one substantive bug with security or reliability impact
   - Optionally one dependency or SAST finding for breadth — but not more than one

### Step 4: Build the Selection Table

Create a markdown table with these columns for EACH selected issue:

| Column | Description |
|--------|-------------|
| Issue Link | URL to the original apache/superset issue |
| Source | How it was found (security label / bug label / advisory / pip-audit / bandit / semgrep) |
| Category | security / high-impact bug / dependency / SAST |
| Business Impact | Why an engineering leader would care |
| Why Non-Trivial | What makes this more than a one-liner |
| Why Devin Can Fix It | Bounded scope, clear acceptance criteria |
| Estimated Complexity | Low / Medium / High (target: Medium) |
| Verification Strategy | How to confirm the fix works |

Also include:
- A **rejected candidates** section with 5+ candidates that didn't make the cut and WHY
- For each pick, explicitly note whether it was found via security search or bug fallback
- For each pick, call out any risk of looking "too easy" and explain what makes it interesting

### Step 5: Create Issues on the Fork

For each selected issue, create a new issue on `victorlga/superset`:

```bash
gh issue create --repo victorlga/superset \
  --title "<original title>" \
  --body "<original body + backlink to original issue>" \
  --label "<original labels>"
```

Preserve:
- Original title
- Original body (with a note at the top: "Mirrored from apache/superset#XXXX for automated remediation")
- Original labels (create labels on the fork if they don't exist)
- Add label `remediation-target`

### Step 6: Create GitHub Project Board

Create a GitHub Project (v2) on the fork with columns: **Backlog, Planning, Building, Reviewing, Done**.

```bash
# Create the project
gh project create --owner victorlga --title "Vulnerability Remediation" --format board

# Add all selected issues to Backlog
gh project item-add <project-number> --owner victorlga --url <issue-url>
```

Configure the Status field with the required columns. Add all issues to the Backlog column.

### Step 7: Configure Webhook

Set up a webhook on `victorlga/superset` for `projects_v2_item` events. The webhook URL will be configured in Phase 2 — for now, document the webhook secret and note that it needs to be pointed at the orchestrator's `/webhooks/github` endpoint.

```bash
# Generate webhook secret
python3 -c "import secrets; print(secrets.token_hex(32))"

# Create webhook (URL will be updated in Phase 2)
gh api repos/victorlga/superset/hooks -f name=web \
  -f 'config[url]=https://placeholder.ngrok.io/webhooks/github' \
  -f 'config[content_type]=json' \
  -f 'config[secret]=<generated-secret>' \
  -f 'events[]=projects_v2_item'
```

### Step 8: Verify

1. List all created issue URLs
2. Confirm project board exists with correct columns
3. Confirm all issues are in the Backlog column
4. Take a screenshot or JSON dump of the project board state

---

## Deliverables

- [ ] Selection table with 3–5 justified picks + rejected candidates (saved in CHANGELOG entry)
- [ ] Issues created on `victorlga/superset` with original content and backlinks
- [ ] GitHub Project board "Vulnerability Remediation" with columns: Backlog, Planning, Building, Reviewing, Done
- [ ] All issues in Backlog column
- [ ] Webhook configured (URL placeholder, secret generated)
- [ ] Verification output: issue URLs + board state

---

## Test Plan & Verification

1. `gh issue list --repo victorlga/superset --label remediation-target` returns 3–5 issues
2. `gh project list --owner victorlga` shows the "Vulnerability Remediation" project
3. Each issue on the fork has a backlink to the original apache/superset issue
4. The selection table has no picks that violate the difficulty bar
5. The set includes at least one code-level security fix and at least one high-impact bug

---

## Definition of Done

- 3–5 issues created on `victorlga/superset` that clear the difficulty bar
- GitHub Project board created and populated
- Selection rationale documented with rejected candidates
- Webhook configured (URL to be updated in Phase 2)

---

## CHANGELOG Entry Template

```markdown
## [PHASE_1] — YYYY-MM-DD — Selected N issues and seeded fork project board

**What changed:**
- Selected N issues from apache/superset (X security, Y bugs, Z dependency/SAST)
- Created issues on victorlga/superset: #A, #B, #C, ...
- Created GitHub Project "Vulnerability Remediation" with kanban columns
- Configured webhook for projects_v2_item events

**Files touched:**
- `CHANGELOG.md` (appended this entry)

**How it was verified:**
- All issues listed and confirmed on fork
- Project board screenshot/JSON captured
- Selection table reviewed against difficulty bar

**What the next phase needs to know:**
- Issue numbers on the fork: #A, #B, #C, ...
- Project board number: N
- Webhook secret stored as GITHUB_WEBHOOK_SECRET
- Status field node IDs: [list them]

**Open questions / known gaps:**
- [any issues found during selection]
```

---

## Stop Condition

If fewer than 3 viable issues that clear the difficulty bar can be found across both the security and bug pools, **STOP and report to the user** rather than padding with weak picks. That is a signal to revisit the framing.
