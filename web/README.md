# web/

The public site for Ramp: Next.js (App Router) exported as static HTML and deployed to GitHub Pages
by `.github/workflows/pages.yml`. Every number on it is read at build time from
`../evals/results/*.json`; a result that has not been measured is shown as not measured.

```bash
npm ci
NEXT_PUBLIC_BASE_PATH="" npm run dev   # http://localhost:3000
npm run check:contrast                 # WCAG AA for every token pair, light and dark
npm run lint && npm run typecheck && npm run build   # static site in out/
```

Accessibility: semantic landmarks and headings, a skip link, visible focus everywhere, status
shown with an icon and a word (never colour alone), tables that scroll inside a focusable
region on small screens, `prefers-reduced-motion` and `prefers-color-scheme` respected. The built
site is audited with Ramp itself before release.
