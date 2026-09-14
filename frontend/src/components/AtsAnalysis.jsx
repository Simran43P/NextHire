import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Check,
  Loader2,
  Quote,
  RefreshCw,
  Sparkles,
  TriangleAlert,
  X,
} from "lucide-react";
import { analyzeAts } from "../api/pipeline";
import ErrorNotice from "./ui/ErrorNotice";

/**
 * The ATS analysis dashboard.
 *
 * This screen previously rendered a hardcoded array and never called the
 * analysis endpoint at all - it displayed "-" and "Analysis Pending" forever.
 * It now runs a real analysis per selected job.
 *
 * Three behaviours matter here:
 *
 * 1. **Parallel, independent requests.** One request per job, fired at once.
 *    The server bounds how many actually reach the model, so the client does
 *    not need to serialise - and each result renders the moment it lands
 *    rather than after the slowest one.
 *
 * 2. **A failure is never a zero.** A job whose analysis failed shows as failed,
 *    with its own retry. It is not folded into the averages and never displays
 *    a 0% that would read as "you are a terrible fit".
 *
 * 3. **Claims are evidenced.** Every matched skill the model found in the
 *    posting can be expanded to show the sentence it came from.
 */

const STATUS = {
  loading: "loading",
  done: "done",
  error: "error",
};

function scoreColour(score) {
  if (score >= 85) return "bg-green-100 text-green-700";
  if (score >= 70) return "bg-emerald-100 text-emerald-700";
  if (score >= 55) return "bg-yellow-100 text-yellow-700";
  if (score >= 40) return "bg-orange-100 text-orange-700";
  return "bg-red-100 text-red-700";
}

function SummaryStat({ value, label }) {
  return (
    <div className="text-center">
      <div className="text-2xl font-bold text-slate-900 tabular-nums">{value}</div>
      <div className="text-sm text-slate-500">{label}</div>
    </div>
  );
}

function SkillChip({ skill, evidence, isOpen, onToggle, tone }) {
  const hasEvidence = Boolean(evidence);
  const styles =
    tone === "matched"
      ? "bg-green-50 border-green-200 text-green-700"
      : "bg-red-50 border-red-200 text-red-700";

  return (
    <button
      type="button"
      onClick={hasEvidence ? onToggle : undefined}
      title={hasEvidence ? "Show where this appears in the posting" : undefined}
      className={`rounded-full border px-3 py-1 text-sm flex items-center gap-1 transition-colors ${styles} ${
        hasEvidence ? "cursor-pointer hover:brightness-95" : "cursor-default"
      } ${isOpen ? "ring-2 ring-offset-1 ring-green-300" : ""}`}
    >
      {tone === "matched" ? (
        <Check className="w-3.5 h-3.5" />
      ) : (
        <X className="w-3.5 h-3.5" />
      )}
      {skill}
      {hasEvidence && <Quote className="w-3 h-3 opacity-50" />}
    </button>
  );
}

function AnalysisPanel({ job, state, onRetry }) {
  // Keyed by job, so switching jobs collapses the open quote without needing
  // an effect to reset it.
  const [open, setOpen] = useState({ jobId: null, skill: null });
  const openSkill = open.jobId === job?.id ? open.skill : null;

  if (!job) {
    return (
      <div className="bg-white rounded-3xl shadow-md border border-slate-100 p-8 text-center text-slate-400">
        Select a job to see its analysis.
      </div>
    );
  }

  const analysis = state?.analysis;

  return (
    <div className="bg-white rounded-3xl shadow-md border border-slate-100 p-8">
      <div className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-purple-700 bg-purple-50 rounded-full px-3 py-1 mb-6">
        <Sparkles className="w-3 h-3" />
        AI ATS analysis
      </div>

      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <h3 className="text-3xl font-bold text-slate-900">{job.title}</h3>
          <p className="text-slate-500 mt-1">{job.company}</p>
        </div>

        <div className="text-right flex-shrink-0">
          {state?.status === STATUS.done ? (
            <>
              <div className="text-4xl font-extrabold text-slate-900 tabular-nums">
                {analysis.match_score}%
              </div>
              <span
                className={`inline-block rounded-full px-3 py-1 text-sm font-medium mt-1 ${scoreColour(
                  analysis.match_score
                )}`}
              >
                {analysis.label}
              </span>
            </>
          ) : state?.status === STATUS.error ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-red-50 text-red-700 px-3 py-1 text-sm font-medium">
              <TriangleAlert className="w-3.5 h-3.5" />
              Analysis failed
            </span>
          ) : (
            <span className="inline-flex items-center gap-2 rounded-full bg-slate-100 text-slate-500 px-3 py-1 text-sm font-medium">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Analysing
            </span>
          )}
        </div>
      </div>

      {state?.status === STATUS.error && (
        <ErrorNotice error={state.error} className="mt-6" onRetry={onRetry} />
      )}

      {state?.status === STATUS.loading && (
        <div className="mt-8 space-y-4" aria-busy="true">
          <p className="text-sm text-slate-500">
            Comparing your resume against this posting. This usually takes 30-45 seconds.
          </p>
          <div className="space-y-2.5">
            {[...Array(4)].map((_, index) => (
              <div
                key={index}
                className="h-3 rounded-full bg-slate-100 animate-pulse"
                style={{ width: `${90 - index * 15}%` }}
              />
            ))}
          </div>
        </div>
      )}

      {state?.status === STATUS.done && (
        <>
          <p className="text-slate-600 mt-4">{analysis.summary}</p>

          {/* A raised score is never silent. If the model claimed the candidate
              lacked something their own resume lists, say so plainly rather
              than quietly presenting an adjusted number. */}
          {analysis.corrected_skills?.length > 0 && (
            <div className="mt-4 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3">
              <p className="text-xs text-blue-900 leading-relaxed">
                <span className="font-semibold">Corrected:</span> the first pass marked{" "}
                {analysis.corrected_skills.join(", ")}{" "}
                {analysis.corrected_skills.length === 1 ? "as missing" : "as missing"},
                but {analysis.corrected_skills.length === 1 ? "it is" : "they are"} on
                your resume. Counted as matched and the score raised to suit.
              </p>
            </div>
          )}

          <div className="mb-8" />

          <div>
            <div className="text-sm font-bold text-slate-900 mb-3">
              Matched skills
              {analysis.matched_skills.length > 0 && (
                <span className="ml-2 font-normal text-xs text-slate-400">
                  tap one to see where it appears in the posting
                </span>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              {analysis.matched_skills.length === 0 && (
                <p className="text-sm text-slate-400">
                  None of your listed skills matched this posting.
                </p>
              )}
              {analysis.matched_skills.map((skill) => (
                <SkillChip
                  key={skill}
                  skill={skill}
                  tone="matched"
                  evidence={analysis.evidence?.[skill]}
                  isOpen={openSkill === skill}
                  onToggle={() =>
                    setOpen({
                      jobId: job.id,
                      skill: openSkill === skill ? null : skill,
                    })
                  }
                />
              ))}
            </div>

            {openSkill && analysis.evidence?.[openSkill] && (
              <blockquote className="mt-3 rounded-2xl border-l-4 border-green-300 bg-green-50/60 px-4 py-3">
                <p className="text-xs font-semibold text-green-800 mb-1">
                  "{openSkill}" in this posting
                </p>
                <p className="text-sm text-slate-700 italic leading-relaxed">
                  {analysis.evidence[openSkill]}
                </p>
              </blockquote>
            )}
          </div>

          <div>
            <div className="text-sm font-bold text-slate-900 mt-6 mb-3">
              Missing or weak skills
            </div>
            <div className="flex flex-wrap gap-2">
              {analysis.missing_skills.length === 0 ? (
                <p className="text-sm text-slate-400">
                  Nothing major missing for this role.
                </p>
              ) : (
                analysis.missing_skills.map((skill) => (
                  <SkillChip key={skill} skill={skill} tone="missing" />
                ))
              )}
            </div>
          </div>

          {analysis.recommendations.length > 0 && (
            <div>
              <div className="text-sm font-bold text-slate-900 mt-6 mb-3">
                What you can improve
              </div>
              <ul className="bg-purple-50/50 border border-purple-100 rounded-2xl p-5 space-y-2">
                {analysis.recommendations.map((line) => (
                  <li
                    key={line}
                    className="text-sm text-slate-700 leading-relaxed flex gap-2"
                  >
                    <span className="text-purple-400 flex-shrink-0">•</span>
                    {line}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Not built yet (Phase 3). Labelled rather than left looking live. */}
          <button
            type="button"
            disabled
            className="w-full mt-8 py-4 rounded-full text-slate-500 font-bold text-lg bg-slate-100 flex items-center justify-center gap-2 cursor-not-allowed"
          >
            Optimize resume
            <span className="bg-blue-50 text-blue-600 text-[10px] uppercase font-bold px-2 py-0.5 rounded-full">
              Coming soon
            </span>
          </button>

          <div className="text-center mt-4">
            <span className="text-sm text-slate-500">Get upskilling plan</span>
            <span className="bg-blue-50 text-blue-600 text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ml-2 align-middle">
              Coming soon
            </span>
          </div>
        </>
      )}
    </div>
  );
}

export default function ATSAnalysisDashboard({
  selectedJobs = [],
  resumeProfile,
  profileId = null,
  background = false,
  onBack,
}) {
  const [jobs, setJobs] = useState(selectedJobs);
  const [selectedId, setSelectedId] = useState(selectedJobs[0]?.id ?? null);
  const [results, setResults] = useState({});
  const abortRef = useRef(new Map());

  const runAnalysis = useCallback(
    async (job, { refresh = false } = {}) => {
      abortRef.current.get(job.id)?.abort();
      const controller = new AbortController();
      abortRef.current.set(job.id, controller);

      setResults((previous) => ({
        ...previous,
        [job.id]: { status: STATUS.loading },
      }));

      try {
        // With both ids the server serves a cached result when the profile has
        // not changed, so revisiting a job is instant instead of another
        // 30-second inference.
        const analysis = await analyzeAts(
          {
            profile: resumeProfile,
            profileId,
            jobId: job.job_id ?? null,
            jobDescription: job.description ?? "",
          },
          { background, refresh, signal: controller.signal }
        );
        if (controller.signal.aborted) return;
        setResults((previous) => ({
          ...previous,
          [job.id]: { status: STATUS.done, analysis },
        }));
      } catch (error) {
        if (error?.name === "AbortError") return;
        // Deliberately not a zero score. The candidate must be able to tell a
        // failed analysis from a genuine bad match.
        setResults((previous) => ({
          ...previous,
          [job.id]: { status: STATUS.error, error },
        }));
      }
    },
    [resumeProfile, profileId, background]
  );

  useEffect(() => {
    // Fire every job at once. The server's semaphore decides how many actually
    // reach the model; each result renders as it arrives.
    jobs.forEach((job) => runAnalysis(job));

    const inFlight = abortRef.current;
    return () => {
      inFlight.forEach((controller) => controller.abort());
      inFlight.clear();
    };
    // Intentionally runs once for the initial set; retries are manual.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const removeJob = (id, event) => {
    event.stopPropagation();
    abortRef.current.get(id)?.abort();
    abortRef.current.delete(id);

    const remaining = jobs.filter((job) => job.id !== id);
    setJobs(remaining);
    setResults((previous) => {
      const next = { ...previous };
      delete next[id];
      return next;
    });
    if (id === selectedId) setSelectedId(remaining[0]?.id ?? null);
  };

  const selected = jobs.find((job) => job.id === selectedId) ?? jobs[0] ?? null;

  // Summary figures come only from analyses that actually completed. Averaging
  // in a pending or failed job would understate every number on the page.
  const scored = jobs
    .map((job) => results[job.id])
    .filter((state) => state?.status === STATUS.done)
    .map((state) => state.analysis.match_score);

  const pending = jobs.filter(
    (job) => results[job.id]?.status === STATUS.loading
  ).length;
  const failed = jobs.filter((job) => results[job.id]?.status === STATUS.error).length;

  const best = scored.length ? Math.max(...scored) : null;
  const average = scored.length
    ? Math.round(scored.reduce((total, score) => total + score, 0) / scored.length)
    : null;

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white border-b border-slate-100">
        <div className="max-w-6xl mx-auto px-8 py-5 flex items-center">
          <Sparkles className="w-6 h-6 text-blue-500 mr-2" fill="currentColor" />
          <span className="text-xl font-extrabold text-slate-900">NextHire</span>
        </div>
      </div>

      <div className="max-w-6xl mx-auto p-8">
        <div className="text-center mb-10">
          {onBack && (
            <button
              onClick={onBack}
              className="inline-flex items-center gap-2 text-sm text-slate-500 font-medium mb-4 hover:text-slate-700 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to job listings
            </button>
          )}
          <h1 className="text-4xl md:text-5xl font-extrabold text-slate-900">
            Your{" "}
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-fuchsia-500">
              ATS analysis
            </span>
          </h1>
          <p className="text-slate-500 text-base max-w-2xl mx-auto mt-4">
            Compare how your resume matches the jobs you selected and decide which roles
            are worth applying to.
          </p>
        </div>

        <div className="bg-white rounded-3xl shadow-sm px-8 py-4 mx-auto flex items-center justify-center gap-12 w-fit mb-4 border border-slate-100">
          <SummaryStat value={jobs.length} label="Jobs selected" />
          <div className="w-px h-10 bg-slate-100" />
          <SummaryStat value={best === null ? "-" : `${best}%`} label="Best match" />
          <div className="w-px h-10 bg-slate-100" />
          <SummaryStat
            value={average === null ? "-" : `${average}%`}
            label="Average match"
          />
        </div>

        {(pending > 0 || failed > 0) && (
          <p className="text-center text-xs text-slate-400 mb-10">
            {pending > 0 && `${pending} still analysing. `}
            {failed > 0 &&
              `${failed} failed and ${failed === 1 ? "is" : "are"} excluded from these figures.`}
          </p>
        )}
        {pending === 0 && failed === 0 && <div className="mb-10" />}

        <div className="grid grid-cols-12 gap-8">
          <div className="col-span-12 md:col-span-5 lg:col-span-4">
            <h2 className="text-lg font-bold text-slate-900">Selected jobs</h2>
            <p className="text-sm text-slate-500 mb-4">Review your matches</p>

            <div className="flex flex-col gap-4">
              {jobs.map((job) => {
                const state = results[job.id];
                const isActive = job.id === selected?.id;

                const card = (
                  <div
                    onClick={() => setSelectedId(job.id)}
                    className={`bg-white p-4 flex items-center justify-between cursor-pointer transition-colors ${
                      isActive
                        ? "rounded-[14px]"
                        : "rounded-2xl shadow-sm border border-slate-100 hover:border-slate-200"
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="font-bold text-slate-900 truncate">{job.title}</div>
                      <div className="flex items-center gap-1.5 mt-1">
                        {state?.status === STATUS.loading && (
                          <>
                            <Loader2 className="w-3 h-3 animate-spin text-slate-400" />
                            <span className="text-xs text-slate-500">Analysing...</span>
                          </>
                        )}
                        {state?.status === STATUS.done && (
                          <>
                            <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                            <span className="text-xs text-slate-500">
                              {state.analysis.label}
                            </span>
                          </>
                        )}
                        {state?.status === STATUS.error && (
                          <>
                            <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                            <span className="text-xs text-red-600">Failed</span>
                            <button
                              onClick={(event) => {
                                event.stopPropagation();
                                runAnalysis(job);
                              }}
                              className="ml-1 inline-flex items-center gap-1 text-xs font-semibold text-red-700 hover:text-red-900"
                            >
                              <RefreshCw className="w-3 h-3" />
                              Retry
                            </button>
                          </>
                        )}
                        {!state && (
                          <span className="text-xs text-slate-400">{job.company}</span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                      {state?.status === STATUS.done && (
                        <span
                          className={`rounded-full px-3 py-1 text-sm font-semibold tabular-nums ${scoreColour(
                            state.analysis.match_score
                          )}`}
                        >
                          {state.analysis.match_score}%
                        </span>
                      )}
                      <button
                        onClick={(event) => removeJob(job.id, event)}
                        aria-label={`Remove ${job.title}`}
                        className="text-xs text-slate-400 hover:text-red-500 transition-colors"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                );

                return isActive ? (
                  <div
                    key={job.id}
                    className="bg-gradient-to-r from-blue-500 to-fuchsia-500 p-[2px] rounded-2xl"
                  >
                    {card}
                  </div>
                ) : (
                  <div key={job.id}>{card}</div>
                );
              })}

              {jobs.length === 0 && (
                <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 text-center text-sm text-slate-400">
                  No jobs selected.
                </div>
              )}
            </div>
          </div>

          <div className="col-span-12 md:col-span-7 lg:col-span-8">
            <AnalysisPanel
              job={selected}
              state={selected ? results[selected.id] : null}
              onRetry={selected ? () => runAnalysis(selected) : undefined}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
