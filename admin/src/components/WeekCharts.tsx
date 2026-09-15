/**
 * The week behind today, as two small charts.
 *
 * Today's counts answer "what is happening"; they cannot answer "is this a
 * normal Tuesday". Seven days is enough to see that and short enough that
 * every bar is a day somebody on the team remembers. Two charts rather than
 * one: bookings are counted and fares are afghanis, and a second y-axis on
 * one plot would invent a relationship between them that is not in the data.
 *
 * Drawn by hand in SVG. Two bar charts do not earn a charting library, and the
 * rules they follow -- thin bars, a quiet grid, a table for every chart, days
 * that run the way the reader reads -- are easier to keep than to configure.
 */
import { useEffect, useRef, useState, type RefObject } from "react";
import type { WeekHistory } from "../api/operations";
import { useStrings } from "../i18n/strings";
import { Table } from "./ui";

interface Series {
  labelKey: string;
  /** Categorical slot; the colour itself lives in styles.css. */
  slot: 0 | 1;
  values: number[];
}

export function WeekCharts({ history }: { history: WeekHistory }) {
  const { t, num, money } = useStrings();
  const days = history.days.map((day) => day.date);
  const currencyKey = `common.label.currency_${history.currency.toLowerCase()}`;
  const currency = t(currencyKey) === currencyKey ? history.currency : t(currencyKey);
  // Fares are drawn in afghanis, not minor units: the axis should read 12,000,
  // not 1,200,000. `money` takes them back to minor units for the exact figure.
  const whole = (value: number) => num(Math.round(value).toLocaleString("en-US"));

  return (
    <div className="grid two">
      <BarChart
        id="week-trips"
        title={t("admin.week.trips_title")}
        days={days}
        series={[
          { labelKey: "admin.week.bookings", slot: 0, values: history.days.map((day) => day.bookings) },
          { labelKey: "admin.week.completed", slot: 1, values: history.days.map((day) => day.completed_trips) },
        ]}
        tick={num}
        exact={num}
      />
      <BarChart
        id="week-fares"
        title={t("admin.week.fares_title", { currency })}
        days={days}
        series={[
          { labelKey: "admin.week.fares", slot: 0, values: history.days.map((day) => day.revenue_minor / 100) },
        ]}
        tick={whole}
        exact={(value) => money(Math.round(value * 100), history.currency)}
      />
    </div>
  );
}

const HEAD = 20; // room above the tallest bar for its label
const PLOT = 160;
const FOOT = 36; // two lines of day labels under the baseline
const HEIGHT = HEAD + PLOT + FOOT;
const GAP = 2;
const MAX_BAR = 24;

function BarChart({ id, title, days, series, tick, exact }: {
  id: string;
  title: string;
  days: string[];
  series: Series[];
  /** Short: axis ticks and the one direct label. */
  tick: (value: number) => string;
  /** Complete: tooltip, screen reader and table. */
  exact: (value: number) => string;
}) {
  const { t, rtl, dayMonth, date } = useStrings();
  const frameRef = useRef<HTMLDivElement>(null);
  const width = useWidth(frameRef);
  const [asTable, setAsTable] = useState(false);
  const [active, setActive] = useState<{ day: number; series: number } | null>(null);

  const max = Math.max(0, ...series.flatMap((one) => one.values));
  const empty = max === 0;
  const ticks = niceTicks(max);
  const top = ticks[ticks.length - 1] || 1;
  const tickLabels = ticks.map(tick);
  const gutter = Math.max(...tickLabels.map((label) => label.length)) * 7 + 10;

  // The value axis stands at the start of the line and the days run the way
  // the reader reads: oldest on the left in English, on the right in Dari and
  // Pashto, today at the end either way.
  const plotLeft = rtl ? 8 : gutter;
  const plotRight = rtl ? width - gutter : width - 8;
  const band = Math.max(0, plotRight - plotLeft) / Math.max(1, days.length);
  const count = series.length;
  const barWidth = Math.max(2, Math.min(MAX_BAR, (band * 0.72 - GAP * (count - 1)) / count));
  const baseline = HEAD + PLOT;

  const y = (value: number) => HEAD + PLOT - (value / top) * PLOT;
  const center = (day: number) =>
    rtl ? plotRight - (day + 0.5) * band : plotLeft + (day + 0.5) * band;
  const barX = (day: number, index: number) => {
    const offset = (index - (count - 1) / 2) * (barWidth + GAP);
    return center(day) + (rtl ? -offset : offset) - barWidth / 2;
  };
  // A grid line on a half pixel is one device pixel; on a whole one it is a
  // blurred two.
  const rule = (value: number) => Math.round(y(value)) + 0.5;

  const last = days.length - 1;
  // The latest bars carry their value, if it fits over the bar it belongs to;
  // otherwise the tooltip and the table carry it and nothing is crammed.
  const labelFits = series.every((one) => {
    const text = tick(one.values[last] ?? 0);
    return text.length * 6.5 + 2 <= (count > 1 ? barWidth + GAP : band);
  });

  const hitWidth = Math.max(barWidth + GAP, Math.min(24, band / count));

  let tip = null;
  if (active && !asTable && width > 0) {
    const one = series[active.series];
    const value = one?.values[active.day] ?? 0;
    const x = barX(active.day, active.series) + barWidth / 2;
    tip = one && (
      // Physical left, because the position comes from SVG coordinates,
      // which do not mirror.
      <div
        className="viz-tip"
        style={{ left: Math.min(Math.max(x, 72), width - 72), top: y(value) }}
        aria-hidden="true"
      >
        <div className="viz-tip-value">{exact(value)}</div>
        <div className="viz-tip-series">
          <span className={`viz-key s${one.slot}`} />
          {t(one.labelKey)}
        </div>
        <div className="viz-tip-date">{date(days[active.day] ?? "")}</div>
      </div>
    );
  }

  return (
    <figure className="card viz" aria-labelledby={`${id}-title`}>
      <div className="viz-head">
        <h3 className="card-title" id={`${id}-title`}>{title}</h3>
        <button
          className="small"
          aria-pressed={asTable}
          onClick={() => {
            setAsTable((shown) => !shown);
            setActive(null);
          }}
        >
          {asTable ? t("admin.week.show_chart") : t("admin.week.show_table")}
        </button>
      </div>

      {/* A legend only when there is something to tell apart: one series is
          named by the title already. */}
      {count > 1 && !asTable && (
        <div className="viz-legend">
          {series.map((one) => (
            <span key={one.labelKey} className="viz-legend-item">
              <span className={`viz-swatch s${one.slot}`} aria-hidden="true" />
              {t(one.labelKey)}
            </span>
          ))}
        </div>
      )}

      {/* Hidden rather than unmounted, so its width is still observed when
          the chart comes back from the table. */}
      <div ref={frameRef} className="viz-frame" hidden={asTable}>
        {width > 0 && (
          <svg width={width} height={HEIGHT} role="group" aria-labelledby={`${id}-title`}>
            {ticks.map((value, index) => (
              <g key={value}>
                <line
                  className={value === 0 ? "viz-axis" : "viz-grid"}
                  x1={plotLeft} x2={plotRight} y1={rule(value)} y2={rule(value)}
                />
                <text
                  className="viz-tick"
                  x={rtl ? plotRight + 6 : plotLeft - 6}
                  y={y(value)}
                  dy="0.32em"
                  direction="ltr"
                  textAnchor={rtl ? "start" : "end"}
                >
                  {tickLabels[index]}
                </text>
              </g>
            ))}

            {series.map((one, index) =>
              one.values.map((value, day) => {
                const x = barX(day, index);
                const path = columnPath(x, y(value), barWidth, baseline);
                if (!path) return null;
                const on = active?.day === day && active.series === index;
                return (
                  <path
                    key={`${index}-${day}`}
                    className={`viz-bar s${one.slot}${on ? " on" : ""}`}
                    d={path}
                  />
                );
              }),
            )}

            {labelFits && series.map((one, index) => {
              const value = one.values[last] ?? 0;
              if (value <= 0) return null;
              return (
                <text
                  key={one.labelKey}
                  className="viz-label"
                  x={barX(last, index) + barWidth / 2}
                  y={y(value) - 5}
                  textAnchor="middle"
                >
                  {tick(value)}
                </text>
              );
            })}

            {days.map((iso, day) => {
              const parts = dayMonth(iso);
              return (
                <text
                  key={iso}
                  className={day === last ? "viz-day latest" : "viz-day"}
                  y={baseline + 15}
                  textAnchor="middle"
                >
                  <tspan x={center(day)}>{parts.day}</tspan>
                  <tspan x={center(day)} dy="1.25em">{parts.month}</tspan>
                </text>
              );
            })}

            {empty && (
              <text
                className="viz-empty"
                x={(plotLeft + plotRight) / 2}
                y={HEAD + PLOT / 2}
                textAnchor="middle"
              >
                {t("admin.week.empty")}
              </text>
            )}

            {/* Last, so they sit over everything. Wider than the bar and as
                tall as the plot: the reader aims at a day, not at a 24-pixel
                strip, and a zero still has something to point at. */}
            {series.map((one, index) =>
              one.values.map((value, day) => (
                <rect
                  key={`${index}-${day}`}
                  className="viz-hit"
                  x={barX(day, index) + barWidth / 2 - hitWidth / 2}
                  y={HEAD}
                  width={hitWidth}
                  height={PLOT}
                  tabIndex={0}
                  role="img"
                  aria-label={t("admin.week.bar_label", {
                    series: t(one.labelKey),
                    value: exact(value),
                    date: date(days[day] ?? ""),
                  })}
                  onPointerEnter={() => setActive({ day, series: index })}
                  onPointerLeave={() => setActive(null)}
                  onFocus={() => setActive({ day, series: index })}
                  onBlur={() => setActive(null)}
                />
              )),
            )}
          </svg>
        )}
        {tip}
      </div>

      {asTable && (
        <Table
          head={
            <tr>
              <th>{t("admin.week.day")}</th>
              {series.map((one) => (
                <th key={one.labelKey} className="num">{t(one.labelKey)}</th>
              ))}
            </tr>
          }
        >
          {days.map((iso, day) => (
            <tr key={iso}>
              <td>{date(iso)}</td>
              {series.map((one) => (
                <td key={one.labelKey} className="num">{exact(one.values[day] ?? 0)}</td>
              ))}
            </tr>
          ))}
        </Table>
      )}
    </figure>
  );
}

/** Rounded at the data end, square where it stands on the baseline. */
function columnPath(x: number, top: number, width: number, base: number): string {
  const height = base - top;
  if (height <= 0) return "";
  const r = Math.min(4, height, width / 2);
  return `M${x},${base}V${top + r}A${r},${r} 0 0 1 ${x + r},${top}`
    + `H${x + width - r}A${r},${r} 0 0 1 ${x + width},${top + r}V${base}Z`;
}

/**
 * Round steps from zero, about four of them. Never below one: both charts
 * count whole things, and an axis reading 0.25 bookings is a question nobody
 * should have to ask.
 */
function niceTicks(max: number): number[] {
  if (!(max > 0)) return [0];
  const rough = max / 4;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = Math.max(
    1,
    [1, 2, 5, 10].map((multiple) => multiple * power).find((candidate) => candidate >= rough)
      ?? 10 * power,
  );
  const ticks: number[] = [];
  const highest = Math.ceil(max / step) * step;
  for (let value = 0; value <= highest; value += step) ticks.push(value);
  return ticks;
}

/** The element's width, followed as the window or the sidebar changes it. */
function useWidth(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.floor(entry.contentRect.width));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}
