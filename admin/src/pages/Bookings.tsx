import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, query } from "../api/client";
import { Empty, Ltr, PageHeader, Pager, StatusChip, Table, gate } from "../components/ui";
import { useStrings } from "../i18n/strings";

interface Booking {
  id: string;
  number: string;
  trip_number: string;
  passenger_name: string | null;
  passenger_phone: string;
  status: string;
  seat_count: number;
  fare_total_minor: number;
  fare_currency: string;
  payment_method: string;
  payment_status: string | null;
  created_at: string;
}

const LIMIT = 25;

export function BookingsPage() {
  const { t, num, money, dateTime } = useStrings();
  const [offset, setOffset] = useState(0);

  const listQuery = useQuery({
    queryKey: ["bookings", offset],
    queryFn: () => api.list<Booking[]>(`/admin/bookings${query({ limit: LIMIT, offset })}`),
  });
  const { data } = listQuery;

  const blocked = gate(listQuery);
  if (blocked) return blocked;

  const bookings = data?.data ?? [];
  const total = Number(data?.meta?.total ?? bookings.length);

  return (
    <>
      <PageHeader title={t("admin.nav.bookings")} />
      {bookings.length === 0 ? (
        <Empty messageKey="admin.empty.bookings" />
      ) : (
        <>
          <Table
            head={
              <tr>
                <th>{t("admin.col.number")}</th>
                <th>{t("admin.col.status")}</th>
                <th>{t("admin.col.passenger")}</th>
                <th>{t("admin.col.phone")}</th>
                <th>{t("admin.nav.trips")}</th>
                <th className="num">{t("admin.col.seats")}</th>
                <th className="num">{t("admin.col.fare")}</th>
                <th>{t("admin.col.payment")}</th>
                <th>{t("admin.col.created")}</th>
              </tr>
            }
          >
            {bookings.map((booking) => (
              <tr key={booking.id}>
                <td><Ltr>{booking.number}</Ltr></td>
                <td><StatusChip status={booking.status} kind="booking" /></td>
                <td>{booking.passenger_name ?? t("common.value.no_name")}</td>
                {/* A phone number is a sequence to be dialled, never mirrored. */}
                <td><Ltr>{booking.passenger_phone}</Ltr></td>
                <td><Ltr>{booking.trip_number}</Ltr></td>
                <td className="num">{num(booking.seat_count)}</td>
                <td className="num">
                  {money(booking.fare_total_minor, booking.fare_currency)}
                </td>
                <td>
                  <span className="chip">
                    {booking.payment_status
                      ? t(`payment.status.${booking.payment_status.toLowerCase()}`)
                      : t(`payment.method.${booking.payment_method.toLowerCase()}`)}
                  </span>
                </td>
                <td>{dateTime(booking.created_at)}</td>
              </tr>
            ))}
          </Table>
          <Pager total={total} limit={LIMIT} offset={offset} onChange={setOffset} />
        </>
      )}
    </>
  );
}
