import { useEffect, useState } from "react";
import { ArrowLeft, Download, FileText, RefreshCw, Sparkles, TriangleAlert } from "lucide-react";
import {
  TONES,
  downloadCoverLetterPdf,
  downloadCoverLetterText,
  generateCoverLetter,
  saveCoverLetter,
} from "../api/tracker";
import ErrorNotice from "./ui/ErrorNotice";
import StageProgress from "./ui/StageProgress";

/**
 * Write, check, and export a cover letter.
 *
 * Unlike the resume tailoring, an unsupported claim here cannot simply be
 * discarded - a letter is one piece of prose, and throwing it away over a
 * single overreaching sentence would leave the candidate with nothing. So the
 * flagged sentences are shown prominently and the letter stays editable, which
 * is the right remedy: the candidate knows whether they have actually done the
 * thing the sentence claims.
 *
 * The check runs again on save, because the candidate can type a claim in
 * themselves and a warning that only ever applied to the model's draft would be
 * worth very little.
 */
export default function CoverLetter({ job, profile, profileId = null, analysis, onBack }) {
  const [tone, setTone] = useState("professional");
  const [letter, setLetter] = useState("");
  const [unsupported, setUnsupported] = useState([]);
  const [letterId, setLetterId] = useState(null);
  const [phase, setPhase] = useState("generating"); // generating | ready
  const [error, setError] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);

  const jobId = job?.job_id ?? null;

  const [requestToken, setRequestToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    (async () => {
      try {
        const result = await generateCoverLetter(
          {
            profile,
            profileId,
            job: jobId
              ? null
              : { title: job?.title, company: job?.company, description: job?.description },
            jobId,
            analysis,
            tone,
          },
          { signal: controller.signal }
        );
        if (cancelled) return;
        setLetter(result.letter);
        setUnsupported(result.unsupported);
        setLetterId(result.coverLetterId);
        setDirty(false);
      } catch (err) {
        if (!cancelled && err?.name !== "AbortError") setError(err);
      } finally {
        if (!cancelled) setPhase("ready");
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
    // Regenerating on a tone change is intentional; the tone is the prompt.
  }, [profile, profileId, job, jobId, analysis, tone, requestToken]);

  // Synchronous resets belong with the action that triggers them, not in the
  // effect body where they would cause cascading renders.
  const rewrite = () => {
    setPhase("generating");
    setError(null);
    setRequestToken((token) => token + 1);
  };

  const changeTone = (next) => {
    if (next === tone) return;
    setPhase("generating");
    setError(null);
    setTone(next);
  };

  const handleSave = async () => {
    if (!letterId || !dirty) return;
    setSaving(true);
    try {
      const result = await saveCoverLetter(letterId, letter);
      setUnsupported(result.unsupported);
      setDirty(false);
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  };

  const handleExport = async (kind) => {
    setExporting(true);
    setError(null);
    try {
      if (kind === "pdf") {
        await downloadCoverLetterPdf(letter, profile?.name ?? "");
      } else {
        downloadCoverLetterText(letter);
      }
    } catch (err) {
      setError(err);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-100 bg-white">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-blue-500" fill="currentColor" />
          <span className="text-lg font-bold text-slate-900">NextHire</span>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-10 pb-24">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-2 text-sm text-slate-500 font-medium mb-6 hover:text-slate-700 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to analysis
        </button>

        <h1 className="text-3xl font-extrabold text-slate-900">
          Cover letter for{" "}
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-fuchsia-500">
            {job?.title ?? "this role"}
          </span>
        </h1>
        <p className="text-slate-500 mt-2">
          Built only from what your resume already says. Edit it freely — it is yours.
        </p>

        <div className="flex items-center gap-2 mt-6">
          {TONES.map((option) => (
            <button
              key={option.value}
              onClick={() => changeTone(option.value)}
              disabled={phase === "generating"}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
                tone === option.value
                  ? "bg-slate-900 text-white"
                  : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {option.label}
            </button>
          ))}
          <button
            onClick={rewrite}
            disabled={phase === "generating"}
            title="Write it again"
            className="ml-auto rounded-full border border-slate-200 bg-white p-2 text-slate-400 hover:text-slate-700 transition-colors disabled:opacity-50"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {error && <ErrorNotice error={error} className="mt-6" onDismiss={() => setError(null)} />}

        {phase === "generating" ? (
          <StageProgress
            stages={[{ key: "write", label: "Writing your letter" }]}
            current="write"
            hint="This usually takes 30-45 seconds."
          />
        ) : (
          <>
            {unsupported.length > 0 && (
              <div className="rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3.5 mt-6">
                <div className="flex items-start gap-3">
                  <TriangleAlert className="w-4 h-4 mt-0.5 flex-shrink-0 text-amber-600" />
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-amber-900">
                      {unsupported.length} sentence
                      {unsupported.length === 1 ? "" : "s"} claim something your resume
                      does not say. Check {unsupported.length === 1 ? "it" : "them"} before
                      you send this.
                    </p>
                    <div className="mt-2 space-y-2">
                      {unsupported.map((item, index) => (
                        <div
                          key={index}
                          className="rounded-xl bg-white/70 border border-amber-200 p-2.5"
                        >
                          <p className="text-xs text-slate-700 italic">"{item.sentence}"</p>
                          <p className="text-[11px] text-amber-800 mt-1">
                            Not in your resume: {item.claims.join(", ")}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            <textarea
              value={letter}
              onChange={(event) => {
                setLetter(event.target.value);
                setDirty(true);
              }}
              onBlur={handleSave}
              rows={18}
              className="w-full rounded-2xl border border-slate-200 bg-white p-5 mt-6 text-sm leading-relaxed text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
            />

            <div className="flex flex-wrap items-center gap-3 mt-4">
              <span className="text-xs text-slate-400">
                {letter.trim().split(/\s+/).filter(Boolean).length} words
                {saving && " · saving..."}
                {!saving && dirty && letterId && " · unsaved"}
              </span>

              <div className="ml-auto flex items-center gap-2">
                <button
                  onClick={() => handleExport("text")}
                  disabled={!letter.trim() || exporting}
                  className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50"
                >
                  <FileText className="w-4 h-4" />
                  .txt
                </button>
                <button
                  onClick={() => handleExport("pdf")}
                  disabled={!letter.trim() || exporting}
                  className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-blue-500 to-fuchsia-500 text-white px-5 py-2 text-sm font-medium shadow-lg shadow-purple-500/30 hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  <Download className="w-4 h-4" />
                  {exporting ? "Building..." : "Download PDF"}
                </button>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
