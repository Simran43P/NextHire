import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Check,
  Download,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  X,
} from "lucide-react";
import { applyChanges, downloadPdf, listTemplates, proposeChanges } from "../api/optimize";
import ErrorNotice from "./ui/ErrorNotice";
import StageProgress from "./ui/StageProgress";

/**
 * Review and apply tailored edits.
 *
 * Every change is shown as a diff and accepted individually. A single button
 * that rewrites the resume and hands back finished text would be asking the
 * candidate to trust a 3B model with their employment history, which is not a
 * reasonable thing to ask - they are the one who has to sit in the interview.
 *
 * Changes start accepted, because they have already passed the fabrication
 * guard and the common case is agreeing with them. Rejecting is one click.
 */

const KIND_LABELS = {
  summary: "New summary",
  skills: "Skill order",
  bullet: "Rewritten line",
};

/**
 * Word-level diff, so a small rewording does not read as a whole new sentence.
 * A longest-common-subsequence table over words is more than enough at the
 * length of a resume bullet.
 */
function diffWords(before, after) {
  const a = (before || "").split(/(\s+)/).filter(Boolean);
  const b = (after || "").split(/(\s+)/).filter(Boolean);

  const table = Array.from({ length: a.length + 1 }, () =>
    new Array(b.length + 1).fill(0)
  );
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i][j] =
        a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }

  const removed = [];
  const added = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      removed.push({ text: a[i], changed: false });
      added.push({ text: b[j], changed: false });
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      removed.push({ text: a[i], changed: true });
      i += 1;
    } else {
      added.push({ text: b[j], changed: true });
      j += 1;
    }
  }
  while (i < a.length) removed.push({ text: a[i++], changed: true });
  while (j < b.length) added.push({ text: b[j++], changed: true });

  return { removed, added };
}

function DiffText({ parts, tone }) {
  const highlight =
    tone === "removed" ? "bg-red-100 text-red-800" : "bg-green-100 text-green-900";
  return (
    <p className="text-sm leading-relaxed">
      {parts.map((part, index) =>
        part.changed ? (
          <span key={index} className={`${highlight} rounded px-0.5`}>
            {part.text}
          </span>
        ) : (
          <span key={index} className="text-slate-600">
            {part.text}
          </span>
        )
      )}
    </p>
  );
}

function ChangeCard({ change, accepted, onToggle }) {
  const { removed, added } = useMemo(
    () => diffWords(change.before, change.after),
    [change.before, change.after]
  );
  const isAddition = !change.before?.trim();

  return (
    <div
      className={`rounded-2xl border p-5 transition-colors ${
        accepted ? "border-slate-200 bg-white" : "border-slate-100 bg-slate-50/60 opacity-70"
      }`}
    >
      <div className="flex items-start justify-between gap-4 mb-3">
        <div>
          <span className="inline-block rounded-full bg-purple-50 text-purple-700 px-2.5 py-0.5 text-xs font-semibold">
            {KIND_LABELS[change.kind] ?? "Change"}
          </span>
          {change.why && (
            <p className="text-xs text-slate-500 mt-1.5">{change.why}</p>
          )}
        </div>

        <button
          type="button"
          onClick={() => onToggle(change.id)}
          className={`flex-shrink-0 inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
            accepted
              ? "bg-green-100 text-green-800 hover:bg-green-200"
              : "bg-slate-200 text-slate-600 hover:bg-slate-300"
          }`}
        >
          {accepted ? <Check className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}
          {accepted ? "Accepted" : "Rejected"}
        </button>
      </div>

      {!isAddition && (
        <div className="border-l-2 border-red-200 pl-3 mb-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-red-400 mb-0.5">
            Before
          </p>
          <DiffText parts={removed} tone="removed" />
        </div>
      )}

      <div className="border-l-2 border-green-300 pl-3">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-green-500 mb-0.5">
          {isAddition ? "Added" : "After"}
        </p>
        <DiffText parts={added} tone="added" />
      </div>
    </div>
  );
}

function RejectedNotice({ rejected }) {
  const [open, setOpen] = useState(false);
  if (!rejected?.length) return null;

  return (
    <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3.5 mb-6">
      <div className="flex items-start gap-3">
        <ShieldCheck className="w-4 h-4 mt-0.5 flex-shrink-0 text-amber-600" />
        <div className="min-w-0 flex-1">
          <p className="text-xs text-amber-900 leading-relaxed">
            <span className="font-semibold">
              {rejected.length} suggestion{rejected.length === 1 ? "" : "s"} discarded.
            </span>{" "}
            {rejected.length === 1 ? "It claimed" : "They claimed"} something your resume
            does not say, so {rejected.length === 1 ? "it was" : "they were"} thrown out
            before you saw {rejected.length === 1 ? "it" : "them"}.
          </p>
          <button
            onClick={() => setOpen((value) => !value)}
            className="text-xs font-semibold text-amber-800 hover:text-amber-950 mt-1.5"
          >
            {open ? "Hide" : "Show what was discarded"}
          </button>

          {open && (
            <div className="mt-3 space-y-2">
              {rejected.map((change, index) => (
                <div key={index} className="rounded-xl bg-white/70 border border-amber-200 p-3">
                  <p className="text-xs text-slate-600 italic">"{change.after}"</p>
                  <p className="text-[11px] text-amber-800 mt-1">
                    Not in your resume: {(change.fabricated ?? []).join(", ")}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Result({ result, onDownload, downloading, templates, template, setTemplate }) {
  const delta =
    result.beforeScore !== null && result.beforeScore !== undefined
      ? result.afterScore - result.beforeScore
      : null;

  return (
    <div className="rounded-3xl border border-slate-100 bg-white shadow-md p-8 text-center">
      <div className="inline-flex items-center gap-1.5 rounded-full bg-green-50 text-green-700 px-3 py-1 text-xs font-semibold mb-5">
        <Check className="w-3.5 h-3.5" />
        Tailored resume ready
      </div>

      <div className="flex items-center justify-center gap-6">
        {result.beforeScore !== null && result.beforeScore !== undefined && (
          <>
            <div>
              <div className="text-3xl font-bold text-slate-400 tabular-nums">
                {result.beforeScore}%
              </div>
              <div className="text-xs text-slate-500 mt-1">Before</div>
            </div>
            <TrendingUp
              className={`w-6 h-6 ${delta > 0 ? "text-green-500" : "text-slate-300"}`}
            />
          </>
        )}
        <div>
          <div className="text-4xl font-extrabold text-slate-900 tabular-nums">
            {result.afterScore}%
          </div>
          <div className="text-xs text-slate-500 mt-1">After</div>
        </div>
      </div>

      {delta !== null && (
        <p className="text-sm text-slate-500 mt-4">
          {delta > 0
            ? `Up ${delta} points against this posting.`
            : delta === 0
            ? "The same score - the edits were phrasing, not new substance."
            : `Down ${Math.abs(delta)} points. Your original wording scored better here.`}
        </p>
      )}

      {templates.length > 1 && (
        <div className="flex flex-wrap items-center justify-center gap-2 mt-7">
          {templates.map((option) => (
            <button
              key={option.key}
              onClick={() => setTemplate(option.key)}
              title={option.description}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                template === option.key
                  ? "bg-slate-900 text-white"
                  : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}

      <button
        onClick={onDownload}
        disabled={downloading}
        className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-blue-500 to-fuchsia-500 text-white px-7 py-3 text-sm font-medium shadow-lg shadow-purple-500/30 hover:opacity-90 transition-opacity mt-5 disabled:opacity-50"
      >
        <Download className="w-4 h-4" />
        {downloading ? "Building PDF..." : "Download tailored resume"}
      </button>

      <p className="text-xs text-slate-400 mt-3">
        Every template is single column with selectable text and standard headings.
        They differ in density, never in what a parser can read.
      </p>
    </div>
  );
}

export default function ResumeOptimizer({
  job,
  profile,
  profileId = null,
  analysis = null,
  onBack,
}) {
  const [phase, setPhase] = useState("loading"); // loading | review | applying | done
  const [changes, setChanges] = useState([]);
  const [rejected, setRejected] = useState([]);
  const [acceptedIds, setAcceptedIds] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [template, setTemplate] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  const jobId = job?.job_id ?? null;
  const jobDescription = job?.description ?? "";

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    (async () => {
      try {
        const proposed = await proposeChanges(
          { profile, profileId, jobDescription, jobId, analysis },
          { signal: controller.signal }
        );
        if (cancelled) return;

        setChanges(proposed.changes);
        setRejected(proposed.rejected);
        setAcceptedIds(proposed.changes.map((change) => change.id));
        if (proposed.changes.length === 0 && proposed.rejected.length === 0) {
          setError({
            message:
              "No safe improvements were found for this posting. Your resume may already be well matched, or the model could not find wording to improve without inventing something.",
            retryable: true,
          });
        }
      } catch (err) {
        if (cancelled || err?.name === "AbortError") return;
        setError(err);
      } finally {
        if (!cancelled) setPhase("review");
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [profile, profileId, jobDescription, jobId, analysis, reloadToken]);

  useEffect(() => {
    let cancelled = false;
    listTemplates()
      .then((result) => {
        if (cancelled) return;
        setTemplates(result.templates);
        setTemplate((current) => current ?? result.default);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const toggle = useCallback((id) => {
    setAcceptedIds((previous) =>
      previous.includes(id)
        ? previous.filter((item) => item !== id)
        : [...previous, id]
    );
  }, []);

  const handleApply = async () => {
    if (acceptedIds.length === 0) return;
    setPhase("applying");
    setError(null);

    try {
      const applied = await applyChanges({
        profile,
        profileId,
        jobDescription,
        jobId,
        changes,
        acceptedIds,
        rejected,
        beforeScore: analysis?.match_score ?? null,
      });
      setResult(applied);
      setPhase("done");
    } catch (err) {
      setError(err);
      setPhase("review");
    }
  };

  const handleDownload = async () => {
    setDownloading(true);
    setError(null);
    try {
      await downloadPdf({
        profile: result.tailoredProfile,
        tailoredResumeId: result.tailoredResumeId,
        template,
      });
    } catch (err) {
      setError(err);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-100 bg-white">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-blue-500" fill="currentColor" />
          <span className="text-lg font-bold text-slate-900">NextHire</span>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-10 pb-32">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-2 text-sm text-slate-500 font-medium mb-6 hover:text-slate-700 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to analysis
        </button>

        <div className="text-center mb-8">
          <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900">
            Tailor your resume for{" "}
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-fuchsia-500">
              {job?.title ?? "this role"}
            </span>
          </h1>
          <p className="text-slate-500 mt-3 max-w-xl mx-auto">
            Every edit below reorders or rephrases something already on your resume.
            Nothing here invents experience - review each one and keep what you agree with.
          </p>
        </div>

        {phase === "loading" && (
          <StageProgress
            stages={[{ key: "propose", label: "Finding safe improvements" }]}
            current="propose"
            hint="Comparing your wording against this posting. This usually takes 30-45 seconds."
          />
        )}

        {phase === "applying" && (
          <StageProgress
            stages={[{ key: "apply", label: "Applying edits and re-scoring" }]}
            current="apply"
            hint="Scoring the tailored version against the same posting."
          />
        )}

        {error && (
          <ErrorNotice
            error={error}
            className="mb-6"
            onRetry={
              phase === "review" && changes.length === 0
                ? () => {
                    setError(null);
                    setPhase("loading");
                    setReloadToken((token) => token + 1);
                  }
                : undefined
            }
            onDismiss={() => setError(null)}
          />
        )}

        {phase === "done" && result && (
          <Result
            result={result}
            onDownload={handleDownload}
            downloading={downloading}
            templates={templates}
            template={template}
            setTemplate={setTemplate}
          />
        )}

        {phase === "review" && (
          <>
            <RejectedNotice rejected={rejected} />

            {changes.length > 0 && (
              <>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-bold text-slate-900">
                    {changes.length} proposed change{changes.length === 1 ? "" : "s"}
                  </h2>
                  <div className="flex items-center gap-3 text-xs">
                    <button
                      onClick={() => setAcceptedIds(changes.map((c) => c.id))}
                      className="font-semibold text-slate-500 hover:text-slate-800"
                    >
                      Accept all
                    </button>
                    <span className="text-slate-300">|</span>
                    <button
                      onClick={() => setAcceptedIds([])}
                      className="font-semibold text-slate-500 hover:text-slate-800"
                    >
                      Reject all
                    </button>
                  </div>
                </div>

                <div className="space-y-4">
                  {changes.map((change) => (
                    <ChangeCard
                      key={change.id}
                      change={change}
                      accepted={acceptedIds.includes(change.id)}
                      onToggle={toggle}
                    />
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </main>

      {phase === "review" && changes.length > 0 && (
        <div className="fixed bottom-0 left-0 right-0 border-t border-slate-100 bg-white/90 backdrop-blur">
          <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
            <p className="text-sm text-slate-500">
              {acceptedIds.length} of {changes.length} accepted
            </p>
            <button
              onClick={handleApply}
              disabled={acceptedIds.length === 0}
              className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-blue-500 to-fuchsia-500 text-white px-7 py-3 text-sm font-medium shadow-lg shadow-purple-500/30 hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Apply and re-score
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
