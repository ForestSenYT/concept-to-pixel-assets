"""Concept character -> 1x pixel sprite on a fixed canvas, plus the hand-editing tools used to finish it.

Steps:
  1. cutout()            binary alpha (if the concept has a plain background)
  2. pixelize()          skeleton-based downscale to a target height: dark strokes become 1 px lines, colour cells
                         take the most common quantized non-line colour, silhouette always gets an outline
  3. place_on_canvas()   feet on the foot line, centred, same canvas as the rest of the cast
  4. apply_materials()   every pixel snapped to its material's fixed ramp (few colours per material);
                         interior strokes inside one soft material (hair strands, cloth folds) -> that material's
                         darkest tone instead of black
  5. hand finish         ascii dump / paint, grid_zoom, fill_enclosed_holes, merge colours; redraw the face by hand
                         (a straight downscale always destroys eyes and mouth)
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi
from skimage.morphology import skeletonize
from .palette import lab, pack_key, unpack_key, palette_reduce, quantize, unique_colors

LINE = (21, 4, 3)


# ---------------------------------------------------------------- 1-3
def cutout(rgb, tol=18):
    """Flood-fill the background from the four corners (colour within tol) -> RGBA with binary alpha."""
    a = np.asarray(rgb)[..., :3].astype(int)
    H, W = a.shape[:2]
    mask = np.zeros((H, W), bool)
    for y, x in ((0, 0), (0, W - 1), (H - 1, 0), (H - 1, W - 1)):
        d = np.abs(a - a[y, x]).max(-1) <= tol
        lab_, _ = ndi.label(d)
        mask |= lab_ == lab_[y, x]
    out = np.zeros((H, W, 4), np.uint8)
    out[..., :3] = a
    out[..., 3] = np.where(mask, 0, 255)
    return out


def pixelize(rgba, target_h, line=LINE, dark_lum=52, k=26, cover=0.45, skel_thr=0.45, dark_cover=0.6, margin=2):
    """rgba: concept with alpha (>128 = figure). target_h: figure height in 1x px (keep it identical across the cast
    so everyone shares one scale). Returns (small RGBA, info) where info maps source <-> 1x coordinates."""
    a = np.asarray(rgba)
    op = a[..., 3] > 128
    ys, xs = np.nonzero(op)
    y0, y1 = ys.min(), ys.max()
    s = (y1 - y0 + 1) / target_h
    rgb = a[..., :3].copy()
    lum = rgb.astype(float) @ [0.3, 0.59, 0.11]
    dark = ndi.binary_opening(op & (lum < dark_lum), np.ones((2, 2)))
    sk = skeletonize(dark)
    body = op & ~dark
    P = palette_reduce(rgb[body][None], k)
    q = quantize(rgb, P)
    key = pack_key(q)
    Wt = int(np.ceil((xs.max() - xs.min() + 1) / s)) + 2 * margin
    oy = y1 + 1 - target_h * s
    ox = xs.min() - margin * s
    out = np.zeros((target_h, Wt, 4), np.uint8)
    SKL = np.zeros((target_h, Wt))
    DCV = np.zeros((target_h, Wt))
    for j in range(target_h):
        ya, yb = max(int(round(oy + j * s)), 0), int(round(oy + (j + 1) * s))
        for i in range(Wt):
            xa, xb = max(int(round(ox + i * s)), 0), int(round(ox + (i + 1) * s))
            m = op[ya:yb, xa:xb]
            if m.size == 0 or m.mean() < cover:
                continue
            SKL[j, i] = sk[ya:yb, xa:xb].sum() / s
            DCV[j, i] = dark[ya:yb, xa:xb].mean()
            nd = m & ~dark[ya:yb, xa:xb]
            if nd.sum() == 0:
                out[j, i, :3] = line
            else:
                v, c = np.unique(key[ya:yb, xa:xb][nd], return_counts=True)
                out[j, i, :3] = unpack_key(v[np.argmax(c)])
            out[j, i, 3] = 255
    isline = (SKL >= skel_thr) | (DCV > dark_cover)
    out[isline & (out[..., 3] > 0), :3] = line
    o = out[..., 3] > 0
    out[o & ~ndi.binary_erosion(o), :3] = line
    return out, dict(scale=float(s), ox=float(ox), oy=float(oy), src_bbox=[int(xs.min()), int(y0), int(xs.max()), int(y1)])


def place_on_canvas(small, canvas=(96, 160), foot_y=155, center_x=48, feet_rows=6):
    """Put the figure's lowest row on foot_y and centre the feet (mean x of the bottom feet_rows) on center_x."""
    W, H = canvas
    o = small[..., 3] > 0
    ys, xs = np.nonzero(o)
    bottom = ys.max()
    fx = xs[ys > bottom - feet_rows].mean()
    dx = int(round(center_x - fx))
    dy = foot_y - bottom
    out = np.zeros((H, W, 4), np.uint8)
    for y, x in zip(ys, xs):
        Y, X = y + dy, x + dx
        if 0 <= Y < H and 0 <= X < W:
            out[Y, X] = small[y, x]
    return out, (int(dx), int(dy))


def src_to_canvas(x_src, y_src, info, offset):
    """source pixel -> canvas pixel (for placing hand-drawn features where the concept has them)"""
    return ((x_src - info['ox']) / info['scale'] + offset[0], (y_src - info['oy']) / info['scale'] + offset[1])


# ---------------------------------------------------------------- 4 materials
def apply_materials(a, materials, line=LINE, soft_line=(), line_max_sum=60):
    """materials: {name: {'ramp': [[r,g,b], ...dark->light], 'region': [x0,y0,x1,y1] (optional, inclusive-exclusive),
    'priority': int (optional)}}. Each non-line pixel goes to the allowed material whose ramp holds the nearest
    colour (Lab) and is replaced by that ramp colour. Use regions to split same-coloured materials (hair above the
    collar, apron below it). soft_line: materials whose interior black strokes become their darkest tone.
    Returns (image, material_map) where material_map is an object array of names ('' for lines)."""
    a = np.asarray(a).copy()
    H, W = a.shape[:2]
    op = a[..., 3] > 0
    isK = op & (a[..., :3].astype(int).sum(-1) < line_max_sum)
    yy, xx = np.mgrid[0:H, 0:W]
    names = list(materials)
    best = np.full((H, W), np.inf)
    mat = np.full((H, W), '', object)
    col = np.zeros((H, W, 3), np.uint8)
    L = lab(a[..., :3])
    for n in names:
        r = np.array(materials[n]['ramp'], np.uint8)
        allow = op & ~isK
        if 'region' in materials[n]:
            x0, y0, x1, y1 = materials[n]['region']
            allow &= (xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1)
        d = ((L[..., None, :] - lab(r)[None, None]) ** 2).sum(-1)
        di = d.argmin(-1)
        dm = d.min(-1) - 1e-3 * materials[n].get('priority', 0)
        upd = allow & (dm < best)
        best[upd] = dm[upd]
        mat[upd] = n
        col[upd] = r[di[upd]]
    out = a.copy()
    has = mat != ''
    out[has, :3] = col[has]
    out[isK, :3] = line
    if soft_line:
        near_t = ndi.binary_dilation(~op, np.ones((3, 3)))
        for y, x in zip(*np.nonzero(isK & ~near_t)):
            nb = [mat[j, i] for j in (y - 1, y, y + 1) for i in (x - 1, x, x + 1)
                  if 0 <= j < H and 0 <= i < W and not isK[j, i] and mat[j, i] != '']
            if nb and len(set(nb)) == 1 and nb[0] in soft_line:
                out[y, x, :3] = materials[nb[0]]['ramp'][0]
    return out, mat


# ---------------------------------------------------------------- 5 cleanup
def fill_enclosed_holes(a, max_size=3, color=LINE):
    """transparent specks of <= max_size px fully enclosed by the figure -> outline colour"""
    a = a.copy()
    op = a[..., 3] > 0
    lab_, n = ndi.label(~op)
    sz = np.bincount(lab_.ravel())
    H, W = op.shape
    for k in range(1, n + 1):
        if sz[k] <= max_size:
            m = lab_ == k
            ys, xs = np.nonzero(m)
            if ys.min() > 0 and xs.min() > 0 and ys.max() < H - 1 and xs.max() < W - 1:
                a[m, :3] = color
                a[m, 3] = 255
    return a


def stray_pixels(a):
    """opaque pixels with no opaque 8-neighbour"""
    op = a[..., 3] > 0
    nb = ndi.convolve(op.astype(int), np.ones((3, 3), int), mode='constant') - op
    return op & (nb == 0)


def binary_alpha(a, thr=128):
    a = a.copy()
    a[..., 3] = np.where(a[..., 3] >= thr, 255, 0)
    a[a[..., 3] == 0, :3] = 0
    return a


def merge_colors(a, mapping):
    """mapping: {(r,g,b): (r,g,b)} exact colour merges (near-duplicates left over from conversion)"""
    a = a.copy()
    for s, d in mapping.items():
        m = (a[..., :3] == np.array(s)).all(-1) & (a[..., 3] > 0)
        a[m, :3] = d
    return a


# ---------------------------------------------------------------- hand-editing tools
class Symbols:
    """Stable 1-character names for palette colours, so a sprite can be read and edited as text.
    '.' = transparent, ' ' = keep (in paint). Letters are assigned automatically in order of first appearance and
    mean nothing - always read the legend line of a dump, or pass fixed={'K': (21,4,3), 'S': (250,182,143), ...}
    to choose your own letters before dumping."""
    POOL = '123456789ABCDEFGHIJLMNOPQRTUVWXYZabcdefghijklmnopqrstuvwxyz@#$%&*+=<>'

    def __init__(self, palette=(), fixed=None):
        self.c2s, self.s2c = {}, {}
        for s, c in (fixed or {}).items():
            self.add(tuple(int(v) for v in c), s)
        for c in palette:
            self.add(tuple(int(v) for v in c))

    def add(self, c, s=None):
        if c in self.c2s:
            return self.c2s[c]
        if s is None:
            s = next(ch for ch in self.POOL if ch not in self.s2c)
        self.c2s[c] = s
        self.s2c[s] = c
        return s

    def dump(self, a, box=None):
        """box: (x0, y0, x1, y1). Returns text with an x ruler and row numbers."""
        H, W = a.shape[:2]
        x0, y0, x1, y1 = box or (0, 0, W, H)
        lines = ['    ' + ''.join(str(x % 10) for x in range(x0, x1))]
        for y in range(y0, y1):
            row = ''.join('.' if a[y, x, 3] == 0 else self.add(tuple(int(v) for v in a[y, x, :3])) for x in range(x0, x1))
            lines.append(f'{y:3d} {row}')
        return '\n'.join(lines)

    def legend(self):
        return '  '.join(f'{s}={c}' for c, s in self.c2s.items())

    def paint(self, a, x0, y0, rows):
        """Write text rows onto a (in place). '.' = transparent, ' ' = keep the existing pixel."""
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                if ch == ' ':
                    continue
                y, x = y0 + j, x0 + i
                if ch == '.':
                    a[y, x] = 0
                else:
                    a[y, x, :3] = self.s2c[ch]
                    a[y, x, 3] = 255
        return a


def _font(size):
    for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf',
              'C:/Windows/Fonts/arial.ttf'):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def grid_zoom(a, box, scale=12, bg=(60, 64, 74)):
    """Zoomed crop with a pixel grid and coordinates every 5 px - the view used for hand edits."""
    x0, y0, x1, y1 = box
    im = Image.fromarray(np.asarray(a)).convert('RGBA')
    b = Image.new('RGBA', im.size, bg + (255,))
    b.alpha_composite(im)
    c = b.crop(box).resize(((x1 - x0) * scale, (y1 - y0) * scale), Image.NEAREST)
    d = ImageDraw.Draw(c)
    f = _font(max(8, scale - 4))
    for x in range(x0, x1):
        d.line([((x - x0) * scale, 0), ((x - x0) * scale, c.height)], fill=(255, 255, 0, 190) if x % 5 == 0 else (255, 255, 0, 60))
        if x % 5 == 0:
            d.text(((x - x0) * scale + 1, 1), str(x), fill=(255, 255, 255), font=f)
    for y in range(y0, y1):
        d.line([(0, (y - y0) * scale), (c.width, (y - y0) * scale)], fill=(0, 255, 255, 190) if y % 5 == 0 else (0, 255, 255, 60))
        if y % 5 == 0:
            d.text((1, (y - y0) * scale + 1), str(y), fill=(255, 255, 255), font=f)
    return c.convert('RGB')


def on_bg(a, bg=(60, 64, 74), scale=1):
    im = Image.fromarray(np.asarray(a)).convert('RGBA')
    b = Image.new('RGBA', im.size, bg + (255,))
    b.alpha_composite(im)
    b = b.convert('RGB')
    return b.resize((b.width * scale, b.height * scale), Image.NEAREST) if scale != 1 else b


def compare_with_source(sprite, source_rgba, height=800, bg=(60, 64, 74)):
    """sprite (nearest, integer zoom) next to the concept scaled to the same height"""
    z = max(1, height // sprite.shape[0])
    left = on_bg(sprite, bg, z)
    s = Image.fromarray(np.asarray(source_rgba)).convert('RGBA')
    sb = Image.new('RGBA', s.size, bg + (255,))
    sb.alpha_composite(s)
    sb = sb.convert('RGB').resize((int(s.width * left.height / s.height), left.height), Image.LANCZOS)
    out = Image.new('RGB', (left.width + sb.width + 10, left.height), (24, 26, 30))
    out.paste(left, (0, 0))
    out.paste(sb, (left.width + 10, 0))
    return out
