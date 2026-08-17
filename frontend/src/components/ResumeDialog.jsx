import React, { useState, useRef } from "react";

/**
 * ResumeDialog
 * A resume upload dialog with a drag & drop PDF dropzone.
 * Built with React + Tailwind CSS.
 */
export default function ResumeDialog({ showDialog, setShowDialog, setResumeProfile, setShowJobTitlesDialog }) {
  const [isDragging, setIsDragging] = useState(false);
  const [file, setFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);
  
  if (!showDialog) return null;

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    setError(null);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) setFile(dropped);
  };

  const handleBrowseClick = () => {
    inputRef.current?.click();
  };

  const handleFileChange = (e) => {
    setError(null);
    const selected = e.target.files?.[0];
    if (selected) setFile(selected);
  };

  const handleContinue = async () => {
    if (!file) {
      setError("Please select a PDF file first.");
      return;
    }

    setIsUploading(true);
    setError(null);

    // Package the file into FormData
    const formData = new FormData();
    formData.append("file", file);

    try {
      // Send to the FastAPI backend we just created
      const response = await fetch("http://localhost:8000/api/parse-resume", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to parse resume.");
      }

      const data = await response.json();
      
      // Successfully extracted! Log it so you can see it in browser dev tools.
      console.log("Parsed Resume Profile:", data.profile);

      //Save the parsed profile in App.jsx
      setResumeProfile(data.profile);

      // Close the dialog and (optionally) pass the text to a parent component
      setShowDialog(false);

      // Show the JobTitlesDialog after successful upload
      setShowJobTitlesDialog(true); 
      
    } catch (err) {
      console.error("Upload error:", err);
      setError(err.message);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div 
    onClick={() => setShowDialog(false)}
    className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
      <div 
      onClick={(e) => e.stopPropagation()}
      className="w-full max-w-2xl bg-white rounded-3xl shadow-2xl p-6 sm:p-10 md:p-12">
        {/* Header */}
        <div className="flex justify-end">
            <button
                onClick={() => setShowDialog(false)}
                className="text-slate-500 hover:text-slate-800 text-2xl"
                disabled={isUploading}
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

        {/* Drag & Drop Zone */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`flex flex-col items-center justify-center text-center rounded-2xl border-2 border-dashed transition-colors duration-200 py-10 sm:py-12 px-4 sm:px-6 ${
            isDragging
              ? "border-indigo-400 bg-indigo-50/50"
              : "border-indigo-300 hover:bg-indigo-50/50"
          }`}
        >
          {/* PDF Icon */}
          <div className="mb-4 relative flex items-center justify-center w-12 h-12 sm:w-16 sm:h-16 rounded-xl bg-indigo-100">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              className="w-7 h-7 sm:w-9 sm:h-9"
            >
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

          {/* Dropzone Text */}
          <p className="text-lg sm:text-xl font-semibold text-slate-900">
            Drag &amp; drop your PDF resume here
          </p>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 mb-5 sm:mb-6">
            {file ? file.name : "(PDF files only, max 5MB)"}
          </p>

          {/* Browse Button */}
          <button
            type="button"
            onClick={handleBrowseClick}
            disabled={isUploading}
            className="bg-gradient-to-r from-blue-500 to-fuchsia-500 text-white text-sm font-medium rounded-full px-6 py-2 shadow-lg shadow-purple-500/30 hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            Or browse files
          </button>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={handleFileChange}
          />
        </div>

        {/* Error Display */}
        {error && (
          <p className="text-red-500 text-sm text-center mt-4">
            {error}
          </p>
        )}

        {/* Bottom Action Area */}
        <div className="flex justify-end mt-6 sm:mt-8">
          <button
            type="button"
            onClick={handleContinue}
            disabled={isUploading || !file}
            className="flex items-center gap-2 bg-gradient-to-r from-blue-500 to-fuchsia-500 text-white text-sm font-medium rounded-full px-6 sm:px-8 py-2.5 shadow-lg shadow-purple-500/30 hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {isUploading ? "Uploading..." : "Continue"}
            {!isUploading && (
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    d="M5 12h14M13 6l6 6-6 6"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}