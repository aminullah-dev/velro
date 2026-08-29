import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Empty, ErrorState, Loading, Ltr, PageHeader, Table } from "../components/ui";
import { useStrings } from "../i18n/strings";

interface Money {
  amount_minor: number;
  currency: string;
}

interface Offer {
  id: string;
  amount: Money;
  driver_name: string | null;
  driver_rating: number | null;
  vehicle_plate: string | null;
}

interface RideRequest {
  id: string;
  status: string;
  origin_station_name: string | null;
  destination_name: string | null;
  passenger_count: number;
  offered_fare: Money;
  passenger_name: string | null;
  passenger_phone: string | null;
  offer_count: number;
  offers: Offer[];
  created_at: string;
  note: string | null;
}

/**
 * Live negotiations, section 89.
 *
 * Read only, and deliberately so: the fare is agreed between the passenger and
 * the driver, and an operator who could change it would be a third party to a
 * private agreement. What support needs is to see whether anyone has answered
 * someone who rings to say nobody will take them.
 */
export function NegotiationsPage() {
  const { t, money, num, dateTime } = useStrings();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["negotiations"],
    queryFn: () => api.get<RideRequest[]>("/admin/ride-requests"),
    // These change by the minute; an operator on the phone needs what is true
    // now, not what was true when they opened the page.
    refetchInterval: 15_000,
  });

  if (isLoading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;

  const rows = data ?? [];

  return (
    <>
      <PageHeader
        title={t("admin.nav.negotiations")}
        subtitle={t("admin.negotiations.readonly")}
        actions={
          <button className="small" onClick={() => refetch()}>
            {t("admin.action.refresh")}
          </button>
        }
      />

      {rows.length === 0 ? (
        <Empty messageKey="admin.negotiations.none" />
      ) : (
        <Table
          head={
            <tr>
              <th>{t("admin.col.passenger")}</th>
              <th>{t("admin.col.route")}</th>
              <th className="num">{t("admin.negotiations.asking")}</th>
              <th>{t("admin.negotiations.offers")}</th>
              <th>{t("admin.col.waiting")}</th>
            </tr>
          }
        >
          {rows.map((row) => (
            <tr key={row.id}>
              <td>
                <div>{row.passenger_name ?? "—"}</div>
                {row.passenger_phone && (
                  <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                    <Ltr>{row.passenger_phone}</Ltr>
                  </span>
                )}
              </td>
              <td>
                <div>
                  {row.origin_station_name ?? "—"} — {row.destination_name ?? "—"}
                </div>
                <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                  {num(row.passenger_count)}
                  {row.note ? ` · ${row.note}` : ""}
                </span>
              </td>
              <td className="num">
                {money(row.offered_fare.amount_minor, row.offered_fare.currency)}
              </td>
              <td>
                {/* Nobody answering is the thing support is usually being
                    asked about, so it says so rather than showing an empty
                    cell that could mean anything. */}
                {row.offer_count === 0 ? (
                  <span className="chip attention">
                    {t("admin.negotiations.no_offers")}
                  </span>
                ) : (
                  <div className="col" style={{ gap: 2 }}>
                    {row.offers.map((offer) => (
                      <span key={offer.id} style={{ fontSize: 13 }}>
                        {money(offer.amount.amount_minor, offer.amount.currency)}
                        {offer.driver_name ? ` · ${offer.driver_name}` : ""}
                        {offer.vehicle_plate ? " · " : ""}
                        {offer.vehicle_plate && <Ltr>{offer.vehicle_plate}</Ltr>}
                      </span>
                    ))}
                  </div>
                )}
              </td>
              <td style={{ fontSize: 12 }}>{dateTime(row.created_at)}</td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
