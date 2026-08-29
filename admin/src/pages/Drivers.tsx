import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  Empty, ErrorBanner, ErrorState, Loading, Ltr, PageHeader, StatusChip, Table,
} from "../components/ui";
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
}

export function DriversPage() {
  const { t, num } = useStrings();
  const client = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["drivers"],
    queryFn: () => api.get<Driver[]>("/admin/drivers"),
  });

  const decide = useMutation({
    mutationFn: ({ id, action, reason }: { id: string; action: "approve" | "suspend"; reason?: string }) =>
      api.post(`/admin/drivers/${id}/${action}`, action === "suspend" ? { reason } : undefined),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["drivers"] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  if (isLoading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;

  const drivers = data ?? [];

  return (
    <>
      <PageHeader title={t("admin.nav.drivers")} />

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
              <th className="num">{t("admin.col.rating")}</th>
              <th className="num">{t("admin.col.trips")}</th>
              <th>{t("admin.col.actions")}</th>
            </tr>
          }
        >
          {drivers.map((driver) => (
            <tr key={driver.id}>
              <td>{driver.full_name ?? "—"}</td>
              <td><Ltr>{driver.phone}</Ltr></td>
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
