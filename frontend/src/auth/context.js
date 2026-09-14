import { createContext, useContext } from "react";

/**
 * The auth context and its hook, kept apart from the provider component.
 *
 * Fast refresh only preserves state for files that export components alone, so
 * a hook living beside the provider quietly breaks hot reload during
 * development.
 */
export const AuthContext = createContext(null);

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used inside an AuthProvider");
  }
  return context;
}
