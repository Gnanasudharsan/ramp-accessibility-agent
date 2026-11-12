// Status is never colour alone: an icon (hidden from assistive tech) plus a word.
type Kind = "pass" | "fail" | "warning" | "info";

const ICONS: Record<Kind, string> = {
  pass: "M4 10.5 8 14.5 16 6",
  fail: "M5 5 15 15M15 5 5 15",
  warning: "M10 4v7M10 15v.5",
  info: "M10 9v6M10 5.5v.5",
};

const COLOR: Record<Kind, string> = {
  pass: "text-pass",
  fail: "text-fail",
  warning: "text-warning",
  info: "text-info",
};

export function Status({ kind, children }: { kind: Kind; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1.5 font-semibold ${COLOR[kind]}`}>
      <svg aria-hidden="true" viewBox="0 0 20 20" width="16" height="16" className="shrink-0">
        <path d={ICONS[kind]} fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {children}
    </span>
  );
}
