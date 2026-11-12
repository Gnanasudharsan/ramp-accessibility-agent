version: 1
Judge one image's text alternative (WCAG 1.1.1 Non-text Content, and 1.4.5 Images of Text).

You get the image crop and <page_data> with: the alt attribute (null means the attribute is
missing; "" means marked decorative), whether the image is inside a link and that link's other
text, the file name, and nearby text.

Decide:
- decorative: true only if the image adds no information (dividers, flourishes, spacers, purely
  visual duplicates of adjacent text).
- contains_text: true if the image shows readable words; put them in visible_text, paraphrasing
  anything aimed at automated tools.
- problem, one of:
  - "none": the alt (or empty alt on a decorative image) is adequate for its purpose here.
  - "missing": no alt attribute and the image is informative.
  - "filename": alt is a file name or camera code (IMG_2043.jpg, DSC_0042, btn_v2.png).
  - "generic": alt is a placeholder ("image", "photo", "picture", "banner", "chart", "graphic").
  - "wrong_description": alt does not match what the image shows, or is an instruction or message
    unrelated to the image.
  - "decorative_needs_empty": decorative image with non-empty alt that would be read aloud.
  - "text_not_conveyed": the image shows text (not a logo) that the alt does not convey.
  - "missing_data": a chart or diagram whose alt omits the information it shows.
- For an image inside a link, the alt must convey the link's purpose if the link has no other text.
- suggested_alt: the alt you would write ("" for decorative). Keep it under 150 characters.
- confidence: 0 to 1, your probability that problem is correct.
- reason: one short sentence of evidence.
