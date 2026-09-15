import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

/**
 * Who may use this panel at all.
 *
 * Checked twice: when a code is verified, and again whenever the panel opens
 * on a session it already holds. The second check is the one that matters
 * after a role is taken away -- the refresh token keeps working, because the
 * account is still a valid passenger, and without it the operator is shown
 * every page of the console and a 403 on each.
 */
export const STAFF_ROLES = new Set([
  "SUPER_ADMIN", "ADMIN", "OPERATIONS_MANAGER",
  "DISPATCHER", "FINANCE_MANAGER", "SUPPORT_AGENT",
]);

/**
 * The server's `require_operations`: who may look people up and switch their
 * accounts off. Mirrored rather than guessed, so the panel never offers a
 * page the server will refuse -- and never hides one it would serve.
 */
export const OPERATIONS_ROLES: ReadonlySet<string> = new Set([
  "SUPER_ADMIN", "ADMIN", "OPERATIONS_MANAGER", "DISPATCHER",
]);

/** The server's `require_support`: who may read the support queue. */
export const SUPPORT_ROLES: ReadonlySet<string> = new Set([
  "SUPER_ADMIN", "ADMIN", "SUPPORT_AGENT",
]);

export function hasAnyRole(
  roles: readonly string[] | null | undefined,
  allowed: ReadonlySet<string>,
): boolean {
  return (roles ?? []).some((role) => allowed.has(role));
}

export function isStaff(roles: readonly string[] | null | undefined): boolean {
  return hasAnyRole(roles, STAFF_ROLES);
}

/** One cache entry for "who is signed in", shared by the shell and the pages. */
export const ME_KEY = ["auth", "me"] as const;

export function fetchMe() {
  return api.get<{ roles: string[] }>("/auth/me");
}

/**
 * The signed-in operator's roles, or null while they are not yet known.
 *
 * Null is not "none": a caller deciding whether to *show* something should
 * treat it as "not yet decided", and one deciding whether to *ask the server*
 * for something the roles may forbid should wait for the answer.
 */
export function useRoles(enabled = true): readonly string[] | null {
  const me = useQuery({
    queryKey: ME_KEY,
    queryFn: fetchMe,
    enabled,
    staleTime: 5 * 60_000,
  });
  return me.data?.roles ?? null;
}
