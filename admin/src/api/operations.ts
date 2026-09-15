/**
 * What the operations centre reads beyond its counters: where the cars are,
 * how the week went, and which app versions are still out there.
 *
 * One module for the shapes, so the page that fetches and the components that
 * draw agree on them. The two dashboard additions are optional on the
 * snapshot: a panel deployed a minute ahead of its server must still open,
 * with those sections missing rather than the whole page broken.
 */

export type Availability = "ONLINE" | "ON_TRIP";

export interface LiveDriver {
  driver_id: string;
  name: string | null;
  phone: string | null;
  availability: Availability;
  vehicle: { plate: string; brand: string | null; model: string | null } | null;
  location: {
    latitude: number;
    longitude: number;
    heading_degrees: number | null;
    recorded_at: string;
    /** The server's call, against its own threshold -- never recomputed here. */
    stale: boolean;
  } | null;
  trip: {
    id: string;
    number: string | number;
    status: string;
    origin_name: string | null;
    destination_name: string | null;
  } | null;
  /** A test account rehearsing a trip. On the map, but never mistaken for service. */
  rehearsing: boolean;
}

export interface LiveMapSnapshot {
  generated_at: string;
  stale_after_seconds: number;
  drivers: LiveDriver[];
}

export interface HistoryDay {
  /** A Kabul calendar day, YYYY-MM-DD. */
  date: string;
  trips: number;
  bookings: number;
  completed_trips: number;
  cancellations: number;
  revenue_minor: number;
  commission_minor: number;
}

export interface WeekHistory {
  currency: string;
  /** Oldest first; the last one is today. */
  days: HistoryDay[];
}

export type AppKind = "passenger" | "driver";

export interface AppVersion {
  version_code: number;
  version_name: string;
}

export interface AppVersionCount extends AppVersion {
  app: AppKind;
  platform: "android" | "ios";
  checks: number;
}

export interface AppsReport {
  window_days: number;
  latest: Partial<Record<AppKind, AppVersion | null>>;
  versions: AppVersionCount[];
}
