import type { ReactNode } from "react";
import { ErrorState, Loading, OfflineState } from "./ui";

/**
 * What to render instead of a list, if anything.
 *
 * Every page used to write this itself:
 *
 *     if (query.isLoading) return <Loading />;
 *     if (query.error) return <ErrorState ... />;
 *
 * which is wrong in a way that only shows up in the field. When a request
 * fails and the connection looks down, TanStack Query *pauses* the query
 * rather than failing it: `status` stays "pending", `error` stays null, and
 * `isLoading` goes false because nothing is in flight. Both guards are false,
 * the page falls through to `data ?? []`, and the operator is told there are
 * no drivers waiting -- when in fact the panel cannot reach the server at all.
 *
 * On a good connection that state is a blink. In Ghorband it is the normal
 * case, and "no drivers waiting" is the one answer that must never be a lie:
 * an operator who believes the queue is empty stops working.
 *
 * Returns a node to render in place of the page, or null to carry on. A
 * function rather than a component, so it lives outside `ui.tsx`: a module
 * that exports both loses React Fast Refresh.
 */
export function gate(
  query: {
    isPending: boolean;
    fetchStatus: "fetching" | "paused" | "idle";
    error: unknown;
    failureReason?: unknown;
    refetch: () => unknown;
  },
): ReactNode {
  if (query.fetchStatus === "paused") {
    // failureReason carries the error that caused the pause; without it the
    // operator gets "offline" even when the server answered with a 500.
    return (
      <OfflineState
        error={query.failureReason}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  if (query.error) {
    return (
      <ErrorState
        error={query.error}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  if (query.isPending) return <Loading />;
  return null;
}
