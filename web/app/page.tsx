import Link from "next/link";

import { Status } from "@/components/Status";
import { TableRegion } from "@/components/TableRegion";
import { comparison, fmt, redTeam } from "@/lib/results";

export default function Home() {
  const rows = comparison();
  const axe = rows.find((r) => r.system === "axe-baseline");
  const agent = rows.find((r) => r.system === "ramp-agent");
  const injection = redTeam();

  return (
    <article className="space-y-16">
      <section aria-labelledby="intro" className="max-w-3xl space-y-6">
        <h1 id="intro" className="text-4xl font-bold leading-tight sm:text-5xl">
          Finds accessibility barriers, writes the fix, and proves it works.
        </h1>
        <p className="text-lg text-slate">
          Ramp crawls a site in a sandboxed browser, runs the axe-core rule engine, then asks vision
          models about the barriers rules cannot judge: alt text that says nothing, links that only
          say “click here”, text baked into images, focus you cannot see. It writes a minimal source
          patch for each one, re-renders the page to check the patch worked, and opens a pull request
          only after a person approves the exact diff.
        </p>
        <p>
          <Link href="/results/">See the measured results</Link> ·{" "}
          <Link href="/how-it-works/">How it works</Link> ·{" "}
          <Link href="/report/">A real report</Link>
        </p>
      </section>

      {axe && agent && (
        <section aria-labelledby="gap" className="space-y-6">
          <h2 id="gap" className="text-2xl font-bold">
            What rule engines miss
          </h2>
          <p className="max-w-3xl">
            On Ramp’s benchmark of 37 labelled pages, axe-core alone finds every barrier a rule can
            decide, and none of the 21 that need judgment. The agent closes that gap while keeping
            precision above the bar set before the first run (ADR 0005).
          </p>
          <TableRegion label="Benchmark comparison">
            <table>
              <caption>
                Synthetic benchmark, 37 pages. Source: evals/results/comparison.json
              </caption>
              <thead>
                <tr>
                  <th scope="col">Measure</th>
                  <th scope="col" className="num">
                    axe-core only
                  </th>
                  <th scope="col" className="num">
                    Ramp agent
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">Recall on barriers that need judgment</th>
                  <td className="num">{fmt(axe.judgment_recall)}</td>
                  <td className="num">{fmt(agent.judgment_recall)}</td>
                </tr>
                <tr>
                  <th scope="row">Recall on barriers a rule can decide</th>
                  <td className="num">{fmt(axe.rule_recall)}</td>
                  <td className="num">{fmt(agent.rule_recall)}</td>
                </tr>
                <tr>
                  <th scope="row">Precision, all findings</th>
                  <td className="num">{fmt(axe.precision)}</td>
                  <td className="num">{fmt(agent.precision)}</td>
                </tr>
                <tr>
                  <th scope="row">F1, all findings</th>
                  <td className="num">{fmt(axe.f1)}</td>
                  <td className="num">{fmt(agent.f1)}</td>
                </tr>
                <tr>
                  <th scope="row">False positives on clean control pages</th>
                  <td className="num">{axe.control_fps}</td>
                  <td className="num">{agent.control_fps}</td>
                </tr>
                <tr>
                  <th scope="row">Fixes that passed verification</th>
                  <td className="num">—</td>
                  <td className="num">{agent.fixes}</td>
                </tr>
              </tbody>
            </table>
          </TableRegion>
        </section>
      )}

      <section aria-labelledby="limits" className="max-w-3xl space-y-4">
        <h2 id="limits" className="text-2xl font-bold">
          Where it still falls short
        </h2>
        <ul className="list-disc space-y-3 pl-6">
          {agent && (
            <li>
              <Status kind="warning">Prompt injection</Status>{" "}
              {injection ? (
                <>
                  With Phase 4 defences, {injection.adversarial.resisted_strict} of{" "}
                  {injection.adversarial.total} hostile pages were resisted under the strict measure.
                </>
              ) : (
                <>
                  Before Phase 4’s defences the agent resisted {agent.injection} hostile pages. The
                  defended measurement is still running on free-tier model quota and will appear here
                  when every model call has been answered.
                </>
              )}
            </li>
          )}
          {agent && (
            <li>
              <Status kind="warning">W3C demo site</Status> On the W3C Before-and-After pages the
              agent did not beat axe-core (F1 {fmt(agent.bad_f1_w3c)} vs {fmt(axe?.bad_f1_w3c)}),
              because most of its model calls there hit free-tier rate limits and were skipped.
            </li>
          )}
          {agent && (
            <li>
              <Status kind="info">Speed</Status> A judged page takes about {Math.round(agent.p50)} s
              (median) on free-tier models; the rule-only audit takes under a second.
            </li>
          )}
          <li>
            <Status kind="info">Scope</Status> Fix verification works for static sites whose
            repository is the served root. Framework apps need a build step first.
          </li>
        </ul>
      </section>
    </article>
  );
}
