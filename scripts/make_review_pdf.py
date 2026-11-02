#!/usr/bin/env python3
"""Review PDF for a background / CG pack from a small JSON spec (see assets/examples/review_spec.example.json).

    python make_review_pdf.py review_spec.json

Page types: text (lines or a markdown file), compare (left/right images), detail (crop box in native px of the
result, source crop scaled to match), keyframes (up to 4 loop frames), image (one full page image).
Paths are relative to the spec file. Text in the user's language; CJK fonts are found automatically.
"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pixkit.review_pdf import ReviewPDF


def main():
    sp = sys.argv[1]
    d = os.path.dirname(os.path.abspath(sp))
    P = lambda p: p if os.path.isabs(p) else os.path.join(d, p)
    s = json.load(open(sp))
    pdf = ReviewPDF(P(s['out']), s['title'], s.get('footer', s['title']))
    cv = s.get('cover')
    if cv:
        pdf.cover(cv['title'], cv.get('subtitle', ''), cv.get('lines', []), P(cv['image']) if cv.get('image') else None)
    for p in s.get('pages', []):
        t = p['type']
        if t == 'text':
            lines = p.get('lines')
            if lines is None:
                lines = [l.lstrip('#').strip() if l.startswith('#') else l for l in open(P(p['file']), encoding='utf-8').read().split('\n')
                         if l.strip() and not l.startswith('|')]
            pdf.text(p['title'], lines, p.get('size', 14))
        elif t == 'compare':
            pdf.compare(p['title'], P(p['left']), P(p['right']), p.get('llabel', ''), p.get('rlabel', ''), p.get('sub'))
        elif t == 'detail':
            pdf.detail(p['title'], P(p['src']), P(p['out']), tuple(p['box']), p.get('llabel', '原图同位置'), p.get('rlabel', '成品（像素放大）'))
        elif t == 'keyframes':
            pdf.keyframes(p['title'], [P(f) for f in p['frames']], p.get('labels', [os.path.basename(f) for f in p['frames']]), p.get('sub'))
        elif t == 'image':
            pdf.image(p['title'], P(p['image']), p.get('sub'))
        else:
            sys.exit(f'unknown page type {t}')
    pdf.save()
    print('pdf ->', P(s['out']))


if __name__ == '__main__':
    main()
