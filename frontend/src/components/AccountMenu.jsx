import { useState } from "react";
import { ChevronDown, Download, LogOut, Trash2, User } from "lucide-react";
import { deleteAccount, exportAccount } from "../api/account";
import { useAuth } from "../auth/context";
import ErrorNotice from "./ui/ErrorNotice";

/**
 * The signed-in menu, or a sign-in prompt for guests.
 *
 * Export and delete live here rather than buried in a settings page. Someone
 * who handed over their full employment history should not have to go looking
 * for the way to take it back or remove it.
 */

function DeleteConfirm({ onCancel, onDeleted }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const handleDelete = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await deleteAccount(password);
      onDeleted();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 px-4"
      onClick={() => !busy && onCancel()}
    >
      <form
        onClick={(event) => event.stopPropagation()}
        onSubmit={handleDelete}
        className="w-full max-w-md bg-white rounded-3xl shadow-2xl p-8"
      >
        <h2 className="text-xl font-bold text-slate-900">Delete your account?</h2>
        <p className="text-sm text-slate-600 mt-3 leading-relaxed">
          This removes your resume files, every profile extracted from them, and all
          your saved searches and analyses. It cannot be undone.
        </p>

        <label className="block mt-5">
          <span className="text-xs font-medium text-slate-500">
            Enter your password to confirm
          </span>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm outline-none focus:border-red-400 focus:ring-2 focus:ring-red-100"
          />
        </label>

        {error && <ErrorNotice error={error} compact className="mt-4" />}

        <div className="flex gap-3 mt-6">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="flex-1 rounded-full bg-slate-100 text-slate-700 py-2.5 text-sm font-medium hover:bg-slate-200 transition-colors"
          >
            Keep my account
          </button>
          <button
            type="submit"
            disabled={busy || !password}
            className="flex-1 rounded-full bg-red-600 text-white py-2.5 text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50"
          >
            {busy ? "Deleting..." : "Delete everything"}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function AccountMenu({ onRequestSignIn, onSignedOut }) {
  const { user, loading, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [error, setError] = useState(null);

  if (loading) return <div className="w-24 h-9" aria-hidden />;

  if (!user) {
    return (
      <button
        onClick={onRequestSignIn}
        className="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
      >
        Sign in
      </button>
    );
  }

  const handleExport = async () => {
    setOpen(false);
    setError(null);
    try {
      const data = await exportAccount();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "nexthire-data.json";
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((value) => !value)}
        className="inline-flex items-center gap-2 rounded-full border border-slate-200 pl-2 pr-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 transition-colors"
      >
        <span className="w-6 h-6 rounded-full bg-gradient-to-r from-blue-500 to-fuchsia-500 flex items-center justify-center">
          <User className="w-3.5 h-3.5 text-white" />
        </span>
        <span className="max-w-[10rem] truncate">{user.email}</span>
        <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-2 w-60 rounded-2xl border border-slate-100 bg-white shadow-xl p-2 z-20">
            <button
              onClick={handleExport}
              className="w-full flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm text-slate-700 hover:bg-slate-50 transition-colors"
            >
              <Download className="w-4 h-4 text-slate-400" />
              Download my data
            </button>
            <button
              onClick={async () => {
                setOpen(false);
                await signOut();
                onSignedOut?.();
              }}
              className="w-full flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm text-slate-700 hover:bg-slate-50 transition-colors"
            >
              <LogOut className="w-4 h-4 text-slate-400" />
              Sign out
            </button>
            <div className="h-px bg-slate-100 my-1" />
            <button
              onClick={() => {
                setOpen(false);
                setConfirmingDelete(true);
              }}
              className="w-full flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm text-red-600 hover:bg-red-50 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              Delete account
            </button>
          </div>
        </>
      )}

      {error && (
        <div className="absolute right-0 mt-2 w-72 z-20">
          <ErrorNotice error={error} compact onDismiss={() => setError(null)} />
        </div>
      )}

      {confirmingDelete && (
        <DeleteConfirm
          onCancel={() => setConfirmingDelete(false)}
          onDeleted={() => {
            setConfirmingDelete(false);
            onSignedOut?.();
          }}
        />
      )}
    </div>
  );
}
