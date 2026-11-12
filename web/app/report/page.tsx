import type { Metadata } from "next";

import { type Report, ReportView } from "@/components/ReportView";
import sample from "@/data/sample-report.json";

export const metadata: Metadata = { title: "Sample report" };

export default function SampleReport() {
  return (
    <article className="space-y-10">
      <header className="max-w-3xl space-y-4">
        <h1 className="text-4xl font-bold">Sample report</h1>
        <p className="text-lg text-slate">
          A real rule-engine audit of the W3C’s deliberately inaccessible demo home page, produced
          by <code className="font-mono">ramp audit</code> and shown unedited apart from removing
          local file paths and screenshots.
        </p>
      </header>
      <ReportView report={sample as unknown as Report} />
    </article>
  );
}
