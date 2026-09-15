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

export function isStaff(roles: readonly string[] | null | undefined): boolean {
  return (roles ?? []).some((role) => STAFF_ROLES.has(role));
}
