/**
 * The people behind the accounts: one row per user, and what one passenger
 * has done on VELRO.
 *
 * Everything past the row itself is optional. The panel may be deployed ahead
 * of its server, and a section whose numbers are missing is hidden rather than
 * drawn as zeros -- a zero is a claim about somebody, and a wrong one is worse
 * than a gap.
 */
import { KABUL } from "../i18n/calendar";

export interface UserRow {
  id: string;
  /** null once the person deleted their account. */
  phone: string | null;
  full_name: string | null;
  /** ACTIVE, SUSPENDED or DEACTIVATED. */
  status: string;
  locale: string | null;
  roles: string[];
  rating_average: number | null;
  rating_count: number;
  created_at: string;
  last_seen_at: string | null;
}

export interface PassengerStats {
  bookings_total: number;
  bookings_completed: number;
  bookings_cancelled: number;
  no_shows: number;
  seats_booked: number;
  spent_minor: number;
  currency: string;
  first_booking_at: string | null;
  last_booking_at: string | null;
  ride_requests_total: number;
  open_ride_requests: number;
  tickets_total: number;
  tickets_open: number;
}

export interface UserDetail {
  user: UserRow;
  /** Set when the same person also drives. */
  driver_id?: string | null;
  passenger?: PassengerStats | null;
}

/**
 * The Kabul calendar day an instant falls on, as YYYY-MM-DD.
 *
 * `date()` reads the first ten characters of whatever it is given, which for
 * a UTC timestamp is the UTC day -- and for anyone who signed up after 19:30
 * UTC, that is yesterday in Kabul. Converting first keeps "member since" on
 * the day the passenger's own phone would show.
 */
export function kabulDay(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: KABUL,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(at);
}

/**
 * "3 min ago", "2 h ago", "4 days ago": the key and its value. Minutes past an
 * hour read as hours and hours past a day as days, as on the drivers' page.
 */
export function agoKey(seconds: number): [string, Record<string, number>] {
  const minutes = Math.max(0, Math.floor(seconds / 60));
  if (minutes < 60) return ["common.value.minutes_ago", { minutes }];
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return ["common.value.hours_ago", { hours }];
  return ["common.value.days_ago", { days: Math.floor(hours / 24) }];
}
