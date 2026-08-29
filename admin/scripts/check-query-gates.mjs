/**
 * Every page that fetches a list must route its query state through `gate`.
 *
 * The hand-written guard that used to be in every page --
 *
 *     if (query.isLoading) return <Loading />;
 *     if (query.error) return <ErrorState ... />;
 *
 * -- misses the state TanStack Query actually settles into when a request
 * fails and the connection looks down: paused, with `status` still "pending",
 * `error` still null and `isLoading` false. Both guards fall through, the page
 * renders `data ?? []`, and the operator is told the list is empty when the
 * panel cannot reach the server at all. In Ghorband that is not an edge case,
 * and "no drivers waiting" is the one answer that must never be a lie.
 */
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const pages = resolve(here, "../src/pages");

const failures = [];
let checked = 0;

for (const name of readdirSync(pages)) {
  if (!name.endsWith(".tsx")) continue;
  const source = readFileSync(join(pages, name), "utf8");
  if (!source.includes("useQuery(")) continue;
  checked += 1;

  if (!source.includes("gate(")) {
    failures.push(`${name}: fetches with useQuery but never calls gate()`);
  }
  // The old shape, in any spelling.
  const handRolled = /if \(\s*\w*\.?isLoading\s*\)\s*return\s*<Loading/.exec(source);
  if (handRolled) {
    failures.push(
      `${name}: hand-written loading guard "${handRolled[0]}" -- use gate() instead, `
        + "it also handles the paused state",
    );
  }
}

if (failures.length) {
  console.error("query state is not gated:");
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log(`query gates ok: ${checked} pages fetch, all gated`);
