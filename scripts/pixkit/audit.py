"""QA for finished packs. Run before every delivery and quote the numbers in the README.

audit_sprite_pack(pack_dir, mouth_box=None, eye_box=None) checks, frame by frame:
  colours (whole pack), binary alpha, stray opaque pixels, enclosed 1-3 px transparent holes, normal-map alpha ==
  colour alpha, identical colour frames -> identical normals, loops start on their expression still, one-shots end
  on their state's still, talk frames change only the mouth box, blink frames change only the eye box.
audit_loop(frames, still) checks a scene loop: palette subset of the still, frame 0 vs still, seam vs neighbour
  changes, per-pixel toggle counts (flicker).
"""
import glob
import json
import os
import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def _ld(p):
    return np.array(Image.open(p).convert('RGBA'))


def _holes(a, max_size=3):
    """list of (y, x) - one pixel per enclosed transparent speck of <= max_size px"""
    op = a[..., 3] > 0
    lab, k = ndi.label(~op)
    sz = np.bincount(lab.ravel())
    H, W = op.shape
    out = []
    for i in range(1, k + 1):
        if sz[i] <= max_size:
            ys, xs = np.nonzero(lab == i)
            if ys.min() > 0 and xs.min() > 0 and ys.max() < H - 1 and xs.max() < W - 1:
                out.append((int(ys[0]), int(xs[0])))
    return out


def _inside(diff, box):
    if box is None or not diff.any():
        return True
    y0, y1, x0, x1 = box
    ys, xs = np.nonzero(diff)
    return ys.min() >= y0 and ys.max() <= y1 and xs.min() >= x0 and xs.max() <= x1


def audit_sprite_pack(pack_dir, mouth_box=None, eye_box=None):
    O = pack_dir.rstrip('/') + '/'
    m = json.load(open(O + 'manifest.json'))
    stills = {s['name'].split('_', 1)[1] if '_' in s['name'] else s['name']: _ld(O + s['file']) for s in m['states']}
    pal = set()
    rep = dict(frames=0, unique_images=0, colours=0, non_binary_alpha_px=0, stray_px=0, enclosed_holes=0,
               normal_alpha_mismatch=0, normal_nondeterministic=0, continuity=[], talk_outside_mouth=[], blink_outside_eyes=[],
               where=[])    # 'where': up to 50 locations of stray pixels / holes as 'clip[frame] (y,x) kind'
    seen = {}
    for clip, v in m['animations'].items():
        frames = [_ld(O + f['file']) for f in v['frames']]
        st = v['state'].split('_', 1)[1] if '_' in v['state'] else v['state']
        for i, a in enumerate(frames):
            rep['frames'] += 1
            op = a[..., 3] > 0
            pal |= set(map(tuple, a[op][:, :3]))
            rep['non_binary_alpha_px'] += int(((a[..., 3] > 0) & (a[..., 3] < 255)).sum())
            nb = ndi.convolve(op.astype(int), np.ones((3, 3), int), mode='constant') - op
            stray = np.argwhere(op & (nb == 0))
            holes = _holes(a)
            rep['stray_px'] += len(stray)
            rep['enclosed_holes'] += len(holes)
            for (y, x) in list(map(tuple, stray))[:5]:
                if len(rep['where']) < 50:
                    rep['where'].append(f'{clip}[{i}] ({int(y)},{int(x)}) stray pixel')
            for (y, x) in holes[:5]:
                if len(rep['where']) < 50:
                    rep['where'].append(f'{clip}[{i}] ({y},{x}) enclosed hole')
            nm = _ld(O + f'normals/{clip}/{i:02d}_n.png')
            rep['normal_alpha_mismatch'] += int(((nm[..., 3] > 0) != op).sum())
            k = a.tobytes()
            if k in seen and not (seen[k] == nm).all():
                rep['normal_nondeterministic'] += 1
            seen[k] = nm
        still = stills.get(st)
        if still is not None:
            if v['loop'] and not (frames[0] == still).all():
                rep['continuity'].append(f'{clip}: frame 0 != expression still')
            if not v['loop'] and not (frames[-1] == still).all():
                rep['continuity'].append(f'{clip}: last frame != {st} still')
        if not v['loop'] and not any((frames[0] == s).all() for s in stills.values()):
            rep['continuity'].append(f'{clip}: first frame is not an expression still')
        for i, (a, f) in enumerate(zip(frames, v['frames'])):
            d = (a != frames[0]).any(-1)
            if clip.startswith('Talk_') and not _inside(d, mouth_box):
                rep['talk_outside_mouth'].append(f'{clip}[{i}]')
            if clip.startswith('Idle_') and 'blink' in f['note'] and not _inside(d, eye_box):
                rep['blink_outside_eyes'].append(f'{clip}[{i}]')
    rep['unique_images'] = len(seen)
    rep['colours'] = len(pal)
    rep['palette'] = sorted([list(map(int, c)) for c in pal])
    rep['ok'] = (rep['non_binary_alpha_px'] == 0 and rep['stray_px'] == 0 and rep['enclosed_holes'] == 0 and rep['normal_alpha_mismatch'] == 0
                 and rep['normal_nondeterministic'] == 0 and not rep['continuity'] and not rep['talk_outside_mouth'] and not rep['blink_outside_eyes'])
    return rep


def audit_loop(frames, still):
    """frames: list of RGB arrays (or a directory of PNGs); still: RGB array or path."""
    if isinstance(frames, str):
        frames = [np.array(Image.open(p).convert('RGB')) for p in sorted(glob.glob(os.path.join(frames, '*.png')))]
    if isinstance(still, str):
        still = np.array(Image.open(still).convert('RGB'))
    F = np.stack(frames)
    spal = set(map(tuple, still.reshape(-1, 3)))
    fpal = set(map(tuple, F.reshape(-1, 3)))
    ch = (F != np.roll(F, -1, 0)).any(-1)          # changes from frame i to i+1 (last wraps to 0)
    d = ch.sum((1, 2))
    tog = ch.sum(0)
    rep = dict(frames=len(F), new_colours=len(fpal - spal), frame0_vs_still_px=int((F[0] != still).any(-1).sum()),
               seam_changed_px=int(d[-1]), mean_neighbour_changed_px=round(float(d[:-1].mean()), 1) if len(d) > 1 else 0.0,
               moving_px=int((tog > 0).sum()), max_toggles_per_px=int(tog.max()),
               px_toggling_more_than_8=int((tog > 8).sum()))
    rep['seamless'] = rep['seam_changed_px'] <= max(3 * rep['mean_neighbour_changed_px'], 10)
    rep['ok'] = rep['new_colours'] == 0 and rep['seamless']
    return rep


if __name__ == '__main__':
    import sys
    print(json.dumps(audit_sprite_pack(sys.argv[1]), indent=1, ensure_ascii=False))
