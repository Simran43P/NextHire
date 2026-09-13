// import { useState , useEffect } from "react";
// import NextHireLanding from "./components/NextHireLanding";
// import ResumeDialog from "./components/ResumeDialog";
// import JobTitlesDialog from "./components/JobTitlesdialog";
// import JobListings from "./components/JobListings";
// import ATSAnalysisDashboard from "./components/AtsAnalysis";

// function App() {
//   const [showDialog, setShowDialog] = useState(false);
//   const [resumeProfile, setResumeProfile] = useState(null);
//   const [showJobTitlesDialog, setShowJobTitlesDialog] = useState(false);
//   const [selectedTitles, setSelectedTitles] = useState([]);
//   const [jobs, setJobs] = useState([]);
//   const [selectedJob, setSelectedJob] = useState([]);
//   const [showATS, setShowATS] = useState(false);
  
//   useEffect(() => {
//   console.log("App resumeProfile:", resumeProfile);
//   }, [resumeProfile]);

//   return (
//     <>
//     {!showJobTitlesDialog && jobs.length === 0 && (
//       < NextHireLanding 
//        setShowDialog={setShowDialog}
//     />
//     )}
    

//     <ResumeDialog
//       showDialog={showDialog}
//       setShowDialog={setShowDialog}
//       setResumeProfile={setResumeProfile}
//       setShowJobTitlesDialog={setShowJobTitlesDialog}
//     />

//     {showJobTitlesDialog && (
//       <JobTitlesDialog
//         resumeProfile={resumeProfile}
//         onClose={() => setShowJobTitlesDialog(false)}
//         setSelectedTitles={setSelectedTitles}
//         setJobs={setJobs}
//       />
//      )}

//      {!showJobTitlesDialog && (
//           <JobListings 
//           jobs={jobs}
//           selectedTitles={selectedTitles}
//           setSelectedJob={setSelectedJob}
//           setShowATS={setShowATS}
//           />
//         )}
//   </>
//   );
// }

// export default App;





// TEMPORARY WORKFLOW FOR TESTING THE CURRENT COMPONENT.
import { useState } from "react";
import ResumeDialog from "./components/ResumeDialog";
import JobListings from "./components/JobListings";
import ATSAnalysisDashboard from "./components/AtsAnalysis";

function App() {
  const [showDialog, setShowDialog] = useState(true);
  const [resumeProfile, setResumeProfile] = useState(null);
  const [selectedJobs, setSelectedJobs] = useState([]);
  const [showATS, setShowATS] = useState(false);

  if (showATS) {
    return (
      <ATSAnalysisDashboard
        selectedJobs={selectedJobs}
        resumeProfile={resumeProfile}
      />
    );
  }

  return (
    <>
      <ResumeDialog
        showDialog={showDialog}
        setShowDialog={setShowDialog}
        setResumeProfile={setResumeProfile}
        setShowJobTitlesDialog={() => {}}
      />
      {!showDialog && resumeProfile && (
        <JobListings
          jobs={[]}
          selectedTitles={[]}
          setSelectedJobs={setSelectedJobs}
          setShowATS={setShowATS}
        />
      )}
    </>
  );
}

export default App;