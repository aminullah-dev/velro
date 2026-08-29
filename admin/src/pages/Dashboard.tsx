import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { MoneyStat, PageHeader, Stat, gate } from "../components/ui";
import { useStrings } from "../i18n/strings";

interface Dashboard {
  active_trips: number;
  trips_today: number;
  bookings_today: number;
  passengers: number;
  drivers_total: number;
  drivers_pending: number;
  drivers_online: number;
  vehicles: number;
  revenue_today_minor: number;
  commission_today_minor: number;
  driver_earnings_today_minor: number;
  currency: string;
  cancellations_today: number;
  unassigned_trips: number;
}

export function DashboardPage() {
  const { t, num } = useStrings();
  const listQuery = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<Dashboard>("/admin/dashboard"),
    // The operator leaves this open on a screen; a minute is often enough to
    // notice a trip with nobody driving it.
    refetchInterval: 60_000,
  });
  const { data } = listQuery;

  const blocked = gate(listQuery);
  if (blocked) return blocked;
  if (!data) return null;

  return (
    <>
      <PageHeader
        title={t("admin.nav.dashboard")}
        actions={
          <button className="small" onClick={() => listQuery.refetch()}>
            {t("admin.action.refresh")}
          </button>
        }
      />

      <div className="grid stats">
        <Stat labelKey="admin.stat.active_trips" value={num(data.active_trips)} />
        <Stat
          labelKey="admin.stat.unassigned"
          value={num(data.unassigned_trips)}
          // The one number on this screen that means someone has to act.
          attention={data.unassigned_trips > 0}
        />
        <Stat labelKey="admin.stat.trips_today" value={num(data.trips_today)} />
        <Stat labelKey="admin.stat.bookings_today" value={num(data.bookings_today)} />
      </div>

      <div className="grid stats" style={{ marginTop: "var(--s-4)" }}>
        <MoneyStat
          labelKey="admin.stat.revenue_today"
          amountMinor={data.revenue_today_minor}
          currency={data.currency}
        />
        <MoneyStat
          labelKey="admin.stat.commission_today"
          amountMinor={data.commission_today_minor}
          currency={data.currency}
        />
        <MoneyStat
          labelKey="admin.stat.driver_earnings_today"
          amountMinor={data.driver_earnings_today_minor}
          currency={data.currency}
        />
        <Stat labelKey="admin.stat.cancellations_today" value={num(data.cancellations_today)} />
      </div>

      <div className="grid stats" style={{ marginTop: "var(--s-4)" }}>
        <Stat labelKey="admin.stat.drivers" value={num(data.drivers_total)} />
        <Stat labelKey="admin.stat.drivers_online" value={num(data.drivers_online)} />
        <Stat
          labelKey="admin.stat.drivers_pending"
          value={num(data.drivers_pending)}
          attention={data.drivers_pending > 0}
        />
        <Stat labelKey="admin.stat.vehicles" value={num(data.vehicles)} />
        <Stat labelKey="admin.stat.passengers" value={num(data.passengers)} />
      </div>
    </>
  );
}
