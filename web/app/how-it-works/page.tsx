import type { Metadata } from "next";

export const metadata: Metadata = { title: "How it works" };

const STEPS: { name: string; body: string }[] = [
  {
    name: "Crawl",
    body: "A read-only browser visits the site: robots.txt respected, at most one request per second per site, no forms submitted, no private or internal addresses, a page cap. Identical pages are audited once.",
  },
  {
    name: "Rule checks",
    body: "axe-core runs on every page, with results reproduced exactly against Deque’s reference integration. These findings never pass through a model, so a hostile page cannot talk them away.",
  },
  {
    name: "Judgment checks",
    body: "Ramp collects candidates (images with screenshot crops, links with their context, heading-like text, tables, media) and asks a vision model to judge them against fixed WCAG rules. Focus visibility is decided by comparing pixels, not by a model.",
  },
  {
    name: "Merge and prioritise",
    body: "Findings on the same element are merged. Severity and WCAG criterion come from fixed tables, never from model output.",
  },
  {
    name: "Write the fix",
    body: "For each issue, Ramp locates the source line and asks for one minimal exact replacement. Patches may not add scripts, event handlers, new external URLs, or text addressed to automated tools.",
  },
  {
    name: "Prove it",
    body: "Each patch is applied to a copy of the site and re-rendered. It counts as a fix only if the barrier is gone, no new violation appears, and the page still renders. Failed fixes get one more attempt with the failure reason.",
  },
  {
    name: "Human review",
    body: "The audit stops and shows every verified diff. Nothing is published until a person approves specific fixes.",
  },
  {
    name: "Pull request",
    body: "Approved fixes are re-verified together, the target repository’s contribution and AI policies are read first, and one pull request is opened with before-and-after screenshots and a list of what was not checked.",
  },
];

export default function HowItWorks() {
  return (
    <article className="max-w-3xl space-y-12">
      <header className="space-y-4">
        <h1 className="text-4xl font-bold">How it works</h1>
        <p className="text-lg text-slate">
          A LangGraph agent with checkpoints, so an audit survives a crash and can wait for a person.
          Models only judge evidence and propose text; every action is ordinary code in a graph node.
        </p>
      </header>

      <section aria-labelledby="pipeline" className="space-y-6">
        <h2 id="pipeline" className="text-2xl font-bold">
          The pipeline
        </h2>
        <ol className="space-y-6">
          {STEPS.map((step, i) => (
            <li key={step.name} className="grid grid-cols-[2.5rem_1fr] gap-x-4">
              <span aria-hidden="true" className="font-mono text-lg font-bold text-accent">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div>
                <h3 className="text-lg font-bold">{step.name}</h3>
                <p>{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="untrusted" className="space-y-4">
        <h2 id="untrusted" className="text-2xl font-bold">
          Every page is untrusted
        </h2>
        <p>
          A page can contain text written to steer an AI. Ramp treats all page content as data: it
          reaches models inside escaped, delimited blocks; a per-call secret marker detects when a
          model is steered into leaking its instructions; model text is scrubbed of anything
          addressed to tools; and models have no tools at all. The browser itself runs in a
          container with a read-only filesystem, no Linux capabilities, and no route to Ramp’s own
          services.
        </p>
      </section>

      <section aria-labelledby="not-compliance" className="space-y-4">
        <h2 id="not-compliance" className="text-2xl font-bold">
          What a report is not
        </h2>
        <p>
          A Ramp report lists what was checked, what was not, and what was found. It is not a
          statement that a site is compliant with WCAG or the ADA: automated tools cover only part of
          WCAG, and many barriers only show up with a keyboard, a screen reader, or magnification.
        </p>
      </section>
    </article>
  );
}
