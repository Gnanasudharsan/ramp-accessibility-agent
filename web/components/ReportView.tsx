// Renders a Ramp AuditReport (report schema 1.x): issues grouped by WCAG criterion, then what was
// and was not checked. Used for the sample report; the same component can render a live audit.
import { Status } from "@/components/Status";
import wcag from "@/data/wcag.json";

type Issue = {
  id: string;
  rule_id: string;
  title: string;
  criteria: string[];
  severity: "critical" | "serious" | "moderate" | "minor";
  selector: string;
  source: "rule" | "vision" | "both";
  help_url?: string | null;
  suggested_fix?: string | null;
  evidence: { html_snippet?: string; failure_summary?: string };
};

export type Report = {
  target: string;
  finished_at: string;
  ramp_version: string;
  pages: { url: string; title?: string | null; issues: Issue[] }[];
  coverage: {
    axe_version: string;
    criteria_checked: string[];
    criteria_not_checked: string[];
  };
  disclaimer: string;
};

const CRITERIA = wcag as Record<string, { name: string; level: string; in_target: boolean }>;

const SEVERITY = {
  critical: "fail",
  serious: "fail",
  moderate: "warning",
  minor: "info",
} as const;

const SOURCE = { rule: "Rule engine", vision: "Model judgment", both: "Rule and model" };

function criterionLabel(id: string): string {
  const c = CRITERIA[id];
  return c ? `${id} ${c.name} (Level ${c.level})` : id;
}

export function ReportView({ report }: { report: Report }) {
  const issues = report.pages.flatMap((p) => p.issues);
  const groups = new Map<string, Issue[]>();
  for (const issue of issues) {
    const key = issue.criteria[0] ?? "best-practice";
    groups.set(key, [...(groups.get(key) ?? []), issue]);
  }
  const ordered = [...groups.entries()].sort(([a], [b]) =>
    a.localeCompare(b, undefined, { numeric: true }),
  );
  const bySeverity = issues.reduce<Record<string, number>>((acc, i) => {
    acc[i.severity] = (acc[i.severity] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-12">
      <section aria-labelledby="summary" className="space-y-4">
        <h2 id="summary" className="text-2xl font-bold">
          Summary
        </h2>
        <dl className="grid max-w-xl grid-cols-[max-content_1fr] gap-x-6 gap-y-2">
          <dt className="text-slate">Audited</dt>
          <dd className="break-all">{report.target}</dd>
          <dt className="text-slate">Pages</dt>
          <dd>{report.pages.length}</dd>
          <dt className="text-slate">Issues</dt>
          <dd>
            {issues.length} ({["critical", "serious", "moderate", "minor"]
              .filter((s) => bySeverity[s])
              .map((s) => `${bySeverity[s]} ${s}`)
              .join(", ")}
            )
          </dd>
          <dt className="text-slate">Criteria checked</dt>
          <dd>
            {report.coverage.criteria_checked.length} automatically, {" "}
            {report.coverage.criteria_not_checked.length} need manual testing
          </dd>
          <dt className="text-slate">Engine</dt>
          <dd>
            Ramp {report.ramp_version}, axe-core {report.coverage.axe_version}
          </dd>
        </dl>
        <p className="max-w-3xl border-l-4 border-warning pl-4">
          <Status kind="warning">Not a compliance statement</Status> {report.disclaimer}
        </p>
      </section>

      <section aria-labelledby="findings" className="space-y-8">
        <h2 id="findings" className="text-2xl font-bold">
          Findings by WCAG criterion
        </h2>
        {ordered.map(([criterion, list]) => (
          <section key={criterion} aria-labelledby={`c-${criterion}`} className="space-y-3">
            <h3 id={`c-${criterion}`} className="text-xl font-bold">
              {criterion === "best-practice" ? "Best practice (no WCAG criterion)" : criterionLabel(criterion)}{" "}
              <span className="font-normal text-slate">· {list.length}</span>
            </h3>
            <ul className="divide-y divide-line rounded-md border border-line bg-surface">
              {list.map((issue) => (
                <li key={issue.id} className="space-y-2 p-4">
                  <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <Status kind={SEVERITY[issue.severity]}>
                      {issue.severity[0].toUpperCase() + issue.severity.slice(1)}
                    </Status>
                    <span className="font-semibold">{issue.title}</span>
                    <span className="text-sm text-slate">{SOURCE[issue.source]}</span>
                  </p>
                  {issue.evidence.html_snippet && (
                    <pre className="whitespace-pre-wrap break-all rounded bg-paper p-3 font-mono text-sm">
                      <code>{issue.evidence.html_snippet}</code>
                    </pre>
                  )}
                  {issue.help_url && (
                    <p className="text-sm">
                      <a href={issue.help_url}>
                        How to fix: {issue.rule_id}
                        <span className="sr-only"> (Deque University)</span>
                      </a>
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </section>

      <section aria-labelledby="not-checked" className="space-y-4">
        <h2 id="not-checked" className="text-2xl font-bold">
          Not checked automatically
        </h2>
        <p className="max-w-3xl">
          These WCAG 2.2 criteria need a person: keyboard use, screen readers, magnification, and
          judgment about content.
        </p>
        <ul className="columns-1 gap-8 sm:columns-2">
          {report.coverage.criteria_not_checked.map((id) => (
            <li key={id} className="break-inside-avoid py-0.5">
              {criterionLabel(id)}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
