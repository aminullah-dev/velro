/**
 * The TypeScript calendar against the shared specification.
 *
 * `docs/domain/calendar.json` is checked by the Kotlin implementation too. The
 * driver reads a date in the app and quotes it to an operator reading the
 * panel; if the two calendars disagree, the operator is looking for a booking
 * on the wrong day and neither of them can tell why.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const specPath = resolve(here, "../../docs/domain/calendar.json");
const spec = JSON.parse(readFileSync(specPath, "utf8"));

const { shamsiFromParts, isShamsiLeap, shamsiMonthLength } = await import(
  resolve(here, "../src/i18n/calendar.ts")
);

const failures = [];
const check = (ok, message) => { if (!ok) failures.push(message); };
const parse = (iso) => iso.split("-").map(Number);
const asDay = (iso) => Date.UTC(...[parse(iso)[0], parse(iso)[1] - 1, parse(iso)[2]]) / 86_400_000;

for (const [year, iso] of Object.entries(spec.nowruz)) {
  const got = shamsiFromParts(...parse(iso));
  check(
    got.year === Number(year) && got.month === 1 && got.day === 1,
    `Nowruz ${year} (${iso}) came out as ${got.year}-${got.month}-${got.day}, not 1 Hamal ${year}`,
  );
}

// The definition, not a second opinion: Nowruz dates 366 days apart mean the
// year between them had a leap day, whatever any cycle rule says.
const years = Object.keys(spec.nowruz).map(Number).sort((a, b) => a - b);
let spans = 0;
for (const year of years) {
  // The table has gaps -- only years whose successor is also listed can be
  // measured this way.
  const next = spec.nowruz[String(year + 1)];
  if (!next) continue;
  spans += 1;
  const span = asDay(next) - asDay(spec.nowruz[String(year)]);
  check(
    span === (isShamsiLeap(year) ? 366 : 365),
    `year ${year} spans ${span} days but isShamsiLeap says ${isShamsiLeap(year)}`,
  );
}

for (const [year, leap] of Object.entries(spec.leap_years)) {
  if (year.startsWith("$")) continue;
  check(isShamsiLeap(Number(year)) === leap, `leap for ${year}: expected ${leap}`);
}

for (const { gregorian, shamsi, note } of spec.conversions) {
  const [year, month, day] = shamsi;
  const got = shamsiFromParts(...parse(gregorian));
  check(
    got.year === year && got.month === month && got.day === day,
    `${gregorian} (${note}): got ${got.year}-${got.month}-${got.day}, expected ${year}-${month}-${day}`,
  );
}

// Every year must be 365 or 366 days, or a month boundary is wrong somewhere.
for (let year = 1390; year <= 1430; year += 1) {
  let total = 0;
  for (let month = 1; month <= 12; month += 1) total += shamsiMonthLength(year, month);
  check(
    total === (isShamsiLeap(year) ? 366 : 365),
    `year ${year} month lengths sum to ${total}`,
  );
}

if (failures.length) {
  console.error("calendar does not match docs/domain/calendar.json:");
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log(
  `calendar ok: ${spec.conversions.length} conversions, ${years.length} Nowruz dates, `
    + `${spans} measured year lengths`,
);
