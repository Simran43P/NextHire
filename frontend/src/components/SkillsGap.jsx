import { useEffect, useState } from "react";
import { BookOpen, ExternalLink, Loader2, Target, TrendingUp } from "lucide-react";
import { fetchSkillsGap } from "../api/tracker";
import ErrorNotice from "./ui/ErrorNotice";

/**
 * What is costing you, across every posting you have analysed.
 *
 * One analysis tells you what a posting wants. Ten tell you what the market
 * you are applying into wants, which is a different and more useful question.
 *
 * The lift figures come from re-running the real scoring rule with one more
 * skill supported, not from a made-up multiplier. They are still estimates and
 * are labelled as such - a number someone might spend a month acting on should
 * not be invented.
 */
export default function SkillsGap() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    (async () => {
      try {
        const result = await fetchSkillsGap({ signal: controller.signal });
        if (!cancelled) setData(result);
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
  }, []);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-slate-400 py-8 justify-center">
        <Loader2 className="w-4 h-4 animate-spin" />
        Working out what is costing you...
      </div>
    );
  }

  if (error) return <ErrorNotice error={error} />;

  if (!data || data.analysed === 0) {
    return (
      <div className="rounded-2xl border border-slate-100 bg-white p-8 text-center">
        <Target className="w-6 h-6 text-slate-300 mx-auto mb-3" />
        <p className="text-sm text-slate-500">
          Analyse a few postings and this will show which missing skills cost you the most.
        </p>
      </div>
    );
  }

  if (data.gaps.length === 0) {
    return (
      <div className="rounded-2xl border border-green-100 bg-green-50/50 p-8 text-center">
        <p className="text-sm text-green-800">
          Nothing is showing up as missing across the {data.analysed} posting
          {data.analysed === 1 ? "" : "s"} you have analysed.
        </p>
      </div>
    );
  }

  const lift = data.projected_average - data.average_score;

  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2 mb-5">
        <div>
          <span className="text-2xl font-bold text-slate-900 tabular-nums">
            {data.average_score}%
          </span>
          <span className="text-sm text-slate-500 ml-2">
            average across {data.analysed} posting{data.analysed === 1 ? "" : "s"}
          </span>
        </div>
        {lift > 0 && (
          <div className="inline-flex items-center gap-1.5 text-sm text-green-700">
            <TrendingUp className="w-4 h-4" />
            <span>
              about <span className="font-semibold tabular-nums">{data.projected_average}%</span>{" "}
              if you closed the gaps below
            </span>
          </div>
        )}
      </div>

      <div className="space-y-3">
        {data.gaps.map((gap) => (
          <div
            key={gap.skill}
            className="rounded-2xl border border-slate-100 bg-white p-4"
          >
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="font-semibold text-slate-900">{gap.skill}</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  Asked for in {gap.occurrences} of {data.analysed} posting
                  {data.analysed === 1 ? "" : "s"} ({gap.share}%)
                </p>
              </div>

              <div className="text-right flex-shrink-0">
                <div className="text-lg font-bold text-slate-900 tabular-nums">
                  +{gap.average_lift}
                </div>
                <div className="text-[11px] text-slate-400">est. avg points</div>
              </div>
            </div>

            {gap.resources?.length > 0 && (
              <div className="flex flex-wrap items-center gap-2 mt-3">
                <BookOpen className="w-3.5 h-3.5 text-slate-300" />
                {gap.resources.map((resource) => (
                  <a
                    key={resource.url}
                    href={resource.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs transition-colors ${
                      resource.kind === "docs"
                        ? "bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100"
                        : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    {resource.label}
                    <ExternalLink className="w-3 h-3" />
                  </a>
                ))}
              </div>
            )}

            <button
              onClick={() => setExpanded(expanded === gap.skill ? null : gap.skill)}
              className="text-xs font-semibold text-blue-600 hover:text-blue-800 mt-2"
            >
              {expanded === gap.skill ? "Hide postings" : "Which postings?"}
            </button>

            {expanded === gap.skill && (
              <div className="mt-3 space-y-1.5">
                {gap.postings.map((posting) => (
                  <div
                    key={posting.job_id}
                    className="flex items-center justify-between gap-3 text-xs rounded-xl bg-slate-50 px-3 py-2"
                  >
                    <span className="truncate text-slate-700">
                      {posting.title}
                      {posting.company ? ` — ${posting.company}` : ""}
                    </span>
                    <span className="flex-shrink-0 tabular-nums text-slate-500">
                      {posting.current_score}% → {posting.estimated_score}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <p className="text-xs text-slate-400 mt-4 leading-relaxed">
        Estimates, not promises. Each one re-scores the posting with that skill
        supported and nothing else changed — the real gain depends on how well
        you can evidence it.
      </p>
    </div>
  );
}
