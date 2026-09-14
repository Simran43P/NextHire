import { useState } from "react";
import NextHireLanding from "./components/NextHireLanding";
import ResumeDialog from "./components/ResumeDialog";
import ProfileReview from "./components/ProfileReview";
import JobTitlesDialog from "./components/JobTitlesDialog";
import JobListings from "./components/JobListings";
import ATSAnalysisDashboard from "./components/AtsAnalysis";

/**
 * The pipeline, as one explicit state machine.
 *
 *   landing -> review -> titles -> jobs -> ats
 *
 * Previously this file held a block labelled "TEMPORARY WORKFLOW FOR TESTING"
 * with the real flow commented out beneath it, which left the landing page and
 * the job-titles step unreachable. Each stage is now a named step rather than a
 * set of independent booleans, so no combination of flags can put the app into
 * a state that renders two screens at once or none at all.
 */

const STEP = {
  landing: "landing",
  review: "review",
  titles: "titles",
  jobs: "jobs",
  ats: "ats",
};

export default function App() {
  const [step, setStep] = useState(STEP.landing);
  const [showResumeDialog, setShowResumeDialog] = useState(false);

  const [profile, setProfile] = useState(null);
  const [gaps, setGaps] = useState([]);
  const [selectedTitles, setSelectedTitles] = useState([]);
  const [search, setSearch] = useState({ jobs: [], warnings: [] });
  const [selectedJobs, setSelectedJobs] = useState([]);

  const restart = () => {
    setStep(STEP.landing);
    setShowResumeDialog(false);
    setProfile(null);
    setGaps([]);
    setSelectedTitles([]);
    setSearch({ jobs: [], warnings: [] });
    setSelectedJobs([]);
  };

  if (step === STEP.review) {
    return (
      <ProfileReview
        profile={profile}
        gaps={gaps}
        onBack={restart}
        onConfirm={(corrected) => {
          setProfile(corrected);
          setStep(STEP.titles);
        }}
      />
    );
  }

  if (step === STEP.titles) {
    return (
      <JobTitlesDialog
        profile={profile}
        onClose={() => setStep(STEP.review)}
        onJobsFound={(result, titles) => {
          setSearch(result);
          setSelectedTitles(titles);
          setStep(STEP.jobs);
        }}
      />
    );
  }

  if (step === STEP.jobs) {
    return (
      <JobListings
        jobs={search.jobs}
        warnings={search.warnings}
        selectedTitles={selectedTitles}
        onBack={() => setStep(STEP.titles)}
        onAnalyze={(jobs) => {
          setSelectedJobs(jobs);
          setStep(STEP.ats);
        }}
      />
    );
  }

  if (step === STEP.ats) {
    return (
      <ATSAnalysisDashboard
        selectedJobs={selectedJobs}
        resumeProfile={profile}
        onBack={() => setStep(STEP.jobs)}
      />
    );
  }

  return (
    <>
      <NextHireLanding setShowDialog={setShowResumeDialog} />
      <ResumeDialog
        showDialog={showResumeDialog}
        onClose={() => setShowResumeDialog(false)}
        onParsed={({ profile: parsed, gaps: found }) => {
          setProfile(parsed);
          setGaps(found);
          setShowResumeDialog(false);
          setStep(STEP.review);
        }}
      />
    </>
  );
}
