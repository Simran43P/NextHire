import { useMemo, useState } from "react";
import { ArrowLeft, MapPin, Search, Sparkles, Tag, X } from "lucide-react";
import { MAX_JOB_SELECTIONS } from "../api/pipeline";
import { WarningNotice } from "./ui/ErrorNotice";

/**
 * The postings found for the selected titles.
 *
 * There is no mock-data switch in this component. It used to carry a hardcoded
 * `USE_MOCK_DATA = true`, which meant live results were fetched and then thrown
 * away. Sample data is a backend mode now, decided by env config - which is
 * also where it belongs, because the backend is what spends the API quota.
 *
 * Filtering and sorting happen here rather than in another search: the results
 * are already in memory, and a second aggregator call to hide remote jobs would
 * spend quota to show the candidate less.
 */

const SORTS = [
  { key: "match", label: "Best skill overlap" },
  { key: "recent", label: "Most recent" },
  { key: "salary", label: "Highest salary" },
];

const POSTED_WINDOWS = [
  { key: "any", label: "Any time", days: null },
  { key: "week", label: "Past week", days: 7 },
  { key: "fortnight", label: "Past 2 weeks", days: 14 },
  { key: "month", label: "Past month", days: 30 },
];

function formatSalary(salary) {
  if (!salary || typeof salary !== "object") return null;
  const { min, max } = salary;
  if (!min && !max) return null;

  const format = (value) => {
    if (!value) return null;
    if (value >= 10000000) return `${(value / 10000000).toFixed(1).replace(/\.0$/, "")} Cr`;
    if (value >= 100000) return `${(value / 100000).toFixed(1).replace(/\.0$/, "")} L`;
    return value.toLocaleString("en-IN");
  };

  if (min && max) return `₹${format(min)} - ₹${format(max)}`;
  return `₹${format(min ?? max)}${min ? "+" : " max"}`;
}

function formatPostedAt(value) {
  if (!value) return null;
  const posted = new Date(value);
  if (Number.isNaN(posted.getTime())) return null;

  const days = Math.floor((Date.now() - posted.getTime()) / 86400000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  if (days < 30) return `${Math.floor(days / 7)} week${days < 14 ? "" : "s"} ago`;
  return `${Math.floor(days / 30)} month${days < 60 ? "" : "s"} ago`;
}

function daysOld(value) {
  if (!value) return Number.POSITIVE_INFINITY;
  const posted = new Date(value);
  if (Number.isNaN(posted.getTime())) return Number.POSITIVE_INFINITY;
  return (Date.now() - posted.getTime()) / 86400000;
}

function JobCard({ job, isSelected, isCapped, onToggle, onView }) {
  const salary = formatSalary(job.salary);
  const posted = formatPostedAt(job.posted_at);
  const matchedKeywords = job.matched_keywords ?? [];
  const hasPrescore = typeof job.keyword_matches === "number";

  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-md p-6 flex flex-col">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-bold text-slate-900 truncate">{job.company}</p>
          <div className="flex items-center gap-1.5 mt-1 text-sm text-slate-500">
            <MapPin className="w-3.5 h-3.5 flex-shrink-0" />
            <span className="truncate">{job.location}</span>
          </div>
        </div>

        {/*
          A count of the candidate's own skills found in this posting - not a
          match percentage. The percentage that used to sit here was the
          title-level confidence stamped onto every result for that title, so
          unrelated jobs displayed identical numbers. The real score arrives
          from the ATS analysis on the next screen.
        */}
        {hasPrescore && (
          <span
            title={
              matchedKeywords.length
                ? `Your skills found in this posting: ${matchedKeywords.join(", ")}`
                : "None of your listed skills appear in this posting"
            }
            className={`flex-shrink-0 inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold whitespace-nowrap ${
              job.keyword_matches > 0
                ? "bg-blue-50 text-blue-700 border border-blue-200"
                : "bg-slate-100 text-slate-500 border border-slate-200"
            }`}
          >
            <Tag className="w-3 h-3" strokeWidth={2.5} />
            {job.keyword_matches} skill{job.keyword_matches === 1 ? "" : "s"}
          </span>
        )}
      </div>

      <h3 className="text-xl font-bold text-slate-900 mt-5 mb-3">{job.title}</h3>

      {matchedKeywords.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-4">
          {matchedKeywords.slice(0, 5).map((skill) => (
            <span
              key={skill}
              className="rounded-full bg-green-50 border border-green-200 text-green-700 px-2.5 py-0.5 text-xs"
            >
              {skill}
            </span>
          ))}
          {matchedKeywords.length > 5 && (
            <span className="text-xs text-slate-400 self-center">
              +{matchedKeywords.length - 5} more
            </span>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 mt-auto">
        <div>
          <p className="text-xs text-slate-500">Job type</p>
          <p className="text-sm text-slate-900 font-medium mt-0.5">
            {job.is_remote ? "Remote" : job.type || "Not specified"}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-500">{salary ? "Salary" : "Posted"}</p>
          <p className="text-sm text-slate-900 font-medium mt-0.5">
            {salary ?? posted ?? "Not specified"}
          </p>
        </div>
      </div>

      <div className="flex gap-3 mt-6">
        <button
          onClick={() => onView(job.apply_link)}
          disabled={!job.apply_link}
          className="flex-1 rounded-full py-2.5 font-medium transition-colors bg-slate-100 text-slate-700 hover:bg-slate-200 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          View job
        </button>
        <button
          onClick={() => onToggle(job)}
          disabled={!isSelected && isCapped}
          className={`flex-1 rounded-full py-2.5 font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
            isSelected
              ? "bg-slate-900 text-white hover:bg-slate-800"
              : "bg-slate-100 text-slate-700 hover:bg-slate-200"
          }`}
        >
          {isSelected ? "Selected" : "Select role"}
        </button>
      </div>
    </div>
  );
}

function FilterBar({ filters, setFilters, types, total, shown }) {
  const update = (changes) => setFilters((previous) => ({ ...previous, ...changes }));
  const isFiltered = shown !== total;

  return (
    <div className="mt-8 rounded-2xl border border-slate-100 bg-white p-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[12rem]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-300" />
          <input
            value={filters.query}
            onChange={(event) => update({ query: event.target.value })}
            placeholder="Filter by title or company"
            className="w-full rounded-xl border border-slate-200 pl-9 pr-3 py-2 text-sm outline-none focus:border-blue-400"
          />
        </div>

        <select
          value={filters.remote}
          onChange={(event) => update({ remote: event.target.value })}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-400"
        >
          <option value="any">Anywhere</option>
          <option value="remote">Remote only</option>
          <option value="onsite">On-site only</option>
        </select>

        <select
          value={filters.type}
          onChange={(event) => update({ type: event.target.value })}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-400"
        >
          <option value="any">Any type</option>
          {types.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>

        <select
          value={filters.posted}
          onChange={(event) => update({ posted: event.target.value })}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-400"
        >
          {POSTED_WINDOWS.map((window) => (
            <option key={window.key} value={window.key}>
              {window.label}
            </option>
          ))}
        </select>

        <select
          value={filters.sort}
          onChange={(event) => update({ sort: event.target.value })}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-400"
        >
          {SORTS.map((sort) => (
            <option key={sort.key} value={sort.key}>
              Sort: {sort.label}
            </option>
          ))}
        </select>

        {isFiltered && (
          <button
            onClick={() =>
              setFilters({ query: "", remote: "any", type: "any", posted: "any", sort: "match" })
            }
            className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-slate-800"
          >
            <X className="w-3.5 h-3.5" />
            Clear
          </button>
        )}
      </div>

      {isFiltered && (
        <p className="text-xs text-slate-400 mt-3">
          Showing {shown} of {total} postings.
        </p>
      )}
    </div>
  );
}

export default function JobListings({
  jobs = [],
  warnings = [],
  selectedTitles = [],
  onAnalyze,
  onBack,
}) {
  const [selected, setSelected] = useState([]);
  const [filters, setFilters] = useState({
    query: "",
    remote: "any",
    type: "any",
    posted: "any",
    sort: "match",
  });

  const types = useMemo(
    () => [...new Set(jobs.map((job) => job.type).filter(Boolean))].sort(),
    [jobs]
  );

  const visible = useMemo(() => {
    const query = filters.query.trim().toLowerCase();
    const window = POSTED_WINDOWS.find((entry) => entry.key === filters.posted);

    const filtered = jobs.filter((job) => {
      if (query) {
        const haystack = `${job.title} ${job.company} ${job.location}`.toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      if (filters.remote === "remote" && !job.is_remote) return false;
      if (filters.remote === "onsite" && job.is_remote) return false;
      if (filters.type !== "any" && job.type !== filters.type) return false;
      if (window?.days && daysOld(job.posted_at) > window.days) return false;
      return true;
    });

    const sorted = [...filtered];
    if (filters.sort === "recent") {
      sorted.sort((a, b) => daysOld(a.posted_at) - daysOld(b.posted_at));
    } else if (filters.sort === "salary") {
      const value = (job) => job.salary?.max ?? job.salary?.min ?? -1;
      sorted.sort((a, b) => value(b) - value(a));
    } else {
      sorted.sort((a, b) => (b.keyword_matches ?? 0) - (a.keyword_matches ?? 0));
    }
    return sorted;
  }, [jobs, filters]);

  const toggleRole = (job) =>
    setSelected((previous) => {
      if (previous.some((item) => item.id === job.id)) {
        return previous.filter((item) => item.id !== job.id);
      }
      if (previous.length >= MAX_JOB_SELECTIONS) return previous;
      return [...previous, job];
    });

  const handleView = (applyLink) => {
    if (!applyLink) return;
    window.open(applyLink, "_blank", "noopener,noreferrer");
  };

  const isCapped = selected.length >= MAX_JOB_SELECTIONS;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-100 bg-white">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-blue-500" fill="currentColor" />
          <span className="text-lg font-bold text-slate-900">NextHire</span>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-10 pb-32">
        {onBack && (
          <button
            onClick={onBack}
            className="inline-flex items-center gap-2 text-sm text-slate-500 font-medium mb-6 hover:text-slate-700 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Change job titles
          </button>
        )}

        <h1 className="text-4xl sm:text-5xl font-extrabold text-slate-900 leading-tight">
          Here are your matching{" "}
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-cyan-500">
            job
          </span>{" "}
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-pink-600 to-fuchsia-500">
            listings
          </span>
        </h1>

        <div className="mt-4 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div className="max-w-[60%]">
            <p className="text-slate-600 text-base">
              Select up to {MAX_JOB_SELECTIONS} roles to run a full ATS analysis against
              your resume.
            </p>
            {selectedTitles.length > 0 && (
              <p className="text-sm text-slate-400 mt-1">
                Searched: {selectedTitles.map((entry) => entry.title).join(", ")}
              </p>
            )}
          </div>
          <span className="shrink-0 self-start inline-flex items-center px-3 py-1.5 rounded-full bg-purple-100 text-purple-700 font-medium text-sm">
            {selected.length}/{MAX_JOB_SELECTIONS} selected
          </span>
        </div>

        <WarningNotice messages={warnings} className="mt-6" />

        {jobs.length === 0 ? (
          <div className="mt-10 rounded-2xl border border-slate-100 bg-white p-10 text-center">
            <p className="text-slate-500">No postings came back for those titles.</p>
            {onBack && (
              <button
                onClick={onBack}
                className="mt-4 text-sm font-semibold text-blue-600 hover:text-blue-800 transition-colors"
              >
                Try different job titles
              </button>
            )}
          </div>
        ) : (
          <>
            <FilterBar
              filters={filters}
              setFilters={setFilters}
              types={types}
              total={jobs.length}
              shown={visible.length}
            />

            {visible.length === 0 ? (
              <div className="mt-6 rounded-2xl border border-slate-100 bg-white p-10 text-center">
                <p className="text-slate-500">
                  Nothing matches those filters. Try widening them.
                </p>
              </div>
            ) : (
              <div className="mt-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {visible.map((job) => (
                  <JobCard
                    key={job.id}
                    job={job}
                    isSelected={selected.some((item) => item.id === job.id)}
                    isCapped={isCapped}
                    onToggle={toggleRole}
                    onView={handleView}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </main>

      {selected.length > 0 && (
        <div className="fixed bottom-8 left-0 right-0 flex justify-center pointer-events-none px-6">
          <button
            className="pointer-events-auto rounded-full px-8 py-3 bg-gradient-to-r from-blue-500 to-fuchsia-500 text-white font-medium shadow-lg shadow-purple-500/30 hover:opacity-95 transition-opacity"
            onClick={() => onAnalyze(selected)}
          >
            Analyse {selected.length} role{selected.length === 1 ? "" : "s"} against my resume →
          </button>
        </div>
      )}
    </div>
  );
}
