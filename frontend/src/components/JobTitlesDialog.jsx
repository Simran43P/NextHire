import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Brain, Check, Globe, Loader2, Plus, Target, X } from "lucide-react";
import { MAX_TITLE_SELECTIONS, inferTitles, searchJobs } from "../api/pipeline";
import { COUNTRIES, DEFAULT_COUNTRY } from "../api/countries";
import ErrorNotice from "./ui/ErrorNotice";
import StageProgress from "./ui/StageProgress";

/**
 * Shows the job titles inferred from the profile and searches postings for the
 * ones the candidate keeps.
 *
 * Each selected title costs one job-search API call, so the selection cap is
 * enforced here and the count is always visible.
 */

function JobTitleRow({ job, isSelected, isDisabled, onToggle }) {
  const id = job.id ?? job.title;

  const row = (
    <div
      className={`flex items-center justify-between p-4 rounded-xl bg-white ${
        isSelected ? "rounded-[10px]" : "border border-slate-200"
      } ${
        isDisabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:border-slate-300"
      } transition-colors`}
      onClick={() => !isDisabled && onToggle(id)}
      role="checkbox"
      aria-checked={isSelected}
      aria-disabled={isDisabled}
      tabIndex={isDisabled ? -1 : 0}
      onKeyDown={(event) => {
        if (!isDisabled && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          onToggle(id);
        }
      }}
    >
      <div className="flex items-center gap-3 min-w-0">
        <span
          className={`flex-shrink-0 w-5 h-5 rounded-md flex items-center justify-center ${
            isSelected ? "bg-blue-500" : "bg-white border border-slate-300"
          }`}
        >
          {isSelected && <Check className="w-3.5 h-3.5 text-white" strokeWidth={3} />}
        </span>

        <div className="min-w-0">
          <p className="font-semibold text-slate-900 text-base truncate">{job.title}</p>
          {/* The model's own reason for suggesting this title, so the list is
              inspectable rather than an oracle. */}
          <p className="text-xs text-slate-500 truncate">
            {job.reason || `Matches ${job.matchPercentage}% of your resume`}
          </p>
        </div>
      </div>

      {job.matchPercentage === null || job.matchPercentage === undefined ? (
        <span className="flex-shrink-0 inline-flex items-center gap-1 bg-slate-100 text-slate-500 border border-slate-200 rounded-full px-3 py-1 text-xs font-medium ml-3">
          Yours
        </span>
      ) : (
        <span className="flex-shrink-0 inline-flex items-center gap-1 bg-green-50 text-green-600 border border-green-200 rounded-full px-3 py-1 text-xs font-medium ml-3">
          <Target className="w-3 h-3" />
          {job.matchPercentage}%
        </span>
      )}
    </div>
  );

  if (!isSelected) return row;
  return (
    <div className="bg-gradient-to-r from-blue-500 to-purple-500 p-[2px] rounded-xl">{row}</div>
  );
}

export default function JobTitlesDialog({
  profile,
  profileId = null,
  background = false,
  onClose,
  onJobsFound,
}) {
  const [titles, setTitles] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [phase, setPhase] = useState(profile || profileId ? "inferring" : "ready");
  const [error, setError] = useState(() =>
    profile || profileId
      ? null
      : { message: "No resume profile available.", retryable: false }
  );
  // Bumped to re-run inference; the fetch itself lives entirely in the effect.
  const [reloadToken, setReloadToken] = useState(0);
  const [country, setCountry] = useState(DEFAULT_COUNTRY);
  // Titles the candidate adds. The model infers what a resume supports; it
  // cannot know that someone is deliberately changing direction.
  const [customTitles, setCustomTitles] = useState([]);
  const [draftTitle, setDraftTitle] = useState("");

  useEffect(() => {
    if (!profile && !profileId) return undefined;

    const controller = new AbortController();
    let cancelled = false;

    (async () => {
      try {
        const result = await inferTitles(
          { profile, profileId },
          { background, signal: controller.signal }
        );
        if (cancelled) return;

        setTitles(result);
        // Pre-select the strongest matches, up to the cap.
        setSelectedIds(
          [...result]
            .sort((a, b) => b.matchPercentage - a.matchPercentage)
            .slice(0, MAX_TITLE_SELECTIONS)
            .map((entry) => entry.id ?? entry.title)
        );

        if (result.length === 0) {
          setError({
            message:
              "No job titles could be inferred from this resume. Try adding more skills or projects on the previous screen.",
            retryable: false,
          });
        }
      } catch (err) {
        if (cancelled || err?.name === "AbortError") return;
        setError(err);
      } finally {
        if (!cancelled) setPhase("ready");
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [profile, profileId, background, reloadToken]);

  const retryTitles = () => {
    setTitles([]);
    setSelectedIds([]);
    setError(null);
    setPhase("inferring");
    setReloadToken((token) => token + 1);
  };

  const allTitles = [...titles, ...customTitles];

  const addCustomTitle = () => {
    const value = draftTitle.trim();
    if (!value) return;

    const exists = allTitles.some(
      (entry) => entry.title.toLowerCase() === value.toLowerCase()
    );
    if (exists) {
      setDraftTitle("");
      return;
    }

    const entry = {
      id: `custom-${customTitles.length}`,
      title: value,
      // No confidence: the model did not infer this one, and showing a made-up
      // percentage beside it would be the same lie the job cards used to tell.
      matchPercentage: null,
      reason: "Added by you",
      custom: true,
    };
    setCustomTitles((previous) => [...previous, entry]);
    setSelectedIds((previous) =>
      previous.length < MAX_TITLE_SELECTIONS ? [...previous, entry.id] : previous
    );
    setDraftTitle("");
  };

  const toggleSelection = useCallback((id) => {
    setSelectedIds((previous) => {
      if (previous.includes(id)) return previous.filter((item) => item !== id);
      if (previous.length >= MAX_TITLE_SELECTIONS) return previous;
      return [...previous, id];
    });
  }, []);

  const handleSearch = async () => {
    if (selectedIds.length === 0 || phase === "searching") return;

    const selected = allTitles.filter((entry) =>
      selectedIds.includes(entry.id ?? entry.title)
    );

    setPhase("searching");
    setError(null);

    try {
      const result = await searchJobs(selected, { profile, profileId, country });
      onJobsFound(result, selected);
    } catch (err) {
      // Previously a browser alert(), which blocked the page and offered no
      // way back other than dismissing it.
      setError(err);
      setPhase("ready");
    }
  };

  const isBusy = phase === "inferring" || phase === "searching";
  const canSearch = selectedIds.length > 0 && !isBusy;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
      <div className="w-full max-w-2xl mx-auto bg-white rounded-3xl shadow-2xl p-8 sm:p-10 relative">
        <button
          type="button"
          onClick={onClose}
          disabled={isBusy}
          aria-label="Close dialog"
          className={`absolute top-5 right-5 transition-colors ${
            isBusy ? "text-slate-300 cursor-not-allowed" : "text-slate-400 hover:text-slate-600"
          }`}
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex flex-col items-center">
          <span className="inline-flex items-center gap-1.5 bg-purple-50 text-purple-700 text-xs font-medium rounded-full px-3 py-1">
            <Brain className="w-3.5 h-3.5" />
            Inferred from your resume
          </span>

          <h2 className="text-2xl sm:text-3xl font-bold text-center mt-4 text-slate-900">
            Job{" "}
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-500 to-purple-500">
              titles
            </span>{" "}
            worth applying for
          </h2>

          <p className="text-sm text-slate-500 text-center mt-2 mb-6">
            Deselect any roles you are not interested in, then search for matching jobs.
          </p>
        </div>

        {phase === "inferring" ? (
          <StageProgress
            stages={[{ key: "infer", label: "Working out which roles fit you" }]}
            current="infer"
            hint="This usually takes 15-30 seconds."
          />
        ) : phase === "searching" ? (
          <StageProgress
            stages={[{ key: "search", label: "Searching live job postings" }]}
            current="search"
            hint={`Searching ${selectedIds.length} title${
              selectedIds.length === 1 ? "" : "s"
            }.`}
          />
        ) : (
          <>
            {error && (
              <ErrorNotice
                error={error}
                className="mb-4"
                onRetry={titles.length === 0 ? retryTitles : handleSearch}
                onDismiss={() => setError(null)}
              />
            )}

            {allTitles.length > 0 && (
              <div className="flex flex-col gap-3">
                {allTitles.map((job) => {
                  const id = job.id ?? job.title;
                  const isSelected = selectedIds.includes(id);
                  return (
                    <JobTitleRow
                      key={id}
                      job={job}
                      isSelected={isSelected}
                      isDisabled={!isSelected && selectedIds.length >= MAX_TITLE_SELECTIONS}
                      onToggle={toggleSelection}
                    />
                  );
                })}
              </div>
            )}
          </>
        )}

        {!isBusy && (
          <div className="flex gap-2 mt-4">
            <input
              value={draftTitle}
              onChange={(event) => setDraftTitle(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  addCustomTitle();
                }
              }}
              placeholder="Add a title of your own"
              className="flex-1 rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
            />
            <button
              type="button"
              onClick={addCustomTitle}
              disabled={!draftTitle.trim()}
              className="inline-flex items-center gap-1.5 rounded-xl bg-slate-900 text-white px-4 py-2.5 text-sm font-medium hover:bg-slate-800 transition-colors disabled:opacity-40"
            >
              <Plus className="w-4 h-4" />
              Add
            </button>
          </div>
        )}

        {!isBusy && allTitles.length > 0 && (
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mt-6">
            <div className="flex items-center gap-3">
              <p className="text-xs text-slate-400">
                {selectedIds.length}/{MAX_TITLE_SELECTIONS} selected
              </p>
              <label className="inline-flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5 text-slate-400" />
                <span className="sr-only">Country to search</span>
                <select
                  value={country}
                  onChange={(event) => setCountry(event.target.value)}
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600 outline-none focus:border-blue-400"
                >
                  {COUNTRIES.map((option) => (
                    <option key={option.code} value={option.code}>
                      {option.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <button
              type="button"
              onClick={handleSearch}
              disabled={!canSearch}
              className={`inline-flex items-center gap-2 rounded-full px-6 py-2.5 text-sm font-medium text-white bg-gradient-to-r from-blue-500 to-fuchsia-500 shadow-lg shadow-purple-500/30 transition-opacity ${
                canSearch ? "hover:opacity-90" : "opacity-50 cursor-not-allowed"
              }`}
            >
              Search jobs for selected titles
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {phase === "searching" && (
          <div className="flex justify-center mt-2">
            <Loader2 className="w-4 h-4 animate-spin text-slate-300" />
          </div>
        )}
      </div>
    </div>
  );
}
