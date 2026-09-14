# NextHire

AI job-matching and resume analysis. Upload a resume once; NextHire reads it,
works out which roles it actually qualifies you for, finds live postings for
those roles, and scores your resume against each one — showing which
requirements you meet, which you miss, and what to change.

Everything that reads your resume runs **locally**. Resume content never leaves
your machine.

- [docs/PRD.md](docs/PRD.md) — what the product is and what it must do
- [docs/BUILD-PLAN.md](docs/BUILD-PLAN.md) — the 44 steps to build it, and where we are

---

## The pipeline

```
Upload PDF  →  Structured profile  →  Review & correct  →  Job titles
                                                               ↓
                       ATS analysis  ←  Pick up to 5  ←  Live job postings
```

Each stage is one backend call. The slow ones (extraction, inference, analysis)
run against a local model and take tens of seconds; every one of them shows
staged progress rather than a spinner.

---

## Setup

### 1. Prerequisites

- **Python 3.11+**
- **Node 20.19+ or 22.12+**
- **[Ollama](https://ollama.com)** — runs the model that reads your resume

### 2. Install the model

```bash
ollama pull qwen2.5:3b
```

`qwen2.5:3b` (~1.9GB) is the right default on a CPU-only machine. `qwen2.5:7b`
scores better but runs roughly 2-3x slower without a GPU - pull it and set
`OLLAMA_MODEL` if extraction quality matters more to you than speed.

Ollama must be running (`ollama serve`) before you upload a resume. Without it
the app still starts, and tells you clearly that the model is unreachable — it
does not silently show you a zero score.

### 3. Backend

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r backend/requirements.txt

cd backend
uvicorn main:app --reload
```

Runs on http://localhost:8000. Check it with http://localhost:8000/api/health.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Runs on http://localhost:5173.

---

## Configuration

Both sides run with no config at all. To change anything, copy the templates:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

The values worth knowing about:

| Setting | Default | Why you would change it |
|---|---|---|
| `USE_MOCK_JOBS` | on when no API key | Serve built-in sample postings instead of calling the job API |
| `RAPIDAPI_KEY` | unset | Enables live job search (see below) |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Set to `qwen2.5:3b` on CPU-only machines, or larger for better scoring |
| `LLM_CONCURRENCY` | `2` | Set to `1` on CPU - parallel calls contend for the same cores |
| `EXTRACTION_TIMEOUT_SECONDS` | `300` | Lower it on fast hardware |
| `MAX_UPLOAD_MB` | `5` | Upload ceiling, enforced server-side |

### Live job search

Job postings come from [JSearch on RapidAPI](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch),
which has a free tier. **Without a key, NextHire serves sample postings and the
rest of the pipeline works normally** — including real ATS analysis against
those postings, since that runs on your local model.

To use live postings:

1. Get a free RapidAPI key for JSearch.
2. Put it in `backend/.env` as `RAPIDAPI_KEY=...`
3. Set `USE_MOCK_JOBS=false`.

> Each search spends **one API call per selected job title**, up to five per
> search. Leaving `USE_MOCK_JOBS=true` during development keeps the free tier
> intact. If the quota does run out, the app says so rather than showing an
> empty list.

---

## Tests

```bash
cd backend
python -m pytest
```

142 tests. The model and every external API are mocked, so the suite runs
offline in under two seconds and spends no quota.

```bash
cd frontend
npm run lint
npm run build
```

---

## Project layout

```
backend/
  main.py           FastAPI routes - one per pipeline stage
  config.py         Every tunable, read from the environment
  llm.py            Async Ollama client: bounded concurrency, typed errors
  schema_utils.py   Forces model output into a known shape
  extractor.py      Resume text  -> structured profile
  infer_titles.py   Profile      -> ranked job titles
  job_search.py     Titles       -> live postings (or samples)
  prescore.py       Free local keyword overlap per posting
  ats_matcher.py    Profile + posting -> match analysis
  tests/            Offline regression suite

frontend/src/
  App.jsx           The pipeline as an explicit step machine
  api/client.js     HTTP layer; normalises every failure
  api/pipeline.js   The four stage calls
  components/       One component per stage, plus shared ui/
```

---

## Notes on behaviour

A few things work the way they do deliberately:

- **A failed analysis is never shown as a score.** If the model is down or times
  out, that job shows as failed with its own retry button, and is excluded from
  the best/average figures. A `0%` would be indistinguishable from a genuinely
  bad match.
- **Job cards show a skill count, not a match percentage.** Before analysis runs,
  the only honest per-posting signal is how many of your own skills appear in the
  posting text. The real percentage appears after the ATS analysis.
- **Matched skills are evidenced.** Tap one on the analysis screen to see the
  sentence in the posting it came from. Skills with no quote are ones the model
  claimed but the posting never mentions.
- **Extraction is deterministic.** The same resume always produces the same
  profile.

### Why the score is not just whatever the model said

A small model's **score** is the least reliable thing it produces. Its **lists**
are much better, and unlike the score they can be checked independently — a
matched skill can be verified against the profile *and* against the posting
text. Every failure observed in testing was the score contradicting the model's
own lists:

| What it did | Why it is wrong |
|---|---|
| Scored **85%** on a Java role | It credited Postman, Express and React — skills that posting never mentions |
| Scored **10%** on another role | Its own lists said 4 matched against 7 missing, which is 36% coverage |
| Marked **Docker and Git missing** | Both were in the candidate's own profile |

So the lists anchor the score, under three rules:

1. **A skill the model calls missing is checked against the profile first.** A
   demonstrable false negative moves to matched, and the correction is shown in
   the UI rather than applied silently.
2. **The score may not exceed evidenced coverage** — matched skills that appear
   nowhere in the posting are not requirements it stated, so they cannot be
   evidence of fit.
3. **Nor may it sit far below that coverage**, and either way it never moves
   more than **15 points** from what the model said. Pessimism inside that
   allowance is respected: a missing core requirement should weigh more than a
   missing nice-to-have, and a ratio cannot see the difference.

Scoring is also **deterministic** (`temperature: 0`, fixed seed), like
extraction. At 0.1 the same resume and posting scored 73% on one run and 80% on
the next, naming 17 matched skills one time and 8 the next. A scoring tool whose
answer changes when you press retry cannot be trusted or cached. Note that the
very first analysis after Ollama loads the model can still differ; runs after
that are stable.

If you move to a larger model these guards stay useful but should bite less
often. `OLLAMA_MODEL` is the only thing you need to change.

