#!/usr/bin/env python3
"""Seamless ambient loop for a finished still, from a JSON spec (see assets/examples/loop_spec.example.json).

    python make_loop.py spec.json

Masks are PNGs at the still's size (white / opaque = on). Make them with numpy (colour picks, polygons) or ask the
user to paint them. Effects run in the listed order on palette indices, so no colour outside the still's palette
can ever appear. Every effect is 0 at frame 0, so frame 0 == the still (except particles that are always present).
Writes <out>/<name>/frames_native/*.png, a review mp4, <out>/<name>/<name>_STILL_frame0.png (ship this as the
still so still and loop match exactly) and <out>/<name>/<name>_loop_audit.json.
"""
import json
import os
import sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pixkit import loopfx as FX
from pixkit.audit import audit_loop


def load_mask(path, base_dir, shape):
    p = path if os.path.isabs(path) else os.path.join(base_dir, path)
    im = Image.open(p)
    a = np.array(im.convert('RGBA'))
    m = (a[..., 3] > 0) & (a[..., :3].max(-1) > 127) if im.mode in ('RGBA', 'LA', 'P') else (a[..., :3].max(-1) > 127)
    assert m.shape == shape, f'mask {path} is {m.shape[::-1]}, still is {shape[::-1]}'
    return m


def anchor_weight(mask, anchor):
    """(H,) weight 0 at the anchored end of the mask's rows, 1 at the free end"""
    H = mask.shape[0]
    rows = np.nonzero(mask.any(1))[0]
    w = np.zeros(H)
    if len(rows) == 0:
        return w
    y0, y1 = rows.min(), rows.max()
    span = max(y1 - y0, 1)
    for y in rows:
        w[y] = (y1 - y) / span if anchor == 'bottom' else (y - y0) / span
    return w


def main():
    spec_path = sys.argv[1]
    base_dir = os.path.dirname(os.path.abspath(spec_path))
    spec = json.load(open(spec_path))
    still = spec['still'] if os.path.isabs(spec['still']) else os.path.join(base_dir, spec['still'])
    vig = spec.get('vignette', [0.36, 0.55])
    S = FX.Scene(still, T=spec.get('frames', 48), vig=tuple(vig) if vig else None)
    shape = (S.H, S.W)
    up, down = S.step_map(True), S.step_map(False)
    dims = S.dim_maps()
    prepared = []
    for e in spec['effects']:
        e = dict(e)
        if 'mask' in e:
            e['_m'] = load_mask(e['mask'], base_dir, shape)
        if 'light' in e:
            e['_light'] = load_mask(e['light'], base_dir, shape)
        if 'sky' in e:
            e['_sky'] = load_mask(e['sky'], base_dir, shape)
        if 'occlude' in e:
            e['_occ'] = load_mask(e['occlude'], base_dir, shape)
        t = e['type']
        if t == 'leaves':
            cols = [int(i) for i in S.nearest(np.array(e['colors']))]
            e['_obj'] = FX.Leaves(S, e.get('n', 20), e['x'], e['y'], cols, seed=e.get('seed', 5), kmin=e.get('kmin', 1), kmax=e.get('kmax', 2))
        elif t == 'dust':
            x0, y0, x1, y1 = e['box']
            sampler = lambda rng, b=(x0, y0, x1, y1): (rng.uniform(b[0], b[2]), rng.uniform(b[1], b[3]))
            e['_obj'] = FX.Dust(S, e.get('n', 60), sampler, seed=e.get('seed', 41), light=e.get('_light'))
        elif t == 'birds':
            col = int(S.nearest(np.array([e['color']]))[0])
            e['_obj'] = FX.Birds(S, e.get('n', 4), e['centers'], col, seed=e.get('seed', 7), sky=e.get('_sky'))
        elif t == 'sway':
            e['_w'] = anchor_weight(e['_m'], e.get('anchor', 'bottom'))
        prepared.append(e)
    frames = []
    for ti in range(S.T):
        u = ti / S.T
        I = S.idx.copy()
        for e in prepared:
            t = e['type']
            if t == 'ripple':
                I = FX.ripple(S, I, S.idx, e['_m'], u, amp=e.get('amp', 1), cycles=e.get('cycles', 2), seed=e.get('seed', 0), band=e.get('band', 1))
            elif t == 'sparkle':
                I = FX.sparkle(S, I, e['_m'], u, up, rate=e.get('rate', 0.04), hold=e.get('hold', 3), seed=e.get('seed', 1))
            elif t == 'wisps':
                fmap = down if e.get('darken') else up
                I = FX.wisps(S, I, e['_m'].astype(float), u, fmap, period=e.get('period', 160), cycles=e.get('cycles', 1), seed=e.get('seed', 3),
                             thr=e.get('thr', 0.6), sx=e.get('sx', 24), sy=e.get('sy', 1.2), drift=e.get('drift'))
            elif t == 'sway':
                I = FX.sway(S, I, S.idx, e['_m'], u, e.get('amp', 1), e['_w'], cycles=e.get('cycles', 1), phase=e.get('phase', 0.0))
            elif t == 'flicker':
                lev = float(e.get('frames', {}).get(str(ti), 1.0))
                I = FX.flicker(S, I, e['_m'], lev, dims)
            elif t == 'flicker_radial':
                amt = 1.0 - float(e.get('frames', {}).get(str(ti), 1.0))
                cand = e.get('_m', np.ones(shape, bool))
                I = FX.flicker_radial(S, I, cand, e['center'], e['radius'], amt, dims[0.5])
            elif t in ('leaves',):
                I = e['_obj'].draw(I, u, occl=e.get('_occ'))
            elif t in ('dust', 'birds'):
                I = e['_obj'].draw(I, u)
            elif t == 'shift':
                if ti in set(e.get('frames', [])):
                    I = FX.shift_region(S, I, I.copy(), e['_m'], e.get('dx', 0), e.get('dy', -1))
            elif t == 'static':
                pass
            else:
                sys.exit(f'unknown effect type {t}')
        for e in prepared:
            if e['type'] == 'static':
                I[e['_m']] = S.idx[e['_m']]
        frames.append(I)
    out = spec.get('out', 'loops')
    out = out if os.path.isabs(out) else os.path.join(base_dir, out)
    name = spec.get('name', os.path.splitext(os.path.basename(still))[0])
    FX.write_loop(name, frames, S.pal, out, fps=spec.get('fps', 12), review_scale=spec.get('review_scale', 3), mp4=spec.get('mp4', True))
    # the still to ship is frame 0 (mist / particles included), so the loop can replace it without a jump
    Image.fromarray(S.pal[frames[0]].astype(np.uint8)).save(os.path.join(out, name, f'{name}_STILL_frame0.png'))
    rep = audit_loop([S.pal[I] for I in frames], S.rgb)
    json.dump(rep, open(os.path.join(out, name, f'{name}_loop_audit.json'), 'w'), indent=1)
    print(json.dumps(rep))


if __name__ == '__main__':
    main()
