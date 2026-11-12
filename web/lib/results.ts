// Build-time access to the repository's measured results (evals/results/*.json).
// Every number on the site comes from these files, written by the eval runner, the comparison
// script, and the load test. A result that does not exist yet is null, and the page says so.
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const RESULTS = path.resolve(process.cwd(), "..", "evals", "results");

function load<T>(rel: string): T | null {
  const file = path.join(RESULTS, rel);
  return existsSync(file) ? (JSON.parse(readFileSync(file, "utf8")) as T) : null;
}

export type Comparison = {
  system: string;
  precision: number;
  recall: number;
  f1: number;
  rule_recall: number | null;
  judgment_recall: number | null;
  model_precision: number | null;
  control_fps: number;
  bad_f1_w3c: number;
  bad_f1_verified: number;
  injection: string;
  fix_rate: number | null;
  fixes: string;
  p50: number;
  p95: number;
  tokens_per_1000: number;
  failed_calls: number;
};

export type Reproduction = {
  axe_version: string;
  exact_match: boolean;
  pages: { page: string; reference_findings: number; ramp_findings: number; exact_match: boolean }[];
};

export type LoadLevel = {
  concurrency: number;
  audits_completed: number;
  errors: number;
  throughput_per_min: number;
  end_to_end_p50_s: number | null;
  end_to_end_p95_s: number | null;
  submit_p95_s: number | null;
};

export type LoadRun = { workers: number; sites: number; levels: LoadLevel[] };

export type RedTeam = {
  failed_model_calls: number;
  adversarial: {
    total: number;
    resisted: number;
    resisted_strict?: number;
    rate_strict?: number | null;
    raw_model_output_clean?: number;
  };
};

export function comparison(): Comparison[] {
  return load<Comparison[]>("comparison.json") ?? [];
}

export function reproduction(): Reproduction | null {
  return load<Reproduction>("bad_reproduction.json");
}

export function loadTests(): { name: string; label: string; run: LoadRun }[] {
  const runs: [string, string][] = [
    ["capacity-1-worker", "1 worker, 1 sandboxed browser"],
    ["capacity-2-workers", "2 workers, 1 sandboxed browser"],
    ["capacity-2-workers-2-browsers", "2 workers, 2 sandboxed browsers"],
    ["politeness-one-host", "Every client auditing the same site"],
  ];
  return runs.flatMap(([name, label]) => {
    const run = load<LoadRun>(`loadtest/${name}.json`);
    return run ? [{ name, label, run }] : [];
  });
}

/** The red-team result, only if it is a valid measurement (every model call answered). */
export function redTeam(): RedTeam | null {
  const run = load<RedTeam>("ramp-agent/adversarial.json");
  return run && run.failed_model_calls === 0 ? run : null;
}

export const fmt = (x: number | null | undefined, digits = 3): string =>
  x === null || x === undefined ? "—" : x.toFixed(digits);
