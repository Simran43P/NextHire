# NextHire — Product Requirements Document

| | |
|---|---|
| **Product** | NextHire — AI job-matching and resume-tailoring agent |
| **Platform** | React 19 + Vite web app (SPA) + FastAPI backend + local LLM via Ollama |
| **Document status** | Draft v1.0 |
| **Last updated** | 2026-09-14 |
| **Source** | The existing Notion PRD, reconciled against the codebase at commit `bafee84` |

---

## 1. Overview

Applying for a job is a repetitive, low-information process. A candidate reads a
posting, guesses whether they are a fit, edits their resume by hand, applies, and
hears nothing back. They never learn *why*. Meanwhile the first reader of their
resume is usually not a person — it is an Applicant Tracking System matching
keywords.

NextHire inverts that loop. The candidate uploads a resume once. The system reads
it, works out what roles that resume actually qualifies them for, finds live
postings for those roles, and scores the resume against each one — showing exactly
which requirements are met, which are missing, and what to change.

A working prototype already exists and covers the path from resume upload through
to job listings. ATS analysis is half-built: the backend endpoint works, the
frontend screen that should call it does not. This document defines the full
product and marks what is built, what is partially built, and what is new.

### 1.1 Problem statement

1. **Candidates don't know what to apply for.** Especially freshers, whose skills
   live in projects rather than job titles. They search for the title they *want*,
   not the titles their resume actually supports.
2. **Job search is untargeted.** A candidate types one keyword into one job board
   and reads hundreds of postings, most irrelevant.
3. **Fit is invisible until rejection.** Nothing tells a candidate, before they
   apply, that a posting requires Docker and their resume never mentions it.
4. **Tailoring a resume per application is manual.** It is the single highest-value
   activity in a job search and the one candidates skip because it is tedious.
5. **There is no memory.** Every session starts from zero — re-upload, re-parse,
   re-search. Nothing the candidate did yesterday is available today.

### 1.2 Goals

- **G1** — Turn an uploaded PDF resume into a complete structured profile with no
  manual data entry and no hallucinated content.
- **G2** — Infer realistic, board-searchable job titles from that profile, ranked
  by confidence, without penalising candidates who lack formal experience.
- **G3** — Aggregate live job postings for those titles into one deduplicated list.
- **G4** — Give every selected posting a genuine ATS match score with named matched
  skills, named missing skills, and specific recommendations.
- **G5** — Produce a tailored resume for a specific posting from that analysis.
- **G6** — Persist the candidate's profile, searches, analyses, and applications
  across sessions.

### 1.3 Non-goals (this release)

- Auto-applying to jobs on the candidate's behalf. NextHire prepares applications;
  the candidate submits them.
- Recruiter- or employer-facing product. NextHire is candidate-side only.
- Running NextHire's own job board or storing a scraped job corpus. Postings are
  fetched live from an aggregator and are not warehoused.
- Non-PDF resume formats (DOCX, plain text, images requiring OCR).
- Mobile applications. Responsive web only.
- Payments, subscriptions, or usage billing.

---

## 2. Users and roles

NextHire is single-sided. There is one product user, plus an operator role for
whoever runs the deployment.

| Role | Who | Access |
|---|---|---|
| **Guest** | A first-time visitor, not signed in | Landing page; may run one full analysis per session, held in browser state only |
| **Candidate** | A registered job seeker | Their own profile, searches, analyses, tailored resumes, and application history — persisted |
| **Operator** | Whoever deploys NextHire | Model configuration, API quota monitoring, error logs. No access to candidate resume content |

> **Change required.** No concept of a user exists in the codebase today. There is
> no authentication, no session, and no database — every artefact lives in React
> component state and is destroyed on refresh. The Guest/Candidate split above is
> introduced in Phase 2 (§8).

### 2.1 Access and data-ownership model

A resume is among the most sensitive documents a person will upload: full name,
personal phone number, home location, and complete employment history. That shapes
three hard rules.

- **Guest-first.** A visitor must be able to run upload → titles → jobs → ATS
  analysis without creating an account. Registration is what makes results
  *persist*, not what makes them *possible*.
- **Resume text is never a third-party payload.** Resume content is processed by
  the locally hosted model. It is not sent to any hosted LLM provider, and only
  the inferred *job title strings* — never profile content — reach the job-search
  API.
- **Deletion is real.** A candidate can delete their account, and that removes the
  stored resume file, the extracted profile, and every derived analysis.

---

## 3. Information architecture

The product is a linear pipeline. Each stage consumes the previous stage's output,
and each stage is a separate backend call.

```
                      Landing page
                           |
                    [Upload resume PDF]
                           |
              POST /api/parse-resume  (PyMuPDF -> LLM)
                           |
                   Structured profile
                           |
              POST /api/infer-titles  (LLM)
                           |
              Job titles + confidence  -> select up to 5
                           |
              POST /api/jobs  (JSearch, concurrent, deduped)
                           |
                    Job listings  -> select up to 5
                           |
              POST /api/analyze-ats  (LLM, per job)
                           |
        +------------------+-------------------+
        |                  |                   |
   ATS dashboard     Optimize Resume    Upskilling plan
   score / matched   (not built)        (not built)
   missing / recs
```

> **Change required.** The pipeline above is what the code *intends*. The pipeline
> that currently *runs* is shorter and partly severed — see §4.

### 3.1 Stage contracts

| Stage | Endpoint | Input | Output |
|---|---|---|---|
| Parse | `POST /api/parse-resume` | `multipart/form-data` PDF | `profile`, `raw_text` |
| Infer | `POST /api/infer-titles` | profile JSON | `titles[]` — `{id, title, matchPercentage}` |
| Search | `POST /api/jobs?country=` | selected titles | `jobs[]` — standardised posting shape |
| Analyse | `POST /api/analyze-ats` | `{resume_profile, job_description}` | `{match_score, matched_skills, missing_skills, recommendations}` |

---

## 4. Current state of the codebase

Establishes the baseline this PRD builds on. **Phases 0 and 1 of
[BUILD-PLAN.md](BUILD-PLAN.md) are complete**; this table reflects the state
after that work.

| Area | State | Notes |
|---|---|---|
| PDF text extraction | **Built** | `backend/main.py` via PyMuPDF, streamed and size-capped, rejects non-PDFs by magic bytes and scans by text yield |
| Structured profile extraction | **Built** | `backend/extractor.py` — Qwen 2.5 7B, deterministic (`temperature: 0`, `seed: 42`), schema-validated by `schema_utils.fill_defaults` |
| Profile review and correction | **Built** | `ProfileReview.jsx` — editable profile between extraction and inference, flagging empty sections |
| Job title inference | **Built** | `backend/infer_titles.py` — top 5 with confidence and a stated reason, validated and deduplicated |
| Job search | **Built** | `backend/job_search.py` — JSearch via RapidAPI, concurrent per title, deduplicated, partial-failure tolerant, with a no-quota mock mode |
| Per-posting keyword pre-score | **Built** | `backend/prescore.py` — free local skill overlap; replaced the reused title confidence on job cards |
| ATS analysis — backend | **Built** | `backend/ats_matcher.py` + `POST /api/analyze-ats`; typed failures, deep validation, evidence quoting |
| ATS analysis — frontend | **Built** | `AtsAnalysis.jsx` runs one analysis per selected job in parallel, with per-job loading, error, and retry states |
| Landing page | **Built** | Reachable again; `App.jsx` is an explicit step machine |
| Resume upload dialog | **Built** | `ResumeDialog.jsx` — staged progress, real upload percentage, client-side validation |
| Job titles dialog | **Built** | `JobTitlesDialog.jsx` — inline errors with retry |
| Job listings | **Built** | Renders live server results; salary, posting age, and matched skills shown |
| Model serving | **Built** | `backend/llm.py` — async, bounded concurrency, typed errors; all config in `backend/config.py` |
| Tests | **Built** | 127 tests in `backend/tests/`, model fully mocked, offline, no quota spent |
| Python dependency manifest | **Built** | `backend/requirements.txt`, pinned |
| Accounts / auth | **Not started** | Phase 2 |
| Persistence / database | **Not started** | No database of any kind. Everything still lives in React state |
| Resume optimisation | **Not started** | Phase 3. The button is present and labelled "Coming soon" |
| Cover letter generator | **Not started** | Phase 4. Advertised on the landing page |
| Application tracker | **Not started** | Phase 4. Advertised on the landing page |
| Interview prep | **Not started** | Phase 4. Advertised on the landing page |
| Skills gap / upskilling | **Not started** | Phase 4. Marked "Coming soon" in the UI |

### 4.1 Defects found in the original code — all resolved

These were the thirteen defects Phase 0 existed to close. All are fixed; the
list is kept because it records what the original prototype's failure modes
were, and several of them are worth not reintroducing.

| # | Defect | Location |
|---|---|---|
| D1 | The real application flow is commented out and replaced by a block labelled `TEMPORARY WORKFLOW FOR TESTING`. The landing page and the job-titles dialog are unreachable. | `frontend/src/App.jsx` |
| D2 | The commented-out original passes `setSelectedJob` to `JobListings`, which accepts `setSelectedJobs`. Restoring it verbatim would break job selection. | `frontend/src/App.jsx` |
| D3 | `USE_MOCK_DATA = true` is hardcoded, so real search results are fetched and then discarded in favour of six static postings. | `frontend/src/components/JobListings.jsx` |
| D4 | The ATS dashboard never calls `/api/analyze-ats`. `analysisResults` and `isAnalyzing` are declared and never written; `useEffect` is imported and never used; a 5-entry hardcoded `JOBS` array sits unused at the top of the file. | `frontend/src/components/AtsAnalysis.jsx` |
| D5 | The dashboard reads `job.matched`, `job.missing`, `job.improve`, `job.label`, and `job.summary` — fields that exist on neither the real JSearch shape nor `MOCK_JOBS`. The panel can only ever render empty until D4 is fixed. | `frontend/src/components/AtsAnalysis.jsx` |
| D6 | `getJobs()` issues a `GET` to `/api/jobs`; the backend defines that route as `POST` only. The helper is dead and would 405 if called. | `frontend/src/api/jobs.js` |
| D7 | The match percentage on each job card is the *title-level* confidence copied onto every posting returned for that title, not a per-posting score. Several different jobs show the same number, which reads as a per-job match and is not one. | `job_search.py`, `JobListings.jsx` |
| D8 | `salary` is an object `{min, max}` in real results but a scalar in `MOCK_JOBS`. Any code that renders salary will break when the mock flag is flipped. | `job_search.py` vs `mocks/jobs.js` |
| D9 | CORS is configured with `allow_origins=["*"]` together with `allow_credentials=True` — a combination browsers reject, and unsafe once auth exists. | `backend/main.py` |
| D10 | The upload dialog states "max 5MB"; neither client nor server enforces any size limit. A large PDF is read fully into memory. | `ResumeDialog.jsx`, `main.py` |
| D11 | An unreachable `print(extraction_result)` sits after a `raise` in the parse handler. | `backend/main.py` |
| D12 | A job-search failure surfaces as a browser `alert()`. | `JobTitlesDialog.jsx` |
| D13 | The repository-root `package.json` declares `axios`, `react-router-dom`, `lucide-react`, and `react-icons`, none of which the app imports — the frontend has its own manifest. | `package.json` |

---

## 5. Functional requirements

Requirements are identified as `FR-<module>-<n>` and carry a priority:
**P0** must-have for launch · **P1** important · **P2** desirable.

### 5.1 M1 — Resume ingestion  *(built)*

| ID | Priority | Requirement |
|---|---|---|
| FR-ING-1 | P0 | A candidate can upload a PDF resume by drag-and-drop or file browser. *(Built)* |
| FR-ING-2 | P0 | Only PDF is accepted; any other type is rejected with a clear message before upload. *(Built — server-side check on extension)* |
| FR-ING-3 | P0 | Text is extracted page by page with layout preserved well enough that section headings survive. *(Built)* |
| FR-ING-4 | P0 | Uploads are capped at 5 MB, enforced on **both** client and server, matching the stated UI limit. *(Not built — see D10)* |
| FR-ING-5 | P0 | A PDF that yields no extractable text (a scanned image) is rejected with an explanation, not passed to the model as an empty string. |
| FR-ING-6 | P1 | The candidate sees staged progress — uploading, reading, analysing — rather than a single indefinite spinner, because extraction can take tens of seconds. |
| FR-ING-7 | P1 | The uploaded file is validated as a real PDF by content, not by filename extension alone. |
| FR-ING-8 | P2 | DOCX resumes are accepted and converted before extraction. |

### 5.2 M2 — Structured profile extraction  *(built)*

| ID | Priority | Requirement |
|---|---|---|
| FR-PROF-1 | P0 | Raw resume text is converted into a fixed JSON profile: identity, contact, location, skills, years of experience, education, experience, projects, certifications, languages, and links. *(Built)* |
| FR-PROF-2 | P0 | The model must not invent information. Absent fields take typed defaults — `""`, `[]`, `0`. *(Built — enforced in the prompt **and** structurally by `_fill_defaults`)* |
| FR-PROF-3 | P0 | The returned profile always matches the schema exactly regardless of model output; malformed model JSON returns a clean error, never a partial object. *(Built)* |
| FR-PROF-4 | P0 | Extraction is deterministic — the same resume produces the same profile. *(Built — `temperature: 0`, `top_k: 1`, fixed seed)* |
| FR-PROF-5 | P0 | Multi-page resumes are not truncated. *(Built — `num_ctx: 8192`; must be re-verified if the model changes)* |
| FR-PROF-6 | P1 | The candidate can review and correct the extracted profile before it is used downstream. Extraction is good, not perfect, and every later stage inherits its errors. |
| FR-PROF-7 | P1 | A confidence or completeness indicator flags profiles where major sections came back empty. |
| FR-PROF-8 | P2 | The candidate can maintain more than one profile (for example, one aimed at data roles and one at backend roles). |

### 5.3 M3 — Job title inference  *(built)*

| ID | Priority | Requirement |
|---|---|---|
| FR-TITLE-1 | P0 | The system infers the top 5 job titles for a profile, each with a 0–100 confidence score, ranked best first. *(Built)* |
| FR-TITLE-2 | P0 | Freshers are not penalised for lacking employment history; inference weights skills and projects first. *(Built — explicit in the prompt)* |
| FR-TITLE-3 | P0 | Only titles that genuinely appear on job boards are returned — no invented or creative titles, and no senior or managerial titles unless the experience justifies them. *(Built)* |
| FR-TITLE-4 | P0 | Near-duplicate titles are collapsed, keeping the highest-confidence variant in its original position. *(Built)* |
| FR-TITLE-5 | P0 | Malformed model output degrades to an empty list and a user-facing message, never an unhandled exception. *(Built)* |
| FR-TITLE-6 | P0 | The candidate selects which titles to search, up to a cap of 5, with the cap and current count always visible. *(Built)* |
| FR-TITLE-7 | P1 | The candidate can add a title of their own that the model did not infer. |
| FR-TITLE-8 | P2 | Each title carries a one-line rationale — which skills or projects drove it. |

### 5.4 M4 — Job discovery  *(built)*

| ID | Priority | Requirement |
|---|---|---|
| FR-JOB-1 | P0 | Selected titles are searched concurrently against the job aggregator and returned as one list. *(Built — `asyncio.gather`)* |
| FR-JOB-2 | P0 | Results are deduplicated across titles by posting ID. *(Built)* |
| FR-JOB-3 | P0 | Every posting is normalised to one shape: id, title, company, location, employment type, description, apply link, remote flag, posted date, salary range. *(Built)* |
| FR-JOB-4 | P0 | The job list renders **live** results. The mock data path is a development aid and must be switchable without editing source. *(Not built — see D3)* |
| FR-JOB-5 | P0 | Postings are restricted to the last 30 days; the country is selectable and defaults to India. *(Partially built — `date_posted: month` is fixed; country is a parameter but has no UI control)* |
| FR-JOB-6 | P0 | An aggregator failure for one title does not fail the whole search; remaining titles still return. *(Built — per-title exception handling)* |
| FR-JOB-7 | P0 | A posting with no usable apply link renders its action disabled rather than opening a dead tab. *(Built)* |
| FR-JOB-8 | P1 | The percentage shown on a job card must be a per-posting figure, not the title confidence reused across every result for that title. *(Not built — see D7)* |
| FR-JOB-9 | P1 | The candidate can filter by remote, employment type, location, and date posted, and sort by match or recency. |
| FR-JOB-10 | P1 | Salary renders as a range and degrades gracefully when the aggregator returns nothing — the field is frequently null. |
| FR-JOB-11 | P2 | More than one aggregator is supported behind a common interface, so a quota exhaustion or outage at one source is survivable. |
| FR-JOB-12 | P2 | Results are paginated beyond the first page of each title's results. |

### 5.5 M5 — ATS match analysis  *(backend built, frontend disconnected)*

The core of the product. This is where a candidate learns something they could not
have worked out themselves.

| ID | Priority | Requirement |
|---|---|---|
| FR-ATS-1 | P0 | For a chosen posting, the system returns a 0–100 match score, matched skills, missing skills, and 2–3 specific recommendations. *(Backend built)* |
| FR-ATS-2 | P0 | The ATS dashboard actually requests analysis for each selected job and renders the real result. *(Not built — see D4. This single gap is what makes the feature non-functional today.)* |
| FR-ATS-3 | P0 | Analyses run per selected job — up to 5 — with per-job loading, success, and failure states. One job failing must not blank the others. |
| FR-ATS-4 | P0 | Scoring is critical and objective: a profile missing core requirements scores low. Inflated scores make the product worthless. *(Built into the prompt; `temperature: 0.1` for score stability)* |
| FR-ATS-5 | P0 | Scoring is grounded strictly in the posting's stated requirements and the profile's stated content — no invented requirements, no credit for skills the resume does not contain. |
| FR-ATS-6 | P0 | An analysis failure is shown as a failure with a retry action, never as a `0%` score, which is indistinguishable from a genuine bad match. *(Currently the backend returns `match_score: 0` on error — this must become an explicit error state.)* |
| FR-ATS-7 | P0 | The dashboard summary — job count, best match, average match — is computed from real scores. *(Currently computed from `job.match`, the title confidence.)* |
| FR-ATS-8 | P1 | Results are cached per (profile version, posting) pair, so re-opening a job does not re-run a 30–120 second inference. |
| FR-ATS-9 | P1 | A one-line verdict band accompanies the number — Strong / Good / Fair / Weak / Mismatch — so the score is interpretable at a glance. *(Thresholds already exist in `matchPillClasses`; they must be driven by real scores.)* |
| FR-ATS-10 | P1 | Matched and missing skills link back to where they appear in the posting, so the candidate can verify the judgement. |
| FR-ATS-11 | P2 | Side-by-side comparison of all analysed jobs on one screen. |

### 5.6 M6 — Resume optimisation

The "Optimize Resume" button exists in the UI and does nothing. This module is what
converts an analysis into an outcome.

| ID | Priority | Requirement |
|---|---|---|
| FR-OPT-1 | P0 | For a given posting and analysis, the system generates a tailored version of the resume that foregrounds matched skills and the language the posting uses. |
| FR-OPT-2 | P0 | Optimisation **rewrites and reorders**; it never fabricates experience, skills, employers, or dates the profile does not contain. This is a hard constraint, not a preference. |
| FR-OPT-3 | P0 | Every change is shown as a reviewable diff against the original, and the candidate accepts or rejects each one. |
| FR-OPT-4 | P0 | The tailored resume exports as a PDF that survives ATS parsing — selectable text, single column, standard section headings, no text in images or tables. |
| FR-OPT-5 | P1 | The tailored resume is scored against the same posting so the candidate sees the before/after delta. |
| FR-OPT-6 | P1 | Tailored resumes are stored per posting, so the candidate can see which version was sent where. |
| FR-OPT-7 | P2 | Multiple templates, with an ATS-safe template as the default. |

### 5.7 M7 — Accounts, persistence, and session continuity

| ID | Priority | Requirement |
|---|---|---|
| FR-ACC-1 | P0 | A Guest can complete the full pipeline once without registering. |
| FR-ACC-2 | P0 | A Candidate can register with email and password, sign in, and sign out. |
| FR-ACC-3 | P0 | On registration, the Guest's in-flight profile, titles, and analyses are carried into the new account rather than discarded. |
| FR-ACC-4 | P0 | A Candidate's profile, searches, analyses, and tailored resumes persist across sessions and devices. |
| FR-ACC-5 | P0 | A Candidate can delete their account, which permanently removes the stored resume file, profile, and all derived analyses. |
| FR-ACC-6 | P0 | Long-running operations survive a page refresh: work is tracked server-side and the client reattaches to it. |
| FR-ACC-7 | P1 | Password reset by emailed single-use, time-limited link. |
| FR-ACC-8 | P1 | The Candidate can download everything the system holds about them as JSON. |
| FR-ACC-9 | P2 | Social sign-in (Google). |

### 5.8 M8 — Application tracker

Advertised on the landing page as a kanban board; not built.

| ID | Priority | Requirement |
|---|---|---|
| FR-TRK-1 | P0 | A Candidate can save a posting to a tracked list with a status: `SAVED → APPLIED → INTERVIEWING → OFFER / REJECTED`. |
| FR-TRK-2 | P0 | Each tracked application retains its match score, the tailored resume sent, and the date applied. |
| FR-TRK-3 | P0 | Applications are viewable as a board grouped by status. |
| FR-TRK-4 | P1 | Free-text notes and a follow-up reminder date per application. |
| FR-TRK-5 | P1 | Summary counts — applied this week, awaiting response, response rate. |
| FR-TRK-6 | P2 | A posting whose source listing has expired is flagged. |

### 5.9 M9 — Cover letter generator

| ID | Priority | Requirement |
|---|---|---|
| FR-CL-1 | P1 | Generate a cover letter for a posting from the profile and the analysis. |
| FR-CL-2 | P1 | Tone is selectable — professional, friendly, or bold — as advertised. |
| FR-CL-3 | P1 | The letter draws only on real profile content; the same no-fabrication rule as FR-OPT-2 applies. |
| FR-CL-4 | P1 | The letter is editable in place before export. |
| FR-CL-5 | P2 | Export as PDF and as plain text for pasting into application forms. |

### 5.10 M10 — Skills gap and upskilling plan

Marked "Coming Soon" in the current UI.

| ID | Priority | Requirement |
|---|---|---|
| FR-GAP-1 | P1 | Missing skills are aggregated across all analysed postings and ranked by how often they appear. |
| FR-GAP-2 | P1 | The Candidate sees which 3–5 skills would most raise their average match score. |
| FR-GAP-3 | P2 | Each gap links to concrete learning resources. |
| FR-GAP-4 | P2 | A projected match improvement per skill acquired. |

### 5.11 M11 — Interview preparation

Advertised on the landing page. Lowest priority of the advertised set.

| ID | Priority | Requirement |
|---|---|---|
| FR-INT-1 | P2 | Generate likely interview questions for a posting from its description and the candidate's profile. |
| FR-INT-2 | P2 | Questions are split into technical, behavioural, and gap-probing — the last targeting the analysis's missing skills. |

---

## 6. Data model

### 6.1 Current state

There is none. No database, no ORM, no migrations, no file storage. Every artefact
lives in React component state for the lifetime of a page view. Uploaded PDFs are
read into memory and discarded. This is the single largest structural gap between
the prototype and the product.

### 6.2 In-flight object shapes (already defined in code)

These contracts exist and are stable; they become the persisted schema.

| Shape | Defined in | Fields |
|---|---|---|
| `ResumeProfile` | `extractor.py` → `SCHEMA_TEMPLATE` | name, email, phone, location, skills[], years_of_experience, education[], experience[], projects[], certifications[], languages[], links{} |
| `InferredTitle` | `main.py` → `/api/infer-titles` | id, title, matchPercentage |
| `Job` | `job_search.py` | id, title, company, location, match, type, description, apply_link, is_remote, posted_at, salary{min,max} |
| `AtsAnalysis` | `ats_matcher.py` | match_score, matched_skills[], missing_skills[], recommendations[] |

### 6.3 Tables required

| Table | Purpose |
|---|---|
| `users` | id, email, password_hash, created_at, deleted_at |
| `resumes` | user_id, original_filename, storage_path, raw_text, uploaded_at |
| `profiles` | resume_id, profile_json, extraction_model, extracted_at, version |
| `inferred_titles` | profile_id, title, confidence, is_selected, inferred_at |
| `job_searches` | profile_id, titles_searched, country, searched_at, result_count |
| `jobs` | search_id, external_id, title, company, location, employment_type, description, apply_link, is_remote, posted_at, salary_min, salary_max |
| `ats_analyses` | profile_id, job_id, match_score, matched_skills, missing_skills, recommendations, model, analysed_at |
| `tailored_resumes` | profile_id, job_id, content, storage_path, generated_at |
| `applications` | user_id, job_id, status, applied_at, tailored_resume_id, notes, follow_up_on |
| `cover_letters` | profile_id, job_id, tone, content, generated_at |
| `jobs_queue` | id, user_id, kind, status, payload, result, error, created_at, finished_at — backs FR-ACC-6 |

### 6.4 Schema notes

- `profiles.version` increments on every re-extraction or manual correction.
  Cached analyses (FR-ATS-8) key on `(profile_version, job_id)` and invalidate when
  the profile changes — otherwise a corrected profile silently keeps stale scores.
- `jobs` is a **cache of what was seen at search time**, not a job board. Postings
  expire; the stored copy is what the candidate's analysis referred to.
- `resumes.raw_text` is retained because re-extraction with a better model should
  not require the candidate to re-upload.
- `ats_analyses.model` and `profiles.extraction_model` are recorded so results
  produced by different models remain distinguishable after a model upgrade.

---

## 7. Non-functional requirements

### 7.1 Security and privacy

| ID | Requirement |
|---|---|
| NFR-SEC-1 | `RAPIDAPI_KEY` is read from the environment and must never be committed. `backend/.env` stays untracked; `.env.example` carries placeholders only. *(Currently correct — `.gitignore` covers it.)* |
| NFR-SEC-2 | CORS must name explicit allowed origins. `allow_origins=["*"]` with `allow_credentials=True` is invalid and must be fixed before any auth work (see D9). |
| NFR-SEC-3 | Uploads are validated by content type and magic bytes, size-capped at 5 MB, and streamed rather than buffered whole. |
| NFR-SEC-4 | Resume content is processed only by the self-hosted model. No resume text, and no profile field, may be sent to a third-party API. Only inferred title strings reach the job aggregator. |
| NFR-SEC-5 | Stored resume files are not web-accessible by guessable path; access is authorised per request against the owning user. |
| NFR-SEC-6 | Passwords are hashed with a memory-hard algorithm (Argon2id or bcrypt). Sessions use signed, httpOnly, secure cookies or short-lived bearer tokens. |
| NFR-SEC-7 | Every endpoint that touches stored data authorises the caller against the owning `user_id`. Ownership is enforced server-side, never inferred from a client-supplied id. |
| NFR-SEC-8 | Upload and inference endpoints are rate-limited per IP and per account. Each carries real compute cost and is trivially abusable. |
| NFR-SEC-9 | Account deletion removes the resume file, profile, and derived rows within 30 days, and immediately revokes access. |
| NFR-SEC-10 | All production traffic over HTTPS. |

### 7.2 Performance and AI serving

Local 7B inference is the dominant cost in the system, and the numbers below are
what the current timeouts already concede.

| ID | Requirement |
|---|---|
| NFR-PERF-1 | Resume parse and extraction completes within 60 seconds for a 2-page resume. *(The current timeout is 300 s — an admission that this is slow and unbounded.)* |
| NFR-PERF-2 | Title inference completes within 30 seconds. *(Current timeout: 90 s.)* |
| NFR-PERF-3 | A single ATS analysis completes within 45 seconds. *(Current timeout: 120 s.)* |
| NFR-PERF-4 | Analyses for up to 5 selected jobs run concurrently, not serially. Five sequential analyses at current latency is a multi-minute wait. |
| NFR-PERF-5 | Job search across 5 titles returns within 10 seconds. *(Already concurrent.)* |
| NFR-PERF-6 | Every stage longer than 3 seconds shows determinate progress, and the candidate can navigate away and return without losing the work (FR-ACC-6). |
| NFR-PERF-7 | Model inference is serialised behind a queue with a declared concurrency limit. A single Ollama instance cannot serve parallel users, and the current architecture has no queue at all. |
| NFR-PERF-8 | The model endpoint, model name, and timeouts are configuration, not literals in three separate source files. `http://localhost:11434` is hardcoded in `extractor.py`, `infer_titles.py`, and `ats_matcher.py`. |

### 7.3 Reliability and correctness

| ID | Requirement |
|---|---|
| NFR-REL-1 | Every model response is schema-validated before it reaches the client. *(Established in `extractor.py` via `_fill_defaults` and `_validate_job_titles`; `ats_matcher.py` does this only shallowly and should adopt the same approach.)* |
| NFR-REL-2 | Model failure, timeout, and malformed JSON are distinguishable from a genuine result in the API response. A zero score and a failed analysis must not look alike (FR-ATS-6). |
| NFR-REL-3 | Third-party aggregator failure degrades gracefully — partial results are returned with an indication of what was missed. *(Already true per title.)* |
| NFR-REL-4 | Aggregator quota consumption is monitored, and quota exhaustion produces a clear user-facing message rather than an empty result list. |
| NFR-REL-5 | Extraction determinism is preserved: fixed seed and zero temperature for extraction; low temperature for scoring so the same pair scores consistently. *(Built.)* |
| NFR-REL-6 | Backend dependencies are declared in a `requirements.txt` or `pyproject.toml` with pinned versions. Today they are undeclared entirely, and the project is not reproducibly installable. |
| NFR-REL-7 | A regression suite covers the four stage contracts in §3.1 against fixture resumes, with the model mocked. There are currently no tests. |
| NFR-REL-8 | Prompt changes are versioned and recorded against the results they produced, so a scoring change can be traced to its cause. |

### 7.4 Usability and platform

| ID | Requirement |
|---|---|
| NFR-UX-1 | Responsive web, targeting desktop first and usable down to 375 px. |
| NFR-UX-2 | No error is reported via `alert()`. Failures render inline with a retry action (see D12). |
| NFR-UX-3 | Development mocks are controlled by environment configuration, not by a constant edited in source (see D3). |
| NFR-UX-4 | Every number shown to a candidate is either real or explicitly labelled as pending. Placeholder text must never ship — `JobListings.jsx` currently renders the literal string `text-sm, font-medium` as a company subtitle. |
| NFR-UX-5 | The landing page advertises seven capabilities, of which two and a half exist. Marketing copy and shipped functionality are reconciled before public launch — unbuilt features are labelled "Coming Soon" or removed. |
| NFR-UX-6 | Wait states set expectations honestly: a 45-second analysis says so. |

---

## 8. Release phasing

Sequenced so each phase ships something usable on its own.

### Phase 0 — Reconnect the pipeline *(prerequisite, no new features)*

Restore the real flow in `App.jsx` and delete the temporary testing block. Fix the
`setSelectedJob` / `setSelectedJobs` mismatch. Move `USE_MOCK_DATA` to environment
configuration and default it off. Wire `AtsAnalysis.jsx` to `/api/analyze-ats` and
delete its hardcoded `JOBS` array and unused state. Remove the dead `getJobs()`
helper or correct it to `POST`. Fix CORS. Enforce the 5 MB upload limit on both
sides. Add `requirements.txt`. Remove the stray root `package.json` dependencies
and the placeholder string in the job card.

**Outcome:** every feature already written actually runs, end to end, on live data.
This is the highest-leverage work in the document — the code is largely present and
merely disconnected.

### Phase 1 — Make the analysis trustworthy

Per-job concurrent analysis with individual loading and error states. Real scores
driving the summary bar and the verdict bands. Explicit failure states distinct
from a zero score. Per-posting match percentages replacing the reused title
confidence. Profile review and correction before downstream use.

**Outcome:** the ATS analysis is genuinely useful and its numbers can be believed.

### Phase 2 — Accounts and persistence *(structural)*

Database, migrations, and file storage. Registration, sign-in, guest-to-account
carryover. Persisted profiles, searches, analyses. A job queue so long operations
survive a refresh. Analysis caching keyed on profile version.

**Outcome:** NextHire becomes a product a candidate returns to, rather than a demo
they run once.

### Phase 3 — Resume optimisation *(core value)*

Tailored resume generation from an analysis, with reviewable diffs, the
no-fabrication guarantee, ATS-safe PDF export, and before/after re-scoring.

**Outcome:** the candidate leaves with a better application, not just a better
understanding of why their current one fails.

### Phase 4 — Application lifecycle

Application tracker board. Cover letter generator. Skills gap aggregation and
upskilling plan. Interview preparation.

**Outcome:** the full loop the landing page already promises.

---

## 9. Success metrics

| Metric | Target |
|---|---|
| Upload → first ATS score | Under 2 minutes end to end |
| Sessions reaching the ATS dashboard with a real score | Above 70% of resume uploads |
| Extraction accuracy on key fields (name, email, skills, experience) | Above 95%, measured against a hand-labelled fixture set |
| Inferred titles a candidate keeps rather than deselects | Above 60% |
| Analyses that fail or time out | Below 5% |
| Candidates who generate at least one tailored resume | Above 40% after Phase 3 |
| Return rate within 7 days | Above 30% after Phase 2 |
| Candidate-reported score accuracy ("did this match your own judgement?") | Above 80% agreement |

---

## 10. Assumptions

1. Candidates are primarily Indian early-career and fresher technical job seekers —
   the default country is `in` and the inference prompt targets entry-level hiring.
2. Resumes are text-based PDFs. Scanned or image-only resumes are rejected, not OCR'd.
3. A single Ollama instance running `qwen2.5:7b` serves inference, and hardware
   adequate to that is available wherever NextHire is deployed.
4. Job postings come from JSearch via RapidAPI, and the deployment's plan quota is
   sufficient for expected volume — five titles per search is five API calls.
5. Postings are transient. NextHire caches what it showed but does not maintain a
   job corpus.
6. A tailored resume is downloaded and submitted by the candidate; NextHire does
   not submit applications.
7. English-language resumes and postings only.

---

## 11. Open questions

| # | Question | Needed by |
|---|---|---|
| Q1 | Is the local Ollama deployment the long-term plan, or will a hosted model be used in production? This decides NFR-SEC-4 — the privacy guarantee that resume content never leaves the deployment is only free while the model is self-hosted. | Phase 2 |
| Q2 | What is the RapidAPI plan and monthly quota? Five titles per search consumes five calls; the ceiling determines whether search needs throttling or caching. | Phase 0 |
| Q3 | Should Guests get the full pipeline or a limited preview? Unlimited guest access means unlimited unauthenticated inference cost. | Phase 2 |
| Q4 | Does "Optimize Resume" produce an editable document or a finished PDF? The former needs a resume editor — a substantial piece of UI not currently scoped. | Phase 3 |
| Q5 | How long are resume files and profiles retained for an inactive account? | Phase 2 |
| Q6 | Is `qwen2.5:7b` sufficient for scoring quality, or does the ATS stage need a larger model? Extraction and scoring have different accuracy requirements and could use different models. | Phase 1 |
| Q7 | Should the title cap stay at 5? The dialog caps and pre-selects all 5, so the default behaviour is always the maximum number of API calls. | Phase 0 |
| Q8 | Is there a target country expansion beyond India, and does the inference prompt need regional title vocabularies if so? | Phase 4 |
| Q9 | How is the score explained to a candidate who disagrees with it? Trust in the number is the product; a wrong-looking score with no reasoning is worse than no score. | Phase 1 |

---

## 12. Out of scope

Auto-applying to postings · recruiter or employer tooling · a proprietary job board
or crawled job corpus · OCR for scanned resumes · non-English resumes · mobile
applications · payments and subscription billing · salary negotiation tooling ·
referral or networking features · background checks or credential verification ·
LinkedIn profile import or scraping.
