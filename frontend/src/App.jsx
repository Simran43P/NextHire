import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import NextHireLanding from "./components/NextHireLanding";
import ResumeDialog from "./components/ResumeDialog";
import ProfileReview from "./components/ProfileReview";
import JobTitlesDialog from "./components/JobTitlesDialog";
import JobListings from "./components/JobListings";
import ATSAnalysisDashboard from "./components/AtsAnalysis";
import ResumeOptimizer from "./components/ResumeOptimizer";
import CoverLetter from "./components/CoverLetter";
import InterviewPrep from "./components/InterviewPrep";
import ApplicationTracker from "./components/ApplicationTracker";
import AuthDialog from "./components/AuthDialog";
import AccountMenu from "./components/AccountMenu";
import { AuthProvider } from "./auth/AuthContext";
import { useAuth } from "./auth/context";
import { awaitTask, fetchProfile, listActiveTasks, saveProfile } from "./api/pipeline";
import { trackJob } from "./api/tracker";

/**
 * The pipeline, as one explicit state machine.
 *
 *   landing -> review -> titles -> jobs -> ats -> optimize | cover | interview
 *
 * Plus a tracker, reachable at any time once signed in.
 *
 * Each stage is a named step rather than a set of independent booleans, so no
 * combination of flags can render two screens at once or none at all.
 *
 * Signing in changes what persists, never what is possible: a guest runs the
 * whole pipeline, and registering carries that work into the new account
 * instead of discarding it.
 */

const STEP = {
  landing: "landing",
  review: "review",
  titles: "titles",
  jobs: "jobs",
  ats: "ats",
  optimize: "optimize",
  cover: "cover",
  interview: "interview",
  tracker: "tracker",
};

function Pipeline() {
  const { isAuthenticated, loading: authLoading } = useAuth();

  const [step, setStep] = useState(STEP.landing);
  const [showResumeDialog, setShowResumeDialog] = useState(false);
  const [authDialog, setAuthDialog] = useState(null); // null | "signin" | "register"

  const [profile, setProfile] = useState(null);
  const [profileId, setProfileId] = useState(null);
  const [gaps, setGaps] = useState([]);
  const [carryover, setCarryover] = useState(null);

  const [selectedTitles, setSelectedTitles] = useState([]);
  const [search, setSearch] = useState({ jobs: [], warnings: [] });
  const [selectedJobs, setSelectedJobs] = useState([]);
  const [focusedJob, setFocusedJob] = useState(null); // { job, analysis }
  const [trackedJobIds, setTrackedJobIds] = useState([]);

  const [resuming, setResuming] = useState(false);

  const restart = useCallback(() => {
    setStep(STEP.landing);
    setShowResumeDialog(false);
    setProfile(null);
    setProfileId(null);
    setGaps([]);
    setCarryover(null);
    setSelectedTitles([]);
    setSearch({ jobs: [], warnings: [] });
    setSelectedJobs([]);
    setFocusedJob(null);
    setTrackedJobIds([]);
  }, []);

  // Reattach to work that was already running.
  //
  // Extraction takes about a minute. If someone refreshed, switched tabs, or
  // closed the laptop while it ran, the task is still going server-side - so
  // rejoin it rather than making them upload the same file again.
  useEffect(() => {
    if (authLoading || !isAuthenticated || profile || step !== STEP.landing) return undefined;

    const controller = new AbortController();
    let cancelled = false;

    (async () => {
      try {
        const active = await listActiveTasks({ signal: controller.signal });
        const extraction = active.find((task) => task.kind === "extraction");
        if (!extraction || cancelled) return;

        setResuming(true);
        const result = await awaitTask(extraction.id, { signal: controller.signal });
        if (cancelled) return;

        setProfile(result.profile);
        setProfileId(result.profile_id ?? null);
        setGaps(result.gaps ?? []);
        setStep(STEP.review);
      } catch {
        // Nothing to resume, or it failed while we were away. Either way the
        // landing page is a fine place to be.
      } finally {
        if (!cancelled) setResuming(false);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [authLoading, isAuthenticated, profile, step]);

  const accountSlot = (
    <AccountMenu
      onRequestSignIn={() => setAuthDialog("signin")}
      onSignedOut={restart}
    />
  );

  const handleAuthClosed = async ({ signedIn, carried }) => {
    setAuthDialog(null);
    if (!signedIn) return;

    // The guest's work followed them in; adopt the stored copy so everything
    // from here on is persisted and cacheable.
    if (carried?.profile_id) {
      setProfileId(carried.profile_id);
      setCarryover(null);
      try {
        const stored = await fetchProfile(carried.profile_id);
        setProfile(stored.profile);
        setGaps(stored.gaps ?? []);
      } catch {
        // Keep the in-memory copy; it is the same data.
      }
    }
  };

  const guestHasWork = !isAuthenticated && Boolean(profile);

  const header = (
    <div className="fixed top-3 right-6 z-40 flex items-center gap-3">
      {isAuthenticated && step !== STEP.tracker && (
        <button
          onClick={() => setStep(STEP.tracker)}
          className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
        >
          My applications
        </button>
      )}
      {guestHasWork && (
        <button
          onClick={() => {
            setCarryover({ profile, gaps, rawText: "", filename: "" });
            setAuthDialog("register");
          }}
          className="rounded-full bg-slate-900 text-white px-4 py-2 text-sm font-medium hover:bg-slate-800 transition-colors"
        >
          Save my work
        </button>
      )}
      {accountSlot}
    </div>
  );

  const dialogs = (
    <AuthDialog
      open={authDialog !== null}
      initialMode={authDialog ?? "signin"}
      carryover={carryover}
      onClose={handleAuthClosed}
    />
  );

  if (step === STEP.review) {
    return (
      <>
        {header}
        <ProfileReview
          profile={profile}
          gaps={gaps}
          onBack={restart}
          onConfirm={async (corrected) => {
            setProfile(corrected);
            // Persisting bumps the profile version, which is what invalidates
            // any analysis cached against the uncorrected version.
            if (profileId) {
              try {
                await saveProfile(profileId, corrected);
              } catch {
                // The corrected profile is still used for this session.
              }
            }
            setStep(STEP.titles);
          }}
        />
        {dialogs}
      </>
    );
  }

  if (step === STEP.titles) {
    return (
      <>
        {header}
        <JobTitlesDialog
          profile={profile}
          profileId={profileId}
          background={isAuthenticated}
          onClose={() => setStep(STEP.review)}
          onJobsFound={(result, titles) => {
            setSearch(result);
            setSelectedTitles(titles);
            setStep(STEP.jobs);
          }}
        />
        {dialogs}
      </>
    );
  }

  if (step === STEP.jobs) {
    return (
      <>
        {header}
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
        {dialogs}
      </>
    );
  }

  if (step === STEP.ats) {
    return (
      <>
        {header}
        <ATSAnalysisDashboard
          selectedJobs={selectedJobs}
          resumeProfile={profile}
          profileId={profileId}
          background={isAuthenticated}
          onBack={() => setStep(STEP.jobs)}
          trackedJobIds={trackedJobIds}
          onOptimize={(job, analysis) => {
            setFocusedJob({ job, analysis });
            setStep(STEP.optimize);
          }}
          onCoverLetter={(job, analysis) => {
            setFocusedJob({ job, analysis });
            setStep(STEP.cover);
          }}
          onInterviewPrep={(job, analysis) => {
            setFocusedJob({ job, analysis });
            setStep(STEP.interview);
          }}
          onTrack={async (job) => {
            if (!job?.job_id) return;
            try {
              await trackJob({ jobId: job.job_id });
              setTrackedJobIds((previous) => [...previous, job.job_id]);
            } catch {
              // Signed out, or already tracked. The board is the source of
              // truth either way, so there is nothing useful to say here.
            }
          }}
        />
        {dialogs}
      </>
    );
  }

  if (step === STEP.optimize) {
    return (
      <>
        {header}
        <ResumeOptimizer
          job={focusedJob?.job}
          analysis={focusedJob?.analysis}
          profile={profile}
          profileId={profileId}
          onBack={() => setStep(STEP.ats)}
        />
        {dialogs}
      </>
    );
  }

  if (step === STEP.cover) {
    return (
      <>
        {header}
        <CoverLetter
          job={focusedJob?.job}
          analysis={focusedJob?.analysis}
          profile={profile}
          profileId={profileId}
          onBack={() => setStep(STEP.ats)}
        />
        {dialogs}
      </>
    );
  }

  if (step === STEP.interview) {
    return (
      <>
        {header}
        <InterviewPrep
          job={focusedJob?.job}
          analysis={focusedJob?.analysis}
          profile={profile}
          profileId={profileId}
          onBack={() => setStep(STEP.ats)}
        />
        {dialogs}
      </>
    );
  }

  if (step === STEP.tracker) {
    return (
      <>
        {header}
        <ApplicationTracker
          onBack={() => setStep(selectedJobs.length ? STEP.ats : STEP.landing)}
        />
        {dialogs}
      </>
    );
  }

  return (
    <>
      <NextHireLanding setShowDialog={setShowResumeDialog} accountSlot={accountSlot} />

      {resuming && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 inline-flex items-center gap-2 rounded-full bg-slate-900 text-white px-5 py-2.5 text-sm shadow-lg">
          <Loader2 className="w-4 h-4 animate-spin" />
          Picking up where you left off...
        </div>
      )}

      <ResumeDialog
        showDialog={showResumeDialog}
        background={isAuthenticated}
        onClose={() => setShowResumeDialog(false)}
        onParsed={({ profile: parsed, gaps: found, profileId: storedId, rawText, filename }) => {
          setProfile(parsed);
          setProfileId(storedId);
          setGaps(found);
          // Held in case they sign up later - registering should not cost them
          // the upload they just waited a minute for.
          if (!storedId) setCarryover({ profile: parsed, gaps: found, rawText, filename });
          setShowResumeDialog(false);
          setStep(STEP.review);
        }}
      />

      {dialogs}
    </>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Pipeline />
    </AuthProvider>
  );
}
