import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Empty, ErrorBanner, Ltr, PageHeader, Phone, Table, gate } from "../components/ui";
import { InputDialog } from "../components/InputDialog";
import { useStrings } from "../i18n/strings";

interface Money {
  amount_minor: number;
  currency: string;
}

interface Debtor {
  driver_id: string;
  driver_name: string | null;
  driver_phone: string | null;
  amount_owed: Money;
  completed_trips: number;
}

interface Settlement {
  id: string;
  reference: string;
  amount: Money;
  direction: "PAYOUT" | "COLLECTION";
  status: "PENDING" | "PROCESSING" | "PAID" | "REJECTED";
  period_start: string;
  period_end: string;
  paid_at: string | null;
  rejection_reason: string | null;
  driver_id: string;
  driver_name: string | null;
  driver_phone: string | null;
}

/**
 * The payout queue, section 88.
 *
 * Oldest first: this is the one list where waiting longest should mean being
 * served first. A driver's money is held against their request from the moment
 * they ask, so every row here is someone waiting to be paid.
 */
export function SettlementsPage() {
  const { t, money, date, num } = useStrings();
  const client = useQueryClient();
  // Which settlement is being refused, or null. Held here rather than in the
  // row so the dialog is not remounted as the queue refreshes underneath it.
  const [refusing, setRefusing] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["settlements", "queue"],
    queryFn: () => api.get<Settlement[]>("/admin/settlements"),
  });
  const { data } = listQuery;

  const { data: debtors } = useQuery({
    queryKey: ["settlements", "debtors"],
    queryFn: () => api.get<Debtor[]>("/admin/settlements/debtors"),
  });

  const collect = useMutation({
    mutationFn: (driverId: string) =>
      api.post("/admin/settlements/collect", { driver_id: driverId }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["settlements"] }),
  });

  const decide = useMutation({
    mutationFn: (input: { id: string; to: string; reason?: string }) =>
      api.post(`/admin/settlements/${input.id}/decide`, {
        to: input.to,
        reason: input.reason ?? null,
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["settlements"] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const blocked = gate(listQuery);
  if (blocked) return blocked;

  const queue = data ?? [];

  return (
    <>
      <PageHeader
        title={t("admin.nav.settlements")}
        subtitle={t("admin.settlements.queue")}
        actions={
          <button className="small" onClick={() => listQuery.refetch()}>
            {t("admin.action.refresh")}
          </button>
        }
      />

      {decide.error && <ErrorBanner error={decide.error} />}

      <InputDialog
        open={refusing !== null}
        titleKey="admin.settlements.reject_reason"
        confirmKey="admin.settlements.reject"
        onCancel={() => setRefusing(null)}
        onConfirm={(reason) => {
          if (refusing) decide.mutate({ id: refusing, to: "REJECTED", reason });
          setRefusing(null);
        }}
      />
      {collect.error && <ErrorBanner error={collect.error} />}

      {/* Cash fares mean drivers hold VELRO's share, so this is the ordinary
          working list rather than an exception report -- and it comes first
          because it is what an operator opens this page to do. */}
      <h2 className="section">{t("admin.settlements.debtors")}</h2>
      {(debtors ?? []).length === 0 ? (
        <Empty messageKey="admin.settlements.no_debtors" />
      ) : (
        <Table
          head={
            <tr>
              <th>{t("admin.col.name")}</th>
              <th className="num">{t("admin.col.trips")}</th>
              <th className="num">{t("admin.settlements.owed")}</th>
              <th>{t("admin.col.actions")}</th>
            </tr>
          }
        >
          {(debtors ?? []).map((d) => (
            <tr key={d.driver_id}>
              <td>
                <div>{d.driver_name ?? "—"}</div>
                {d.driver_phone && (
                  <span style={{ fontSize: 12 }}>
                    {/* Dialable: this is the table an operator works through
                        when cash is owed, and every row ends in a phone call. */}
                    <Phone number={d.driver_phone} />
                  </span>
                )}
              </td>
              <td className="num">{num(d.completed_trips)}</td>
              <td className="num">
                {money(d.amount_owed.amount_minor, d.amount_owed.currency)}
              </td>
              <td>
                <button
                  className="small primary"
                  disabled={collect.isPending}
                  onClick={() => collect.mutate(d.driver_id)}
                >
                  {t("admin.settlements.collect")}
                </button>
              </td>
            </tr>
          ))}
        </Table>
      )}

      <h2 className="section">{t("admin.settlements.queue")}</h2>

      {queue.length === 0 ? (
        <Empty messageKey="admin.settlements.none" />
      ) : (
        <Table
          head={
            <tr>
              <th>{t("admin.col.reference")}</th>
              <th>{t("admin.col.name")}</th>
              <th>{t("admin.col.period")}</th>
              <th>{t("admin.col.direction")}</th>
              <th className="num">{t("admin.col.amount")}</th>
              <th>{t("admin.col.status")}</th>
              <th>{t("admin.col.actions")}</th>
            </tr>
          }
        >
          {queue.map((s) => (
            <tr key={s.id}>
              {/* A reference is quoted over the phone; never mirrored. */}
              <td><Ltr>{s.reference}</Ltr></td>
              <td>
                <div>{s.driver_name ?? "—"}</div>
                {s.driver_phone && (
                  <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                    <Ltr>{s.driver_phone}</Ltr>
                  </span>
                )}
              </td>
              <td style={{ fontSize: 12 }}>
                {date(s.period_start)} — {date(s.period_end)}
              </td>
              <td>
                {/* Which way the money moves is the first thing to read on a
                    payments queue; never left to the amount's sign. */}
                <span className="chip">
                  {t(`settlement.direction.${s.direction.toLowerCase()}`)}
                </span>
              </td>
              <td className="num">
                {money(s.amount.amount_minor, s.amount.currency)}
              </td>
              <td>
                <span
                  className={`chip ${s.status === "PROCESSING" ? "active" : "attention"}`}
                >
                  {t(`settlement.status.${s.status.toLowerCase()}`)}
                </span>
              </td>
              <td>
                <div className="row" style={{ gap: "var(--s-2)" }}>
                  {/* PENDING and PROCESSING offer different next steps: the
                      lifecycle refuses a jump straight to paid, so the UI
                      should not appear to offer one. */}
                  {s.status === "PENDING" && (
                    <button
                      className="small primary"
                      disabled={decide.isPending}
                      onClick={() => decide.mutate({ id: s.id, to: "PROCESSING" })}
                    >
                      {t("admin.settlements.start")}
                    </button>
                  )}
                  {s.status === "PROCESSING" && (
                    <button
                      className="small primary"
                      disabled={decide.isPending}
                      onClick={() => decide.mutate({ id: s.id, to: "PAID" })}
                    >
                      {t("admin.settlements.mark_paid")}
                    </button>
                  )}
                  <button
                    className="small danger"
                    disabled={decide.isPending}
                    onClick={() => setRefusing(s.id)}
                  >
                    {t("admin.settlements.reject")}
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
