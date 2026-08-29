import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  Empty, ErrorBanner, ErrorState, Loading, Ltr, PageHeader, StatusChip, Table,
} from "../components/ui";
import { useStrings } from "../i18n/strings";

interface UnassignedTrip {
  id: string;
  number: string;
  status: string;
  scheduled_departure_at: string;
  origin_station_id: string;
  destination_id: string;
  seat_capacity: number;
  seats_available: number;
  booked_seats: number;
}

/**
 * The dispatcher's board, section 89.
 *
 * Trips with nobody to drive them, soonest first, and one action each. Kept
 * deliberately short: this is read under time pressure.
 */
export function DispatchPage() {
  const { t, num, dateTime } = useStrings();
  const client = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["unassigned"],
    queryFn: () => api.get<UnassignedTrip[]>("/dispatch/unassigned"),
    refetchInterval: 30_000,
  });

  const offer = useMutation({
    mutationFn: (tripId: string) =>
      api.post<{ offers_made: number }>(`/dispatch/trips/${tripId}/offer`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["unassigned"] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  if (isLoading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;

  const trips = data ?? [];

  return (
    <>
      <PageHeader
        title={t("admin.nav.operations")}
        subtitle={t("admin.section.unassigned")}
        actions={
          <button className="small" onClick={() => refetch()}>
            {t("admin.action.refresh")}
          </button>
        }
      />

      {/* "No driver available" is the common outcome and worth showing plainly:
          it means nobody is online, not that the button failed. */}
      {offer.error && <ErrorBanner error={offer.error} />}
      {offer.isSuccess && offer.data && (
        <div className="banner info">
          {t("admin.action.offer")} — {num(offer.data.offers_made)}
        </div>
      )}

      {trips.length === 0 ? (
        <Empty messageKey="admin.empty.unassigned" />
      ) : (
        <Table
          head={
            <tr>
              <th>{t("admin.col.number")}</th>
              <th>{t("admin.col.status")}</th>
              <th>{t("admin.col.departure")}</th>
              <th className="num">{t("admin.col.seats")}</th>
              <th>{t("admin.col.actions")}</th>
            </tr>
          }
        >
          {trips.map((trip) => (
            <tr key={trip.id}>
              <td><Ltr>{trip.number}</Ltr></td>
              <td><StatusChip status={trip.status} kind="trip" /></td>
              <td>{dateTime(trip.scheduled_departure_at)}</td>
              <td className="num">
                {num(trip.booked_seats)} / {num(trip.seat_capacity)}
              </td>
              <td>
                <button
                  className="small primary"
                  disabled={offer.isPending}
                  onClick={() => offer.mutate(trip.id)}
                >
                  {t("admin.action.offer")}
                </button>
              </td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
