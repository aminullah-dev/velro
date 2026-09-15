/**
 * Where the cars are, now.
 *
 * The counters above say how many drivers are online; this says where, which
 * is the question an operator actually has when a passenger rings from a
 * station asking whether anybody is coming. One dot per car that has sent a
 * location, coloured by what it is doing and always named in the legend
 * underneath -- colour is never the only way to tell a state apart.
 *
 * The map is created once and fed: every refresh replaces the dots' data and
 * nothing else, so a map the operator has panned and zoomed stays where they
 * left it. Drivers who are online but have never sent a location cannot be
 * drawn, and are listed under the map instead of silently missing from it.
 */
import "maplibre-gl/dist/maplibre-gl.css";
import {
  Map as MapLibre, NavigationControl, Popup, setWorkerUrl,
  type GeoJSONSource, type MapOptions,
} from "maplibre-gl";
// MapLibre looks for its worker next to its own module file, which is exactly
// what a bundler breaks: in development the module is served from Vite's
// dependency cache, in a build it is hashed into a chunk, and the sibling file
// exists in neither place. A URL the bundler produced itself holds in both.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { useEffect, useRef, useState, type RefObject } from "react";
import type { LiveDriver, LiveMapSnapshot } from "../api/operations";
import { useStrings, type StringsContext } from "../i18n/strings";
import { Ltr, Phone } from "./ui";

setWorkerUrl(workerUrl);

/** Kabul, Parwan and Ghorband: where the service runs, so where the map opens. */
const REGION: [number, number, number, number] = [67.9, 34.3, 69.7, 35.6];

type CarState = "trip" | "online" | "stale";

const STATES: { state: CarState; labelKey: string }[] = [
  { state: "trip", labelKey: "admin.map.on_trip" },
  { state: "online", labelKey: "admin.map.online" },
  { state: "stale", labelKey: "admin.map.stale" },
];

/** Drawn last is drawn on top: a car on a trip is never hidden under a waiting one. */
const DRAW_ORDER: Record<CarState, number> = { stale: 0, online: 1, trip: 2 };

function carState(driver: LiveDriver): CarState {
  // An old fix outranks what the car is doing. Grey means "we do not know
  // where this car is now", and that is as true of a car on a trip as of one
  // waiting -- more worrying, if anything, which the popup then says in words.
  if (driver.location?.stale) return "stale";
  return driver.availability === "ON_TRIP" ? "trip" : "online";
}

interface RawStyle {
  glyphs?: string;
  sprite?: string | { id: string; url: string }[];
  sources?: Record<string, { tiles?: string[]; url?: string }>;
  [key: string]: unknown;
}

const OWN_API = /^https?:\/\/[^/]+(\/api\/.*)$/;

/**
 * Points the style's URLs back at the origin this panel was loaded from.
 *
 * The server writes absolute URLs from the Host it was asked on, which is
 * right for the apps and wrong here twice over: through the development proxy
 * that host is localhost:8000, another origin from the panel's, and behind a
 * proxy that terminates TLS it can come back as http:// on an https page,
 * which the browser refuses outright. The path is the API's own and is kept;
 * only the origin changes, and only on URLs into /api/ -- a third-party tile
 * host, if one is ever added, is left alone.
 */
function onThisOrigin(url: string): string {
  const match = OWN_API.exec(url);
  return match ? `${window.location.origin}${match[1]}` : url;
}

function sameOriginStyle(style: RawStyle): RawStyle {
  const sources = Object.fromEntries(
    Object.entries(style.sources ?? {}).map(([id, source]) => [
      id,
      {
        ...source,
        ...(source.tiles ? { tiles: source.tiles.map(onThisOrigin) } : {}),
        ...(source.url ? { url: onThisOrigin(source.url) } : {}),
      },
    ]),
  );
  const sprite = typeof style.sprite === "string"
    ? onThisOrigin(style.sprite)
    : style.sprite?.map((entry) => ({ ...entry, url: onThisOrigin(entry.url) }));
  return {
    ...style,
    sources,
    ...(style.glyphs ? { glyphs: onThisOrigin(style.glyphs) } : {}),
    ...(sprite ? { sprite } : {}),
  };
}

/** The few GeoJSON shapes drawn here; @types/geojson is not worth a dependency for them. */
interface CarFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: { id: string; state: CarState; test: boolean; plate: string; order: number };
}

interface CarCollection {
  type: "FeatureCollection";
  features: CarFeature[];
}

function carFeatures(drivers: LiveDriver[]): CarCollection {
  return {
    type: "FeatureCollection",
    features: drivers.flatMap((driver): CarFeature[] => {
      if (!driver.location) return [];
      const state = carState(driver);
      return [{
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [driver.location.longitude, driver.location.latitude],
        },
        properties: {
          id: driver.driver_id,
          state,
          test: driver.rehearsing,
          plate: driver.vehicle?.plate ?? "",
          order: DRAW_ORDER[state],
        },
      }];
    }),
  };
}

/**
 * The dots' colours, read from styles.css so every colour in the panel lives
 * in one file. Read once per map: the vector style underneath is light in both
 * schemes, so the dots on it keep their light values in both too.
 */
function palette(element: HTMLElement) {
  const css = getComputedStyle(element);
  const read = (name: string) => css.getPropertyValue(name).trim();
  return {
    trip: read("--map-trip"),
    online: read("--map-online"),
    stale: read("--map-stale"),
    ink: read("--map-ink"),
    halo: read("--map-halo"),
  };
}

function addCarLayers(map: MapLibre, colors: ReturnType<typeof palette>) {
  map.addSource("cars", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({
    id: "cars",
    type: "circle",
    source: "cars",
    layout: { "circle-sort-key": ["get", "order"] },
    paint: {
      "circle-radius": 7,
      // A test car is hollow: its state's colour as a ring around the map's
      // own ground. It reads as "a car, but not service" without inventing a
      // fourth colour somebody would have to learn.
      "circle-color": [
        "case", ["get", "test"], colors.halo,
        ["match", ["get", "state"], "trip", colors.trip, "online", colors.online, colors.stale],
      ],
      "circle-stroke-color": [
        "case", ["get", "test"],
        ["match", ["get", "state"], "trip", colors.trip, "online", colors.online, colors.stale],
        colors.halo,
      ],
      "circle-stroke-width": ["case", ["get", "test"], 3, 2],
    },
  });
  // Plates, not names: a plate is Latin and fits the one font the map server
  // ships, and it is what an operator reads back to a passenger anyway.
  map.addLayer({
    id: "car-plates",
    type: "symbol",
    source: "cars",
    layout: {
      "text-field": ["get", "plate"],
      "text-font": ["Noto Sans Regular"],
      "text-size": 11,
      "text-offset": [0, 1.1],
      "text-anchor": "top",
      "symbol-sort-key": ["-", 2, ["get", "order"]],
    },
    paint: {
      "text-color": colors.ink,
      "text-halo-color": colors.halo,
      "text-halo-width": 1.5,
    },
  });
}

/** False while the style is still loading; the load handler draws then. */
function drawCars(map: MapLibre, snapshot: LiveMapSnapshot): boolean {
  const source = map.getSource("cars") as GeoJSONSource | undefined;
  if (!source) return false;
  void source.setData(carFeatures(snapshot.drivers));
  return true;
}

/**
 * Near enough to the region to be a car in service. A phone that has never had
 * a real fix reports wherever its emulator or its last owner left it -- the
 * development database has a driver in San Francisco -- and fitting the first
 * view to that would show half the planet with Kabul as a speck.
 */
function nearRegion(location: { latitude: number; longitude: number }): boolean {
  const [west, south, east, north] = REGION;
  const margin = 0.5;
  return location.longitude >= west - margin && location.longitude <= east + margin
    && location.latitude >= south - margin && location.latitude <= north + margin;
}

function fitToCars(map: MapLibre, drivers: LiveDriver[]) {
  const points = drivers.flatMap((driver) =>
    driver.location && nearRegion(driver.location)
      ? [[driver.location.longitude, driver.location.latitude] as const]
      : [],
  );
  // Nobody has a fix nearby: the map stays on the region it opened on.
  if (points.length === 0) return;
  const lngs = points.map(([lng]) => lng);
  const lats = points.map(([, lat]) => lat);
  map.fitBounds(
    [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
    // One car alone would otherwise be fitted down to street level.
    { padding: 56, maxZoom: 13, duration: 0 },
  );
}

/**
 * The popup's contents, built node by node.
 *
 * Names, plates and station names are typed by people; set as textContent
 * they are only ever text. The popup sits inside the map's left-to-right
 * canvas, so it carries the reader's direction itself.
 */
function popupContent(driver: LiveDriver, strings: StringsContext): HTMLElement {
  const { t, dateTime, rtl } = strings;
  const root = document.createElement("div");
  root.className = "car-popup";
  root.dir = rtl ? "rtl" : "ltr";

  const line = (text: string, className?: string) => {
    const element = document.createElement("div");
    element.textContent = text;
    if (className) element.className = className;
    root.appendChild(element);
    return element;
  };

  const title = line(driver.name ?? driver.phone ?? t("admin.map.unnamed"), "car-popup-title");
  if (driver.rehearsing) {
    const chip = document.createElement("span");
    chip.className = "chip attention";
    chip.textContent = t("admin.map.test");
    title.append(" ", chip);
  }

  if (driver.vehicle) {
    const vehicle = line("");
    const plate = document.createElement("span");
    plate.className = "ltr tabular";
    plate.textContent = driver.vehicle.plate;
    vehicle.appendChild(plate);
    const model = [driver.vehicle.brand, driver.vehicle.model].filter(Boolean).join(" ");
    if (model) vehicle.append(` · ${model}`);
  }

  line(t(driver.availability === "ON_TRIP" ? "admin.map.on_trip" : "admin.map.online"));

  if (driver.trip) {
    // As a string, so a numeric trip number stays in the Latin digits every
    // other screen shows it in.
    line(t("admin.map.trip", { number: String(driver.trip.number) }));
    line(
      t("admin.map.route", {
        origin: driver.trip.origin_name ?? "—",
        destination: driver.trip.destination_name ?? "—",
      }),
      "muted",
    );
  }

  if (driver.location) {
    line(t("admin.map.last_fix", { time: dateTime(driver.location.recorded_at) }), "muted");
    if (driver.location.stale) line(t("admin.map.stale_warning"), "car-popup-warn");
  }
  return root;
}

interface OpenPopup {
  popup: Popup;
  driverId: string;
}

/** Keeps an open popup on its car, and closes it once the car is gone. */
function refreshPopup(
  open: RefObject<OpenPopup | null>,
  snapshot: LiveMapSnapshot,
  strings: StringsContext,
) {
  const current = open.current;
  if (!current) return;
  const driver = snapshot.drivers.find((candidate) => candidate.driver_id === current.driverId);
  if (!driver?.location) {
    current.popup.remove();
    return;
  }
  current.popup
    .setLngLat([driver.location.longitude, driver.location.latitude])
    .setDOMContent(popupContent(driver, strings));
}

export function LiveMap({ snapshot }: { snapshot: LiveMapSnapshot }) {
  const strings = useStrings();
  const { t, num, dateTime, locale } = strings;
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibre | null>(null);
  const popupRef = useRef<OpenPopup | null>(null);
  // The map's handlers are attached once, when it is created; they read the
  // newest data and wording through this rather than the render they began in.
  const latest = useRef({ snapshot, strings });
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    latest.current = { snapshot, strings };
  });

  // Once per language: MapLibre's own controls take their wording at
  // creation, and a language switch is rare enough to rebuild for.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const controller = new AbortController();
    let map: MapLibre | null = null;

    // Not api.get: the style is MapLibre's own document, not an envelope.
    fetch("/api/v1/geo/map/style.json", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`map style: HTTP ${response.status}`);
        return response.json() as Promise<RawStyle>;
      })
      .then((style) => {
        if (controller.signal.aborted) return;
        const { t: tr } = latest.current.strings;
        const colors = palette(container);
        const created = new MapLibre({
          container,
          style: sameOriginStyle(style) as MapOptions["style"],
          bounds: REGION,
          fitBoundsOptions: { padding: 16 },
          attributionControl: { compact: true },
          // The dashboard scrolls. Without this a wheel over the map zooms it
          // and the page stops moving under the operator's hand.
          cooperativeGestures: true,
          dragRotate: false,
          pitchWithRotate: false,
          touchPitch: false,
          renderWorldCopies: false,
          locale: {
            "Map.Title": tr("admin.ops.live_map"),
            "NavigationControl.ZoomIn": tr("admin.map.zoom_in"),
            "NavigationControl.ZoomOut": tr("admin.map.zoom_out"),
            "Popup.Close": tr("common.action.close"),
            "AttributionControl.ToggleAttribution": tr("admin.map.attribution"),
            "CooperativeGesturesHandler.WindowsHelpText": tr("admin.map.gesture_windows"),
            "CooperativeGesturesHandler.MacHelpText": tr("admin.map.gesture_mac"),
            "CooperativeGesturesHandler.MobileHelpText": tr("admin.map.gesture_touch"),
          },
        });
        map = created;
        mapRef.current = created;
        created.touchZoomRotate.disableRotation();
        created.addControl(new NavigationControl({ showCompass: false }), "top-right");

        created.on("load", () => {
          addCarLayers(created, colors);
          drawCars(created, latest.current.snapshot);
          // Only here, never on a refresh: after the first look the view is
          // the operator's, and a map that jumps every half minute is unusable.
          fitToCars(created, latest.current.snapshot.drivers);
        });

        created.on("click", "cars", (event) => {
          const id: unknown = event.features?.[0]?.properties?.id;
          const { snapshot: now, strings: words } = latest.current;
          const driver = now.drivers.find((candidate) => candidate.driver_id === id);
          if (!driver?.location) return;
          // A fresh popup each time. Reusing one fights MapLibre's own
          // close-on-click, which fires after this handler and would shut it.
          popupRef.current?.popup.remove();
          const popup = new Popup({ offset: 12, maxWidth: "300px" })
            .setLngLat([driver.location.longitude, driver.location.latitude])
            .setDOMContent(popupContent(driver, words))
            .addTo(created);
          const entry = { popup, driverId: driver.driver_id };
          popupRef.current = entry;
          popup.on("close", () => {
            if (popupRef.current === entry) popupRef.current = null;
          });
        });
        created.on("mouseenter", "cars", () => {
          created.getCanvas().style.cursor = "pointer";
        });
        created.on("mouseleave", "cars", () => {
          created.getCanvas().style.cursor = "";
        });
        setFailed(false);
      })
      .catch(() => {
        // The style, or the renderer itself (no WebGL on an old office PC).
        // The legend and the list still work without either.
        if (!controller.signal.aborted) setFailed(true);
      });

    return () => {
      controller.abort();
      popupRef.current?.popup.remove();
      popupRef.current = null;
      map?.remove();
      mapRef.current = null;
    };
  }, [locale]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !drawCars(map, snapshot)) return;
    refreshPopup(popupRef, snapshot, strings);
  }, [snapshot, strings]);

  const counts: Record<CarState, number> = { trip: 0, online: 0, stale: 0 };
  let testOnMap = 0;
  for (const driver of snapshot.drivers) {
    if (!driver.location) continue;
    counts[carState(driver)] += 1;
    if (driver.rehearsing) testOnMap += 1;
  }
  const withoutFix = snapshot.drivers.filter((driver) => !driver.location);
  // Drawn where they say they are, but off the first view -- so named here,
  // or they would be online and nowhere.
  const faraway = snapshot.drivers.filter(
    (driver) => driver.location && !nearRegion(driver.location),
  );

  return (
    <div className="live-map">
      <div className="live-map-frame">
        {failed && <div className="state">{t("admin.map.unavailable")}</div>}
        {/* Left to right in every language: it is a picture of the ground,
            and MapLibre's controls and gestures assume it. What is written
            over it -- the popup -- carries the reader's direction itself. */}
        <div ref={containerRef} className="live-map-canvas" dir="ltr" hidden={failed} />
      </div>

      <div className="map-legend">
        {STATES.map(({ state, labelKey }) => (
          <span key={state} className="map-legend-item">
            <span className={`map-dot ${state}`} aria-hidden="true" />
            {t(labelKey)}
            <span className="muted tabular">{num(counts[state])}</span>
          </span>
        ))}
        <span className="map-legend-item">
          <span className="map-dot test" aria-hidden="true" />
          {t("admin.map.test_legend")}
          <span className="muted tabular">{num(testOnMap)}</span>
        </span>
        <span className="spacer" />
        <span className="muted map-meta">
          {t("admin.map.as_of", { time: dateTime(snapshot.generated_at) })}
        </span>
      </div>

      {snapshot.drivers.length === 0 && (
        <p className="muted map-note">{t("admin.map.none_online")}</p>
      )}

      <DriverList titleKey="admin.map.no_fix_title" drivers={withoutFix} />
      <DriverList titleKey="admin.map.outside_title" drivers={faraway} />
    </div>
  );
}

/** Drivers the map cannot usefully show, by name, so none is simply missing. */
function DriverList({ titleKey, drivers }: { titleKey: string; drivers: LiveDriver[] }) {
  const { t, num, dateTime } = useStrings();
  if (drivers.length === 0) return null;
  return (
    <div>
      <h3 className="map-subhead">
        {t(titleKey)} <span className="tabular">{num(drivers.length)}</span>
      </h3>
      <ul className="map-nofix">
        {drivers.map((driver) => (
          <li key={driver.driver_id}>
            <span className="map-nofix-name">{driver.name ?? t("admin.map.unnamed")}</span>
            {driver.vehicle && <Ltr>{driver.vehicle.plate}</Ltr>}
            <span className="muted">
              {t(driver.availability === "ON_TRIP" ? "admin.map.on_trip" : "admin.map.online")}
            </span>
            {driver.location && (
              <span className="muted">
                {t("admin.map.last_fix", { time: dateTime(driver.location.recorded_at) })}
              </span>
            )}
            {driver.rehearsing && <span className="chip attention">{t("admin.map.test")}</span>}
            {driver.phone && <Phone number={driver.phone} />}
          </li>
        ))}
      </ul>
    </div>
  );
}
