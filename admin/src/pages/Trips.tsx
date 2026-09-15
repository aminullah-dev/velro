import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api, query } from "../api/client";
import { gate } from "../components/gate";
import { Empty, Ltr, PageHeader, Pager, Phone, StatusChip, Table } from "../components/ui";
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
  driver_phone: string | null;
  plate_number: string | null;
  seat_capacity: number;
  seats_available: number;
  booked_seats: number;
}

const LIMIT = 25;

/**
 * Which slice of the trips this page shows. In the URL, not in state, so a
 * dashboard card can open exactly the rows it counted and the operator can
 * send a colleague the same view.
 */
type Slice = "all" | "active" | "unassigned" | "overdue" | "soon";

const SLICES: { key: Slice; labelKey: string; params: Record<string, string | number | boolean> }[] = [
  { key: "all", labelKey: "admin.filter.all", params: {} },
  { key: "active", labelKey: "admin.filter.active_only", params: { active_only: true } },
  { key: "unassigned", labelKey: "admin.filter.needs_driver", params: { unassigned: true } },
  { key: "overdue", labelKey: "admin.filter.overdue", params: { overdue: true } },
  { key: "soon", labelKey: "admin.filter.departing_soon", params: { departing_within_hours: 2 } },
];

function sliceFrom(search: URLSearchParams): { slice: Slice; hours: number | null } {
  if (search.get("overdue")) return { slice: "overdue", hours: null };
  if (search.get("unassigned")) return { slice: "unassigned", hours: null };
  if (search.get("active_only")) return { slice: "active", hours: null };
  const hours = Number(search.get("departing_within_hours"));
  if (hours > 0) return { slice: "soon", hours };
  return { slice: "all", hours: null };
}

export function TripsPage() {
  const { t, num, dateTime } = useStrings();
  const [search, setSearch] = useSearchParams();
  const { slice, hours } = sliceFrom(search);
  // One trip by the number on its receipt -- the link from a booking. It
  // stands in for the slices rather than narrowing one: the trip is wanted
  // whatever state it is in, and no chip is lit while it is shown.
  const number = search.get("number");
  const [offset, setOffset] = useState(0);

  const params = number
    ? { number }
    : {
      ...SLICES.find((s) => s.key === slice)!.params,
      // A card may ask for a window the chip row does not offer (24 h for
      // "nearly full"); honour what the URL says over the chip's default.
      ...(slice === "soon" && hours ? { departing_within_hours: hours } : {}),
    };

  const listQuery = useQuery({
    queryKey: ["trips", slice, hours, number, offset],
    queryFn: () => api.list<Trip[]>(`/admin/trips${query({ ...params, limit: LIMIT, offset })}`),
    // The live slices move; the archive does not.
    refetchInterval: slice === "all" ? false : 20_000,
  });
  const { data } = listQuery;

  const blocked = gate(listQuery);
  if (blocked) return blocked;

  const trips = data?.data ?? [];
  const total = Number(data?.meta?.total ?? trips.length);

  return (
    <>
      <PageHeader title={t("admin.nav.trips")} />

      <div className="filters filter-notice" role="group" aria-label={t("admin.col.status")}>
        {SLICES.map((entry) => {
          const on = !number && entry.key === slice;
          return (
            <button
              key={entry.key}
              type="button"
              className={`small${on ? " on" : ""}`}
              aria-pressed={on}
              onClick={() => {
                const next = new URLSearchParams();
                for (const [k, v] of Object.entries(entry.params)) next.set(k, String(v));
                setSearch(next);
                setOffset(0);
              }}
            >
              {t(entry.labelKey)}
            </button>
          );
        })}
        {number && <span className="chip active">{t("admin.map.trip", { number })}</span>}
      </div>

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
                <td>{trip.driver_name ?? <Phone number={trip.driver_phone} />}</td>
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
