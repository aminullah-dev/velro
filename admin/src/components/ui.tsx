/**
 * The shared pieces every page is built from.
 *
 * Each one takes props and renders; none fetches. Every list has the loading,
 * empty and error state it needs, because a page that only handles the happy
 * path is a page that shows a blank rectangle in the field.
 */
import type { ReactNode } from "react";
import { ApiError } from "../api/client";
import { useStrings } from "../i18n/strings";

export function PageHeader({ title, subtitle, actions }: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-sub">{subtitle}</p>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </div>
  );
}

export function Loading() {
  const { t } = useStrings();
  return <div className="state">{t("common.state.loading")}</div>;
}

export function Empty({ messageKey }: { messageKey: string }) {
  const { t } = useStrings();
  return <div className="state">{t(messageKey)}</div>;
}

/**
 * A failure an operator can act on.
 *
 * Takes the error, not a message: the sentence is resolved from the code in the
 * locale being read. The request id is shown for anything unexpected, because
 * it is the first thing support will ask for.
 */
export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t, forErrorCode } = useStrings();
  const apiError = error instanceof ApiError ? error : null;

  return (
    <div className="state">
      <div className="headline">
        {apiError
          ? forErrorCode(apiError.code, apiError.context)
          : t("error.internal_error")}
      </div>
      {apiError?.requestId && (
        <div className="ltr tabular" style={{ fontSize: 12, marginBottom: 12 }}>
          {apiError.requestId}
        </div>
      )}
      {onRetry && <button onClick={onRetry}>{t("common.action.retry")}</button>}
    </div>
  );
}

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
 * Returns a node to render in place of the page, or null to carry on.
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

/**
 * The panel cannot reach the server, and has not given up.
 *
 * Distinct from ErrorState on purpose: nothing is broken, the request is
 * waiting for a connection, and saying so is what stops an operator from
 * reading an empty screen as an empty queue.
 */
export function OfflineState({ error, onRetry }: { error?: unknown; onRetry?: () => void }) {
  const { t, forErrorCode } = useStrings();
  const apiError = error instanceof ApiError ? error : null;
  return (
    <div className="state">
      {/* Not common.state.offline: that one says saved information is being
          shown, which is true in the apps and false here -- nothing is shown
          at all. Telling an operator they are looking at cached data when the
          screen is blank is how "empty queue" gets believed. */}
      <div className="headline">{t("common.state.unreachable")}</div>
      <div style={{ fontSize: 13, marginBottom: 12 }}>
        {apiError && apiError.code !== "NETWORK_OFFLINE"
          ? forErrorCode(apiError.code, apiError.context)
          : t("common.state.unreachable_hint")}
      </div>
      {onRetry && <button onClick={onRetry}>{t("common.action.retry")}</button>}
    </div>
  );
}

export function ErrorBanner({ error }: { error: unknown }) {
  const { t, forErrorCode } = useStrings();
  const apiError = error instanceof ApiError ? error : null;
  return (
    <div className="banner error">
      {apiError ? forErrorCode(apiError.code, apiError.context) : t("error.internal_error")}
    </div>
  );
}

type Tone = "neutral" | "active" | "attention" | "ended" | "failed";

const TRIP_TONES: Record<string, Tone> = {
  SCHEDULED: "neutral", REQUESTED: "neutral",
  DRIVER_ASSIGNED: "active", DRIVER_ARRIVING: "active",
  ARRIVED_AT_PICKUP: "active", BOARDING: "active",
  IN_TRANSIT: "active", ARRIVED: "active",
  COMPLETED: "ended",
  CANCELLED: "failed", EXPIRED: "failed", NO_DRIVER_AVAILABLE: "failed",
};

const BOOKING_TONES: Record<string, Tone> = {
  PENDING: "neutral", CONFIRMED: "active", DRIVER_ASSIGNED: "active",
  READY: "attention", ONBOARD: "attention",
  COMPLETED: "ended", CANCELLED: "failed", NO_SHOW: "failed",
};

const DRIVER_TONES: Record<string, Tone> = {
  APPROVED: "active", PENDING: "attention",
  REJECTED: "failed", SUSPENDED: "failed",
};

/**
 * A status, rendered from its key.
 *
 * The word is always present; colour never carries the meaning alone.
 */
export function StatusChip({ status, kind }: {
  status: string;
  kind: "trip" | "booking" | "driver" | "plain";
}) {
  const { t } = useStrings();
  const tones =
    kind === "trip" ? TRIP_TONES : kind === "booking" ? BOOKING_TONES : DRIVER_TONES;
  const tone: Tone = kind === "plain" ? "neutral" : (tones[status] ?? "neutral");

  const key =
    kind === "trip" ? `trip.status.${status.toLowerCase()}`
    : kind === "booking" ? `booking.status.${status.toLowerCase()}`
    : kind === "driver" ? `driver.approval.${status.toLowerCase()}`
    : null;
  // A missing key falls back to the raw value rather than a blank chip -- an
  // untranslated status is a visible bug, an empty one is a mystery.
  const label = key ? t(key) : status;

  return <span className={`chip ${tone}`}>{label === key ? status : label}</span>;
}

export function Table({ head, children }: { head: ReactNode; children: ReactNode }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>{head}</thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Pager({ total, limit, offset, onChange }: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  const { t, num } = useStrings();
  if (total <= limit) return null;

  const from = offset + 1;
  const to = Math.min(offset + limit, total);

  return (
    <div className="row" style={{ marginTop: "var(--s-4)" }}>
      <span style={{ color: "var(--text-muted)", fontSize: 13 }}>
        {t("admin.showing", { from: num(from), to: num(to), total: num(total) })}
      </span>
      <div className="spacer" />
      <button
        className="small"
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - limit))}
      >
        {t("admin.action.previous")}
      </button>
      <button className="small" disabled={to >= total} onClick={() => onChange(offset + limit)}>
        {t("admin.action.next")}
      </button>
    </div>
  );
}

export function Stat({ labelKey, value, note, attention }: {
  labelKey: string;
  value: string;
  note?: string;
  attention?: boolean;
}) {
  const { t } = useStrings();
  return (
    <div className="card">
      <div className="stat-label">{t(labelKey)}</div>
      <div className={`stat-value${attention ? " attention" : ""}`}>{value}</div>
      {note && <div className="stat-note">{note}</div>}
    </div>
  );
}

export function MoneyStat({ labelKey, amountMinor, currency }: {
  labelKey: string;
  amountMinor: number;
  currency?: string;
}) {
  const { t, money } = useStrings();
  return (
    <div className="card">
      <div className="stat-label">{t(labelKey)}</div>
      <div className="stat-value money">{money(amountMinor, currency)}</div>
    </div>
  );
}

/** Latin text inside RTL prose: plates, phone numbers, business numbers. */
export function Ltr({ children }: { children: ReactNode }) {
  return <span className="ltr tabular">{children}</span>;
}
