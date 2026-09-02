import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  ActionStat, MoneyStat, PageHeader, Section, Stat, gate,
} from "../components/ui";
import { useStrings } from "../i18n/strings";

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
 * No charts. A count that has to be acted on in the next twenty minutes is
 * better read as a count; a trend is a question for the finance page.
 */
export function DashboardPage() {
  const { t, num, dateTime } = useStrings();
  const snapshotQuery = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<Snapshot>("/admin/dashboard"),
    // Left open on a screen all day. Half a minute is often enough to notice
    // a departure with nobody driving it before the passenger does.
    refetchInterval: 30_000,
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

      <Section titleKey="admin.nav.drivers">
        <div className="grid stats">
          <ActionStat labelKey="admin.stat.drivers_online" value={data.drivers.online} to="/drivers" />
          <ActionStat labelKey="admin.stat.drivers_on_trip" value={data.drivers.on_trip} to="/trips?active_only=1" />
          <Stat labelKey="admin.stat.drivers_offline" value={num(data.drivers.offline)} />
          <ActionStat labelKey="admin.stat.stale_gps" value={data.drivers.without_fix} to="/drivers?stale_gps=1" attention />
          <ActionStat labelKey="admin.stat.drivers_pending" value={data.drivers.pending} to="/approvals" attention />
          <Stat labelKey="admin.stat.drivers_suspended" value={num(data.drivers.suspended)} />
          <Stat labelKey="admin.stat.passengers" value={num(data.people.passengers)} />
        </div>
      </Section>

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
