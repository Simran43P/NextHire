import { useEffect, useState } from "react";
import { Sparkles, ArrowLeft, Check, X, ArrowRight } from "lucide-react";

const JOBS = [
  {
    id: 1,
    title: "Data Engineer",
    company: "Company D",
    match: 91,
    label: "Strong Match",
    summary: "Your resume strongly matches the core requirements for this role.",
    matched: ["Python", "SQL", "Pandas", "Tableau"],
    missing: ["AWS", "Docker"],
    improve: [
      "Quantify project impact",
      "Highlight cloud-related experience",
      "Add relevant dashboard/project examples",
    ],
  },
  {
    id: 2,
    title: "Data Analyst",
    company: "Company A",
    match: 74,
    label: "Fair Match",
    summary: "Your resume covers most core requirements, with a few gaps to close.",
    matched: ["Excel", "SQL", "PowerPoint"],
    missing: ["Python", "A/B Testing"],
    improve: [
      "Add measurable business outcomes",
      "Highlight stakeholder communication",
      "Include reporting cadence examples",
    ],
  },
  {
    id: 3,
    title: "Data Scientist",
    company: "Company C",
    match: 84,
    label: "Good Match",
    summary: "Your resume is a good fit, with a couple of skills worth reinforcing.",
    matched: ["Python", "Machine Learning", "SQL"],
    missing: ["TensorFlow"],
    improve: [
      "Detail model deployment experience",
      "Add quantified accuracy improvements",
      "Mention experimentation frameworks used",
    ],
  },
  {
    id: 4,
    title: "Business Analyst",
    company: "Company E",
    match: 68,
    label: "Weak Match",
    summary: "Your resume matches some requirements, but several key skills are missing.",
    matched: ["Excel", "Stakeholder Management"],
    missing: ["SQL", "Process Mapping", "Jira"],
    improve: [
      "Add examples of requirements gathering",
      "Highlight cross-functional collaboration",
      "Include process improvement metrics",
    ],
  },
  {
    id: 5,
    title: "Marketing Coordinator",
    company: "Company B",
    match: 54,
    label: "Mismatch",
    summary: "This role doesn't align closely with your current resume.",
    matched: ["Content Writing"],
    missing: ["SEO", "Campaign Management", "Analytics"],
    improve: [
      "Consider tailoring resume toward marketing skills",
      "Highlight any campaign or content experience",
      "Add measurable engagement results",
    ],
  },
];

function matchPillClasses(match) {
  if (match > 80) return "bg-green-100 text-green-700";
  if (match >= 70) return "bg-yellow-100 text-yellow-700";
  if (match >= 60) return "bg-orange-100 text-orange-700";
  return "bg-red-100 text-red-700";
}

export default function ATSAnalysisDashboard({ selectedJobs, resumeProfile }) {
  const [selectedId, setSelectedId] = useState(
    selectedJobs?.[0]?.id || null
  );

  const [jobs, setJobs] = useState(selectedJobs || []);
  const [analysisResults, setAnalysisResults] = useState({});
  const [isAnalyzing, setIsAnalyzing] = useState(true);

  const selected = jobs.find((j) => j.id === selectedId) || jobs[0];

  const matchedSkills = selected?.matched || [];
  const missingSkills = selected?.missing || [];
  const improvements = selected?.improve || [];

  const best = jobs.length ? Math.max(...jobs.map((j) => j.match)) : 0;
  const avg = jobs.length
    ? Math.round(jobs.reduce((s, j) => s + j.match, 0) / jobs.length)
    : 0;

  const removeJob = (id, e) => {
    e.stopPropagation();
    const remaining = jobs.filter((j) => j.id !== id);
    setJobs(remaining);
    if (id === selectedId && remaining.length) {
      setSelectedId(remaining[0].id);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Top Navigation */}
      <div className="bg-white border-b border-slate-100">
        <div className="max-w-6xl mx-auto px-8 py-5 flex items-center">
          <Sparkles className="w-6 h-6 text-blue-500 mr-2" fill="currentColor" />
          <span className="text-xl font-extrabold text-slate-900">NextHire</span>
        </div>
      </div>

      <div className="max-w-6xl mx-auto p-8">
        {/* Header */}
        <div className="text-center mb-10">
          <button className="inline-flex items-center gap-2 text-sm text-slate-500 font-medium mb-4 hover:text-slate-700 transition-colors">
            <ArrowLeft className="w-4 h-4" />
            Back to Job Listings
          </button>
          <h1 className="text-4xl md:text-5xl font-extrabold text-slate-900">
            Your{" "}
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-fuchsia-500">
              ATS Analysis
            </span>
          </h1>
          <p className="text-slate-500 text-base max-w-2xl mx-auto mt-4">
            Compare how your resume matches the jobs you selected and decide which
            roles are worth applying to.
          </p>
        </div>

        {/* Summary Stats Bar */}
        <div className="bg-white rounded-3xl shadow-sm px-8 py-4 mx-auto flex items-center justify-center gap-12 w-fit mb-12 border border-slate-100">
          <div className="text-center">
            <div className="text-2xl font-bold text-slate-900">{jobs.length}</div>
            <div className="text-sm text-slate-500">Jobs Selected</div>
          </div>
          <div className="w-px h-10 bg-slate-100" />
          <div className="text-center">
            <div className="text-2xl font-bold text-slate-900">{best}%</div>
            <div className="text-sm text-slate-500">Best Match</div>
          </div>
          <div className="w-px h-10 bg-slate-100" />
          <div className="text-center">
            <div className="text-2xl font-bold text-slate-900">{avg}%</div>
            <div className="text-sm text-slate-500">Average Match</div>
          </div>
        </div>

        {/* Main Content */}
        <div className="grid grid-cols-12 gap-8">
          {/* Left Column */}
          <div className="col-span-12 md:col-span-5 lg:col-span-4">
            <h2 className="text-lg font-bold text-slate-900">Selected Jobs</h2>
            <p className="text-sm text-slate-500 mb-4">Review your matches</p>

            <div className="flex flex-col gap-4">
              {jobs.map((job) => {
                const isActive = job.id === selectedId;
                if (isActive) {
                  return (
                    <div
                      key={job.id}
                      onClick={() => setSelectedId(job.id)}
                      className="bg-gradient-to-r from-blue-500 to-fuchsia-500 p-[2px] rounded-2xl cursor-pointer"
                    >
                      <div className="bg-white rounded-[14px] p-4 flex items-center justify-between">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-slate-900">
                              {job.title}
                            </span>
                            <span className="bg-green-100 text-green-700 rounded-full px-2 py-1 text-xs font-semibold">
                              {job.match}% match
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5 mt-1">
                            <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                            <span className="text-xs text-slate-500">
                              {job.label || "ATS Analysis Pending"}
                            </span>
                          </div>
                        </div>
                        <button
                          onClick={(e) => removeJob(job.id, e)}
                          className="text-xs text-slate-400 hover:text-red-500 transition-colors"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  );
                }
                return (
                  <div
                    key={job.id}
                    onClick={() => setSelectedId(job.id)}
                    className="bg-white rounded-2xl shadow-sm border border-slate-100 p-4 flex items-center justify-between cursor-pointer hover:border-slate-200 transition-colors"
                  >
                    <div>
                      <div className="font-bold text-slate-900">{job.title}</div>
                      <div className="text-xs text-slate-500">{job.company}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-500">{job.label || "ATS Analysis Pending"}</span>
                      <span
                        className={`rounded-full px-3 py-1 text-sm font-semibold ${matchPillClasses(
                          job.match
                        )}`}
                      >
                        {job.match}%
                      </span>
                    </div>
                  </div>
                );
              })}
              {jobs.length === 0 && (
                <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 text-center text-sm text-slate-400">
                  No jobs selected.
                </div>
              )}
            </div>
          </div>

          {/* Right Column */}
          <div className="col-span-12 md:col-span-7 lg:col-span-8">
            {selected ? (
              <div className="bg-white rounded-3xl shadow-md border border-slate-100 p-8">
                <div className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-purple-700 bg-purple-50 rounded-full px-3 py-1 mb-6">
                  <Sparkles className="w-3 h-3" />
                  AI ATS Analysis
                </div>

                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-3xl font-bold text-slate-900">
                      {selected.title}
                    </h3>
                    <p className="text-slate-500 mt-1">{selected.company}</p>
                  </div>
                  <div className="text-right">
                    <div className="text-4xl font-extrabold text-slate-900">
                      -
                    </div>
                    <span className="inline-block bg-green-100 text-green-700 rounded-full px-3 py-1 text-sm font-medium mt-1">
                      Analysis Pending
                    </span>
                  </div>
                </div>

                <p className="text-slate-600 mt-4 mb-8">{selected.summary || "Summary will be available after analysis is complete."}</p>

                {/* Matched Skills */}
                <div>
                  <div className="text-sm font-bold text-slate-900 mb-3">
                    Matched Skills
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {matchedSkills.map((skill) => (
                      <span
                        key={skill}
                        className="bg-green-50 border border-green-200 text-green-700 rounded-full px-3 py-1 text-sm flex items-center gap-1"
                      >
                        <Check className="w-3.5 h-3.5" />
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Missing Skills */}
                <div>
                  <div className="text-sm font-bold text-slate-900 mt-6 mb-3">
                    Missing or Weak Skills
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {missingSkills.map((skill) => (
                      <span
                        key={skill}
                        className="bg-red-50 border border-red-200 text-red-700 rounded-full px-3 py-1 text-sm flex items-center gap-1"
                      >
                        <X className="w-3.5 h-3.5" />
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>

                {/* What You Can Improve */}
                <div>
                  <div className="text-sm font-bold text-slate-900 mt-6 mb-3">
                    What You Can Improve
                  </div>
                  <div className="bg-purple-50/50 border border-purple-100 rounded-2xl p-5">
                    {improvements.map((line, i) => (
                      <p
                        key={i}
                        className="text-sm text-slate-700 leading-relaxed"
                      >
                        {line}
                      </p>
                    ))}
                  </div>
                </div>

                {/* Bottom Action */}
                <button className="w-full mt-8 py-4 rounded-full text-white font-bold text-lg bg-gradient-to-r from-blue-500 to-fuchsia-500 shadow-xl shadow-fuchsia-500/20 flex items-center justify-center gap-2 hover:opacity-95 transition-opacity">
                  Optimize Resume
                  <ArrowRight className="w-5 h-5" />
                </button>

                <div className="text-center mt-4">
                  <span className="text-sm text-slate-500">
                    Get Upskilling Plan
                  </span>
                  <span className="bg-blue-50 text-blue-600 text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ml-2 align-middle">
                    Coming Soon
                  </span>
                </div>
              </div>
            ) : (
              <div className="bg-white rounded-3xl shadow-md border border-slate-100 p-8 text-center text-slate-400">
                Select a job to see its analysis.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}