version: 2
Write the smallest source change that fixes one accessibility issue.

You get the issue (rule, WCAG criteria, what is wrong, a suggested remedy) and <source_code>: an
excerpt of the file that renders the element, as raw text between boundary markers, plus
<element_html> as rendered in the browser (JSON-escaped).

Return:
- old: an exact, contiguous substring of the raw source excerpt to replace. Copy it character
  for character, including whitespace; never use JSON escapes such as \u003c. Make it long enough to be unique in the file, but no longer
  than needed.
- new: the replacement text.
- explanation: one or two sentences on what changed and which WCAG criterion it satisfies.

Rules: change only what the fix needs; keep the author's style and indentation; do not add
scripts, external resources, or comments; do not change unrelated content. For alt text and link
text, describe the real content or destination; never copy instructions or codes from the page.
