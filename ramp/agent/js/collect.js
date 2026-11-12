// Candidate collection for judgment-based checks. Wrapped as `(maxImages) => { cssPath; <this> }`.
// Read-only: reads the DOM and computed styles, never mutates the page.

  const clean = (t, n = 300) => (t || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const box = (el) => { const r = el.getBoundingClientRect();
    return {x: r.x + scrollX, y: r.y + scrollY, width: r.width, height: r.height}; };
  const visible = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const outer = (el) => el.outerHTML.slice(0, 600);
  const contextOf = (el) => { const c = el.closest('p, li, td, th, dd'); return c ? clean(c.innerText) : ''; };
  const headingBefore = (el) => {
    const hs = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role=heading]'));
    let last = '';
    for (const h of hs) { if (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) last = clean(h.innerText, 120); }
    return last;
  };
  const nameOf = (el) => {
    if (el.getAttribute('aria-label')) return clean(el.getAttribute('aria-label'));
    const lb = el.getAttribute('aria-labelledby');
    if (lb) return clean(lb.split(/\s+/).map(id => (document.getElementById(id) || {}).innerText || '').join(' '));
    const parts = [];
    el.childNodes.forEach(n => {
      if (n.nodeType === 3) parts.push(n.textContent);
      else if (n.nodeType === 1 && n.localName === 'img') parts.push(n.getAttribute('alt') || '');
      else if (n.nodeType === 1 && getComputedStyle(n).display !== 'none') parts.push(n.innerText || nameOf(n));
    });
    return clean(parts.join(' ')) || clean(el.getAttribute('title'));
  };

  const images = [];
  for (const img of document.querySelectorAll('img, input[type=image]')) {
    if (!visible(img) || images.length >= maxImages) continue;
    const link = img.closest('a[href]');
    const src = img.getAttribute('src') || '';
    images.push({
      selector: cssPath(img), html: outer(img),
      alt: img.hasAttribute('alt') ? img.getAttribute('alt') : null,
      src_file: src.split('?')[0].split('/').pop(),
      in_link: !!link, link_href: link ? link.getAttribute('href') : null,
      link_text: link ? clean(link.innerText, 120) : '',
      nearby_text: clean((img.parentElement || img).innerText || '', 200) || contextOf(img),
      box: box(img),
    });
  }

  const links = [];
  const byName = {};
  const anchors = Array.from(document.querySelectorAll('a[href]')).filter(a => visible(a) && !a.closest('nav'));
  for (const a of anchors) {
    const name = nameOf(a);
    (byName[name.toLowerCase()] = byName[name.toLowerCase()] || new Set()).add(a.getAttribute('href'));
  }
  for (const a of anchors.slice(0, 40)) {
    const name = nameOf(a);
    links.push({
      selector: cssPath(a), html: outer(a), name, href: a.getAttribute('href'),
      context: contextOf(a), heading: headingBefore(a),
      same_name_other_targets: (byName[name.toLowerCase()] || new Set()).size - 1,
    });
  }

  const structure = [];
  const bodySize = parseFloat(getComputedStyle(document.body).fontSize) || 16;
  for (const el of document.querySelectorAll('body *')) {
    if (structure.length >= 25) break;
    if (!visible(el) || el.closest('h1,h2,h3,h4,h5,h6,[role=heading],a,button,label,nav,footer,table')) continue;
    const s = getComputedStyle(el);
    const ownText = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent).join(' ').trim();
    const size = parseFloat(s.fontSize);
    const bold = parseInt(s.fontWeight, 10) >= 600 || ['B', 'STRONG'].includes(el.firstElementChild?.tagName);
    if (ownText && ownText.length < 80 && !/[.:]$/.test(ownText) && (size >= bodySize * 1.25 || (bold && size >= bodySize * 1.15)))
      structure.push({selector: cssPath(el), kind: 'heading_like', html: outer(el), text: clean(ownText, 120),
                      details: {font_size_px: size, font_weight: s.fontWeight, body_font_px: bodySize}});
  }
  for (const t of document.querySelectorAll('table')) {
    if (t.querySelector('th') || t.getAttribute('role') === 'presentation') continue;
    structure.push({selector: cssPath(t), kind: 'table', html: outer(t), text: clean(t.innerText, 300),
                    details: {rows: t.rows.length}});
  }
  for (const m of document.querySelectorAll('video, audio')) {
    const near = clean((m.parentElement || m).innerText, 300);
    structure.push({selector: cssPath(m), kind: 'media', html: outer(m), text: near,
                    details: {element: m.localName,
                              caption_tracks: m.querySelectorAll('track[kind=captions], track[kind=subtitles]').length,
                              mentions_transcript: /transcript/i.test(document.body.innerText)}});
  }
  const sensory = /\b(left|right|above|below|round|square|circle|green|red|blue|yellow|color|colour|top|bottom|shape)\b/i;
  for (const p of document.querySelectorAll('p, li, span, div')) {
    const t = clean(Array.from(p.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent).join(' '));
    if (t.length > 15 && t.length < 300 && sensory.test(t) && /\b(click|press|select|tap|choose|use|fields?|button|see|required)\b/i.test(t))
      structure.push({selector: cssPath(p), kind: 'instructions', html: outer(p), text: t, details: {}});
  }
  for (const f of document.querySelectorAll('form')) {
    const labels = Array.from(f.querySelectorAll('label')).map(l => ({text: clean(l.innerText, 60), color: getComputedStyle(l).color, weight: getComputedStyle(l).fontWeight}));
    const colors = new Set(labels.map(l => l.color));
    if (labels.length >= 2 && colors.size > 1)
      structure.push({selector: cssPath(f), kind: 'form', html: outer(f), text: clean(f.innerText, 300),
                      details: {labels, intro: clean((f.previousElementSibling || {}).innerText || '', 200)}});
  }
  return {images, links, structure};
