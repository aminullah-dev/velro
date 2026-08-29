import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  Empty, ErrorBanner, ErrorState, Loading, Ltr, PageHeader, Table,
} from "../components/ui";
import { useStrings } from "../i18n/strings";

interface Money {
  amount_minor: number;
  currency: string;
}

interface Settlement {
  id: string;
  reference: string;
  amount: Money;
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
  const { t, money, date } = useStrings();
  const client = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["settlements", "queue"],
    queryFn: () => api.get<Settlement[]>("/admin/settlements"),
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

  if (isLoading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;

  const queue = data ?? [];

  return (
    <>
      <PageHeader
        title={t("admin.nav.settlements")}
        subtitle={t("admin.settlements.queue")}
        actions={
          <button className="small" onClick={() => refetch()}>
            {t("admin.action.refresh")}
          </button>
        }
      />

      {decide.error && <ErrorBanner error={decide.error} />}

      {queue.length === 0 ? (
        <Empty messageKey="admin.settlements.none" />
      ) : (
        <Table
          head={
            <tr>
              <th>{t("admin.col.reference")}</th>
              <th>{t("admin.col.name")}</th>
              <th>{t("admin.col.period")}</th>
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
                    onClick={() => {
                      const reason = prompt(t("admin.settlements.reject_reason"), "");
                      if (!reason || !reason.trim()) return;
                      decide.mutate({ id: s.id, to: "REJECTED", reason: reason.trim() });
                    }}
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
