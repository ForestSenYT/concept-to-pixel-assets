"""Concept image -> native pixel-art scene (background or CG).

Pipeline (each step is a function so a scene script can stop, hand-fix, and continue):
  1. to_native()      area-resize the concept to the native grid (default 640x360), optional edge-preserving smoothing
  2. stylize()        "hand-drawn simplification": palette reduce, flatten each object to <= n tones, merge specks,
                      while protecting small bright features (lamps, windows) and thin lines (rails, frames, road marks)
  3. hand fixes       ramp_paint() flat lit gradients over AI-mottled surfaces, inpaint() removals, paste kept props
  4. finish()         colour grade (preset) + 4-level ordered-dither vignette + final palette lock (default 24 colours)
  5. upscale()        exact integer nearest-neighbour copy for review / 1920x1080
"""
import numpy as np
import cv2
from collections import Counter
from scipy import ndimage as ndi
from skimage.segmentation import felzenszwalb
from .palette import lab, from_lab, pack_key, unpack_key, palette_reduce, quantize, BAYER4


# ---------------------------------------------------------------- 1. native grid
def to_native(src, size=(640, 360), smooth=None):
    """src: RGB uint8 (any size). size: (W,H). smooth: None or (spatial, colour) for mean-shift filtering, useful for
    noisy sources (GIF dither, JPEG, AI grain) before the resize."""
    a = np.asarray(src)[..., :3]
    if smooth:
        b = cv2.cvtColor(a, cv2.COLOR_RGB2BGR)
        b = cv2.pyrMeanShiftFiltering(b, smooth[0], smooth[1])
        a = cv2.cvtColor(b, cv2.COLOR_BGR2RGB)
    return cv2.resize(a, size, interpolation=cv2.INTER_AREA)


def upscale(a, f=3):
    return np.repeat(np.repeat(np.asarray(a), f, 0), f, 1)


# ---------------------------------------------------------------- 2. hand-drawn simplification
def comp_sizes(a, with_len=False):
    """per-pixel size (and bbox length) of its same-colour 8-connected component"""
    key = pack_key(a)
    out = np.zeros(key.shape, np.int64)
    ln = np.zeros(key.shape, np.int64)
    for v in np.unique(key):
        m = key == v
        lab_, n = ndi.label(m, np.ones((3, 3)))
        cnt = np.bincount(lab_.ravel())
        out[m] = cnt[lab_[m]]
        if with_len and n:
            L = np.zeros(n + 1, np.int64)
            for i, sl in enumerate(ndi.find_objects(lab_), 1):
                L[i] = max(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start)
            ln[m] = L[lab_[m]]
    return (out, key, ln) if with_len else (out, key)


def merge_islands(a, min_px, protect=None, rounds=6, max_len=None, de_merge=None):
    """Absorb same-colour components smaller than min_px into their dominant neighbour colour.
    de_merge: only merge when the neighbour is within this Lab distance (clearly different specks are structure)."""
    a = a.copy()
    for _ in range(rounds):
        sz, key, ln = comp_sizes(a, True)
        small = sz < min_px
        if max_len is not None:
            small &= ln <= max_len
        if protect is not None:
            small &= ~protect
        if not small.any():
            break
        H, W = key.shape
        P = np.pad(key, 1, constant_values=-1)
        S = np.pad(small, 1, constant_values=True)
        cands, wts = [], []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == dx == 0:
                    continue
                cands.append(P[1 + dy:1 + dy + H, 1 + dx:1 + dx + W])
                wts.append(np.where(S[1 + dy:1 + dy + H, 1 + dx:1 + dx + W], 0, 2 if dy == 0 or dx == 0 else 1))
        cands = np.stack(cands, -1)
        wts = np.stack(wts, -1)
        best = np.full(key.shape, -1, np.int64)
        bestw = np.zeros(key.shape)
        for i in range(8):
            c = cands[..., i]
            w = ((cands == c[..., None]) * wts).sum(-1) * (wts[..., i] > 0)
            upd = w > bestw
            best[upd] = c[upd]
            bestw[upd] = w[upd]
        m = small & (best >= 0)
        if de_merge is not None and m.any():
            nb = unpack_key(best)
            ys, xs = np.nonzero(m)
            d = np.sqrt(((lab(a[ys, xs]) - lab(nb[ys, xs])) ** 2).sum(-1))
            m[ys[d >= de_merge], xs[d >= de_merge]] = False
        if not m.any():
            break
        a[m] = unpack_key(best[m])
    return a


def tone_limit(a, seg, ntones=3):
    """inside each object-level segment keep only its ntones most used colours (others -> nearest kept one)"""
    key = pack_key(a)
    out = a.reshape(-1, 3).copy()
    L = lab(a).reshape(-1, 3)
    kf = key.ravel()
    order = np.argsort(seg.ravel(), kind='stable')
    s_sorted = seg.ravel()[order]
    for grp in np.split(order, np.flatnonzero(np.diff(s_sorted)) + 1):
        v, c = np.unique(kf[grp], return_counts=True)
        if len(v) <= ntones:
            continue
        keep = v[np.argsort(-c)[:ntones]]
        ki = [grp[np.flatnonzero(kf[grp] == k)[0]] for k in keep]
        d = ((L[grp][:, None, :] - L[ki][None]) ** 2).sum(-1)
        out[grp] = out[ki][d.argmin(1)]
    return out.reshape(a.shape)


def feature_mask(q, l_min=None, de_min=22, max_area=400, min_area=2):
    """small, clearly brighter features (lit windows, lamps, sun, highlights) that carry meaning"""
    L = lab(q)
    if l_min is None:
        l_min = max(18.0, float(np.percentile(L[..., 0], 60)))
    sz, _ = comp_sizes(q)
    bgL = cv2.blur(L[..., 0].astype(np.float32), (15, 15))
    return (L[..., 0] >= l_min) & ((L[..., 0] - bgL) > de_min * 0.6) & (sz <= max_area) & (sz >= min_area)


def bright_spots(a, de=12, max_area=400, min_area=2, pct=70, win=21):
    """Small spots clearly brighter than their neighbourhood (lamp bulbs, lit windows, sun), found on the
    continuous image - unlike feature_mask this still works when the spot shares a colour with a big region."""
    L = lab(a[..., :3])[..., 0].astype(np.float32)
    bg = cv2.blur(L, (win, win))
    m = (L - bg > de) & (L >= np.percentile(L, pct))
    lab_, n = ndi.label(m, np.ones((3, 3)))
    if not n:
        return m
    sz = np.bincount(lab_.ravel())
    keep = (sz >= min_area) & (sz <= max_area)
    keep[0] = False
    return keep[lab_]


def line_mask(q, min_len=8, max_thick=2.4, min_contrast=12):
    """thin, elongated same-colour components that differ from their surroundings: road marks, rails, frames"""
    key = pack_key(q)
    LL = lab(q)
    out = np.zeros(key.shape, bool)
    for v in np.unique(key):
        m = key == v
        lab_, n = ndi.label(m, np.ones((3, 3)))
        if n == 0:
            continue
        area = np.bincount(lab_.ravel())
        for i, sl in enumerate(ndi.find_objects(lab_), 1):
            ln = max(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start)
            if ln >= min_len and area[i] / ln <= max_thick:
                cm = lab_[sl] == i
                ring = ndi.binary_dilation(cm, np.ones((3, 3))) & ~cm
                if ring.any() and np.sqrt(((LL[sl][cm].mean(0) - LL[sl][ring].mean(0)) ** 2).sum()) >= min_contrast:
                    out[sl][cm] = True
    return out


def stylize(a, k=22, scale=400, min_size=50, ntones=3, min_island=12, protect_feats=True, protect_lines=True,
            fixed_pal=None, pal_extra=None, de_keep=None, de_merge=20, keep_boxes=(), reserve=3):
    """Hand-drawn simplification of a native-size RGB image.
    k: palette size; scale/min_size: felzenszwalb object scale (bigger = larger flat blocks);
    ntones: tones kept per object (2 = very flat, 4 for dark interiors); min_island: speck size to absorb;
    keep_boxes: [(x0,y0,x1,y1)] props whose shape carries story logic - only palette-reduced, never flattened.
    reserve: extra palette slots for the protected small bright features (lamp bulbs, lit windows), so k-means over
    the whole image cannot average them away. protect_lines=False if spurious thin lines get protected (check the
    returned mask: ridge / shore edges sometimes qualify).
    Returns (image, palette, protected_mask)."""
    src_pal = np.unique(a.reshape(-1, 3), axis=0)
    p = fixed_pal if fixed_pal is not None else palette_reduce(a, k, src_pal, extra=pal_extra)
    q = quantize(a, p)
    feat = feature_mask(q) if protect_feats else np.zeros(a.shape[:2], bool)
    spots = bright_spots(a) if protect_feats else np.zeros(a.shape[:2], bool)
    if fixed_pal is None and reserve and spots.sum() >= 2:
        p = np.unique(np.vstack([p, palette_reduce(a[spots][None], reserve, src_pal)]), axis=0)
        q = quantize(a, p)
        feat = feature_mask(q) if protect_feats else feat
    feat |= spots
    if protect_lines:
        feat |= line_mask(q)
    seg = felzenszwalb(q.astype(np.float64) / 255.0, scale=scale, sigma=0.6, min_size=min_size)
    t = tone_limit(q, seg, ntones)
    t[feat] = q[feat]
    if de_keep is not None:
        dE = np.sqrt(((lab(q) - lab(t)) ** 2).sum(-1))
        keep = dE > de_keep
        t[keep] = q[keep]
    t = merge_islands(t, min_island, protect=feat, de_merge=de_merge)
    for x0, y0, x1, y1 in keep_boxes:
        t[y0:y1, x0:x1] = q[y0:y1, x0:x1]
    return t, p, feat


# ---------------------------------------------------------------- 3. hand-fix helpers
def poly_mask(pts, H, W):
    m = np.zeros((H, W), np.uint8)
    cv2.fillPoly(m, [np.array(pts, np.int32)], 1)
    return m.astype(bool)


def box_mask(x0, y0, x1, y1, H, W):
    yy, xx = np.mgrid[0:H, 0:W]
    return (xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1)


def inpaint(a, mask, allow=None):
    """Fill mask pixels from the weighted mode of already-known 8-neighbours, growing inwards. Never invents colours.
    allow: pixels usable as sources (default: everything outside mask)."""
    a = a.copy()
    H, W = a.shape[:2]
    known = ~mask if allow is None else (allow & ~mask)
    todo = mask.copy()
    while todo.any():
        new = []
        for y, x in zip(*np.nonzero(todo)):
            c = Counter()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == dx == 0:
                        continue
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < H and 0 <= xx < W and known[yy, xx]:
                        c[tuple(int(v) for v in a[yy, xx])] += 2 if (dy == 0 or dx == 0) else 1
            if c:
                new.append((y, x, max(c.items(), key=lambda kv: (kv[1], -sum(kv[0])))[0]))
        if not new:
            break
        for y, x, col in new:
            a[y, x] = col
            known[y, x] = True
            todo[y, x] = False
    return a


def masked_blur(v, mask, sigma):
    """normalized-convolution blur of v using only pixels in mask"""
    m = mask.astype(np.float32)
    num = cv2.GaussianBlur(v.astype(np.float32) * m, (0, 0), sigma)
    den = cv2.GaussianBlur(m, (0, 0), sigma)
    return num / np.maximum(den, 1e-4)


def cdf_light(L, mask):
    """luminance -> its rank inside the region (0..1), so tone areas follow the source's light distribution"""
    v = L[mask]
    srt = np.sort(v)
    out = np.zeros_like(L, dtype=float)
    out[mask] = np.searchsorted(srt, v) / max(len(v) - 1, 1)
    return out


def common_tones(t, mask, k):
    """the k most used colours inside mask, sorted dark -> light"""
    c, n = np.unique(t[mask].reshape(-1, 3), axis=0, return_counts=True)
    tones = c[np.argsort(-n)[:k]]
    return tones[np.argsort(lab(tones)[:, 0])]


def ramp_paint(t, mask, light, tones, lo=None, hi=None, band=0.22, gamma=1.0):
    """Replace an AI-mottled surface (floor, desk, wall) with a flat lit gradient over `tones` (dark -> light).
    light: (H,W) float, e.g. masked_blur(lab(src)[...,0], mask, 7) or cdf_light(...). Ordered dither appears only in
    a narrow band at each tone step, so the surface reads as hand-painted bands, not a checkerboard."""
    H, W = mask.shape
    yy, xx = np.mgrid[0:H, 0:W]
    if lo is None:
        lo, hi = np.percentile(light[mask], [3, 97])
    v = np.clip((light - lo) / max(hi - lo, 1e-6), 0, 0.999) ** gamma * (len(tones) - 1)
    lev = np.floor(v).astype(int)
    fr = v - lev
    dith = np.clip(lev + (fr > BAYER4[yy % 4, xx % 4] * 0.999), 0, len(tones) - 1)
    lev = np.where(np.abs(fr - 0.5) < band, dith, np.clip(np.round(v).astype(int), 0, len(tones) - 1))
    out = t.copy()
    out[mask] = np.array(tones)[lev[mask]]
    return out


def line_mask_src(src, mask_native, size=(640, 360), dark=True, thr=14, cov_thr=0.22, minlen=14, ksize=21, thick=2.4):
    """Thin long lines (plank seams, grain, worn edges) found in the full-res source, returned at native size, so a
    flattened surface can get its seams drawn back as 1 px lines."""
    S = src.astype(int)
    LS = ((S[..., :3] @ [30, 59, 11]) // 100).astype(np.uint8)
    med = cv2.medianBlur(LS, ksize).astype(int)
    m = (LS < med - thr) if dark else (LS > med + thr)
    cov = cv2.resize(m.astype(np.float32), size, interpolation=cv2.INTER_AREA)
    sm = mask_native & (cov > cov_thr)
    eye = np.eye(3, dtype=bool)
    lin = (ndi.binary_opening(sm, np.ones((1, 4))) | ndi.binary_opening(sm, np.ones((4, 1))) |
           ndi.binary_opening(sm, eye) | ndi.binary_opening(sm, np.fliplr(eye)))
    lab_, n = ndi.label(lin, np.ones((3, 3)))
    keep = np.zeros(n + 1, bool)
    for i, sl in enumerate(ndi.find_objects(lab_), 1):
        h_ = sl[0].stop - sl[0].start
        w_ = sl[1].stop - sl[1].start
        keep[i] = max(h_, w_) >= minlen and (lab_[sl] == i).sum() <= thick * max(h_, w_)
    return lin & keep[lab_]


def shift_tone(t, m, pal, direction=-1, dl=5):
    """Move pixels in m one palette step darker (direction=-1) or lighter (+1) within a similar hue."""
    PL = lab(pal)
    out = t.copy()
    cache = {}
    for y, x in zip(*np.nonzero(m)):
        k = tuple(int(v) for v in t[y, x])
        if k not in cache:
            i = int(np.argmin(((pal.astype(int) - np.array(k)) ** 2).sum(1)))
            L0 = PL[i]
            cand = [j for j in range(len(pal)) if (PL[j, 0] - L0[0]) * direction > dl]
            if not cand:
                cache[k] = np.array(k, np.uint8)
            else:
                d = [((PL[j] - L0) ** 2 * np.array([0.25, 1, 1])).sum() for j in cand]
                cache[k] = pal[cand[int(np.argmin(d))]]
        out[y, x] = cache[k]
    return out


# ---------------------------------------------------------------- 4. grade + vignette + palette lock
GRADES = {
    # cold dusk (tense / moody): darker, crushed shadows, desaturated cold blue-green; only warm lights
    # (lamps, lit windows, the last sunset glow) keep their warmth. Story time stays "last minutes of sunset".
    'cold_dusk': dict(gamma=1.15, gain=0.90, chroma=0.55, cast_a=-1.5, cast_b=-5.5, keep_warm=True),
    # keeps a golden-hour source bright and warm (alternative for endings / memories)
    'warm': dict(gamma=1.08, gain=0.95, chroma=0.82, cast_a=0.0, cast_b=0.0, keep_warm=True),
    # desaturated cool grey for flashbacks / memories
    'memory': dict(gamma=1.0, gain=1.0, chroma=0.45, cast_a=-0.5, cast_b=-3.0, keep_warm=False),
    'none': None,
}


def grade_palette(cols, preset='cold_dusk', **override):
    """Grade a palette (N,3) uint8 -> (N,3) uint8. Grading the palette (not the pixels) keeps flat areas flat."""
    g = GRADES[preset] if isinstance(preset, str) else preset
    if g is None:
        return np.asarray(cols).copy()
    g = dict(g, **override)
    L = lab(np.asarray(cols))
    l, A, B = L[:, 0], L[:, 1], L[:, 2]
    warm = (l > 58) & (B > 12) if g['keep_warm'] else np.zeros(len(l), bool)
    l2 = 100 * (l / 100) ** g['gamma'] * g['gain']
    l2 = np.where(warm, l * 0.93, l2)
    k = np.where(warm, 0.92, g['chroma'])
    A2 = A * k + g['cast_a']
    B2 = B * k + np.where(warm, 0, g['cast_b'])
    return from_lab(np.stack([l2, A2, B2], -1))


def vignette_levels(H, W, strength=0.36, inner=0.55, step=0.12):
    """Per-pixel vignette level 0..n (ordered-dithered rings). Shared with loopfx so animated content can be kept
    from crossing ring boundaries (otherwise the dither ring appears to crawl)."""
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.hypot((xx - W / 2) / (W / 2), (yy - H / 2) / (H / 2)) / np.sqrt(2) * 1.25
    t = np.clip((r - inner) / (1.0 - inner), 0, 1) ** 1.3 * strength
    q = t / step
    lo = np.floor(q)
    nlev = int(round(strength / step))
    return np.clip(lo + ((q - lo) > BAYER4[yy % 4, xx % 4]), 0, nlev).astype(int)


def vignette(a, strength=0.36, inner=0.55, step=0.12, rows_off=None):
    """4-level dithered vignette: each level darkens Lab lightness by `step`. rows_off: optional (H,) 0..1 weight to
    fade the vignette out on some rows (e.g. a scrolling ground in a parallax scene)."""
    H, W = a.shape[:2]
    lev = vignette_levels(H, W, strength, inner, step)
    if rows_off is not None:
        lev = np.floor(lev * np.asarray(rows_off)[:, None]).astype(int)
    L = lab(a[..., :3])
    L[..., 0] *= 1 - step * lev
    out = from_lab(L)
    return out


def finish(a, grade='cold_dusk', k=24, vig=True, vig_kw=None, extra=None, protect='auto', reserve=2):
    """grade -> vignette -> palette lock to <= k colours. extra: other images that must share the palette (pairs of
    shots that cut together, e.g. a door closed / open).
    protect: bool mask (of `a`) whose colours get `reserve` dedicated palette slots - small bright features such as
    lamp bulbs and lit windows, which k-means over the whole image would otherwise merge into their surroundings.
    'auto' = bright_spots(a); None = no reserved slots."""
    imgs = [a] + list(extra or [])
    outs = []
    for im in imgs:
        pal, inv = np.unique(im.reshape(-1, 3), axis=0, return_inverse=True)
        g = grade_palette(pal, grade)[inv.ravel()].reshape(im.shape)
        if vig:
            g = vignette(g, **(vig_kw or {}))
        outs.append(g)
    both = np.vstack(outs)
    if isinstance(protect, str) and protect == 'auto':
        protect = bright_spots(a) if reserve else None
    if protect is not None and reserve and protect.sum() >= 2:
        pr = palette_reduce(outs[0][protect][None], reserve)
        p = np.unique(np.vstack([palette_reduce(both, max(k - len(pr), 2)), pr]), axis=0)
    else:
        p = palette_reduce(both, k)
    res = [quantize(o, p) for o in outs]
    return res[0] if extra is None else res


def nearest_in_palette(rgb, pal):
    from .palette import nearest_index
    return np.asarray(pal)[nearest_index(np.asarray(rgb).reshape(-1, 3), pal)]
