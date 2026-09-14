import { useEffect, useState } from "react";
import { ArrowLeft, MessageSquare, RefreshCw, Sparkles, Target, Wrench } from "lucide-react";
import { generateInterviewPrep } from "../api/tracker";
import ErrorNotice from "./ui/ErrorNotice";
import StageProgress from "./ui/StageProgress";

/**
 * Likely interview questions for one posting.
 *
 * Split three ways, and the split is the useful part. A flat list of twenty
 * questions is a wall; knowing which three exist purely because of a gap in
 * your resume tells you where to spend the evening.
 */

const GROUPS = [
  {
    key: "technical",
    label: "Technical",
    icon: Wrench,
    blurb: "Pitched at what your own projects and experience invite.",
    tone: "border-blue-200 bg-blue-50/40",
  },
  {
    key: "behavioural",
    label: "Behavioural",
    icon: MessageSquare,
    blurb: "How you work, collaborate, and handle things going wrong.",
    tone: "border-purple-200 bg-purple-50/40",
  },
  {
    key: "gaps",
    label: "Probing your gaps",
    icon: Target,
    blurb:
      "These come from what this posting wants and your resume does not evidence. You will be least ready for these, which is exactly why they are here.",
    tone: "border-amber-200 bg-amber-50/40",
  },
];

export default function InterviewPrep({ job, profile, profileId = null, analysis, onBack }) {
  const [questions, setQuestions] = useState(null);
  const [cached, setCached] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const jobId = job?.job_id ?? null;

  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    (async () => {
      try {
        const result = await generateInterviewPrep(
          {
            profile,
            profileId,
            job: jobId
              ? null
              : { title: job?.title, company: job?.company, description: job?.description },
            jobId,
            analysis,
          },
          { refresh: refreshToken > 0, signal: controller.signal }
        );
        if (cancelled) return;
        setQuestions(result.questions);
        setCached(result.cached);
      } catch (err) {
        if (!cancelled && err?.name !== "AbortError") setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [profile, profileId, job, jobId, analysis, refreshToken]);

  // The synchronous resets that go with starting a request live here rather
  // than in the effect body, where they would cause cascading renders.
  const refresh = () => {
    setLoading(true);
    setError(null);
    setRefreshToken((token) => token + 1);
  };

  const total = questions
    ? questions.technical.length + questions.behavioural.length + questions.gaps.length
    : 0;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-100 bg-white">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-blue-500" fill="currentColor" />
          <span className="text-lg font-bold text-slate-900">NextHire</span>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-10 pb-24">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-2 text-sm text-slate-500 font-medium mb-6 hover:text-slate-700 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to analysis
        </button>

        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-extrabold text-slate-900">
              Interview prep for{" "}
              <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-fuchsia-500">
                {job?.title ?? "this role"}
              </span>
            </h1>
            <p className="text-slate-500 mt-2">
              {job?.company ? `${job.company}. ` : ""}
              The questions an interviewer would actually reach for.
            </p>
          </div>

          {!loading && (
            <button
              onClick={refresh}
              title="Generate a fresh set"
              className="flex-shrink-0 rounded-full border border-slate-200 bg-white p-2 text-slate-400 hover:text-slate-700 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          )}
        </div>

        {error && <ErrorNotice error={error} className="mt-6" onDismiss={() => setError(null)} />}

        {loading ? (
          <StageProgress
            stages={[{ key: "think", label: "Working out what they will ask" }]}
            current="think"
            hint="This usually takes 30-45 seconds."
          />
        ) : questions && total > 0 ? (
          <>
            {cached && (
              <p className="text-xs text-slate-400 mt-6">
                Saved from an earlier run. Use refresh for a new set.
              </p>
            )}

            <div className="space-y-6 mt-6">
              {GROUPS.map((group) => {
                const items = questions[group.key] ?? [];
                if (items.length === 0) return null;
                const Icon = group.icon;

                return (
                  <section
                    key={group.key}
                    className={`rounded-2xl border p-5 ${group.tone}`}
                  >
                    <div className="flex items-center gap-2">
                      <Icon className="w-4 h-4 text-slate-600" />
                      <h2 className="font-bold text-slate-900">{group.label}</h2>
                      <span className="text-xs text-slate-400 tabular-nums">
                        {items.length}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mt-1 mb-4">{group.blurb}</p>

                    <ol className="space-y-3">
                      {items.map((item, index) => {
                        const text = typeof item === "string" ? item : item.question;
                        const probes = typeof item === "string" ? "" : item.probes;
                        return (
                          <li key={index} className="flex gap-3">
                            <span className="flex-shrink-0 w-5 text-xs text-slate-400 tabular-nums pt-0.5">
                              {index + 1}.
                            </span>
                            <div className="min-w-0">
                              <p className="text-sm text-slate-800 leading-relaxed">{text}</p>
                              {probes && (
                                <p className="text-[11px] text-amber-700 mt-1">
                                  Probing: {probes}
                                </p>
                              )}
                            </div>
                          </li>
                        );
                      })}
                    </ol>
                  </section>
                );
              })}
            </div>
          </>
        ) : (
          !error && (
            <div className="rounded-2xl border border-slate-100 bg-white p-12 text-center mt-6">
              <p className="text-slate-500">
                No questions came back for this posting. Try refreshing.
              </p>
            </div>
          )
        )}
      </main>
    </div>
  );
}
