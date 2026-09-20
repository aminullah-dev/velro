// The QR codes the posters carry, as SVG so they print sharp at any size.
// One file per link; re-run this after changing a link in links.md.
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";

// qrcode-generator ships as UMD; give it a CommonJS window to attach to.
const src = readFileSync(new URL("./qrcode.min.js", import.meta.url), "utf8");
const module_ = { exports: {} };
new Function("module", "exports", src)(module_, module_.exports);
const qrcode = module_.exports;

const links = {
  "qr-driver": "https://play.google.com/apps/testing/af.velro.driver",
  "qr-passenger": "https://play.google.com/apps/testing/af.velro.passenger",
};

for (const [name, url] of Object.entries(links)) {
  // Error correction H: a poster on a station wall gets dirty and torn.
  const qr = qrcode(0, "H");
  qr.addData(url);
  qr.make();
  const n = qr.getModuleCount();
  const cells = [];
  for (let r = 0; r < n; r++)
    for (let c = 0; c < n; c++)
      if (qr.isDark(r, c)) cells.push(`M${c} ${r}h1v1h-1z`);
  const quiet = 2;
  const size = n + quiet * 2;
  writeFileSync(`${name}.svg`,
`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" shape-rendering="crispEdges">
<rect width="${size}" height="${size}" fill="#fff"/>
<g transform="translate(${quiet} ${quiet})" fill="#06301F"><path d="${cells.join("")}"/></g>
</svg>
`);
  console.log(`${name}.svg  ${n}x${n} modules  ${url}`);
}
