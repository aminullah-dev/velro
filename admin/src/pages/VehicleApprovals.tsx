import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Empty, ErrorBanner, Ltr, PageHeader, Table, gate } from "../components/ui";
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
  const [inspecting, setInspecting] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["vehicles", "pending"],
    queryFn: () => api.get<PendingVehicle[]>("/admin/vehicles/pending"),
  });
  const { data } = listQuery;

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

  const blocked = gate(listQuery);
  if (blocked) return blocked;

  const pending = data ?? [];

  return (
    <>
      <PageHeader
        title={t("admin.nav.vehicle_approvals")}
        subtitle={t("admin.vehicles.pending")}
        actions={
          <button className="small" onClick={() => listQuery.refetch()}>
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
                    className="small"
                    onClick={() =>
                      setInspecting(inspecting === vehicle.id ? null : vehicle.id)
                    }
                  >
                    {t("vehicle.documents.title")}
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

      {/* The car's own papers. Activation is refused without them, so an
          operator who cannot see them here would be clicking a button that
          fails for a reason the screen never showed. */}
      {inspecting && <VehiclePapers vehicleId={inspecting} />}
    </>
  );
}

interface VehicleDocument {
  id: string;
  vehicle_id: string;
  document_type_code: string;
  status: string;
  expires_on: string | null;
  rejection_reason: string | null;
  uploaded_at: string;
  is_current: boolean;
}

interface VehicleChecklist {
  vehicle_id: string;
  plate_number: string;
  required: string[];
  missing: string[];
  documents: VehicleDocument[];
  vehicle_status: string;
  can_carry: boolean;
}

function VehiclePapers({ vehicleId }: { vehicleId: string }) {
  const { t, date, dateTime } = useStrings();
  const client = useQueryClient();
  const [rejecting, setRejecting] = useState<string | null>(null);

  const papersQuery = useQuery({
    queryKey: ["vehicle-documents", vehicleId],
    queryFn: () => api.get<VehicleChecklist>(`/admin/vehicles/${vehicleId}/documents`),
  });

  const review = useMutation({
    mutationFn: (input: { id: string; verified: boolean; reason?: string }) =>
      api.post(`/admin/vehicle-documents/${input.id}/review`, {
        verified: input.verified,
        rejection_reason: input.reason ?? null,
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["vehicle-documents", vehicleId] });
      client.invalidateQueries({ queryKey: ["vehicles"] });
    },
  });

  const blocked = gate(papersQuery);
  if (blocked) return blocked;

  const papers = papersQuery.data;
  if (!papers) return null;

  return (
    <div className="card" style={{ marginBlockStart: "var(--s-4)" }}>
      <div className="row" style={{ marginBlockEnd: "var(--s-3)" }}>
        <strong>{t("vehicle.documents.title")}</strong>
        <Ltr>{papers.plate_number}</Ltr>
      </div>

      {review.error && <ErrorBanner error={review.error} />}

      <InputDialog
        open={rejecting !== null}
        titleKey="admin.approvals.reject_reason"
        confirmKey="admin.approvals.reject"
        hintKey="admin.approvals.reject_hint"
        onCancel={() => setRejecting(null)}
        onConfirm={(reason) => {
          if (rejecting) review.mutate({ id: rejecting, verified: false, reason });
          setRejecting(null);
        }}
      />

      <Table
        head={
          <tr>
            <th>{t("admin.col.type")}</th>
            <th>{t("admin.col.status")}</th>
            <th>{t("admin.approvals.uploaded")}</th>
            <th>{t("admin.col.expires")}</th>
            <th>{t("admin.col.actions")}</th>
          </tr>
        }
      >
        {papers.required.map((code) => {
          const document = papers.documents.find(
            (d) => d.document_type_code === code && d.is_current,
          );
          return (
            <tr key={code}>
              <td>{t(`document.type.${code.toLowerCase()}`)}</td>
              <td>
                <span
                  className={`chip ${
                    document?.status === "VERIFIED" ? "active"
                    : document?.status === "PENDING" ? "attention"
                    : "failed"
                  }`}
                >
                  {document
                    ? t(`document.status.${document.status.toLowerCase()}`)
                    : t("driver.documents.not_sent")}
                </span>
              </td>
              <td>{document ? dateTime(document.uploaded_at) : "—"}</td>
              <td>{document?.expires_on ? date(document.expires_on) : "—"}</td>
              <td>
                {document && (
                  <div className="row" style={{ gap: "var(--s-2)" }}>
                    <a
                      className="small"
                      href={`/api/v1/admin/vehicle-documents/${document.id}/file`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {t("admin.approvals.view")}
                    </a>
                    <button
                      className="small primary"
                      disabled={review.isPending}
                      onClick={() => review.mutate({ id: document.id, verified: true })}
                    >
                      {t("admin.approvals.verify")}
                    </button>
                    <button
                      className="small danger"
                      disabled={review.isPending}
                      onClick={() => setRejecting(document.id)}
                    >
                      {t("admin.approvals.reject")}
                    </button>
                  </div>
                )}
              </td>
            </tr>
          );
        })}
      </Table>

      {papers.missing.length > 0 && (
        <p style={{ color: "var(--text-muted)", marginBlockStart: "var(--s-3)" }}>
          {t("admin.approvals.still_missing", {
            list: papers.missing
              .map((code) => t(`document.type.${code.toLowerCase()}`))
              .join("، "),
          })}
        </p>
      )}
    </div>
  );
}
