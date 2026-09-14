import { useState } from "react";
import { Loader2, Sparkles, X } from "lucide-react";
import { requestPasswordReset } from "../api/account";
import { useAuth } from "../auth/context";
import ErrorNotice from "./ui/ErrorNotice";

/**
 * Sign in, register, or start a password reset.
 *
 * When a guest opens this mid-pipeline, `carryover` holds the work they have
 * already done. Registering sends it along so it lands in the new account -
 * nobody should have to re-upload a resume as the price of signing up.
 */

const MODES = {
  signin: {
    title: "Welcome back",
    subtitle: "Sign in to pick up where you left off.",
    submit: "Sign in",
  },
  register: {
    title: "Create your account",
    subtitle: "Keep your profile, searches and analyses between visits.",
    submit: "Create account",
  },
  forgot: {
    title: "Reset your password",
    subtitle: "We will send a link to your email.",
    submit: "Send reset link",
  },
};

export default function AuthDialog({ open, onClose, initialMode = "signin", carryover = null }) {
  const { signIn, signUp } = useAuth();
  const [mode, setMode] = useState(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  if (!open) return null;

  const copy = MODES[mode];
  const hasCarryover = Boolean(carryover?.profile);

  const switchTo = (next) => {
    setMode(next);
    setError(null);
    setNotice(null);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (busy) return;

    setBusy(true);
    setError(null);
    setNotice(null);

    try {
      if (mode === "signin") {
        await signIn({ email, password });
        onClose?.({ signedIn: true });
      } else if (mode === "register") {
        const result = await signUp({ email, password, carryover });
        onClose?.({ signedIn: true, carried: result.carried ?? null });
      } else {
        const result = await requestPasswordReset(email);
        setNotice(result.message);
      }
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 px-4"
      onClick={() => !busy && onClose?.({ signedIn: false })}
    >
      <div
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-md bg-white rounded-3xl shadow-2xl p-8 relative"
      >
        <button
          type="button"
          onClick={() => !busy && onClose?.({ signedIn: false })}
          disabled={busy}
          aria-label="Close"
          className="absolute top-5 right-5 text-slate-400 hover:text-slate-600 disabled:opacity-30"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex flex-col items-center mb-6">
          <Sparkles className="w-7 h-7 text-blue-500" fill="currentColor" />
          <h2 className="text-2xl font-bold text-slate-900 mt-3">{copy.title}</h2>
          <p className="text-sm text-slate-500 text-center mt-1">{copy.subtitle}</p>
        </div>

        {hasCarryover && mode === "register" && (
          <div className="rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 mb-5">
            <p className="text-xs text-blue-900 leading-relaxed">
              The resume you just analysed will be saved to your new account. You will
              not need to upload it again.
            </p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="block">
            <span className="text-xs font-medium text-slate-500">Email</span>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
            />
          </label>

          {mode !== "forgot" && (
            <label className="block">
              <span className="text-xs font-medium text-slate-500">Password</span>
              <input
                type="password"
                required
                autoComplete={mode === "register" ? "new-password" : "current-password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              />
              {mode === "register" && (
                <span className="text-xs text-slate-400 mt-1 block">
                  At least 10 characters. Length beats punctuation.
                </span>
              )}
            </label>
          )}

          {error && <ErrorNotice error={error} compact onDismiss={() => setError(null)} />}

          {notice && (
            <div className="rounded-2xl border border-green-200 bg-green-50 px-4 py-3">
              <p className="text-xs text-green-900 leading-relaxed">{notice}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full inline-flex items-center justify-center gap-2 rounded-full bg-gradient-to-r from-blue-500 to-fuchsia-500 text-white px-6 py-3 text-sm font-medium shadow-lg shadow-purple-500/30 hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {busy && <Loader2 className="w-4 h-4 animate-spin" />}
            {copy.submit}
          </button>
        </form>

        <div className="text-center text-sm text-slate-500 mt-6 space-y-1">
          {mode === "signin" && (
            <>
              <p>
                No account?{" "}
                <button
                  onClick={() => switchTo("register")}
                  className="font-semibold text-blue-600 hover:text-blue-800"
                >
                  Create one
                </button>
              </p>
              <p>
                <button
                  onClick={() => switchTo("forgot")}
                  className="text-xs text-slate-400 hover:text-slate-600"
                >
                  Forgot your password?
                </button>
              </p>
            </>
          )}
          {mode === "register" && (
            <p>
              Already have an account?{" "}
              <button
                onClick={() => switchTo("signin")}
                className="font-semibold text-blue-600 hover:text-blue-800"
              >
                Sign in
              </button>
            </p>
          )}
          {mode === "forgot" && (
            <p>
              <button
                onClick={() => switchTo("signin")}
                className="font-semibold text-blue-600 hover:text-blue-800"
              >
                Back to sign in
              </button>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
