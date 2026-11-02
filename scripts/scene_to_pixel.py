#!/usr/bin/env python3
"""Concept image -> native pixel-art scene, in two stages so hand fixes can happen in between.

Stage 1 (stylize):  python scene_to_pixel.py concept.png OUT --name BG01
    writes OUT/BG01_stylized.png     hand-drawn simplification at native size, UNGRADED (edit / fix this one)
           OUT/BG01_native.png       the area-resized source (use it for ramp_paint light / masks / comparisons)
           OUT/BG01_protected.png    pixels stylize kept unflattened (bright features + thin lines) - check for
                                     spurious lines (ridge / shore edges) and inpaint them, or --no-protect-lines
           OUT/BG01_compare.png      source vs stylized, side by side
Stage 2 (finish):   python scene_to_pixel.py OUT/BG01_fixed.png OUT --name BG01 --finish
    writes OUT/BG01.png              graded + vignette + palette-locked still (the deliverable)
           OUT/BG01_1920.png         exact 3x nearest upscale
           OUT/BG01_palette.json     the final palette
Use --all to run both stages without a pause (quick look).
"""
import argparse
import json
import os
import sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pixkit import scene as SC
from pixkit.palette import unique_colors


def box(s):
    return tuple(int(v) for v in s.split(','))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('out')
    ap.add_argument('--name', required=True)
    ap.add_argument('--size', default='640x360')
    ap.add_argument('--finish', action='store_true', help='src is an already stylized/fixed native image: only grade + lock')
    ap.add_argument('--all', action='store_true', help='stylize and finish in one go')
    ap.add_argument('--smooth', default=None, help='mean-shift "spatial,colour" before resizing noisy sources, e.g. 6,12')
    ap.add_argument('--stylize-colors', type=int, default=22)
    ap.add_argument('--scale', type=int, default=400, help='object scale for flattening (bigger = flatter, try 600)')
    ap.add_argument('--tones', type=int, default=3, help='tones kept per object (2 = flatter, 4 for dark interiors)')
    ap.add_argument('--min-island', type=int, default=12)
    ap.add_argument('--keep', action='append', default=[], type=box, help='x0,y0,x1,y1 prop box kept unflattened (repeatable)')
    ap.add_argument('--no-protect-lines', action='store_true', help='do not protect thin elongated lines')
    ap.add_argument('--reserve', type=int, default=3, help='extra stylize palette slots for small bright features')
    ap.add_argument('--reserve-final', type=int, default=2, help='final palette slots kept for small bright features (0 = off)')
    ap.add_argument('--grade', default='cold_dusk', choices=list(SC.GRADES))
    ap.add_argument('--colors', type=int, default=24)
    ap.add_argument('--no-vignette', action='store_true')
    ap.add_argument('--review-scale', type=int, default=3)
    a = ap.parse_args()
    W, H = (int(v) for v in a.size.split('x'))
    os.makedirs(a.out, exist_ok=True)
    src = np.array(Image.open(a.src).convert('RGB'))
    if not a.finish:
        smooth = tuple(int(v) for v in a.smooth.split(',')) if a.smooth else None
        nat = SC.to_native(src, (W, H), smooth)
        t, pal, feat = SC.stylize(nat, k=a.stylize_colors, scale=a.scale, ntones=a.tones, min_island=a.min_island, keep_boxes=a.keep,
                                  protect_lines=not a.no_protect_lines, reserve=a.reserve)
        Image.fromarray(t).save(os.path.join(a.out, f'{a.name}_stylized.png'))
        Image.fromarray(nat).save(os.path.join(a.out, f'{a.name}_native.png'))
        Image.fromarray((feat * 255).astype(np.uint8)).save(os.path.join(a.out, f'{a.name}_protected.png'))
        cmp_ = np.concatenate([nat, np.full((H, 8, 3), 24, np.uint8), t], 1)
        Image.fromarray(SC.upscale(cmp_, 2)).save(os.path.join(a.out, f'{a.name}_compare.png'))
        print(f'stylized: {len(unique_colors(t))} colours, {int(feat.sum())} protected feature px -> {a.name}_stylized.png')
        if not a.all:
            return
        src = t
    if src.shape[:2] != (H, W):
        sys.exit(f'--finish expects a native {W}x{H} image, got {src.shape[1]}x{src.shape[0]}')
    fin = SC.finish(src, grade=a.grade, k=a.colors, vig=not a.no_vignette, reserve=a.reserve_final)
    Image.fromarray(fin).save(os.path.join(a.out, f'{a.name}.png'))
    Image.fromarray(SC.upscale(fin, a.review_scale)).save(os.path.join(a.out, f'{a.name}_{W * a.review_scale}.png'))
    pal = unique_colors(fin)
    json.dump({'name': a.name, 'size': [W, H], 'grade': a.grade, 'vignette': not a.no_vignette, 'colours': len(pal),
               'palette': pal.tolist()}, open(os.path.join(a.out, f'{a.name}_palette.json'), 'w'), indent=1)
    print(f'finished: {len(pal)} colours -> {a.name}.png, {a.name}_{W * a.review_scale}.png')


if __name__ == '__main__':
    main()
