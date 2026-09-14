// Accounts: who you are, and what you can take away or delete.

import { getJson, postJson } from "./client";

export function fetchMe(options = {}) {
  return getJson("/auth/me", options);
}

/**
 * Register.
 *
 * `carryover` is the work a guest did before signing up - their extracted
 * profile and the resume text behind it. Passing it means the pipeline they
 * just completed follows them into the account instead of being discarded,
 * which is the difference between signing up and starting over.
 */
export function register({ email, password, displayName = "", carryover = null }) {
  return postJson("/auth/register", {
    email,
    password,
    display_name: displayName,
    carryover: carryover
      ? {
          profile: carryover.profile,
          gaps: carryover.gaps ?? [],
          raw_text: carryover.rawText ?? "",
          filename: carryover.filename ?? "",
        }
      : null,
  });
}

export function login({ email, password }) {
  return postJson("/auth/login", { email, password });
}

export function logout() {
  return postJson("/auth/logout", {});
}

export function requestPasswordReset(email) {
  return postJson("/auth/forgot-password", { email });
}

export function resetPassword({ token, password }) {
  return postJson("/auth/reset-password", { token, password });
}

export function exportAccount() {
  return getJson("/account/export");
}

export function deleteAccount(password) {
  return postJson("/account/delete", { password });
}
