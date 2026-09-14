import { AlertTriangle, RefreshCw } from "lucide-react";

/**
 * Inline failure notice.
 *
 * Replaces the browser `alert()` the job search used to throw. An alert blocks
 * the page, cannot be styled, cannot be retried from, and tells the user
 * nothing about whether trying again is worth it - which the backend does say.
 *
 * A retry button appears only when the failure is actually retryable. Offering
 * "try again" on a file that is too large just wastes the user's time.
 */
export default function ErrorNotice({
  error,
  onRetry,
  onDismiss,
  className = "",
  compact = false,
}) {
  if (!error) return null;

  const message =
    typeof error === "string"
      ? error
      : error.message || "Something went wrong. Please try again.";
  const canRetry = Boolean(onRetry) && (typeof error === "string" || error.retryable !== false);

  return (
    <div
      role="alert"
      className={`flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 ${
        compact ? "px-3 py-2.5" : "px-4 py-3.5"
      } ${className}`}
    >
      <AlertTriangle
        className={`${compact ? "w-4 h-4 mt-0.5" : "w-5 h-5 mt-0.5"} flex-shrink-0 text-red-500`}
        strokeWidth={2}
      />

      <div className="min-w-0 flex-1">
        <p className={`${compact ? "text-xs" : "text-sm"} text-red-800 leading-relaxed`}>
          {message}
        </p>

        {(canRetry || onDismiss) && (
          <div className="flex items-center gap-4 mt-2">
            {canRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-red-700 hover:text-red-900 transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Try again
              </button>
            )}
            {onDismiss && (
              <button
                type="button"
                onClick={onDismiss}
                className="text-xs font-medium text-red-600/80 hover:text-red-800 transition-colors"
              >
                Dismiss
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Non-blocking advisory - used for partial results, mock-data notices, and
 * quota warnings. The search still worked; the user just needs to know
 * something about what they are looking at.
 */
export function WarningNotice({ messages, className = "" }) {
  const list = (Array.isArray(messages) ? messages : [messages]).filter(Boolean);
  if (list.length === 0) return null;

  return (
    <div
      className={`rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 ${className}`}
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0 text-amber-500" />
        <div className="min-w-0 space-y-1">
          {list.map((message) => (
            <p key={message} className="text-xs text-amber-800 leading-relaxed">
              {message}
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}
