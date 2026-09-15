import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError, query } from "../api/client";
import { agoKey, kabulDay, type UserRow } from "../api/people";
import { isStaff } from "../api/roles";
import { gate } from "../components/gate";
import { AccountStatusChip, Empty, PageHeader, Pager, Phone, Table } from "../components/ui";
import { useStrings } from "../i18n/strings";

const LIMIT = 25;

/** Long enough that a phone number typed digit by digit is one request. */
const DEBOUNCE_MS = 350;

const FILTERS = [
  { status: "", labelKey: "admin.filter.all" },
  { status: "ACTIVE", labelKey: "admin.user_status.active" },
  { status: "SUSPENDED", labelKey: "admin.user_status.suspended" },
] as const;

/**
 * Somebody who only travels: no driver record, no staff role.
 *
 * Every account starts as a passenger and drivers and staff gain roles on
 * top, so "holds PASSENGER" is everyone. The server narrows with
 * passenger_only; this is the same rule, applied again to what comes back,
 * because a server that does not know the parameter answers without it and a
 * driver listed under "Passengers" is the exact confusion this page exists to
 * end.
 */
function onlyTravels(user: UserRow): boolean {
  const roles = user.roles ?? [];
  return !roles.includes("DRIVER") && !isStaff(roles);
}

/**
 * Everyone who travels with VELRO -- and only them.
 *
 * The call that brings an operator here is almost always a person on the line
 * -- "I booked and nobody came", "my account is blocked" -- so the search takes
 * a name or a phone number in whatever digits it was read out in, and does it
 * on the server: the list is every passenger, not a page of them.
 *
 * Drivers are not here; they have their own page, and a driver's own trips as
 * a passenger are still one link away from any booking of his.
 *
 * The search and the status filter live in the URL, like the other lists, so
 * the dashboard's "suspended" card opens exactly the rows it counted.
 */
export function PassengersPage() {
  const { t, num, date, dateTime } = useStrings();
  const [search, setSearch] = useSearchParams();
  const status = search.get("status") ?? "";
  const term = search.get("q") ?? "";
  const [typed, setTyped] = useState(term);
  // Follow the URL when it changes from outside -- the sidebar entry, Back,
  // a dashboard card -- or the debounce below would write the old search
  // straight back a moment later. Adjusted while rendering rather than in an
  // effect, so the stale text is never painted. The debounce itself writes
  // the trimmed text; the field is left alone then, or the space typed
  // between two words of a name would vanish the moment the operator paused.
  const [seenTerm, setSeenTerm] = useState(term);
  if (term !== seenTerm) {
    setSeenTerm(term);
    if (term !== typed.trim()) setTyped(term);
  }

  // The page belongs to the filter it was chosen under. Compared rather than
  // reset by an effect, so a new search can never render with the old
  // offset for a frame and ask the server for page four of nothing.
  const filterKey = `${status}|${term}`;
  const [page, setPage] = useState({ filterKey, offset: 0 });
  const offset = page.filterKey === filterKey ? page.offset : 0;

  useEffect(() => {
    const wanted = typed.trim();
    if (wanted === term) return;
    const timer = window.setTimeout(() => {
      setSearch(
        (current) => {
          const next = new URLSearchParams(current);
          if (wanted) next.set("q", wanted);
          else next.delete("q");
          return next;
        },
        // Replaced, not pushed: Back should leave the page, not step
        // through every letter that was typed.
        { replace: true },
      );
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [typed, term, setSearch]);

  const listQuery = useQuery({
    queryKey: ["passengers", status, term, offset],
    queryFn: () =>
      api.list<UserRow[]>(
        `/admin/users${query({
          role: "PASSENGER",
          passenger_only: true,
          status,
          search: term,
          limit: LIMIT,
          offset,
        })}`,
      ),
    // The rows stay up while the next search is in flight; otherwise every
    // pause in typing blanks the table to a loading line.
    placeholderData: keepPreviousData,
  });

  // A server older than this page is an answer, not a fault, and it says so
  // rather than offering a retry. Older comes in two shapes: no /admin/users
  // at all (404), or an earlier /admin/users that ignores role, search and
  // offset and counts only its page (meta.count, no meta.total). The second
  // is the dangerous one -- its rows are the newest accounts of every role,
  // unmoved by the search box, and shown under "Passengers" they would be
  // believed. meta.total is how the list says it understood the question.
  const missing =
    (listQuery.error instanceof ApiError && listQuery.error.httpStatus === 404)
    || (listQuery.data !== undefined && listQuery.data.meta?.total === undefined);
  const blocked = missing ? <Empty messageKey="admin.passengers.not_supported" /> : gate(listQuery);

  const rows = (listQuery.data?.data ?? []).filter(onlyTravels);
  const total = Number(listQuery.data?.meta?.total ?? rows.length);
  // "How long ago" is measured from when the list was fetched, not from the
  // clock at render: the same answer every time the same rows are drawn.
  const fetchedAt = listQuery.dataUpdatedAt;

  function lastActive(iso: string | null) {
    if (!iso) return <span className="muted">{t("common.value.never")}</span>;
    const at = Date.parse(iso);
    if (Number.isNaN(at)) return "—";
    const [key, params] = agoKey((fetchedAt - at) / 1000);
    return <span title={dateTime(iso)}>{t(key, params)}</span>;
  }

  return (
    <>
      <PageHeader
        title={t("admin.nav.passengers")}
        // Said on the page, because the first thing an operator who knows a
        // driver travels too will do is search for him here.
        subtitle={t("admin.passengers.only_note")}
        actions={
          <input
            type="search"
            className="search-field"
            value={typed}
            placeholder={t("admin.passengers.search")}
            aria-label={t("admin.passengers.search")}
            onChange={(event) => setTyped(event.target.value)}
          />
        }
      />

      <div className="filters" role="group" aria-label={t("admin.col.status")}>
        {FILTERS.map((entry) => (
          <button
            key={entry.labelKey}
            type="button"
            className={`small${entry.status === status ? " on" : ""}`}
            aria-pressed={entry.status === status}
            onClick={() =>
              setSearch((current) => {
                const next = new URLSearchParams(current);
                if (entry.status) next.set("status", entry.status);
                else next.delete("status");
                return next;
              })
            }
          >
            {t(entry.labelKey)}
          </button>
        ))}
      </div>

      {/* The header and the search box stay put through loading and failure:
          unmounting the field would drop the operator's focus mid-number. */}
      {blocked ?? (
        rows.length === 0 ? (
          <Empty messageKey="admin.passengers.none" />
        ) : (
          <>
            <Table
              head={
                <tr>
                  <th>{t("admin.col.name")}</th>
                  <th>{t("admin.col.phone")}</th>
                  <th className="num">{t("admin.col.rating")}</th>
                  <th>{t("admin.col.member_since")}</th>
                  <th>{t("admin.col.last_active")}</th>
                  <th>{t("admin.col.status")}</th>
                </tr>
              }
            >
              {rows.map((user) => (
                <tr key={user.id}>
                  <td>
                    <Link to={`/passengers/${encodeURIComponent(user.id)}`}>
                      {user.full_name ?? t("common.value.no_name")}
                    </Link>
                  </td>
                  <td><Phone number={user.phone} /></td>
                  <td className="num">
                    {user.rating_average === null || user.rating_average === undefined
                      ? "—"
                      : `★ ${num(user.rating_average.toFixed(1))} (${num(user.rating_count)})`}
                  </td>
                  <td>{date(kabulDay(user.created_at))}</td>
                  <td>{lastActive(user.last_seen_at)}</td>
                  <td><AccountStatusChip status={user.status} /></td>
                </tr>
              ))}
            </Table>
            <Pager
              total={total}
              limit={LIMIT}
              offset={offset}
              onChange={(next) => setPage({ filterKey, offset: next })}
            />
          </>
        )
      )}
    </>
  );
}
