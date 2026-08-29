# ADR 0007 — A paused query is not an empty list

## Status
Accepted, 29 August 2026.

## Context
Every page in the panel guarded its list the same way:

```tsx
if (query.isLoading) return <Loading />;
if (query.error) return <ErrorState error={query.error} onRetry={refetch} />;
const rows = query.data ?? [];
```

That reads as complete. It is not. When a request fails and the connection looks
down, TanStack Query does not fail the query — it **pauses** it. The observed
state, captured from the running panel with the API stopped:

```
{ status: "pending", fetchStatus: "paused", isLoading: false,
  error: null, failureCount: 1,
  failureReason: "ApiError: INTERNAL_ERROR (HTTP 500)" }
```

`isLoading` is false because nothing is in flight. `error` is null because the
query has not given up. Both guards fall through, `data ?? []` yields an empty
array, and the operator is shown **«راننده‌ای در انتظار نیست»** — no drivers
waiting — when the panel cannot reach the server at all.

On a good connection that state is a blink. In Ghorband it is the normal case.
And "no drivers waiting" is the one answer that must never be a lie: an operator
who believes the queue is empty stops working.

This was found only because an unrelated 500 happened to be on screen. Sixteen
pages had the same hole.

## Decision
**One `gate(query)` helper decides what to render instead of a list**, and every
page that fetches calls it. It handles the paused state first, then errors, then
pending — and returns null when the page should carry on.

**Paused gets its own component, `OfflineState`, not `ErrorState`.** Nothing is
broken; the request is waiting for a connection. It shows the underlying
`failureReason` when there is one, so a 500 is not reported as "offline".

**Paused gets its own message.** The existing `common.state.offline` says
"showing saved information" — true in the apps, false here, where nothing is
shown. Telling an operator they are looking at cached data in front of a blank
screen is how "empty queue" gets believed. `common.state.unreachable` says the
list could not be loaded and is not empty.

**`scripts/check-query-gates.mjs` fails the build** if a page uses `useQuery`
without `gate`, or hand-rolls the old `isLoading` guard.

## Consequences
Pages keep the whole query object (`const listQuery = useQuery(...)`) rather
than destructuring `isLoading`/`error`/`refetch`. Slightly less tidy at the call
site, and it is what makes the paused state reachable at all.

The guard is a source scan, not a type. A page that invents a third way to
render a list would pass it. That is the cost of not having a test runner in the
panel; if one is added, this becomes a rendering test instead.

## Verified
Stopping the API and loading `/approvals` showed «راننده‌ای در انتظار نیست»
before the change and the unreachable-server message with a retry button after
it. The guard script fails when `gate` is removed from a page.
