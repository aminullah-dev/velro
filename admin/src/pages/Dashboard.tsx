import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { api, ApiError } from "../api/client";
import { hasAnyRole, OPERATIONS_ROLES, useRoles } from "../api/roles";
import type { AppsReport, LiveMapSnapshot, WeekHistory } from "../api/operations";
import { AppVersions } from "../components/AppVersions";
import { gate } from "../components/gate";
import {
  ActionStat, ErrorBanner, Loading, MoneyStat, PageHeader, Section, Stat,
} from "../components/ui";
import { WeekCharts } from "../components/WeekCharts";
import { useStrings } from "../i18n/strings";

// MapLibre is most of this panel's weight -- more than everything else put
// together. Fetched with the map section rather than with the panel, so a
// slow connection gets the sign-in screen and the counters first, and every
// other page never downloads it at all.
const LiveMap = lazy(() =>
  import("../components/LiveMap").then((module) => ({ default: module.LiveMap })),
);

interface Snapshot {
  generated_at: string;
  live: { on_the_way: number; at_the_station: number; moving: number; departing_soon: number };
  attention: {
    unassigned_trips: number; departures_at_risk: number; overdue_trips: number;
    open_requests: number; unanswered_requests: number;
    pending_drivers: number; pending_vehicles: number; pending_documents: number;
    expiring_documents: number; open_tickets: number; stale_gps_drivers: number;
  };
  today: {
    trips: number; bookings: number; completed_trips: number; cancellations: number;
    seats_capacity: number; seats_sold: number; utilisation_percent: number | null;
  };
  capacity: { upcoming_trips: number; nearly_full_trips: number; empty_departures: number };
  drivers: {
    online: number; on_trip: number; offline: number; pending: number;
    suspended: number; total: number; without_fix: number;
  };
  finance: {
    currency: string; revenue_today_minor: number; commission_today_minor: number;
    driver_earnings_today_minor: number; cash_owed_minor: number;
    payouts_due_minor: number; settlements_open: number;
  };
  network: {
    routes_active: number; stations: number; villages: number;
    villages_without_coordinates: number; villages_without_stations: number;
    stations_without_routes: number; routes_without_upcoming_trips: number;
  };
  people: { passengers: number; drivers: number };
  // Optional: a server older than this panel sends neither, and the page
  // simply goes without those two sections.
  history?: WeekHistory;
  apps?: AppsReport;
  // Optional for the same reason: without it the dashboard keeps the single
  // passenger count it always had, under the drivers.
  passengers?: {
    total: number; new_today: number; new_7d: number;
    active_7d: number; active_30d: number; repeat_30d: number;
    suspended: number; with_open_request: number;
  };
}

/** A server older than this panel, which has no live map to give. */
function isMissing(error: unknown): boolean {
  return error instanceof ApiError && error.httpStatus === 404;
}

/**
 * A staff role the map is not for. The dashboard is open to every staff role
 * but the map is operations-only (names, phones and live positions), so a
 * finance manager or support agent gets 403 here -- an answer, not a fault:
 * asking again every half minute will not change it.
 */
function isForbidden(error: unknown): boolean {
  return error instanceof ApiError && error.httpStatus === 403;
}

function isSettled(error: unknown): boolean {
  return isMissing(error) || isForbidden(error);
}

/**
 * The operations centre, section 47.
 *
 * Four questions, in the order an operator asks them: what is happening
 * now, what needs me, how is today going, and is the network itself in
 * order. Every number that means "act" is a link to the filtered list it
 * was counted from -- the server counts and the list filters with the same
 * clauses, so the card is never a different number from the page it opens.
 *
 * Counts stay counts: a thing to act on in the next twenty minutes is better
 * read as a number. The map beside them answers "where", and the week under
 * today answers "is this normal", which no single day's count can -- both
 * are context for the numbers, never a replacement for them.
 */
export function DashboardPage() {
  const { t, num, dateTime, forErrorCode } = useStrings();
  // The dashboard is every staff role's; the passenger list and the live
  // requests are operations'. A card is only a link where the page it opens
  // would answer -- and, until the roles are known, it is not one yet.
  const canOperate = hasAnyRole(useRoles(), OPERATIONS_ROLES);
  const snapshotQuery = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<Snapshot>("/admin/dashboard"),
    // Left open on a screen all day. Half a minute is often enough to notice
    // a departure with nobody driving it before the passenger does.
    refetchInterval: 30_000,
  });
  // Its own query, so a map that fails leaves the counters standing, and the
  // same half minute, so the dots and the "on a trip" card never disagree for
  // long.
  const liveQuery = useQuery({
    queryKey: ["dashboard", "live-map"],
    queryFn: () => api.get<LiveMapSnapshot>("/admin/live-map"),
    refetchInterval: (query) => (isSettled(query.state.error) ? false : 30_000),
    // Asking an older server three more times will not grow it a live map,
    // and asking again will not grant a role.
    retry: (failures, error) => !isSettled(error) && failures < 3,
  });
  const { data } = snapshotQuery;

  const blocked = gate(snapshotQuery);
  if (blocked) return blocked;
  if (!data) return null;

  const a = data.attention;
  const needsAnyone =
    a.departures_at_risk + a.unassigned_trips + a.overdue_trips + a.unanswered_requests
    + a.stale_gps_drivers + a.pending_drivers + a.pending_vehicles + a.pending_documents
    + a.open_tickets + a.expiring_documents + data.finance.settlements_open > 0;

  return (
    <>
      <PageHeader
        title={t("admin.nav.dashboard")}
        subtitle={t("admin.ops.updated", { time: dateTime(data.generated_at) })}
        actions={
          <button className="small" onClick={() => snapshotQuery.refetch()}>
            {t("admin.action.refresh")}
          </button>
        }
      />

      <Section titleKey="admin.ops.now">
        <div className="grid stats">
          <ActionStat labelKey="admin.stat.on_the_way" value={data.live.on_the_way} to="/trips?active_only=1" />
          <ActionStat labelKey="admin.stat.at_the_station" value={data.live.at_the_station} to="/trips?active_only=1" />
          <ActionStat labelKey="admin.stat.moving" value={data.live.moving} to="/trips?active_only=1" />
          <ActionStat labelKey="admin.stat.departing_soon" value={data.live.departing_soon} to="/trips?departing_within_hours=2" />
        </div>
      </Section>

      <Section titleKey="admin.ops.live_map">
        {isMissing(liveQuery.error) ? (
          <p className="muted">{t("admin.map.not_supported")}</p>
        ) : isForbidden(liveQuery.error) ? (
          <p className="muted">{forErrorCode("PERMISSION_DENIED")}</p>
        ) : liveQuery.data ? (
          <>
            {/* Positions from the last good answer are still worth seeing,
                provided the screen says the answer is old: the banner does,
                and so does the time under the map. */}
            {(liveQuery.error || liveQuery.fetchStatus === "paused") && (
              <ErrorBanner error={liveQuery.error ?? liveQuery.failureReason} />
            )}
            <Suspense fallback={<Loading />}>
              <LiveMap snapshot={liveQuery.data} />
            </Suspense>
          </>
        ) : (
          gate(liveQuery)
        )}
      </Section>

      <Section titleKey="admin.ops.attention">
        {/* Order is urgency: the thing that strands a passenger in the next
            hour first, paperwork last. Nothing is hidden at zero -- the
            operator should be able to see that the queue is empty, not
            wonder whether the card failed to load. */}
        {!needsAnyone && <div className="banner info">{t("admin.ops.all_clear")}</div>}
        <div className="grid stats dense">
          <ActionStat labelKey="admin.stat.departures_at_risk" value={a.departures_at_risk} to="/dispatch" attention hintKey="admin.stat.at_risk_hint" />
          <ActionStat labelKey="admin.stat.unassigned" value={a.unassigned_trips} to="/dispatch" attention />
          <ActionStat labelKey="admin.stat.overdue" value={a.overdue_trips} to="/trips?overdue=1" attention hintKey="admin.stat.overdue_hint" />
          <ActionStat labelKey="admin.stat.unanswered_requests" value={a.unanswered_requests} to="/negotiations" attention />
          <ActionStat labelKey="admin.stat.open_requests" value={a.open_requests} to="/negotiations" />
          <ActionStat labelKey="admin.stat.stale_gps" value={a.stale_gps_drivers} to="/drivers?stale_gps=1" attention />
          <ActionStat labelKey="admin.stat.drivers_pending" value={a.pending_drivers} to="/approvals" attention />
          <ActionStat labelKey="admin.vehicles.pending" value={a.pending_vehicles} to="/vehicle-approvals" attention />
          <ActionStat labelKey="admin.stat.pending_documents" value={a.pending_documents} to="/approvals" attention />
          <ActionStat labelKey="admin.stat.open_tickets" value={a.open_tickets} to="/support" attention />
          <ActionStat labelKey="admin.stat.settlements_open" value={data.finance.settlements_open} to="/settlements" attention />
          <ActionStat labelKey="admin.stat.expiring_documents" value={a.expiring_documents} to="/drivers" />
        </div>
      </Section>

      <Section titleKey="admin.ops.today">
        <div className="grid stats">
          <ActionStat labelKey="admin.stat.trips_today" value={data.today.trips} to="/trips" />
          <Stat labelKey="admin.stat.bookings_today" value={num(data.today.bookings)} />
          <Stat labelKey="admin.stat.completed_today" value={num(data.today.completed_trips)} />
          <Stat labelKey="admin.stat.cancellations_today" value={num(data.today.cancellations)} />
          <Stat
            labelKey="admin.stat.utilisation"
            value={
              data.today.utilisation_percent === null
                ? "—"
                : `${num(data.today.seats_sold)} / ${num(data.today.seats_capacity)}`
            }
            note={
              data.today.utilisation_percent === null
                ? undefined
                : `${num(data.today.utilisation_percent)}٪`
            }
          />
          <ActionStat labelKey="admin.stat.nearly_full" value={data.capacity.nearly_full_trips} to="/trips?departing_within_hours=24" />
          <ActionStat labelKey="admin.stat.empty_departures" value={data.capacity.empty_departures} to="/trips?departing_within_hours=3" />
        </div>
      </Section>

      {data.history && data.history.days.length > 0 && (
        <Section titleKey="admin.ops.week">
          <WeekCharts history={data.history} />
        </Section>
      )}

      <Section titleKey="admin.nav.drivers">
        <div className="grid stats">
          <ActionStat labelKey="admin.stat.drivers_online" value={data.drivers.online} to="/drivers" />
          <ActionStat labelKey="admin.stat.drivers_on_trip" value={data.drivers.on_trip} to="/trips?active_only=1" />
          <Stat labelKey="admin.stat.drivers_offline" value={num(data.drivers.offline)} />
          <ActionStat labelKey="admin.stat.stale_gps" value={data.drivers.without_fix} to="/drivers?stale_gps=1" attention />
          <ActionStat labelKey="admin.stat.drivers_pending" value={data.drivers.pending} to="/approvals" attention />
          <Stat labelKey="admin.stat.drivers_suspended" value={num(data.drivers.suspended)} />
          {/* The one passenger count an older server gives. A newer one has
              a section of its own below, and a second, differently-counted
              "passengers" here would only invite the question of which is right. */}
          {!data.passengers && (
            <Stat labelKey="admin.stat.passengers" value={num(data.people.passengers)} />
          )}
        </div>
      </Section>

      {data.passengers && (
        <Section titleKey="admin.nav.passengers">
          {/* Who is counted, said once for every card below. Every account
              starts as a passenger, so without it "new today" reads as every
              sign-up -- drivers and staff included -- which it is not. */}
          <p className="section-note muted">{t("admin.passengers.only_note")}</p>
          {/* Growth first, then whether people come back, then what needs
              somebody: a suspended account is a decision to revisit, and a
              passenger with a request open is waiting right now. */}
          <div className="grid stats">
            {canOperate
              ? <ActionStat labelKey="admin.passengers.all" value={data.passengers.total} to="/passengers" />
              : <Stat labelKey="admin.passengers.all" value={num(data.passengers.total)} />}
            <Stat labelKey="admin.stat.passengers_new_today" value={num(data.passengers.new_today)} />
            <Stat labelKey="admin.stat.passengers_new_week" value={num(data.passengers.new_7d)} />
            <Stat labelKey="admin.stat.passengers_active_week" value={num(data.passengers.active_7d)} />
            <Stat labelKey="admin.stat.passengers_active_month" value={num(data.passengers.active_30d)} />
            <Stat labelKey="admin.stat.passengers_repeat" value={num(data.passengers.repeat_30d)} />
            {canOperate
              ? <ActionStat labelKey="admin.stat.passengers_with_request" value={data.passengers.with_open_request} to="/negotiations" />
              : <Stat labelKey="admin.stat.passengers_with_request" value={num(data.passengers.with_open_request)} />}
            {canOperate
              ? <ActionStat labelKey="admin.stat.passengers_suspended" value={data.passengers.suspended} to="/passengers?status=SUSPENDED" attention />
              : <Stat labelKey="admin.stat.passengers_suspended" value={num(data.passengers.suspended)} attention={data.passengers.suspended > 0} />}
          </div>
        </Section>
      )}

      <Section titleKey="admin.ops.money">
        <div className="grid stats">
          <MoneyStat labelKey="admin.stat.revenue_today" amountMinor={data.finance.revenue_today_minor} currency={data.finance.currency} />
          <MoneyStat labelKey="admin.stat.commission_today" amountMinor={data.finance.commission_today_minor} currency={data.finance.currency} />
          <MoneyStat labelKey="admin.stat.driver_earnings_today" amountMinor={data.finance.driver_earnings_today_minor} currency={data.finance.currency} />
          <MoneyStat labelKey="admin.stat.cash_owed" amountMinor={data.finance.cash_owed_minor} currency={data.finance.currency} />
          <MoneyStat labelKey="admin.finance.pending_settlement" amountMinor={data.finance.payouts_due_minor} currency={data.finance.currency} />
          <ActionStat labelKey="admin.stat.settlements_open" value={data.finance.settlements_open} to="/settlements" attention />
        </div>
      </Section>

      {data.apps && (
        <Section titleKey="admin.ops.app_versions">
          <AppVersions apps={data.apps} />
        </Section>
      )}

      <Section titleKey="admin.ops.network">
        <div className="grid stats">
          <ActionStat labelKey="admin.stat.routes_active" value={data.network.routes_active} to="/routes" />
          <ActionStat labelKey="admin.section.stations" value={data.network.stations} to="/locations" />
          <ActionStat labelKey="admin.section.villages" value={data.network.villages} to="/locations" />
          <ActionStat labelKey="admin.stat.villages_without_coordinates" value={data.network.villages_without_coordinates} to="/locations?without=coordinates" attention />
          <ActionStat labelKey="admin.stat.villages_without_stations" value={data.network.villages_without_stations} to="/locations?without=stations" attention />
          <ActionStat labelKey="admin.stat.stations_without_routes" value={data.network.stations_without_routes} to="/routes" attention />
          <ActionStat labelKey="admin.stat.routes_without_trips" value={data.network.routes_without_upcoming_trips} to="/routes" />
        </div>
      </Section>
    </>
  );
}
