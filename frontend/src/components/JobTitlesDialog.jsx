import React, { useState, useEffect, useCallback } from "react";

/**
 * JobTitlesDialog
 *
 * Modal dialog that displays AI-inferred job titles (sourced from the
 * `infer_titles.py` backend service) and lets the user select up to
 * 3 titles before kicking off a personalized job search.
 *
 * Expected backend payload shape (per job title):
 * { id: string, title: string, matchPercentage: number }
 */

const MAX_SELECTIONS = 5;

// ---------------------------------------------------------------------------
// Small inline icons (no external icon library dependency)
// ---------------------------------------------------------------------------
const BrainIcon = () => (
  <svg
    className="w-3.5 h-3.5"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M9.5 2a3.5 3.5 0 0 0-3.5 3.5v.34A3.5 3.5 0 0 0 4 9v1a3.5 3.5 0 0 0 1 6.16V17a3.5 3.5 0 0 0 3.5 3.5h1v-16h-1Z" />
    <path d="M14.5 2a3.5 3.5 0 0 1 3.5 3.5v.34A3.5 3.5 0 0 1 20 9v1a3.5 3.5 0 0 1-1 6.16V17a3.5 3.5 0 0 1-3.5 3.5h-1v-16h1Z" />
  </svg>
);

const CheckIcon = () => (
  <svg
    className="w-3.5 h-3.5 text-white"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="3"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M20 6 9 17l-5-5" />
  </svg>
);

const TargetIcon = () => (
  <svg
    className="w-3 h-3"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
  >
    <circle cx="12" cy="12" r="9" />
    <circle cx="12" cy="12" r="5" />
    <circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none" />
  </svg>
);

const ArrowRightIcon = () => (
  <svg
    className="w-4 h-4"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M5 12h14" />
    <path d="M13 6l6 6-6 6" />
  </svg>
);

const SpinnerIcon = () => (
  <svg
    className="w-5 h-5 animate-spin text-purple-500"
    viewBox="0 0 24 24"
    fill="none"
  >
    <circle
      className="opacity-25"
      cx="12"
      cy="12"
      r="10"
      stroke="currentColor"
      strokeWidth="4"
    />
    <path
      className="opacity-75"
      fill="currentColor"
      d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
    />
  </svg>
);

// ---------------------------------------------------------------------------
// Individual selectable row
// ---------------------------------------------------------------------------
function JobTitleRow({ job, isSelected, isDisabled, onToggle }) {
  const rowContent = (
    <div
      className={`flex items-center justify-between p-4 rounded-xl bg-white ${
        isSelected ? "rounded-[10px]" : "border border-slate-200"
      } ${
        isDisabled
          ? "opacity-50 cursor-not-allowed"
          : "cursor-pointer hover:border-slate-300"
      } transition-colors`}
      onClick={() => !isDisabled && onToggle(job.id ?? job.title)}
      role="checkbox"
      aria-checked={isSelected}
      aria-disabled={isDisabled}
      tabIndex={isDisabled ? -1 : 0}
      onKeyDown={(e) => {
        if (!isDisabled && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onToggle(job.id ?? job.title);
        }
      }}
    >
      <div className="flex items-center gap-3 min-w-0">
        <span
          className={`flex-shrink-0 w-5 h-5 rounded-md flex items-center justify-center ${
            isSelected
              ? "bg-blue-500"
              : "bg-white border border-slate-300"
          }`}
        >
          {isSelected && <CheckIcon />}
        </span>

        <div className="min-w-0">
          <p className="font-semibold text-slate-900 text-base truncate">
            {job.title}
          </p>
          <p className="text-xs text-slate-500">
            (Matches {job.matchPercentage}% of resume criteria)
          </p>
        </div>
      </div>

      <span className="flex-shrink-0 inline-flex items-center gap-1 bg-green-50 text-green-600 border border-green-200 rounded-full px-3 py-1 text-xs font-medium ml-3">
        <TargetIcon />
        {job.matchPercentage}% Match
      </span>
    </div>
  );

  if (isSelected) {
    return (
      <div className="bg-gradient-to-r from-blue-500 to-purple-500 p-[2px] rounded-xl">
        {rowContent}
      </div>
    );
  }

  return rowContent;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function JobTitlesDialog({ onClose, resumeProfile, setSelectedTitles, setJobs, }) {
  const [jobTitles, setJobTitles] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [isInferringTitles, setIsInferringTitles] = useState(true);
  const [isSearchingJobs, setIsSearchingJobs] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;

    if (!resumeProfile) {
      setError("No resume profile provided for inference.");
      setIsInferringTitles(false);
      return;
    }

    setIsInferringTitles(true);
    setError(null);

    const fetchRealTitles = async () => {
      try {
        const res = await fetch("http://localhost:8000/api/infer-titles", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(resumeProfile),
        });

        if (!res.ok) {
          const errData = await res.json();
          throw new Error(errData.detail || "Failed to fetch titles.");
        }

        const data = await res.json();
        const titles = data.titles || [];

        if (!isMounted) return;

        if(titles.length === 0) {
          setError("No suitable job titles could be inferred .");
          return;
        }

        setJobTitles(titles);
        
        // Pre-select the top matches, mirroring the reference design.
        setSelectedIds(
          titles
            .slice()
            .sort((a, b) => b.matchPercentage - a.matchPercentage)
            .slice(0, MAX_SELECTIONS)
            .map((job) => job.id ?? job.title)
        );
      } catch (err) {
        console.error("Inference Error:", err);
        if (isMounted) setError("Couldn't load job titles. Please try again.");
      } finally {
        if (isMounted) setIsInferringTitles(false);
      }
    };

    fetchRealTitles();

    return () => {
      isMounted = false;
    };
  }, [resumeProfile]);

  const toggleSelection = useCallback((id) => {
    setSelectedIds((prev) => {
      if (prev.includes(id)) {
        return prev.filter((selectedId) => selectedId !== id);
      }
      if (prev.length >= MAX_SELECTIONS) {
        return prev; // hard cap at MAX_SELECTIONS
      }
      return [...prev, id];
    });
  }, []);

  const handleSearch = async () => {
    if (selectedIds.length === 0) return;

    setIsSearchingJobs(true);

    const selectedJobs = jobTitles.filter((job) =>
      selectedIds.includes(job.id ?? job.title)
    );
    
    try {
      setSelectedTitles(selectedJobs);

      const response = await fetch(
        "http://localhost:8000/api/jobs?country=in",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(selectedJobs),
        }
      );

      if(!response.ok){
        throw new Error("Failed to fetch jobs");
      }

      const data = await response.json();

      setJobs(data.jobs || []);

      onClose?.();

    } catch (err) {
      console.error("Job Search Error:", err);
      alert("Unable to fetch jobs.");

    }

    finally {
      setIsSearchingJobs(false);
    }

  };

  const isSearchDisabled = selectedIds.length === 0 || isSearchingJobs;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
      <div className="w-full max-w-2xl mx-auto bg-white rounded-3xl shadow-2xl p-8 sm:p-10 relative">
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            disabled={isSearchingJobs}
            aria-label="Close dialog"
            className={`absolute top-5 right-5 transition-colors ${
              isSearchingJobs
                ? "text-slate-300 cursor-not-allowed"
                : "text-slate-400 hover:text-slate-600"
            }`

            }
          >
            <svg
              className="w-5 h-5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <path d="M18 6 6 18" />
              <path d="M6 6l12 12" />
            </svg>
          </button>
        )}

        {/* Header */}
        <div className="flex flex-col items-center">
          <span className="inline-flex items-center gap-1.5 bg-purple-50 text-purple-700 text-xs font-medium rounded-full px-3 py-1">
            <BrainIcon />
            AI Confidence: Strong
          </span>

          <h2 className="text-2xl sm:text-3xl font-bold text-center mt-4 text-slate-900">
            AI has inferred suitable{" "}
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-500 to-purple-500">
              job titles
            </span>{" "}
            based on your resume
          </h2>

          <p className="text-sm text-slate-500 text-center mt-2 mb-6">
            Deselect any roles you're not interested in, then search for matching jobs.
          </p>
        </div>

        {/* List */}
        {isInferringTitles ? (
          <div className="flex flex-col items-center justify-center gap-3 py-12">
            <SpinnerIcon />
            <p className="text-sm text-slate-500">
                Analysing your resume...
            </p>
          </div>
        ) : error ? (
          <div className="text-center py-12">
            <p className="text-sm text-red-500"> {error}</p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {jobTitles.map((job) => {
              const isSelected = selectedIds.includes(job.id ?? job.title);

              // Rows are disabled once the cap is hit (existing behavior),
              // and now also while a job search is in flight so selections
              // can't change until it finishes.
              const isDisabled =
                isSearchingJobs ||
                (!isSelected && selectedIds.length >= MAX_SELECTIONS);

               return (
                <JobTitleRow
                 key={job.id ?? job.title}
                 job={job}
                 isSelected={isSelected}
                 isDisabled={isDisabled}
                 onToggle={toggleSelection}
                 />
               );
            })}
          </div>
        )
        }

        {/* Footer */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mt-6">
          <p className="text-xs text-slate-400">
            {selectedIds.length}/{MAX_SELECTIONS} selected
          </p>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={handleSearch}
              disabled={isSearchDisabled}
              className={`inline-flex items-center gap-2 rounded-full px-6 py-2.5 text-sm font-medium text-white bg-gradient-to-r from-blue-500 to-fuchsia-500 shadow-lg shadow-purple-500/30 transition-opacity ${
                isSearchDisabled
                  ? "opacity-50 cursor-not-allowed"
                  : "hover:opacity-90"
              }`}
            >
              {isSearchingJobs ? (
                <>
                <SpinnerIcon />
                Searching jobs...
                </>
              ) : (
                <>
                Search Jobs for Selected Titles
                <ArrowRightIcon />
                </>
              )

              }
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}