import { useRef, useState } from "react";
import { MAX_UPLOAD_MB, parseResume, validateResumeFile } from "../api/pipeline";
import ErrorNotice from "./ui/ErrorNotice";
import StageProgress from "./ui/StageProgress";

const STAGES = [
  { key: "upload", label: "Uploading your resume" },
  { key: "extract", label: "Reading and structuring it" },
];

/**
 * Resume upload dialog.
 *
 * Two things happen behind one button: a fast file upload, then a slow local
 * model call. They are shown as separate stages because conflating them into
 * one spinner makes a working minute-long extraction look like a hang.
 */
export default function ResumeDialog({ showDialog, onClose, onParsed, background = false }) {
  const [isDragging, setIsDragging] = useState(false);
  const [file, setFile] = useState(null);
  const [stage, setStage] = useState(null); // null | "upload" | "extract"
  const [uploadPercent, setUploadPercent] = useState(0);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  if (!showDialog) return null;

  const isBusy = stage !== null;

  const chooseFile = (candidate) => {
    if (!candidate) return;
    setError(null);
    const problem = validateResumeFile(candidate);
    if (problem) {
      setFile(null);
      setError({ message: problem, retryable: false });
      return;
    }
    setFile(candidate);
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setIsDragging(false);
    chooseFile(event.dataTransfer.files?.[0]);
  };

  const handleContinue = async () => {
    if (!file || isBusy) return;

    setError(null);
    setUploadPercent(0);
    setStage("upload");

    try {
      const result = await parseResume(file, {
        // Signed in, this runs as a tracked task: closing the tab no longer
        // throws away the minute the model spends reading the resume.
        background,
        onProgress: (percent) => {
          setUploadPercent(percent);
          // The upload finishing is the moment the model starts working.
          if (percent >= 100) setStage("extract");
        },
      });
      onParsed(result);
    } catch (err) {
      setError(err);
    } finally {
      setStage(null);
      setUploadPercent(0);
    }
  };

  const close = () => {
    if (isBusy) return;
    onClose?.();
  };

  return (
    <div
      onClick={close}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
    >
      <div
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-2xl bg-white rounded-3xl shadow-2xl p-6 sm:p-10 md:p-12"
      >
        <div className="flex justify-end">
          <button
            onClick={close}
            disabled={isBusy}
            aria-label="Close"
            className="text-slate-500 hover:text-slate-800 text-2xl disabled:opacity-30 disabled:cursor-not-allowed"
          >
            &times;
          </button>
        </div>

        <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 text-center mb-2">
          Upload your resume to begin
        </h1>
        <p className="text-sm sm:text-base text-slate-500 text-center mb-6 sm:mb-8">
          Get personalized AI-powered job matching and resume tailoring in seconds.
        </p>

        {isBusy ? (
          <StageProgress
            stages={STAGES}
            current={stage}
            progress={stage === "upload" ? uploadPercent : null}
            hint={
              stage === "extract"
                ? "Your resume is being read by a model running on this machine. This usually takes 30-60 seconds."
                : "Uploading..."
            }
          />
        ) : (
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={(event) => {
              event.preventDefault();
              setIsDragging(false);
            }}
            onDrop={handleDrop}
            className={`flex flex-col items-center justify-center text-center rounded-2xl border-2 border-dashed transition-colors duration-200 py-10 sm:py-12 px-4 sm:px-6 ${
              isDragging
                ? "border-indigo-400 bg-indigo-50/50"
                : "border-indigo-300 hover:bg-indigo-50/50"
            }`}
          >
            <div className="mb-4 flex items-center justify-center w-12 h-12 sm:w-16 sm:h-16 rounded-xl bg-indigo-100">
              <svg viewBox="0 0 24 24" fill="none" className="w-7 h-7 sm:w-9 sm:h-9">
                <path
                  d="M6 2h8l4 4v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"
                  fill="#C7D2FE"
                />
                <path d="M14 2v4a1 1 0 0 0 1 1h4" fill="#A5B4FC" />
                <text
                  x="12"
                  y="15.5"
                  textAnchor="middle"
                  fontSize="5"
                  fontWeight="700"
                  fill="#4338CA"
                >
                  PDF
                </text>
                <path
                  d="M12 17v4m0 0l-2-2m2 2l2-2"
                  stroke="#4338CA"
                  strokeWidth="1.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>

            <p className="text-lg sm:text-xl font-semibold text-slate-900">
              Drag &amp; drop your PDF resume here
            </p>
            <p className="text-xs sm:text-sm text-slate-500 mt-1 mb-5 sm:mb-6">
              {file ? file.name : `(PDF files only, max ${MAX_UPLOAD_MB}MB)`}
            </p>

            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="bg-gradient-to-r from-blue-500 to-fuchsia-500 text-white text-sm font-medium rounded-full px-6 py-2 shadow-lg shadow-purple-500/30 hover:opacity-90 transition-opacity"
            >
              Or browse files
            </button>
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={(event) => chooseFile(event.target.files?.[0])}
            />
          </div>
        )}

        {error && (
          <ErrorNotice
            error={error}
            className="mt-5"
            onRetry={error.retryable !== false && file ? handleContinue : undefined}
            onDismiss={() => setError(null)}
          />
        )}

        {!isBusy && (
          <div className="flex justify-end mt-6 sm:mt-8">
            <button
              type="button"
              onClick={handleContinue}
              disabled={!file}
              className="flex items-center gap-2 bg-gradient-to-r from-blue-500 to-fuchsia-500 text-white text-sm font-medium rounded-full px-6 sm:px-8 py-2.5 shadow-lg shadow-purple-500/30 hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Continue
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <path
                  d="M5 12h14M13 6l6 6-6 6"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
