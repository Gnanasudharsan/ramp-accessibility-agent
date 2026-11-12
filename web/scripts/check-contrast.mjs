// Fails if any text/background token pair used by the UI is below WCAG 2.2 AA (4.5:1 for text,
// 3:1 for focus rings and borders that carry meaning). Tokens are read from app/globals.css, so
// a palette change cannot silently break contrast.
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

function block(selector) {
  const start = css.indexOf(selector);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
  return Object.fromEntries([...body.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]));
}

function luminance(hex) {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const l = c.map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2];
}

function ratio(a, b) {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

const TEXT = ["ink", "slate", "accent", "pass", "fail", "warning", "info"];
const BACKGROUNDS = ["paper", "surface"];
const themes = { light: block(":root {"), dark: block(':root[data-theme="dark"]') };
let failures = 0;
for (const [theme, t] of Object.entries(themes)) {
  for (const fg of TEXT) {
    for (const bg of BACKGROUNDS) {
      const r = ratio(t[fg], t[bg]);
      const ok = r >= 4.5;
      if (!ok) failures += 1;
      console.log(`${ok ? "pass" : "FAIL"}  ${theme.padEnd(5)} ${fg.padEnd(7)} on ${bg.padEnd(7)} ${r.toFixed(2)}:1`);
    }
  }
  for (const bg of BACKGROUNDS) {
    const r = ratio(t.focus, t[bg]);
    if (r < 3) failures += 1;
    console.log(`${r >= 3 ? "pass" : "FAIL"}  ${theme.padEnd(5)} focus   on ${bg.padEnd(7)} ${r.toFixed(2)}:1 (needs 3:1)`);
  }
}
process.exit(failures ? 1 : 0);
