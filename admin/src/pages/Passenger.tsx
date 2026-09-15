import { useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, query } from "../api/client";
import { kabulDay, type UserDetail } from "../api/people";
import { hasAnyRole, isStaff, SUPPORT_ROLES, useRoles } from "../api/roles";
import { gate } from "../components/gate";
import { InputDialog } from "../components/InputDialog";
import {
  AccountStatusChip, ActionStat, Empty, ErrorBanner, Ltr, MoneyStat, PageHeader, Pager,
  Phone, Section, Stat, StatusChip, Table,
} from "../components/ui";
import { LOCALES, useStrings } from "../i18n/strings";

interface PassengerBooking {
  id: string;
  number: string;
  trip_number: string;
  /** Absent on a server that cannot filter by passenger yet. */
  passenger_id?: string | null;
  status: string;
  seat_count: number;
  fare_total_minor: number;
  fare_currency: string;
  created_at: string;
}

interface PassengerTicket {
  id: string;
  reference: string;
  category_code: string;
  status: string;
  is_urgent: boolean;
  created_at: string;
  /** Absent on a server that cannot filter by reporter yet. */
  reporter_id?: string | null;
}

const BOOKINGS = 10;

function hasStatus(error: unknown, status: number): boolean {
  return error instanceof ApiError && error.httpStatus === status;
}

/**
 * One passenger, and everything an operator on the phone needs about them.
 *
 * The questions come in a fixed order on a call: who is this, have they
 * travelled with us, are they waiting for something right now, have they
 * complained before. The page answers them top to bottom in that order.
 *
 * The bookings and the tickets are asked for by id. A server that has not yet
 * learnt those filters would ignore them and answer with everybody's -- so a
 * row is only shown when it says whose it is and that is this passenger. A
 * section that cannot say is left out, never filled with strangers.
 */
export function PassengerPage() {
  const { userId = "" } = useParams();
  const { t, num, money, date, dateTime, forErrorCode } = useStrings();
  const client = useQueryClient();
  const [asking, setAsking] = useState<"suspend" | "reinstate" | null>(null);
  const [bookingOffset, setBookingOffset] = useState(0);
  const path = encodeURIComponent(userId);
  // The support queue is served to support roles only. The tickets are not
  // even asked for otherwise -- nor while the roles are still unknown -- so an
  // operations manager's page never carries a refusal it could not act on.
  const canSupport = hasAnyRole(useRoles(), SUPPORT_ROLES);

  const detailQuery = useQuery({
    queryKey: ["passenger", userId],
    queryFn: () => api.get<UserDetail>(`/admin/users/${path}`),
  });
  const found = Boolean(detailQuery.data);

  const bookingsQuery = useQuery({
    queryKey: ["bookings", "passenger", userId, bookingOffset],
    queryFn: () =>
      api.list<PassengerBooking[]>(
        `/admin/bookings${query({ passenger_id: userId, limit: BOOKINGS, offset: bookingOffset })}`,
      ),
    enabled: found,
    placeholderData: keepPreviousData,
  });

  const ticketsQuery = useQuery({
    queryKey: ["support", "reporter", userId],
    queryFn: () =>
      api.get<{ tickets: PassengerTicket[] }>(
        // ALL, because "has this person complained before" includes the
        // complaints that were answered; the queue's default is open only.
        `/admin/support/tickets${query({ status: "ALL", reporter_id: userId, limit: 50 })}`,
      ),
    enabled: found && canSupport,
  });

  const decide = useMutation({
    mutationFn: ({ action, reason }: { action: "suspend" | "reinstate"; reason: string }) =>
      api.post(`/admin/users/${path}/${action}`, { reason }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["passenger", userId] });
      client.invalidateQueries({ queryKey: ["passengers"] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
      // The same switch takes a driver off the road.
      client.invalidateQueries({ queryKey: ["drivers"] });
    },
  });

  const back = (
    <Link className="back-link" to="/passengers">
      {t("admin.passengers.all")}
    </Link>
  );

  // A 404 is one of two answers, and neither is worth a retry button.
  // USER_NOT_FOUND: no such account, or it was deleted -- the server answers
  // both the same way, and so does this page. Any other code is the path
  // itself missing, a server older than this page; saying "not found" then
  // would tell an operator on the phone that the caller does not exist.
  if (hasStatus(detailQuery.error, 404)) {
    const unknownAccount =
      detailQuery.error instanceof ApiError && detailQuery.error.code === "USER_NOT_FOUND";
    return (
      <>
        {back}
        <Empty
          messageKey={unknownAccount ? "admin.passengers.not_found" : "admin.passengers.not_supported"}
        />
      </>
    );
  }
  const blocked = gate(detailQuery);
  if (blocked) {
    return (
      <>
        {back}
        {blocked}
      </>
    );
  }
  const detail = detailQuery.data;
  if (!detail) return null;

  const { user } = detail;
  const stats = detail.passenger ?? null;
  const driverId = detail.driver_id ?? null;
  const language =
    LOCALES.find((entry) => entry.tag === user.locale)?.label ?? user.locale ?? "—";
  // Refused because he is driving people right now. The shared message for
  // this code is written to the driver ("you are already on a trip"), which
  // read to an operator says something false; this one says what to do.
  const onTrip =
    decide.error instanceof ApiError && decide.error.code === "DRIVER_ALREADY_ON_TRIP";

  const bookingRows = bookingsQuery.data?.data ?? [];
  const bookingsUnderstood = bookingRows.every((row) => row.passenger_id !== undefined);
  const bookings = bookingRows.filter((row) => row.passenger_id === user.id);
  const bookingTotal = Number(bookingsQuery.data?.meta?.total ?? bookings.length);
  const bookingsBlocked = gate(bookingsQuery);

  const ticketRows = ticketsQuery.data?.tickets ?? [];
  const ticketsUnderstood = ticketRows.every((row) => row.reporter_id !== undefined);
  const tickets = ticketRows.filter((row) => row.reporter_id === user.id);

  return (
    <>
      {back}
      <PageHeader
        title={user.full_name ?? t("common.value.no_name")}
        actions={
          <>
            {/* Not offered on a staff account: the server refuses to switch
                one off from here, and its refusal would read as the operator
                lacking permission rather than the account being out of reach. */}
            {!isStaff(user.roles) && user.status === "ACTIVE" && (
              <button
                className="danger"
                disabled={decide.isPending}
                onClick={() => setAsking("suspend")}
              >
                {t("admin.action.suspend")}
              </button>
            )}
            {!isStaff(user.roles) && user.status === "SUSPENDED" && (
              <button
                className="primary"
                disabled={decide.isPending}
                onClick={() => setAsking("reinstate")}
              >
                {t("admin.action.reinstate")}
              </button>
            )}
            <button
              className="small"
              onClick={() => {
                void detailQuery.refetch();
              }}
            >
              {t("admin.action.refresh")}
            </button>
          </>
        }
      />

      {/* A reason either way: the audit entry records it, and whoever next
          reads this account needs to know why it is shut or open. */}
      <InputDialog
        open={asking === "suspend"}
        titleKey="admin.passengers.suspend_reason"
        confirmKey="admin.action.suspend"
        hintKey="admin.passengers.suspend_hint"
        onCancel={() => setAsking(null)}
        onConfirm={(reason) => {
          decide.mutate({ action: "suspend", reason });
          setAsking(null);
        }}
      />
      <InputDialog
        open={asking === "reinstate"}
        titleKey="admin.passengers.reinstate_reason"
        confirmKey="admin.action.reinstate"
        hintKey="admin.passengers.reinstate_hint"
        destructive={false}
        onCancel={() => setAsking(null)}
        onConfirm={(reason) => {
          decide.mutate({ action: "reinstate", reason });
          setAsking(null);
        }}
      />

      {decide.error &&
        (onTrip ? (
          <div className="banner error">{t("admin.passengers.suspend_on_trip")}</div>
        ) : (
          <ErrorBanner error={decide.error} />
        ))}

      <div className="card">
        <dl className="facts">
          <dt>{t("admin.col.phone")}</dt>
          <dd><Phone number={user.phone} /></dd>
          <dt>{t("admin.col.status")}</dt>
          <dd><AccountStatusChip status={user.status} /></dd>
          <dt>{t("passenger.profile.language")}</dt>
          <dd>{language}</dd>
          <dt>{t("admin.col.rating")}</dt>
          <dd>
            {user.rating_average === null || user.rating_average === undefined
              ? "—"
              : `★ ${num(user.rating_average.toFixed(1))} (${num(user.rating_count)})`}
          </dd>
          <dt>{t("admin.col.member_since")}</dt>
          <dd>{date(kabulDay(user.created_at))}</dd>
          <dt>{t("admin.col.last_active")}</dt>
          <dd>
            {user.last_seen_at
              ? dateTime(user.last_seen_at)
              : <span className="muted">{t("common.value.never")}</span>}
          </dd>
          {stats?.first_booking_at && (
            <>
              <dt>{t("admin.passengers.first_booking")}</dt>
              <dd>{dateTime(stats.first_booking_at)}</dd>
            </>
          )}
          {stats?.last_booking_at && (
            <>
              <dt>{t("admin.passengers.last_booking")}</dt>
              <dd>{dateTime(stats.last_booking_at)}</dd>
            </>
          )}
          {driverId && (
            <>
              <dt>{t("role.driver")}</dt>
              <dd>
                <div className="row" style={{ gap: "var(--s-2)" }}>
                  <span className="chip">{t("admin.passengers.also_driver")}</span>
                  <Link to={`/drivers${query({ driver: driverId, search: user.phone })}`}>
                    {t("admin.passengers.open_driver")}
                  </Link>
                </div>
              </dd>
            </>
          )}
        </dl>
      </div>

      {stats && (
        <Section titleKey="admin.passengers.activity">
          <div className="grid stats dense">
            <Stat labelKey="admin.nav.bookings" value={num(stats.bookings_total)} />
            <Stat labelKey="booking.status.completed" value={num(stats.bookings_completed)} />
            <Stat labelKey="booking.status.cancelled" value={num(stats.bookings_cancelled)} />
            {/* A seat held and never sat in is a seat somebody else could
                have had; more than none is worth an operator's glance. */}
            <Stat
              labelKey="booking.status.no_show"
              value={num(stats.no_shows)}
              attention={stats.no_shows > 0}
            />
            <Stat labelKey="admin.passengers.seats_booked" value={num(stats.seats_booked)} />
            <MoneyStat
              labelKey="admin.passengers.spent"
              amountMinor={stats.spent_minor}
              currency={stats.currency}
            />
            {/* The live board holds only requests still open, so this opens
                what the person is waiting for now; the note is the history. */}
            <ActionStat
              labelKey="admin.passengers.open_requests"
              value={stats.open_ride_requests}
              to={`/negotiations${query({ passenger_id: user.id })}`}
              note={t("admin.passengers.requests_total", { count: stats.ride_requests_total })}
            />
            {canSupport ? (
              <ActionStat
                labelKey="admin.support.title"
                value={stats.tickets_total}
                to={`/support${query({ reporter_id: user.id })}`}
                attention={stats.tickets_open > 0}
                note={t("admin.support.open_count", { count: stats.tickets_open })}
              />
            ) : (
              // The count is the server's to give to anyone who may see this
              // page; the queue behind it is not, so it is not a link.
              <Stat
                labelKey="admin.support.title"
                value={num(stats.tickets_total)}
                attention={stats.tickets_open > 0}
                note={t("admin.support.open_count", { count: stats.tickets_open })}
              />
            )}
          </div>
        </Section>
      )}

      {bookingsUnderstood && (
        <Section titleKey="admin.passengers.recent_bookings">
          {bookingsBlocked ?? (
            bookings.length === 0 ? (
              <Empty messageKey="admin.empty.bookings" />
            ) : (
              <>
                <Table
                  head={
                    <tr>
                      <th>{t("admin.col.number")}</th>
                      <th>{t("admin.col.status")}</th>
                      <th>{t("admin.nav.trips")}</th>
                      <th className="num">{t("admin.col.seats")}</th>
                      <th className="num">{t("admin.col.fare")}</th>
                      <th>{t("admin.col.created")}</th>
                    </tr>
                  }
                >
                  {bookings.map((booking) => (
                    <tr key={booking.id}>
                      <td><Ltr>{booking.number}</Ltr></td>
                      <td><StatusChip status={booking.status} kind="booking" /></td>
                      <td>
                        <Link to={`/trips${query({ number: booking.trip_number })}`}>
                          <Ltr>{booking.trip_number}</Ltr>
                        </Link>
                      </td>
                      <td className="num">{num(booking.seat_count)}</td>
                      <td className="num">
                        {money(booking.fare_total_minor, booking.fare_currency)}
                      </td>
                      <td>{dateTime(booking.created_at)}</td>
                    </tr>
                  ))}
                </Table>
                <Pager
                  total={bookingTotal}
                  limit={BOOKINGS}
                  offset={bookingOffset}
                  onChange={setBookingOffset}
                />
              </>
            )
          )}
        </Section>
      )}

      {canSupport && ticketsUnderstood && (
        <Section titleKey="admin.support.title">
          {/* Roles can change under an open session; if the server refuses
              after all, say so in words rather than as a broken section. */}
          {hasStatus(ticketsQuery.error, 403) ? (
            <p className="muted">{forErrorCode("PERMISSION_DENIED")}</p>
          ) : (
            gate(ticketsQuery) ?? (
              tickets.length === 0 ? (
                <Empty messageKey="admin.passengers.no_tickets" />
              ) : (
                <Table
                  head={
                    <tr>
                      <th>{t("admin.col.reference")}</th>
                      <th>{t("admin.col.category")}</th>
                      <th>{t("admin.col.status")}</th>
                      <th>{t("admin.col.created")}</th>
                    </tr>
                  }
                >
                  {tickets.map((ticket) => (
                    <tr key={ticket.id}>
                      <td>
                        <Link to={`/support${query({ reporter_id: user.id, ticket: ticket.id })}`}>
                          <Ltr>{ticket.reference}</Ltr>
                        </Link>
                      </td>
                      <td>
                        <div className="row" style={{ gap: "var(--s-2)" }}>
                          {ticket.is_urgent && (
                            <span className="chip failed">{t("admin.support.urgent")}</span>
                          )}
                          <span>
                            {t(`ticket.category.${ticket.category_code.toLowerCase()}`)}
                          </span>
                        </div>
                      </td>
                      <td>
                        <span
                          className={`chip ${
                            ticket.status === "OPEN" || ticket.status === "IN_PROGRESS"
                              ? "attention"
                              : "active"
                          }`}
                        >
                          {t(`ticket.status.${ticket.status.toLowerCase()}`)}
                        </span>
                      </td>
                      <td>{dateTime(ticket.created_at)}</td>
                    </tr>
                  ))}
                </Table>
              )
            )
          )}
        </Section>
      )}
    </>
  );
}
