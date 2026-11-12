import Link from "next/link";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/results/", label: "Results" },
  { href: "/how-it-works/", label: "How it works" },
  { href: "/report/", label: "Sample report" },
];

export function SiteHeader() {
  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-8 gap-y-3 px-4 py-4">
        <Link href="/" className="text-xl font-bold text-ink no-underline">
          Ramp
        </Link>
        <nav aria-label="Main">
          <ul className="flex flex-wrap gap-x-6 gap-y-2">
            {NAV.map((item) => (
              <li key={item.href}>
                <Link href={item.href} className="text-ink">
                  {item.label}
                </Link>
              </li>
            ))}
            <li>
              <a href="https://github.com/Gnanasudharsan/ramp-accessibility-agent" className="text-ink">
                Source on GitHub
              </a>
            </li>
          </ul>
        </nav>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-line">
      <div className="mx-auto max-w-5xl space-y-2 px-4 py-8 text-sm text-slate">
        <p>
          Ramp never claims a site is compliant. Automated checks find only part of WCAG barriers;
          test with a keyboard and a screen reader too.
        </p>
        <p>
          Built by Gnanasudharsan Ashokumar · MIT licence · Every number on this site is produced by
          code in the{" "}
          <a href="https://github.com/Gnanasudharsan/ramp-accessibility-agent">repository</a>.
        </p>
      </div>
    </footer>
  );
}
