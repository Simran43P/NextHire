import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft,
  CalendarClock,
  ExternalLink,
  Loader2,
  Sparkles,
  Trash2,
} from "lucide-react";
import {
  STATUSES,
  STATUS_LABELS,
  fetchBoard,
  untrackApplication,
  updateApplication,
} from "../api/tracker";
import ErrorNotice from "./ui/ErrorNotice";
import SkillsGap from "./SkillsGap";

/**
 * Where decisions go once they are made.
 *
 * Everything upstream produces one judgement - is this worth applying to. This
 * screen answers the two questions that come after: did I apply to that one,
 * and who owes me a reply.
 *
 * Status is a dropdown rather than drag-and-drop. Dragging is nicer to demo and
 * worse to use on a laptop trackpad, and it is unusable with a keyboard.
 */

const COLUMN_STYLES = {
  SAVED: "bg-slate-100 text-slate-700",
  APPLIED: "bg-blue-100 text-blue-700",
  INTERVIEWING: "bg-purple-100 text-purple-700",
  OFFER: "bg-green-100 text-green-700",
  REJECTED: "bg-red-100 text-red-700",
};

function Stat({ value, label, tone = "" }) {
  return (
    <div className="text-center px-5">
      <div className={`text-2xl font-bold tabular-nums ${tone || "text-slate-900"}`}>
        {value}
      </div>
      <div className="text-xs text-slate-500 mt-0.5">{label}</div>
    </div>
  );
}

function ApplicationCard({ application, onChange, onRemove }) {
  const [notes, setNotes] = useState(application.notes ?? "");
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const overdue =
    application.follow_up_on && new Date(application.follow_up_on) <= new Date();

  const commitNotes = async () => {
    if (notes === (application.notes ?? "")) return;
    setSaving(true);
    try {
      await onChange(application.id, { notes });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-slate-900 text-sm truncate">
            {application.title}
          </p>
          <p className="text-xs text-slate-500 truncate">{application.company}</p>
        </div>
        {application.match_score !== null && application.match_score !== undefined && (
          <span className="flex-shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700 tabular-nums">
            {application.match_score}%
          </span>
        )}
      </div>

      {application.tailored_after_score !== null &&
        application.tailored_after_score !== undefined && (
          <p className="text-[11px] text-green-700 mt-1.5">
            Tailored resume sent — scored {application.tailored_after_score}%
          </p>
        )}

      {overdue && (
        <p className="inline-flex items-center gap-1 text-[11px] text-amber-700 mt-1.5">
          <CalendarClock className="w-3 h-3" />
          Follow-up due
        </p>
      )}

      <div className="flex items-center gap-2 mt-3">
        <select
          value={application.status}
          onChange={(event) => onChange(application.id, { status: event.target.value })}
          className="flex-1 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-700 outline-none focus:border-blue-400"
        >
          {STATUSES.map((status) => (
            <option key={status} value={status}>
              {STATUS_LABELS[status]}
            </option>
          ))}
        </select>

        {application.apply_link && (
          <a
            href={application.apply_link}
            target="_blank"
            rel="noopener noreferrer"
            title="Open the posting"
            className="rounded-lg border border-slate-200 p-1.5 text-slate-400 hover:text-slate-700 transition-colors"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}

        <button
          onClick={() => onRemove(application.id)}
          title="Stop tracking"
          className="rounded-lg border border-slate-200 p-1.5 text-slate-400 hover:text-red-500 transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      <button
        onClick={() => setOpen((value) => !value)}
        className="text-[11px] font-medium text-slate-400 hover:text-slate-600 mt-2"
      >
        {open ? "Hide notes" : application.notes ? "Notes" : "Add notes"}
      </button>

      {open && (
        <div className="mt-2 space-y-2">
          <textarea
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            onBlur={commitNotes}
            rows={3}
            placeholder="Referred by, recruiter name, anything you will want in three weeks."
            className="w-full rounded-xl border border-slate-200 px-2.5 py-2 text-xs outline-none focus:border-blue-400"
          />
          <label className="block">
            <span className="text-[11px] text-slate-500">Follow up on</span>
            <input
              type="date"
              value={application.follow_up_on?.slice(0, 10) ?? ""}
              onChange={(event) =>
                onChange(application.id, {
                  followUpOn: event.target.value
                    ? new Date(`${event.target.value}T09:00:00Z`).toISOString()
                    : null,
                })
              }
              className="mt-0.5 w-full rounded-xl border border-slate-200 px-2.5 py-1.5 text-xs outline-none focus:border-blue-400"
            />
          </label>
          {saving && <p className="text-[11px] text-slate-400">Saving...</p>}
        </div>
      )}
    </div>
  );
}

export default function ApplicationTracker({ onBack }) {
  const [board, setBoard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("board");

  // Bumped after any mutation to pull a fresh board. The fetch lives entirely
  // inside the effect so no state is written on its synchronous path.
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    (async () => {
      try {
        const data = await fetchBoard({ signal: controller.signal });
        if (cancelled) return;
        setBoard(data);
        setError(null);
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
  }, [reloadToken]);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  const handleChange = async (id, changes) => {
    try {
      await updateApplication(id, changes);
      reload();
    } catch (err) {
      setError(err);
    }
  };

  const handleRemove = async (id) => {
    try {
      await untrackApplication(id);
      reload();
    } catch (err) {
      setError(err);
    }
  };

  const stats = board?.stats;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-100 bg-white">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-blue-500" fill="currentColor" />
          <span className="text-lg font-bold text-slate-900">NextHire</span>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-10 pb-24">
        {onBack && (
          <button
            onClick={onBack}
            className="inline-flex items-center gap-2 text-sm text-slate-500 font-medium mb-6 hover:text-slate-700 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </button>
        )}

        <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900">
          Your{" "}
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-fuchsia-500">
            job search
          </span>
        </h1>

        {stats && stats.total > 0 && (
          <div className="mt-6 inline-flex flex-wrap items-center rounded-3xl border border-slate-100 bg-white py-3 shadow-sm divide-x divide-slate-100">
            <Stat value={stats.total} label="Tracked" />
            <Stat value={stats.applied_this_week} label="Applied this week" />
            <Stat value={stats.awaiting_response} label="Awaiting reply" />
            <Stat
              value={stats.response_rate === null ? "—" : `${stats.response_rate}%`}
              label="Response rate"
            />
            {stats.follow_ups_due > 0 && (
              <Stat
                value={stats.follow_ups_due}
                label="Follow-ups due"
                tone="text-amber-600"
              />
            )}
          </div>
        )}

        <div className="flex items-center gap-1 mt-8 border-b border-slate-200">
          {[
            ["board", "Applications"],
            ["gaps", "Skills gap"],
          ].map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
                tab === key
                  ? "border-blue-500 text-slate-900"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {error && <ErrorNotice error={error} className="mt-6" onDismiss={() => setError(null)} />}

        {loading ? (
          <div className="flex items-center gap-2 text-sm text-slate-400 py-16 justify-center">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading...
          </div>
        ) : tab === "gaps" ? (
          <div className="mt-8">
            <SkillsGap />
          </div>
        ) : stats?.total === 0 ? (
          <div className="mt-8 rounded-2xl border border-slate-100 bg-white p-12 text-center">
            <p className="text-slate-500">
              Nothing tracked yet. Save a posting from your analysis and it will appear here.
            </p>
          </div>
        ) : (
          <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            {board.order.map((status) => (
              <div key={status}>
                <div className="flex items-center gap-2 mb-3">
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${COLUMN_STYLES[status]}`}
                  >
                    {STATUS_LABELS[status]}
                  </span>
                  <span className="text-xs text-slate-400 tabular-nums">
                    {board.columns[status].length}
                  </span>
                </div>

                <div className="space-y-3">
                  {board.columns[status].map((application) => (
                    <ApplicationCard
                      key={application.id}
                      application={application}
                      onChange={handleChange}
                      onRemove={handleRemove}
                    />
                  ))}
                  {board.columns[status].length === 0 && (
                    <div className="rounded-2xl border border-dashed border-slate-200 p-4 text-center text-xs text-slate-300">
                      Nothing here
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
