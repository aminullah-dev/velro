// The locale files are the backend's. Copying them rather than keeping a second
// set is what makes "one key set, three surfaces" true: a key added on the
// server cannot be missing here, and no sentence is written twice.
import { cp, mkdir, readdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = join(here, "..", "..", "backend", "resources", "locales");
const target = join(here, "..", "public", "locales");

await mkdir(target, { recursive: true });
const files = (await readdir(source)).filter((name) => name.endsWith(".json"));
for (const name of files) {
  await cp(join(source, name), join(target, name));
}
console.log(`locales synced: ${files.join(", ")}`);
