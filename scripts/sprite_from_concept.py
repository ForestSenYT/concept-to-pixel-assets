#!/usr/bin/env python3
"""Concept character -> first 1x sprite draft on the cast canvas.

    python sprite_from_concept.py concept.png OUT --height 148 [--canvas 96x160 --foot 155]
    python sprite_from_concept.py concept.png OUT --height 148 --materials materials.json

Writes OUT/raw.png (+ .npy), OUT/raw_5x.png, OUT/compare.png (sprite next to the concept), OUT/palette.txt (colours
with counts and symbols), OUT/ascii.txt (whole sprite as text), OUT/info.json (scale + offsets to map concept
coordinates onto the canvas). With --materials (see assets/examples/materials.example.json) it also snaps every
pixel to its material ramp -> OUT/mat.png (+ .npy, ascii_mat.txt).
Next steps are by hand: redraw the face (a downscale always destroys it), clean hands / props, make the
featureless face base, then build_character.py.
"""
import argparse
import json
import os
import sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pixkit import sprite as SP
from pixkit.palette import unique_colors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('out')
    ap.add_argument('--height', type=int, required=True, help='figure height in 1x px (same scale for the whole cast)')
    ap.add_argument('--canvas', default='96x160')
    ap.add_argument('--foot', type=int, default=155)
    ap.add_argument('--line', default='21,4,3')
    ap.add_argument('--k', type=int, default=26)
    ap.add_argument('--dark-lum', type=float, default=52)
    ap.add_argument('--cutout-tol', type=int, default=None, help='flood-fill the background from the corners (no alpha in the concept)')
    ap.add_argument('--materials', default=None)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    W, H = (int(v) for v in a.canvas.split('x'))
    line = tuple(int(v) for v in a.line.split(','))
    im = Image.open(a.src)
    src = np.array(im.convert('RGBA'))
    if a.cutout_tol is not None or im.mode not in ('RGBA', 'LA'):
        src = SP.cutout(src[..., :3], a.cutout_tol if a.cutout_tol is not None else 18)
    small, info = SP.pixelize(src, a.height, line=line, k=a.k, dark_lum=a.dark_lum)
    can, off = SP.place_on_canvas(small, (W, H), a.foot, W // 2)
    can = SP.fill_enclosed_holes(can, 3, line)
    info.update(offset=list(off), canvas=[W, H], foot_y=a.foot, line=list(line))
    json.dump(info, open(os.path.join(a.out, 'info.json'), 'w'), indent=1)
    np.save(os.path.join(a.out, 'raw.npy'), can)
    Image.fromarray(can).save(os.path.join(a.out, 'raw.png'))
    SP.on_bg(can, scale=5).save(os.path.join(a.out, 'raw_5x.png'))
    SP.compare_with_source(can, src).save(os.path.join(a.out, 'compare.png'))
    sym = SP.Symbols(fixed={'K': line})
    txt = sym.dump(can)
    open(os.path.join(a.out, 'ascii.txt'), 'w').write(sym.legend() + '\n' + txt + '\n')
    cols, cnt = np.unique(can[can[..., 3] > 0][:, :3], axis=0, return_counts=True)
    with open(os.path.join(a.out, 'palette.txt'), 'w') as fh:
        for c, n in sorted(zip(map(tuple, cols), cnt), key=lambda t: -t[1]):
            fh.write(f'{sym.add(tuple(int(v) for v in c))}  {tuple(int(v) for v in c)}  {n}\n')
    print(f'raw sprite: {len(cols)} colours, figure {small.shape[1]}x{small.shape[0]} px, offset {off}')
    if a.materials:
        mats = json.load(open(a.materials))
        soft = mats.pop('_soft_line', [])
        out, mat = SP.apply_materials(can, mats, line=line, soft_line=soft)
        out = SP.fill_enclosed_holes(out, 3, line)
        np.save(os.path.join(a.out, 'mat.npy'), out)
        Image.fromarray(out).save(os.path.join(a.out, 'mat.png'))
        SP.on_bg(out, scale=5).save(os.path.join(a.out, 'mat_5x.png'))
        sym2 = SP.Symbols(fixed={'K': line})
        txt2 = sym2.dump(out)
        open(os.path.join(a.out, 'ascii_mat.txt'), 'w').write(sym2.legend() + '\n' + txt2 + '\n')
        print(f'materials applied: {len(unique_colors(out))} colours -> mat.png')


if __name__ == '__main__':
    main()
