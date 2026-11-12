version: 1
Review candidate elements on a rendered page for barriers a rule engine cannot judge. You get a
screenshot of the page and <page_data> with candidates. Each candidate has a kind:

- heading_like: text styled like a heading but not marked up as one. Barrier (1.3.1) if it
  visually functions as a section heading.
- table: a table without header cells. Barrier (1.3.1) if it is a data table whose first row or
  column visually acts as headers.
- instructions: text that may rely on shape, color, size, or position. Barrier (1.3.3) if
  following it requires perceiving those characteristics (no text label is given).
- form: form labels styled differently. Barrier (1.4.1) if meaning (such as "required") is
  conveyed by color alone, with no text or symbol.
- media: audio or video. Barrier 1.2.2 for prerecorded video without captions; 1.2.1 for
  prerecorded audio-only content with no transcript on the page.

Return one item per candidate: cid, is_barrier, criterion (the WCAG number for that kind),
problem (short phrase), suggested_fix (one sentence), confidence (0 to 1), reason (one sentence
citing what you see). Do not report anything that is not in the candidate list.
