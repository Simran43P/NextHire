import { useCallback, useEffect, useMemo, useState } from "react";
import * as accountApi from "../api/account";
import { AuthContext } from "./context";

/**
 * Who is signed in, if anyone.
 *
 * `user === null` is a real, settled answer meaning "browsing as a guest" -
 * distinct from `loading`, which means we have not asked the server yet. The
 * app must not flash a sign-in prompt at someone who is already signed in, so
 * nothing auth-dependent renders until that first check completes.
 */

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    (async () => {
      try {
        const data = await accountApi.fetchMe({ signal: controller.signal });
        if (!cancelled) setUser(data.user ?? null);
      } catch {
        // A guest, or the backend is down. Either way there is no session, and
        // the pipeline still works - so this is not worth surfacing as an error.
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, []);

  const signIn = useCallback(async (credentials) => {
    const data = await accountApi.login(credentials);
    setUser(data.user);
    return data;
  }, []);

  const signUp = useCallback(async (details) => {
    const data = await accountApi.register(details);
    setUser(data.user);
    return data;
  }, []);

  const signOut = useCallback(async () => {
    try {
      await accountApi.logout();
    } finally {
      // Even if the call fails, the local session is over as far as this tab
      // is concerned. Leaving the user "signed in" after they asked to leave
      // would be worse than a stale cookie.
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, loading, isAuthenticated: user !== null, signIn, signUp, signOut, setUser }),
    [user, loading, signIn, signUp, signOut]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
