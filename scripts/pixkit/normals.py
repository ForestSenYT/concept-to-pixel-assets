"""Pixel-art normal maps for 2D sprite lighting (Unity URP 2D 'Normal Map' secondary texture).

Method ("volume" normals):
  * across each row, each part run is a cylinder (left edge faces left, right edge faces right), blended with the
    whole-figure run so the body as a whole also turns away from the light at its sides
  * along each column only the ends of a run turn up / down (shoulders, tops of shoes, hems)
  * the head (skin + hair + face lines) is ONE sphere, so blinking / expression swaps never punch holes in it
  * silhouette outline pixels point outward (rim light); interior line pixels copy the nearest part's normal
  * normals snap to a few directions so light falls in clean pixel-art bands, then a median de-speckle per part
  * deterministic: identical colour frames -> identical normal frames (loops and hand-offs never pop)
Encoding (Unity tangent space): R = x (right +), G = y (up +), B = z; transparent = (128,128,255,0).
"""
import numpy as np
from scipy import ndimage as ndi

LV = np.array([-0.82, -0.5, -0.2, 0.0, 0.2, 0.5, 0.82])


class PartClassifier:
    """rules: [{'part': 'skin', 'colors': [[r,g,b], ...], 'region': [x0,y0,x1,y1] (optional)}, ...] - first match
    wins; unmatched opaque pixels (outline colour) are lines (0). head: {'parts': [...], 'max_row': int, 'above_part': name (optional)} - the
    head sphere = opaque pixels at or above max_row that belong to these parts, outline pixels counted with their
    nearest part (so the collar outline stays with the collar); largest component. With 'above_part' (e.g. the
    shirt) the head ends at the first row of that part in the centre band, so it follows breathing and nods.
    flat: parts that sit flat on the face (eye whites, teeth) - shaded as face, not as bumps."""
    def __init__(self, rules, head=None, flat=()):
        self.rules = rules
        self.names = []
        for r in rules:
            if r['part'] not in self.names:
                self.names.append(r['part'])
        self.head = head
        self.flat = set(flat)

    def labels(self, a):
        H, W = a.shape[:2]
        op = a[..., 3] > 0
        yy, xx = np.mgrid[0:H, 0:W]
        lab = np.zeros((H, W), int)
        done = np.zeros((H, W), bool)
        rgb = a[..., :3].astype(int)
        for r in self.rules:
            m = np.zeros((H, W), bool)
            for c in r['colors']:
                m |= (rgb == np.array(c)).all(-1)
            m &= op & ~done
            if 'region' in r:
                x0, y0, x1, y1 = r['region']
                m &= (xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1)
            lab[m] = self.names.index(r['part']) + 1
            done |= m
        return lab

    def head_mask(self, a, own, lab=None):
        """own: part label per pixel with outline pixels assigned to their nearest part"""
        if not self.head:
            return None
        op = a[..., 3] > 0
        ids = [self.names.index(p) + 1 for p in self.head['parts'] if p in self.names]
        m = op & np.isin(own, ids)
        max_row = self.head.get('max_row', a.shape[0])
        if 'above_part' in self.head and self.head['above_part'] in self.names:
            # follow the body: the head ends where the torso part starts in the centre band (moves with breathing)
            k = self.names.index(self.head['above_part']) + 1
            cols = np.nonzero(op.any(0))[0]
            cx = int(np.median(cols)) if len(cols) else a.shape[1] // 2
            ref = own if lab is None else lab          # coloured torso pixels only (not its outline)
            rows = np.nonzero((ref[:, max(cx - 12, 0):cx + 12] == k).any(1))[0]
            if len(rows):
                max_row = min(max_row, int(rows.min()))
        m[max_row + 1:] = False
        hl, nh = ndi.label(m)
        if nh:
            sz = np.bincount(hl.ravel())
            sz[0] = 0
            m = hl == np.argmax(sz)
        return m

    def flat_mask(self, lab):
        ids = [self.names.index(p) + 1 for p in self.flat if p in self.names]
        return np.isin(lab, ids) if ids else None


def _runs_1d(lab):
    n = len(lab)
    s = np.zeros(n)
    L = np.zeros(n, int)
    i = 0
    while i < n:
        if lab[i] == 0:
            i += 1
            continue
        j = i
        while j + 1 < n and lab[j + 1] == lab[i]:
            j += 1
        ln = j - i + 1
        c = (i + j) / 2.0
        hw = max(ln / 2.0, 0.5)
        s[i:j + 1] = (np.arange(i, j + 1) - c) / hw if ln > 1 else 0.0
        L[i:j + 1] = ln
        i = j + 1
    return s, L


def _field(U, axis):
    H, W = U.shape
    S = np.zeros((H, W))
    L = np.zeros((H, W), int)
    if axis == 1:
        for y in range(H):
            S[y], L[y] = _runs_1d(U[y])
    else:
        for x in range(W):
            S[:, x], L[:, x] = _runs_1d(U[:, x])
    return S, L


def normals(a, classifier):
    """a: RGBA sprite frame. Returns RGBA normal map (uint8)."""
    lab = classifier.labels(a)
    H, W = lab.shape
    op = a[..., 3] > 0
    line = op & (lab == 0)
    if (lab > 0).any():
        idx = ndi.distance_transform_edt(lab == 0, return_distances=False, return_indices=True)
        own = lab[idx[0], idx[1]]
    else:
        own = lab
    own = np.where(op, own, 0)
    head = classifier.head_mask(a, own, lab)
    if head is None:
        head = np.zeros((H, W), bool)
    U = np.where(line, 0, lab)
    U[head] = 999
    sx, _ = _field(U, 1)
    sy, Ly = _field(U, 0)
    bx, _ = _field(op.astype(int), 1)
    nx = 0.62 * sx + 0.38 * bx
    edge = np.sign(sy) * np.clip((np.abs(sy) - 0.45) / 0.55, 0, 1)
    ny = -0.8 * edge * (Ly >= 3)
    if head.any():
        hx, _ = _field(head.astype(int), 1)
        hy, _ = _field(head.astype(int), 0)
        nx = np.where(head, 0.75 * hx + 0.15 * bx, nx)
        ny = np.where(head, -0.62 * hy, ny)
    if line.any():
        src = ~line & op
        if src.any():
            idx = ndi.distance_transform_edt(~src, return_distances=False, return_indices=True)
            nx = np.where(line, nx[idx[0], idx[1]], nx)
            ny = np.where(line, ny[idx[0], idx[1]], ny)
    sil = op & ~ndi.binary_erosion(op)
    dd = ndi.gaussian_filter(op.astype(float), 1.0)
    oy, ox = np.gradient(dd)
    nr = np.hypot(ox, oy) + 1e-6
    nx = np.where(sil, np.clip(0.55 * (-ox / nr) + 0.45 * nx, -1, 1), nx)
    ny = np.where(sil, np.clip(0.55 * (oy / nr) + 0.45 * ny, -1, 1), ny)
    r = np.hypot(nx, ny)
    f = np.where(r > 0.92, 0.92 / np.maximum(r, 1e-6), 1)
    nx *= f
    ny *= f
    snap = lambda v: LV[np.abs(v[..., None] - LV).argmin(-1)]
    qx, qy = snap(nx), snap(ny)
    Uu = np.where(head, 999, own)
    sx0, sy0 = qx.copy(), qy.copy()          # medians read the un-despeckled values -> independent of part order
    for k in np.unique(Uu[op]):
        m = (Uu == k) & op & ~sil
        if not m.any():
            continue
        for q, q0 in ((qx, sx0), (qy, sy0)):
            med = ndi.median_filter(q0, size=3)
            q[m] = snap(med[m])
    flat = classifier.flat_mask(lab)
    nz = np.sqrt(np.clip(1 - qx ** 2 - qy ** 2, 0.12, 1))
    n = np.stack([qx, qy, nz], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    out = np.zeros((H, W, 4), np.uint8)
    out[..., :3] = np.round((n * 0.5 + 0.5) * 255).astype(np.uint8)
    if flat is not None and flat.any():
        out[flat & op, :3] = (128, 128, 255)
    out[~op] = (128, 128, 255, 0)
    out[op, 3] = 255
    return out


def lit(a, n_rgba, light, amb=0.32):
    """Quick Lambert preview (not the game shader): light = [x, y, z] direction toward the light."""
    n = n_rgba[..., :3].astype(float) / 255 * 2 - 1
    L = np.array(light, float)
    L /= np.linalg.norm(L)
    d = np.clip((n * L).sum(-1), 0, 1)
    v = amb + (1 - amb) * d * 1.15
    return np.clip(a[..., :3].astype(float) * v[..., None], 0, 255).astype(np.uint8)
