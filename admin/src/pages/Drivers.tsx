import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api, query } from "../api/client";
import { Empty, ErrorBanner, Ltr, PageHeader, Phone, StatusChip, Table, gate } from "../components/ui";
import { useStrings } from "../i18n/strings";

interface Driver {
  id: string;
  user_id: string;
  full_name: string | null;
  phone: string;
  approval_status: string;
  availability: string;
  rating_average: number | null;
  rating_count: number;
  completed_trips: number;
  plate_number: string | null;
  vehicle_status: string | null;
  location_age_seconds: number | null;
}

export function DriversPage() {
  const { t, num } = useStrings();
  const client = useQueryClient();
  const [search, setSearch] = useSearchParams();
  // In the URL, so the dashboard's "without a fix" card opens exactly the
  // drivers it counted.
  const staleOnly = Boolean(search.get("stale_gps"));

  const listQuery = useQuery({
    queryKey: ["drivers", staleOnly],
    queryFn: () => api.get<Driver[]>(`/admin/drivers${query({ stale_gps: staleOnly })}`),
    refetchInterval: staleOnly ? 20_000 : false,
  });

  /** "3 min ago", "2 h ago", "4 days ago", or "never" -- a car the office
   * cannot place. Minutes past an hour read as hours, hours past a day as
   * days: "1585 min ago" is a number, not a fact anyone can use. */
  function lastSeen(seconds: number | null) {
    if (seconds === null) return <span className="muted">{t("common.value.never")}</span>;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return t("common.value.minutes_ago", { minutes: num(minutes) });
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return t("common.value.hours_ago", { hours: num(hours) });
    return t("common.value.days_ago", { days: num(Math.floor(hours / 24)) });
  }
  const { data } = listQuery;

  const decide = useMutation({
    mutationFn: ({ id, action, reason }: { id: string; action: "approve" | "suspend"; reason?: string }) =>
      api.post(`/admin/drivers/${id}/${action}`, action === "suspend" ? { reason } : undefined),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["drivers"] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const blocked = gate(listQuery);
  if (blocked) return blocked;

  const drivers = data ?? [];

  return (
    <>
      <PageHeader
        title={t("admin.nav.drivers")}
        actions={
          <label className="row" style={{ gap: "var(--s-2)" }}>
            <input
              type="checkbox"
              checked={staleOnly}
              style={{ minHeight: "auto" }}
              onChange={(event) =>
                setSearch(event.target.checked ? { stale_gps: "1" } : {})
              }
            />
            <span>{t("admin.filter.stale_gps")}</span>
          </label>
        }
      />

      {/* A refused approval or suspension is shown here rather than swallowed:
          the reason is usually actionable -- a missing licence, a driver
          mid-trip. */}
      {decide.error && <ErrorBanner error={decide.error} />}

      {drivers.length === 0 ? (
        <Empty messageKey="admin.empty.drivers" />
      ) : (
        <Table
          head={
            <tr>
              <th>{t("admin.col.name")}</th>
              <th>{t("admin.col.phone")}</th>
              <th>{t("admin.col.status")}</th>
              <th>{t("driver.status.online")}</th>
              <th>{t("admin.col.plate")}</th>
              <th>{t("admin.col.last_seen")}</th>
              <th className="num">{t("admin.col.rating")}</th>
              <th className="num">{t("admin.col.trips")}</th>
              <th>{t("admin.col.actions")}</th>
            </tr>
          }
        >
          {drivers.map((driver) => (
            <tr key={driver.id}>
              <td>{driver.full_name ?? t("common.value.no_name")}</td>
              <td><Phone number={driver.phone} /></td>
              <td><StatusChip status={driver.approval_status} kind="driver" /></td>
              <td>
                <span className={`chip ${driver.availability === "OFFLINE" ? "" : "active"}`}>
                  {t(
                    driver.availability === "OFFLINE"
                      ? "driver.status.offline"
                      : "driver.status.online",
                  )}
                </span>
              </td>
              <td>{driver.plate_number ? <Ltr>{driver.plate_number}</Ltr> : "—"}</td>
              <td>{lastSeen(driver.location_age_seconds)}</td>
              <td className="num">
                {driver.rating_average === null
                  ? "—"
                  : `★ ${num(driver.rating_average.toFixed(1))} (${num(driver.rating_count)})`}
              </td>
              <td className="num">{num(driver.completed_trips)}</td>
              <td>
                <div className="row" style={{ gap: "var(--s-2)" }}>
                  {driver.approval_status !== "APPROVED" && (
                    <button
                      className="small primary"
                      disabled={decide.isPending}
                      onClick={() => decide.mutate({ id: driver.id, action: "approve" })}
                    >
                      {t("admin.action.approve")}
                    </button>
                  )}
                  {driver.approval_status === "APPROVED" && (
                    <button
                      className="small danger"
                      disabled={decide.isPending}
                      onClick={() => {
                        if (!confirm(t("admin.confirm.suspend"))) return;
                        decide.mutate({ id: driver.id, action: "suspend" });
                      }}
                    >
                      {t("admin.action.suspend")}
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
