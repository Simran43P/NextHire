import React, { useState } from "react";
import { MOCK_JOBS } from "../mocks/jobs";
import { Target } from "lucide-react";

// Flip this flag to switch data sources during development.
// true  -> render MOCK_JOBS, no network calls
// false -> fetch real jobs from the backend via getJobs()
// The JSX below never needs to change when you flip this.
const USE_MOCK_DATA = true;

function SparkleLogo() {
  return (
    <svg viewBox="0 0 24 24" className="w-6 h-6 text-blue-600" fill="currentColor">
      <path d="M12 2c.6 3.6 2.4 5.4 6 6-3.6.6-5.4 2.4-6 6-.6-3.6-2.4-5.4-6-6 3.6-.6 5.4-2.4 6-6z" />
    </svg>
  );
}

export default function JobListings({ jobs , selectedTitles, setSelectedJobs, setShowATS, }) {
  const [selected, setSelected] = useState([]);
  

  const maxSelected = 5;

  // MODIFIED: toggleRole now takes the full job object (not just its id).
  // It removes the job if it's already selected (matched by id), otherwise
  // adds the whole object so downstream pages have full job data to work with.
  const toggleRole = (job) => {
    setSelected((prev) => {
      const alreadySelected = prev.some((j) => j.id === job.id);
      if (alreadySelected) return prev.filter((j) => j.id !== job.id);
      if (prev.length >= maxSelected) return prev;
      return [...prev, job];
    });
  };

  const handleViewJob = (applyLink) => {
    if (!applyLink) return;
    window.open(applyLink, "_blank", "noopener,noreferrer");
  };

  const handleProceed = () => {
      console.log("Selected Jobs:", selected);

      setSelectedJobs(selected);
      setShowATS(true);
    };

  const displayedJobs = USE_MOCK_DATA ? MOCK_JOBS : (jobs || []);

  

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="border-b border-slate-100 bg-white">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center gap-2">
          <SparkleLogo />
          <span className="text-lg font-bold text-slate-900">NextHire</span>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-10 pb-32">
        {/* Title */}
        <h1 className="text-4xl sm:text-5xl font-extrabold text-slate-900 leading-tight">
          Here are your matching{" "}
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-cyan-500">
            job
          </span>{" "}
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-pink-600 to-fuchsia-500">
            listings
          </span>
        </h1>

        {/* Subtitle row */}
        <div className="mt-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <p className="text-slate-600 text-base max-w-[60%]">
            Please select up to 5 job roles from the options below to proceed
            with your tailored applications.
          </p>
          <span className="shrink-0 self-start sm:self-auto inline-flex items-center px-3 py-1.5 rounded-full bg-purple-100 text-purple-700 font-medium text-sm">
            {selected.length}/{maxSelected} Selected
          </span>
        </div>

        {/* Cards grid */}
        <div className="mt-8 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {displayedJobs.map((job) => {
            // MODIFIED: selected now holds job objects, so we check by id
            // instead of a plain array-of-ids `.includes()`.
            const isSelected = selected.some((j) => j.id === job.id);
            return (
              <div
                key={job.id}
                className="bg-white rounded-2xl border border-slate-100 shadow-md p-6 flex flex-col"
              >
                {/* Top row */}
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-slate-300 rounded-lg" />
                    <div className="flex flex-col">
                      <span className="font-bold text-slate-900">{job.company}</span>
                      <span className="text-sm text-slate-500">text-sm, font-medium</span>
                    </div>
                  </div>
                  <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-green-100 text-green-700 text-xs font-bold whitespace-nowrap">
                    <Target className="w-3 h-3" strokeWidth={2.5} />
                    {job.match}% Match
                  </span>
                </div>

                {/* Job title */}
                <h3 className="text-xl font-bold text-slate-900 mt-5 mb-4">
                  {job.title}
                </h3>

                {/* Details */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-slate-500">Location</p>
                    <p className="text-sm text-slate-900 font-medium mt-0.5">{job.location}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Job Type</p>
                    <p className="text-sm text-slate-900 font-medium mt-0.5">{job.type}</p>
                  </div>
                </div>

                {/* Action buttons */}
                <div className="flex gap-3 mt-6">
                  <button
                    onClick={() => handleViewJob(job.apply_link)}
                    disabled={!job.apply_link}
                    className="flex-1 rounded-full py-2.5 font-medium transition-colors bg-slate-100 text-slate-700 hover:bg-slate-200 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    View Job
                  </button>
                  {/* MODIFIED: pass the whole job object, not just job.id */}
                  <button
                    onClick={() => toggleRole(job)}
                    className={`flex-1 rounded-full py-2.5 font-medium transition-colors ${
                      isSelected
                        ? "bg-slate-900 text-white hover:bg-slate-800"
                        : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                    }`}
                  >
                    {isSelected ? "Selected" : "Select Role"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </main>

      {/* Floating action button */}
      {selected.length > 0 && (
        <div className="fixed bottom-8 left-0 right-0 flex justify-center pointer-events-none">
          <button
            className="pointer-events-auto rounded-full px-8 py-3 bg-gradient-to-r from-blue-500 to-fuchsia-500 text-white font-medium shadow-lg shadow-purple-500/30 hover:opacity-95 transition-opacity"
            onClick={handleProceed}
          >
            Proceed to Application →
          </button>
        </div>
      )}
    </div>
  );
}