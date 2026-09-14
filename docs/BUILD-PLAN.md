# NextHire — Build Plan

| | |
|---|---|
| **Companion to** | [PRD.md](PRD.md) — every step traces to a requirement ID there |
| **Total steps** | **44**, across 5 phases |
| **Progress** | **39 of 44 done** — Phases 0, 1, 2 and 3 complete |
| **Document status** | Draft v1.0 |
| **Last updated** | 2026-09-14 |

---

## 0. How to read this

Each step is **atomic** (one concern), **verifiable** (there is a way to tell it is
done), and **ordered** (its dependencies come before it). Sizes are relative, not
calendar estimates:

- **S** — a focused change in one or two files.
- **M** — a feature touching both ends of the stack.
- **L** — structural work that changes how the system is shaped.

`Blocks` names the steps that cannot start until this one lands. A step with no
blocker in its own phase can run in parallel with its siblings.

### Step count at a glance

| Phase | Steps | Size | Status | What it buys |
|---|---|---|---|---|
| **Phase 0** — Reconnect the pipeline | 12 | Mostly S | **Done** | The app runs end to end on live data |
| **Phase 1** — Make the analysis trustworthy | 9 | S–M | **Done** | The scores can be believed |
| **Phase 2** — Accounts and persistence | 12 | L | **Done** | It becomes a product, not a demo |
| **Phase 3** — Resume optimisation | 6 | M–L | **Done** | The candidate leaves with something |
| **Phase 4** — Application lifecycle | 5 | M | Not started | The loop the landing page promises |
| | **44** | | **39 done** | |

**The shortest path to a working demo is Phase 0 alone — 12 steps, almost all
small, no new features.** Everything needed for it is already written; it is
disconnected, not missing.

---

## Phase 0 — Reconnect the pipeline  *(12 steps — done)*

No new features. This phase closed the 13 defects in PRD §4.1 and made every
feature already written actually run.

### Backend (0.1 – 0.7) — can run in parallel with frontend

| # | Step | Touches | Satisfies | Size | Blocks |
|---|---|---|---|---|---|
| **0.1** | Add `backend/requirements.txt` with pinned versions: `fastapi`, `uvicorn`, `pymupdf`, `requests`, `httpx`, `python-dotenv`. Verify a clean venv install runs the server. | new file | NFR-REL-6 | S | — |
| **0.2** | Delete the four unused dependencies from the repository-root `package.json`, or delete the file if nothing else needs it. | `package.json` | D13 | S | — |
| **0.3** | Replace `allow_origins=["*"]` with an explicit origin list read from the environment; drop `allow_credentials` until auth exists. | `main.py` | D9, NFR-SEC-2 | S | 2.2 |
| **0.4** | Extract a `config.py`: Ollama URL, model name, and the three timeouts. Replace the hardcoded `http://localhost:11434` in all three AI modules. | `extractor.py`, `infer_titles.py`, `ats_matcher.py`, new `config.py` | NFR-PERF-8 | S | 2.7 |
| **0.5** | Enforce the 5 MB upload cap server-side, and validate the file is a real PDF by magic bytes rather than filename extension. Mirror the size check client-side so the user fails fast. | `main.py`, `ResumeDialog.jsx` | FR-ING-4, FR-ING-7, NFR-SEC-3, D10 | S | — |
| **0.6** | Reject a PDF that extracts to empty or near-empty text with an explanatory error, instead of sending an empty string to the model. | `main.py` | FR-ING-5 | S | — |
| **0.7** | Remove dead code: the unreachable `print(extraction_result)` after the `raise`, and the `getJobs()` helper that `GET`s a `POST`-only route. | `main.py`, `api/jobs.js` | D6, D11 | S | — |

### Frontend (0.8 – 0.12) — 0.8 must land first

| # | Step | Touches | Satisfies | Size | Blocks |
|---|---|---|---|---|---|
| **0.8** | **Restore the real flow.** Delete the `TEMPORARY WORKFLOW FOR TESTING` block, uncomment the original, and fix the `setSelectedJob` → `setSelectedJobs` prop mismatch while restoring it. Landing page and job-titles dialog become reachable again. | `App.jsx` | D1, D2 | M | 0.9, 0.10, 0.11, 0.12 |
| **0.9** | Move `USE_MOCK_DATA` to a Vite environment variable, defaulting **off**. Live search results render for the first time. | `JobListings.jsx`, `.env.example` | FR-JOB-4, NFR-UX-3, D3 | S | 0.10 |
| **0.10** | Fix the two data-shape problems the mock was hiding: the literal `text-sm, font-medium` rendering as a company subtitle, and `salary` being a scalar in the mock but `{min, max}` in real results. | `JobListings.jsx`, `mocks/jobs.js` | FR-JOB-10, NFR-UX-4, D8 | S | — |
| **0.11** | **Wire the ATS dashboard to `/api/analyze-ats`.** Call the endpoint for each selected job on mount, populate `analysisResults`, drive the panel from it. Delete the unused hardcoded `JOBS` array and the `job.matched` / `job.missing` / `job.improve` / `job.label` / `job.summary` reads that no real payload satisfies. **This single step is what makes the core feature work.** | `AtsAnalysis.jsx` | FR-ATS-2, D4, D5 | M | 1.3, 1.4 |
| **0.12** | Replace the `alert()` on job-search failure with an inline error and a retry action. | `JobTitlesDialog.jsx` | NFR-UX-2, D12 | S | — |

> **Phase 0 exit test:** upload a real PDF → see inferred titles → search → see live
> postings → select jobs → see real ATS scores. No source edits required to get there.

---

## Phase 1 — Make the analysis trustworthy  *(9 steps — done)*

Phase 0 made the number appear. This phase made it correct, fast, and honest
about its own failures.

| # | Step | Touches | Satisfies | Size | Depends on |
|---|---|---|---|---|---|
| **1.1** | Stop returning `match_score: 0` on error. Return an explicit failure status so a failed analysis is distinguishable from a genuine bad match. | `ats_matcher.py`, `main.py` | FR-ATS-6, NFR-REL-2 | S | — |
| **1.2** | Apply the `_fill_defaults` validation pattern from `extractor.py` to the ATS response, replacing the current shallow `.get()` defaults. | `ats_matcher.py` | NFR-REL-1 | S | — |
| **1.3** | Run the up-to-5 analyses **concurrently** with per-job loading, success, and failure states. One failure must not blank the others. Serial execution at current latency is a multi-minute wait. | `AtsAnalysis.jsx`, `main.py` | FR-ATS-3, NFR-PERF-4 | M | 0.11, 1.1 |
| **1.4** | Drive the summary bar (count, best, average) and the verdict bands from real scores. `matchPillClasses` already has the thresholds; it is being fed the wrong number. | `AtsAnalysis.jsx` | FR-ATS-7, FR-ATS-9 | S | 0.11 |
| **1.5** | Replace the reused title confidence on job cards with a real per-posting figure — either a cheap pre-score or an explicit "not yet analysed" state. Several cards currently show an identical number that reads as a per-job match. | `job_search.py`, `JobListings.jsx` | FR-JOB-8, D7 | M | — |
| **1.6** | Profile review-and-correct screen between extraction and inference. Extraction is good, not perfect, and every downstream stage inherits its errors. | new component, `main.py` | FR-PROF-6 | M | — |
| **1.7** | Staged, determinate progress for every operation over 3 seconds — uploading / reading / analysing — replacing the single indefinite spinner. | `ResumeDialog.jsx`, `JobTitlesDialog.jsx`, `AtsAnalysis.jsx` | FR-ING-6, NFR-PERF-6, NFR-UX-6 | S | — |
| **1.8** | Link matched and missing skills back to where they appear in the posting, so the candidate can check the judgement rather than trust it. | `ats_matcher.py`, `AtsAnalysis.jsx` | FR-ATS-10 | M | 1.3 |
| **1.9** | Regression suite over the four stage contracts (PRD §3.1) against fixture resumes, with the model mocked. There are currently no tests at all. | new `backend/tests/` | NFR-REL-7 | M | — |

---

## Phase 2 — Accounts and persistence  *(12 steps — done)*

Nothing persisted before this phase. No database, no ORM, no migrations, no file storage.
This was the largest phase and the one that turned a demo into a product.

### Foundation (2.1 – 2.3) — strictly sequential

| # | Step | Satisfies | Size | Blocks |
|---|---|---|---|---|
| **2.1** | Pick the database, ORM, and migration tool. Write the initial migration for the 11 tables in PRD §6.3. | PRD §6.3 | L | everything below |
| **2.2** | `users` table and auth: register, sign in, sign out. Argon2id or bcrypt hashing, signed httpOnly session cookies. | FR-ACC-2, NFR-SEC-6 | L | 2.8, 2.9 |
| **2.3** | Resume file storage with non-guessable paths and per-request ownership authorisation. | FR-ACC-5, NFR-SEC-5 | M | 2.4 |

### Persisting the pipeline (2.4 – 2.6) — one step per stage, in pipeline order

| # | Step | Satisfies | Size | Depends on |
|---|---|---|---|---|
| **2.4** | Persist `resumes` and `profiles`, including `profile.version` and `extraction_model`. Retain `raw_text` so a future model upgrade does not require re-upload. | FR-ACC-4, PRD §6.4 | M | 2.1, 2.3 |
| **2.5** | Persist `inferred_titles`, `job_searches`, and `jobs`. The `jobs` table is a cache of what was shown, not a job board. | FR-ACC-4 | M | 2.4 |
| **2.6** | Persist `ats_analyses`, with caching keyed on `(profile_version, job_id)` so re-opening a job does not re-run a 30–120 s inference — and so a corrected profile invalidates its stale scores. | FR-ATS-8, PRD §6.4 | M | 2.5 |

### Making it safe and usable (2.7 – 2.12)

| # | Step | Satisfies | Size | Depends on |
|---|---|---|---|---|
| **2.7** | `jobs_queue` table and a worker with a declared concurrency limit. A single Ollama instance cannot serve parallel users, and there is no queue today. Long operations survive a page refresh; the client reattaches. | FR-ACC-6, NFR-PERF-7 | L | 2.1, 0.4 |
| **2.8** | Ownership authorisation on every endpoint touching stored data — checked server-side against the session, never inferred from a client-supplied id. | NFR-SEC-7 | M | 2.2 |
| **2.9** | Guest-to-account carryover: a Guest completes the pipeline, registers, and keeps the work instead of losing it. | FR-ACC-1, FR-ACC-3 | M | 2.2, 2.6 |
| **2.10** | Rate limiting per IP and per account on upload and every inference endpoint. Each call carries real compute cost. | NFR-SEC-8 | S | 2.2 |
| **2.11** | Account deletion (removes file, profile, and derived rows) and JSON data export. | FR-ACC-5, FR-ACC-8, NFR-SEC-9 | M | 2.4 |
| **2.12** | Password reset by emailed single-use, time-limited link. | FR-ACC-7 | M | 2.2 |

---

## Phase 3 — Resume optimisation  *(6 steps)*

The "Optimize Resume" button exists and does nothing. This phase is what converts
an analysis into an outcome.

| # | Step | Satisfies | Size | Depends on |
|---|---|---|---|---|
| **3.1** | Optimisation endpoint: given a profile and an analysis, generate a tailored resume that foregrounds matched skills and adopts the posting's language. | FR-OPT-1 | M | 2.6 |
| **3.2** | **Fabrication guard.** Validate generated content against the source profile — no employer, date, skill, or achievement may appear that the profile does not contain. A prompt instruction is not sufficient; this needs a programmatic check. | FR-OPT-2 | M | 3.1 |
| **3.3** | Diff UI: every change shown against the original, accepted or rejected individually. | FR-OPT-3 | L | 3.1 |
| **3.4** | ATS-safe PDF renderer — selectable text, single column, standard section headings, no text inside images or tables. | FR-OPT-4 | L | 3.3 |
| **3.5** | Re-score the tailored resume against the same posting and show the before/after delta. | FR-OPT-5 | S | 3.1, 2.6 |
| **3.6** | Persist `tailored_resumes` per posting, so the candidate can see which version went where. | FR-OPT-6 | S | 3.1, 2.1 |

---

## Phase 4 — Application lifecycle  *(5 steps)*

Closes the loop the landing page already advertises.

| # | Step | Satisfies | Size | Depends on |
|---|---|---|---|---|
| **4.1** | Application tracker: `applications` table, the `SAVED → APPLIED → INTERVIEWING → OFFER / REJECTED` lifecycle, and a board grouped by status retaining match score and the resume sent. | FR-TRK-1, FR-TRK-2, FR-TRK-3 | L | 2.1, 3.6 |
| **4.2** | Notes, follow-up reminder dates, and summary counts — applied this week, awaiting response, response rate. | FR-TRK-4, FR-TRK-5 | M | 4.1 |
| **4.3** | Cover letter generator: endpoint, selectable tone, in-place editing, PDF and plain-text export. Same no-fabrication rule as 3.2. | FR-CL-1 … FR-CL-5 | M | 2.6, 3.2 |
| **4.4** | Skills gap aggregation across all analysed postings, ranked by frequency, surfacing the 3–5 skills that would most raise the average match score. | FR-GAP-1, FR-GAP-2 | M | 2.6 |
| **4.5** | Interview preparation: likely questions per posting, split into technical, behavioural, and gap-probing. | FR-INT-1, FR-INT-2 | M | 2.6 |

---

## Critical path

The longest dependency chain, and therefore the thing that determines how long
this takes end to end:

```
0.8  restore App.jsx
 └─ 0.11  wire the ATS dashboard          <- core feature works here
     └─ 1.3  concurrent per-job analysis
         └─ 2.1  database + migrations
             └─ 2.4  persist profiles
                 └─ 2.6  persist analyses + caching
                     └─ 3.1  optimisation endpoint
                         └─ 3.3  diff UI
                             └─ 3.4  ATS-safe PDF
                                 └─ 4.1  application tracker
```

**11 steps on the critical path of 44.** The other 33 can be scheduled around it,
and much of Phase 0 and Phase 1 parallelises cleanly between one person on the
backend and one on the frontend.

### Where the risk actually sits

1. **2.1 → 2.7** is the only genuinely structural work in the plan. Everything
   before it is repair; everything after it depends on it. Nothing in Phase 2
   demos well on its own, which makes it the easiest phase to under-resource and
   the most expensive one to get wrong.
2. **3.2, the fabrication guard,** is the step most likely to be underestimated.
   A resume tool that invents employment history is not a flawed product, it is a
   harmful one, and prompt instructions alone will not hold.
3. **3.4, ATS-safe PDF output,** is unglamorous and larger than it looks. A PDF
   that renders beautifully and parses badly defeats the entire product.

### The two decisions that should be made before writing code

Both are open questions in PRD §11 and both are cheap to answer now and expensive
to answer late:

- **Q2 — the RapidAPI quota.** Five titles per search is five API calls. The
  ceiling decides whether step 1.5 needs caching and whether 2.10 is urgent.
- **Q1 — self-hosted or hosted model.** This is load-bearing for NFR-SEC-4. The
  promise that resume content never leaves the deployment is free while the model
  is local, and becomes a contract negotiation the moment it is not.
