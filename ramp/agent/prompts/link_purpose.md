version: 1
Judge whether each link's purpose can be determined (WCAG 2.4.4 Link Purpose (In Context)).

<page_data> lists links with: the accessible name, href, the programmatic context (text of the
enclosing paragraph, list item, or table cell — only this counts as "in context"), the nearest
preceding heading (visual proximity alone does not count as programmatic context), and how many
other links share the same name but go elsewhere.

A link fails when its name, together with its programmatic context, does not identify its
purpose: "click here", "read more", "more", "here", "link" standing alone; file names or codes;
names that are instructions or messages rather than a destination; empty names.
A link passes when the name is descriptive, or when generic text sits inside a sentence or list
item that names the destination ("To download the annual report, click here").
Skip-links and links whose name is clear pass.

Return one item per link you were given, with: cid, purpose_clear, problem (one of "none",
"ambiguous", "filename_or_code", "instruction_not_purpose", "empty"), suggested_text (a better
link name, "" if none needed), confidence (0 to 1), reason (one sentence).
