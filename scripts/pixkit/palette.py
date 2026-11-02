"""Colour helpers shared by every stage: Lab conversion, palette reduction, quantization, ordered dither.

Everything in this toolkit works on small fixed palettes. A palette is an (N,3) uint8 array of RGB colours;
an image is (H,W,3) uint8 RGB or (H,W,4) uint8 RGBA with binary alpha.
"""
import numpy as np
import cv2
from skimage.color import rgb2lab, lab2rgb

# 4x4 ordered-dither threshold matrix (values in [0,1)). Used for vignettes, light pools and narrow ramp bands.
BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0


def lab(a):
    """RGB uint8 array of any shape (...,3) -> Lab float array of the same shape."""
    a = np.asarray(a)
    shp = a.shape
    return rgb2lab(a.reshape(-1, 1, 3).astype(np.float64) / 255.0).reshape(shp[:-1] + (3,))


def from_lab(L):
    shp = L.shape
    rgb = lab2rgb(L.reshape(-1, 1, 3)).reshape(shp)
    return np.clip(np.rint(rgb * 255), 0, 255).astype(np.uint8)


def pack_key(a):
    """RGB -> one int per pixel (fast unique / equality tests)."""
    a = np.asarray(a)
    return (a[..., 0].astype(np.int64) << 16) | (a[..., 1].astype(np.int64) << 8) | a[..., 2].astype(np.int64)


def unpack_key(k):
    k = np.asarray(k)
    return np.stack([(k >> 16) & 255, (k >> 8) & 255, k & 255], -1).astype(np.uint8)


def unique_colors(a):
    """Palette actually used by an RGB or RGBA image (transparent pixels ignored)."""
    a = np.asarray(a)
    if a.shape[-1] == 4:
        px = a[a[..., 3] > 0][:, :3]
    else:
        px = a.reshape(-1, 3)
    return np.unique(px.reshape(-1, 3), axis=0)


def quantize(a, pal, chunk=200000):
    """Map every pixel to the nearest palette colour in Lab. Works on RGB; for RGBA pass a[..., :3]."""
    a = np.asarray(a)
    shp = a.shape
    X = lab(a.reshape(-1, 3))
    P = lab(np.asarray(pal).reshape(-1, 3))
    out = np.empty(len(X), np.int64)
    for i in range(0, len(X), chunk):
        d = ((X[i:i + chunk, None, :] - P[None]) ** 2).sum(-1)
        out[i:i + chunk] = d.argmin(1)
    return np.asarray(pal)[out].reshape(shp)


def nearest_index(rgb, pal):
    """Index of the nearest palette colour (Lab) for each colour in rgb (M,3)."""
    d = ((lab(np.asarray(rgb).reshape(-1, 3))[:, None] - lab(np.asarray(pal).reshape(-1, 3))[None]) ** 2).sum(-1)
    return d.argmin(1)


def palette_reduce(a, k, src_pal=None, extra=None, attempts=4):
    """k-means in Lab over the image (plus optional extra images), with every centre snapped to the nearest colour
    that already exists in the source. Snapping keeps the result free of muddy averaged colours.
    Returns <= k colours (duplicates after snapping are merged)."""
    a = np.asarray(a)
    X = lab(a.reshape(-1, 3))
    if extra is not None:
        X = np.vstack([X] + [lab(np.asarray(e).reshape(-1, 3)) for e in extra])
    if src_pal is None:
        src_pal = np.unique(np.vstack([a.reshape(-1, 3)] + ([np.asarray(e).reshape(-1, 3) for e in extra] if extra else [])), axis=0)
    k = int(min(k, len(src_pal)))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.2)
    _, _, C = cv2.kmeans(X.astype(np.float32), k, None, crit, attempts, cv2.KMEANS_PP_CENTERS)
    P = lab(src_pal)
    idx = np.unique([int(np.argmin(((P - c) ** 2).sum(1))) for c in C])
    return np.asarray(src_pal)[idx]


def merge_near_colors(a, de=2.0, de_warm=1.0):
    """Merge colours closer than `de` (CIE76) into the more frequent one. Warm / saturated colours (lamps, sunset
    glow) only merge below `de_warm` so small warm accents survive. Returns the new image."""
    a = np.asarray(a).copy()
    rgb = a[..., :3]
    mask = a[..., 3] > 0 if a.shape[-1] == 4 else np.ones(a.shape[:2], bool)
    cols, cnt = np.unique(rgb[mask].reshape(-1, 3), axis=0, return_counts=True)
    order = np.argsort(-cnt)
    cols, cnt = cols[order], cnt[order]
    L = lab(cols)
    target = np.arange(len(cols))
    for i in range(len(cols)):
        if target[i] != i:
            continue
        for j in range(i + 1, len(cols)):
            if target[j] != j:
                continue
            d = np.sqrt(((L[i] - L[j]) ** 2).sum())
            warm = (L[j, 2] > 20 and L[j, 0] > 50) or np.hypot(L[j, 1], L[j, 2]) > 45
            if d < (de_warm if warm else de):
                target[j] = i
    lut = {tuple(cols[j]): cols[target[j]] for j in range(len(cols)) if target[j] != j}
    if lut:
        k = pack_key(rgb)
        for src, dst in lut.items():
            m = (k == pack_key(np.array(src))) & mask
            a[..., :3][m] = dst
    return a


def dither_threshold(H, W):
    yy, xx = np.mgrid[0:H, 0:W]
    return BAYER4[yy % 4, xx % 4]
