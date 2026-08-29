/**
 * Hijri Shamsi, for the operator's panel.
 *
 * A port of `mobile/core/i18n/Calendar.kt`, and deliberately not an independent
 * implementation: both are checked against `docs/domain/calendar.json`, so the
 * date a driver reads out over the phone is the date the operator sees on the
 * screen. Two implementations that merely look similar drift; two that answer
 * to one fixture table cannot.
 */

/** Afghanistan does not observe daylight saving; the offset is +04:30. */
export const KABUL = "Asia/Kabul";

// 1 Hamal 1399 fell on 20 March 2020. Every conversion is counted from here, so
// the arithmetic is exact rather than approximate.
const ANCHOR_SHAMSI_YEAR = 1399;
const ANCHOR_EPOCH_DAY = Date.UTC(2020, 2, 20) / 86_400_000;

// The 33-year cycle. The 2820-year (Birashk) rule is the elegant-looking one and
// it is wrong here: it makes 1404 leap and 1403 common when the observed Nowruz
// dates say the opposite, shifting every date between 20 March 2025 and
// 20 March 2026 by a day. Holds for roughly 1178-1633.
const LEAP_RESIDUES = new Set([1, 5, 9, 13, 17, 22, 26, 30]);

export interface ShamsiDate {
  year: number;
  month: number;
  day: number;
}

const mod = (value: number, by: number) => ((value % by) + by) % by;

export const isShamsiLeap = (year: number): boolean =>
  LEAP_RESIDUES.has(mod(year, 33));

/** Six months of 31, five of 30, then Hoot at 29 or 30. */
export const shamsiMonthLength = (year: number, month: number): number =>
  month <= 6 ? 31 : month <= 11 ? 30 : isShamsiLeap(year) ? 30 : 29;

export const shamsiYearLength = (year: number): number =>
  isShamsiLeap(year) ? 366 : 365;

/** Gregorian to Hijri Shamsi, from an epoch day count. */
export function shamsiFromEpochDay(epochDay: number): ShamsiDate {
  let year = ANCHOR_SHAMSI_YEAR;
  let remaining = epochDay - ANCHOR_EPOCH_DAY;

  if (remaining >= 0) {
    while (remaining >= shamsiYearLength(year)) {
      remaining -= shamsiYearLength(year);
      year += 1;
    }
  } else {
    while (remaining < 0) {
      year -= 1;
      remaining += shamsiYearLength(year);
    }
  }

  for (let month = 1; month <= 12; month += 1) {
    const length = shamsiMonthLength(year, month);
    if (remaining < length) return { year, month, day: remaining + 1 };
    remaining -= length;
  }
  return { year: year + 1, month: 1, day: remaining + 1 };
}

/**
 * The calendar day in Kabul that a given instant falls on.
 *
 * The timezone shift is done by the platform and the result read back as parts,
 * because a UTC instant near midnight belongs to a different Kabul day and
 * getting that wrong dates a receipt to the day before.
 */
export function shamsiInKabul(at: Date): ShamsiDate {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: KABUL,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(at);
  // en-CA formats as YYYY-MM-DD, so the three parts are always present;
  // the defaults exist only to satisfy the compiler.
  const [year = 0, month = 1, day = 1] = parts.split("-").map(Number);
  return shamsiFromParts(year, month, day);
}

/** Gregorian year, month (1-12) and day, as a Shamsi date. */
export const shamsiFromParts = (
  year: number,
  month: number,
  day: number,
): ShamsiDate => shamsiFromEpochDay(Date.UTC(year, month - 1, day) / 86_400_000);
