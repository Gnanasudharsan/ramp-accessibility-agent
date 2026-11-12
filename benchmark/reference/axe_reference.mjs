// Reference runner: Deque's @axe-core/playwright with the same tags Ramp uses.
// Usage: node axe_reference.mjs <url> [<url> ...]   -> JSON on stdout
// Off-origin requests are blocked so results match Ramp's offline eval runs.
import { chromium } from "playwright";
import { AxeBuilder } from "@axe-core/playwright";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];
const urls = process.argv.slice(2);
const browser = await chromium.launch({ headless: true });
const out = [];
for (const url of urls) {
  const origin = new URL(url).origin;
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: "reduce" });
  await context.route("**/*", (route) => {
    const req = route.request();
    const same = new URL(req.url()).origin === origin;
    return same && ["GET", "HEAD"].includes(req.method()) ? route.continue() : route.abort("blockedbyclient");
  });
  const page = await context.newPage();
  await page.goto(url, { waitUntil: "load" });
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  out.push({
    url,
    axe_version: results.testEngine.version,
    violations: results.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      targets: v.nodes.map((n) => n.target),
    })),
  });
  await context.close();
}
await browser.close();
process.stdout.write(JSON.stringify(out, null, 2));
