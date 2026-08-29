import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, query } from "../api/client";
import {
  Empty, ErrorState, Loading, Ltr, PageHeader, Pager, StatusChip, Table,
} from "../components/ui";
import { useStrings } from "../i18n/strings";

interface Trip {
  id: string;
  number: string;
  status: string;
  ride_kind: string;
  scheduled_departure_at: string;
  origin_station_name: string;
  destination_name: string;
  driver_name: string | null;
  plate_number: string | null;
  seat_capacity: number;
  seats_available: number;
  booked_seats: number;
}

const LIMIT = 25;

export function TripsPage() {
  const { t, num, dateTime } = useStrings();
  const [activeOnly, setActiveOnly] = useState(false);
  const [offset, setOffset] = useState(0);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["trips", activeOnly, offset],
    queryFn: () =>
      api.list<Trip[]>(
        `/admin/trips${query({ active_only: activeOnly, limit: LIMIT, offset })}`,
      ),
    refetchInterval: activeOnly ? 20_000 : false,
  });

  if (isLoading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;

  const trips = data?.data ?? [];
  const total = Number(data?.meta?.total ?? trips.length);

  return (
    <>
      <PageHeader
        title={t("admin.nav.trips")}
        actions={
          <label className="row" style={{ gap: "var(--s-2)" }}>
            <input
              type="checkbox"
              checked={activeOnly}
              style={{ minHeight: "auto" }}
              onChange={(event) => {
                setActiveOnly(event.target.checked);
                setOffset(0);
              }}
            />
            <span>{t("admin.filter.active_only")}</span>
          </label>
        }
      />

      {trips.length === 0 ? (
        <Empty messageKey="admin.empty.trips" />
      ) : (
        <>
          <Table
            head={
              <tr>
                <th>{t("admin.col.number")}</th>
                <th>{t("admin.col.status")}</th>
                <th>{t("admin.col.departure")}</th>
                <th>{t("admin.col.origin")}</th>
                <th>{t("admin.col.destination")}</th>
                <th>{t("admin.col.driver")}</th>
                <th>{t("admin.col.plate")}</th>
                <th className="num">{t("admin.col.seats")}</th>
              </tr>
            }
          >
            {trips.map((trip) => (
              <tr key={trip.id}>
                <td><Ltr>{trip.number}</Ltr></td>
                <td><StatusChip status={trip.status} kind="trip" /></td>
                <td>{dateTime(trip.scheduled_departure_at)}</td>
                <td>{trip.origin_station_name}</td>
                <td>{trip.destination_name}</td>
                <td>{trip.driver_name ?? "—"}</td>
                <td>{trip.plate_number ? <Ltr>{trip.plate_number}</Ltr> : "—"}</td>
                <td className="num">
                  {num(trip.booked_seats)} / {num(trip.seat_capacity)}
                </td>
              </tr>
            ))}
          </Table>
          <Pager total={total} limit={LIMIT} offset={offset} onChange={setOffset} />
        </>
      )}
    </>
  );
}
