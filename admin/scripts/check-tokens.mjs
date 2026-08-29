#!/usr/bin/env node
/**
 * Every CSS variable used must be defined.
 *
 * An undefined custom property does not error -- the declaration is simply
 * dropped, so a mistyped token ships as a missing corner radius or a
 * transparent background that nobody notices until a screenshot.
 */
import { readFileSync, readdirSync } from "node:fs";

const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

// Several tokens share a line in the palette, so this is not anchored.
const defined = new Set([...css.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]));
const used = new Set([...css.matchAll(/var\((--[\w-]+)/g)].map((m) => m[1]));
const missing = [...used].filter((name) => !defined.has(name)).sort();

if (missing.length) {
  console.error(`undefined CSS variables: ${missing.join(", ")}`);
  process.exit(1);
}

/**
 * Every className the pages use must exist too.
 *
 * An unknown class is not an error either -- the element simply renders
 * unstyled, which looks like a layout bug rather than a typo. Only single-word
 * literal classNames are checked; anything built from a template string is
 * beyond a regex and is left alone.
 */
const classes = new Set([...css.matchAll(/\.([a-z][\w-]*)\s*[{,:]/g)].map((m) => m[1]));
const pages = readdirSync(new URL("../src/pages", import.meta.url));
const components = readdirSync(new URL("../src/components", import.meta.url));
const sources = [
  ...pages.map((f) => new URL(`../src/pages/${f}`, import.meta.url)),
  ...components.map((f) => new URL(`../src/components/${f}`, import.meta.url)),
];

const unknown = new Set();
for (const file of sources) {
  const text = readFileSync(file, "utf8");
  for (const [, value] of text.matchAll(/className="([a-z][\w\s-]*)"/g)) {
    for (const name of value.trim().split(/\s+/)) {
      if (name && !classes.has(name)) unknown.add(name);
    }
  }
}
if (unknown.size) {
  console.error(`classNames with no CSS rule: ${[...unknown].sort().join(", ")}`);
  process.exit(1);
}
console.log(
  `css ok (${defined.size} vars, ${classes.size} classes; ${used.size} vars used)`,
);
