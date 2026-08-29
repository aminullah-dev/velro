import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, query } from "../api/client";
import { ErrorState, Loading, MoneyStat, PageHeader, Stat } from "../components/ui";
import { useStrings } from "../i18n/strings";

interface Finance {
  period_start: string; period_end: string;
  gross_minor: number; platform_minor: number; driver_minor: number;
  currency: string; completed_bookings: number;
  cash_minor: number; online_minor: number;
  pending_settlement_minor: number; paid_settlement_minor: number;
}

export function FinancePage() {
  const { t, num } = useStrings();
  const [days, setDays] = useState(30);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["finance", days],
    queryFn: () => api.get<Finance>(`/admin/finance${query({ days })}`),
  });

  if (isLoading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!data) return null;

  return (
    <>
      <PageHeader
        title={t("admin.nav.finance")}
        subtitle={t("admin.finance.period", { days: num(days) })}
        actions={
          <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
            {[7, 30, 90, 365].map((option) => (
              <option key={option} value={option}>{num(option)}</option>
            ))}
          </select>
        }
      />

      <div className="grid stats">
        <MoneyStat labelKey="admin.finance.gross" amountMinor={data.gross_minor} />
        <MoneyStat labelKey="admin.finance.platform" amountMinor={data.platform_minor} />
        <MoneyStat labelKey="admin.finance.driver" amountMinor={data.driver_minor} />
        <Stat labelKey="admin.finance.bookings" value={num(data.completed_bookings)} />
      </div>

      <div className="grid stats" style={{ marginTop: "var(--s-4)" }}>
        <MoneyStat labelKey="admin.finance.cash" amountMinor={data.cash_minor} />
        <MoneyStat labelKey="admin.finance.online" amountMinor={data.online_minor} />
        <MoneyStat
          labelKey="admin.finance.pending_settlement"
          amountMinor={data.pending_settlement_minor}
        />
        <MoneyStat
          labelKey="admin.finance.paid_settlement"
          amountMinor={data.paid_settlement_minor}
        />
      </div>
    </>
  );
}
