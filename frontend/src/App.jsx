import { useState , useEffect } from "react";
import NextHireLanding from "./components/NextHireLanding";
import ResumeDialog from "./components/ResumeDialog";
import JobTitlesDialog from "./components/JobTitlesdialog";
import JobListings from "./components/JobListings";

function App() {
  const [showDialog, setShowDialog] = useState(false);
  const [resumeProfile, setResumeProfile] = useState(null);
  const [showJobTitlesDialog, setShowJobTitlesDialog] = useState(false);
  const [selectedTitles, setSelectedTitles] = useState([]);
  const [jobs, setJobs] = useState([]);
  
  useEffect(() => {
  console.log("App resumeProfile:", resumeProfile);
  }, [resumeProfile]);

  return (
    <>
    {!showJobTitlesDialog && jobs.length === 0 && (
      < NextHireLanding 
       setShowDialog={setShowDialog}
    />
    )}
    

    <ResumeDialog
      showDialog={showDialog}
      setShowDialog={setShowDialog}
      setResumeProfile={setResumeProfile}
      setShowJobTitlesDialog={setShowJobTitlesDialog}
    />

    {showJobTitlesDialog && (
      <JobTitlesDialog
        resumeProfile={resumeProfile}
        onClose={() => setShowJobTitlesDialog(false)}
        setSelectedTitles={setSelectedTitles}
        setJobs={setJobs}
      />
     )}

     {!showJobTitlesDialog && (
          <JobListings 
          jobs={jobs}
          selectedTitles={selectedTitles}
          />
        )}
  </>
  );
}

export default App;

// import JobListings from "./components/JobListings";

// function App() {
//   return <JobListings />;
// }

// export default App;