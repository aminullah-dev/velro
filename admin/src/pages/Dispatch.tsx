import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Empty, ErrorBanner, Ltr, PageHeader, StatusChip, Table, gate } from "../components/ui";
import { useStrings } from "../i18n/strings";

interface UnassignedTrip {
  id: string;
  number: string;
  status: string;
  ride_kind: string;
  scheduled_departure_at: string;
  minutes_to_departure: number;
  at_risk: boolean;
  origin_station_id: string;
  origin_station_name: string | null;
  destination_id: string;
  destination_name: string | null;
  seat_capacity: number;
  seats_available: number;
  booked_seats: number;
  open_offers: number;
  offers_expire_at: string | null;
  //: Minutes until the last open offer lapses, as of the snapshot. Computed
  //: where the clock is, not in the browser.
  offers_expire_in_minutes: number | null;
  candidates: number;
}

interface OfferResult {
  offers_made: number;
  driver_ids: string[];
}

/**
 * The dispatcher's board, section 89.
 *
 * Trips with nobody to drive them, soonest first, and everything a person
 * needs to decide in the ten seconds each row gets: where it leaves from
 * and goes, how many are already on it, how long until it leaves, whether
 * drivers have already been asked and are still deciding, and whether there
 * is anybody online to ask at all. Read under time pressure, so nothing here
 * needs a second click to understand.
 */
export function DispatchPage() {
  const { t, num, dateTime } = useStrings();
  const client = useQueryClient();

  const boardQuery = useQuery({
    queryKey: ["unassigned"],
    queryFn: () => api.list<UnassignedTrip[]>("/dispatch/unassigned"),
    refetchInterval: 30_000,
  });
  const { data } = boardQuery;

  const offer = useMutation({
    mutationFn: (tripId: string) =>
      api.post<OfferResult>(`/dispatch/trips/${tripId}/offer`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["unassigned"] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const blocked = gate(boardQuery);
  if (blocked) return blocked;

  const trips = data?.data ?? [];
  const atRisk = Number(data?.meta?.at_risk ?? 0);
  const driversAvailable = Number(data?.meta?.drivers_available ?? 0);

  /** "in 45 min", "2 h 10 min", "12 min ago" -- what the row is really about. */
  function untilDeparture(minutes: number): string {
    const abs = Math.abs(minutes);
    if (minutes < 0) return t("admin.dispatch.minutes_ago", { minutes: num(abs) });
    if (abs < 60) return t("admin.dispatch.in_minutes", { minutes: num(abs) });
    return t("admin.dispatch.in_hours", {
      hours: num(Math.floor(abs / 60)), minutes: num(abs % 60),
    });
  }

  function offersCell(trip: UnassignedTrip) {
    if (trip.open_offers === 0) {
      return <span className="muted">{t("admin.dispatch.no_offers")}</span>;
    }
    return (
      <>
        <div>{t("admin.dispatch.offers_open", { count: num(trip.open_offers) })}</div>
        {trip.offers_expire_in_minutes !== null && (
          <div className="muted" style={{ fontSize: 12 }}>
            {t("admin.dispatch.expires_in", { minutes: num(trip.offers_expire_in_minutes) })}
          </div>
        )}
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={t("admin.nav.operations")}
        subtitle={
          trips.length > 0
            ? t("admin.dispatch.summary", { at_risk: num(atRisk), drivers: num(driversAvailable) })
            : t("admin.section.unassigned")
        }
        actions={
          <button className="small" onClick={() => boardQuery.refetch()}>
            {t("admin.action.refresh")}
          </button>
        }
      />

      {/* "No driver available" is the common outcome and worth showing plainly:
          it means nobody is online, not that the button failed. */}
      {offer.error && <ErrorBanner error={offer.error} />}
      {offer.isSuccess && offer.data && (
        <div className="banner info" role="status">
          {offer.data.offers_made > 0
            ? t("admin.dispatch.offered", { count: num(offer.data.offers_made) })
            : t("admin.dispatch.already_offered")}
        </div>
      )}

      {trips.length === 0 ? (
        <Empty messageKey="admin.empty.unassigned" />
      ) : (
        <Table
          head={
            <tr>
              <th>{t("admin.col.departure")}</th>
              <th>{t("admin.col.number")}</th>
              <th>{t("admin.col.route")}</th>
              <th className="num">{t("admin.col.seats")}</th>
              <th>{t("admin.col.offers")}</th>
              <th className="num">{t("admin.col.available")}</th>
              <th>{t("admin.col.actions")}</th>
            </tr>
          }
        >
          {trips.map((trip) => (
            // The tint says "at risk"; so does the chip, in words. Neither
            // is on its own.
            <tr key={trip.id} className={trip.at_risk ? "at-risk" : undefined}>
              <td>
                <div style={{ fontWeight: 600 }}>{untilDeparture(trip.minutes_to_departure)}</div>
                <div className="muted" style={{ fontSize: 12 }}>
                  {dateTime(trip.scheduled_departure_at)}
                </div>
                {trip.at_risk && (
                  <span className="chip attention" style={{ marginTop: 4 }}>
                    {t("admin.dispatch.at_risk")}
                  </span>
                )}
              </td>
              <td>
                <Ltr>{trip.number}</Ltr>
                <div><StatusChip status={trip.status} kind="trip" /></div>
              </td>
              <td>
                {trip.origin_station_name ?? "—"}
                <span className="muted"> ← </span>
                {trip.destination_name ?? "—"}
              </td>
              <td className="num">
                {num(trip.booked_seats)} / {num(trip.seat_capacity)}
              </td>
              <td>{offersCell(trip)}</td>
              <td className="num">
                {trip.candidates > 0
                  ? t("admin.dispatch.candidates", { count: num(trip.candidates) })
                  : <span className="muted">{t("admin.dispatch.nobody_online")}</span>}
              </td>
              <td>
                <button
                  className={`small${trip.open_offers > 0 ? "" : " primary"}`}
                  disabled={offer.isPending || trip.candidates === 0}
                  // A disabled button with no reason is a broken button. The
                  // tooltip says why; the "Available" cell says it in words
                  // for anyone who cannot hover.
                  title={trip.candidates === 0 ? t("admin.dispatch.nobody_online") : undefined}
                  onClick={() => offer.mutate(trip.id)}
                >
                  {trip.open_offers > 0 ? t("admin.action.offer_again") : t("admin.action.offer")}
                </button>
              </td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
