import { useEffect, useState } from "react";
import { Check, Loader2 } from "lucide-react";

/**
 * Staged progress for the long operations in the pipeline.
 *
 * Resume extraction runs a 7B model locally and can take the better part of a
 * minute. A single indefinite spinner for that long reads as a hang, so this
 * shows which stage is running, how long it has been going, and roughly how
 * long it should take.
 *
 * The elapsed counter is deliberate: it is the honest thing to show when the
 * remaining time genuinely is not known.
 */
export default function StageProgress({ stages, current, hint, progress = null }) {
  // The tick carries the stage it was measured for, so a stage change resets
  // the reading immediately without writing state from the effect body.
  const [tick, setTick] = useState({ stage: current, seconds: 0 });

  useEffect(() => {
    const startedAt = Date.now();
    const timer = setInterval(
      () =>
        setTick({
          stage: current,
          seconds: Math.floor((Date.now() - startedAt) / 1000),
        }),
      1000
    );
    return () => clearInterval(timer);
  }, [current]);

  const elapsed = tick.stage === current ? tick.seconds : 0;

  const currentIndex = stages.findIndex((stage) => stage.key === current);

  return (
    <div className="flex flex-col items-center py-8">
      <div className="w-full max-w-sm space-y-3">
        {stages.map((stage, index) => {
          const isDone = index < currentIndex;
          const isActive = index === currentIndex;

          return (
            <div key={stage.key} className="flex items-center gap-3">
              <span
                className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center transition-colors ${
                  isDone
                    ? "bg-green-500"
                    : isActive
                    ? "bg-gradient-to-r from-blue-500 to-fuchsia-500"
                    : "bg-slate-200"
                }`}
              >
                {isDone ? (
                  <Check className="w-3.5 h-3.5 text-white" strokeWidth={3} />
                ) : isActive ? (
                  <Loader2 className="w-3.5 h-3.5 text-white animate-spin" />
                ) : (
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                )}
              </span>

              <span
                className={`text-sm transition-colors ${
                  isActive
                    ? "font-semibold text-slate-900"
                    : isDone
                    ? "text-slate-500"
                    : "text-slate-400"
                }`}
              >
                {stage.label}
              </span>

              {isActive && elapsed > 2 && (
                <span className="ml-auto text-xs tabular-nums text-slate-400">
                  {elapsed}s
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Determinate bar only where progress is genuinely known - during the
          file upload. Faking one for model inference would be a lie. */}
      {progress !== null && (
        <div className="w-full max-w-sm mt-6 h-1.5 rounded-full bg-slate-100 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-blue-500 to-fuchsia-500 transition-[width] duration-200"
            style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
          />
        </div>
      )}

      {hint && <p className="text-xs text-slate-400 mt-6 text-center px-6">{hint}</p>}
    </div>
  );
}
