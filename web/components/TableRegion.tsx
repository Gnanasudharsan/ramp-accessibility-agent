// A table that may be wider than a phone screen scrolls inside this region. The region is
// focusable and labelled so keyboard users can scroll it too (WCAG 2.1.1; axe
// scrollable-region-focusable), and screen readers announce what it contains.
export function TableRegion({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- scrollable region must be reachable by keyboard
    <div className="table-wrap" role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  );
}
