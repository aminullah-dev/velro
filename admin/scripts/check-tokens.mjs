#!/usr/bin/env node
/**
 * Every CSS variable used must be defined.
 *
 * An undefined custom property does not error -- the declaration is simply
 * dropped, so a mistyped token ships as a missing corner radius or a
 * transparent background that nobody notices until a screenshot.
 */
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

// Several tokens share a line in the palette, so this is not anchored.
const defined = new Set([...css.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]));
const used = new Set([...css.matchAll(/var\((--[\w-]+)/g)].map((m) => m[1]));
const missing = [...used].filter((name) => !defined.has(name)).sort();

if (missing.length) {
  console.error(`undefined CSS variables: ${missing.join(", ")}`);
  process.exit(1);
}
console.log(`css tokens ok (${defined.size} defined, ${used.size} used)`);
