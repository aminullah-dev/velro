import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  Empty, ErrorBanner, ErrorState, Loading, Ltr, PageHeader, Table,
} from "../components/ui";
import { InputDialog } from "../components/InputDialog";
import { useStrings } from "../i18n/strings";

interface PendingVehicle {
  id: string;
  vehicle_type_code: string;
  plate_number: string;
  seat_capacity: number;
  brand: string | null;
  model: string | null;
  year: number | null;
  colour: string | null;
  status: string;
  driver_id: string;
  driver_name: string | null;
  driver_phone: string;
  driver_approval_status: string;
}

/**
 * Vehicle activation, section 52.
 *
 * Separate from driver approval because they answer different questions: the
 * documents say the person may drive, this says the car may carry passengers.
 * A driver approved on documents alone still cannot work, and the driver
 * approval status is shown here so an operator can see which half is missing.
 */
export function VehicleApprovalsPage() {
  const { t, num } = useStrings();
  const client = useQueryClient();
  const [suspending, setSuspending] = useState<string | null>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["vehicles", "pending"],
    queryFn: () => api.get<PendingVehicle[]>("/admin/vehicles/pending"),
  });

  const decide = useMutation({
    mutationFn: (input: { id: string; approve: boolean; reason?: string }) =>
      api.post(`/admin/vehicles/${input.id}/decide`, {
        approve: input.approve,
        reason: input.reason ?? null,
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["vehicles"] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  if (isLoading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;

  const pending = data ?? [];

  return (
    <>
      <PageHeader
        title={t("admin.nav.vehicle_approvals")}
        subtitle={t("admin.vehicles.pending")}
        actions={
          <button className="small" onClick={() => refetch()}>
            {t("admin.action.refresh")}
          </button>
        }
      />

      {decide.error && <ErrorBanner error={decide.error} />}

      <InputDialog
        open={suspending !== null}
        titleKey="admin.vehicles.suspend_reason"
        confirmKey="admin.vehicles.suspend"
        onCancel={() => setSuspending(null)}
        onConfirm={(reason) => {
          if (suspending) decide.mutate({ id: suspending, approve: false, reason });
          setSuspending(null);
        }}
      />

      {pending.length === 0 ? (
        <Empty messageKey="admin.vehicles.none" />
      ) : (
        <Table
          head={
            <tr>
              <th>{t("admin.col.plate")}</th>
              <th>{t("admin.col.type")}</th>
              <th>{t("admin.col.name")}</th>
              <th className="num">{t("admin.col.capacity")}</th>
              <th>{t("admin.vehicles.driver_status")}</th>
              <th>{t("admin.col.actions")}</th>
            </tr>
          }
        >
          {pending.map((vehicle) => (
            <tr key={vehicle.id}>
              {/* Read off a physical car, so never mirrored. */}
              <td><Ltr>{vehicle.plate_number}</Ltr></td>
              <td>
                <span className="chip">
                  {t(`vehicle_type.${vehicle.vehicle_type_code.toLowerCase()}`)}
                </span>
              </td>
              <td>
                {[vehicle.brand, vehicle.model, vehicle.year ? num(vehicle.year) : null]
                  .filter(Boolean)
                  .join(" ") || "—"}
                {vehicle.colour && (
                  <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                    {" · "}{vehicle.colour}
                  </span>
                )}
              </td>
              <td className="num">{num(vehicle.seat_capacity)}</td>
              <td>
                <div>{vehicle.driver_name ?? <Ltr>{vehicle.driver_phone}</Ltr>}</div>
                {/* Which half is still missing: documents, or the car. */}
                <span
                  className={`chip ${
                    vehicle.driver_approval_status === "APPROVED" ? "active" : "attention"
                  }`}
                >
                  {t(`driver.approval.${vehicle.driver_approval_status.toLowerCase()}`)}
                </span>
              </td>
              <td>
                <div className="row" style={{ gap: "var(--s-2)" }}>
                  <button
                    className="small primary"
                    disabled={decide.isPending}
                    onClick={() => decide.mutate({ id: vehicle.id, approve: true })}
                  >
                    {t("admin.vehicles.activate")}
                  </button>
                  <button
                    className="small danger"
                    disabled={decide.isPending}
                    onClick={() => setSuspending(vehicle.id)}
                  >
                    {t("admin.vehicles.suspend")}
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
