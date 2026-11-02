"""Palette-locked, seamless ambient loop effects for a finished pixel scene.

Rules every effect follows:
  * phase u = t / T with integer cycles, so frame T == frame 0 (seamless) and frame 0 == the still
  * all work happens on palette INDICES of the scene: no new colours can ever appear
  * content only moves between pixels of the same baked vignette level (else the dither ring crawls)
Typical use:
    S = Scene('BG02.png')                       # the finished still (already graded + vignetted)
    frames = []
    for t in range(S.T):
        u = t / S.T; I = S.idx.copy()
        I = ripple(S, I, S.idx, water_mask, u, amp=1, cycles=2)
        I = sparkle(S, I, glint_mask, u, S.step_map(True), rate=0.05)
        frames.append(I)
    write_loop('BG02', frames, S.pal, 'out')
"""
import os
import subprocess
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from .palette import lab, pack_key, BAYER4
from .scene import vignette_levels


class Scene:
    def __init__(self, path_or_array, T=48, vig=(0.36, 0.55), pal_from=None):
        """vig: (strength, inner) of the vignette baked into the still by scene.finish(), or None if none."""
        if isinstance(path_or_array, str):
            self.rgb = np.array(Image.open(path_or_array).convert('RGB'))
        else:
            self.rgb = np.asarray(path_or_array)[..., :3].copy()
        src = np.array(Image.open(pal_from).convert('RGB')) if isinstance(pal_from, str) else (pal_from if pal_from is not None else self.rgb)
        self.pal = np.unique(np.asarray(src).reshape(-1, 3), axis=0)
        self.PL = lab(self.pal)
        pk = pack_key(self.pal)
        order = np.argsort(pk)
        self.idx = order[np.searchsorted(pk[order], pack_key(self.rgb))]
        assert (self.pal[self.idx] == self.rgb).all(), 'image uses colours outside pal_from'
        self.T = T
        self.H, self.W = self.idx.shape
        self.lum = self.pal @ np.array([0.3, 0.55, 0.15])
        self.yy, self.xx = np.mgrid[0:self.H, 0:self.W]
        if vig:
            self.vlev = vignette_levels(self.H, self.W, vig[0], vig[1])
            self.vmaps = [np.arange(len(self.pal))] + [self.lmap(1 - 0.12 * k) for k in range(1, int(self.vlev.max()) + 1)]
        else:
            self.vlev = np.zeros((self.H, self.W), int)
            self.vmaps = [np.arange(len(self.pal))]

    # ---------- palette maps (index -> index) ----------
    def nearest(self, rgb, exclude=None):
        d = ((lab(np.asarray(rgb).reshape(-1, 3))[:, None] - self.PL[None]) ** 2).sum(-1)
        if exclude is not None:
            d[np.arange(len(d)), exclude] += 1e9
        return d.argmin(1)

    def lmap(self, f):
        """each colour -> nearest palette colour with lightness * f"""
        L = self.PL.copy()
        L[:, 0] *= f
        return ((L[:, None] - self.PL[None]) ** 2).sum(-1).argmin(1)

    def vcol(self, c, y, x):
        """colour index c as it should look at (y,x) under the baked vignette"""
        return self.vmaps[min(self.vlev[y, x], len(self.vmaps) - 1)][c]

    def scale_map(self, f):
        return self.nearest(np.clip(self.pal * f, 0, 255))

    def mix_map(self, col, a):
        return self.nearest(np.clip(self.pal * (1 - a) + np.array(col) * a, 0, 255))

    def step_map(self, up=True):
        """each colour -> nearest strictly brighter (or darker) palette colour of similar hue"""
        out = np.arange(len(self.pal))
        for i in range(len(self.pal)):
            cand = [j for j in range(len(self.pal)) if (self.lum[j] > self.lum[i] + 3 if up else self.lum[j] < self.lum[i] - 3)]
            if not cand:
                continue
            d = ((self.PL[cand] - self.PL[i]) ** 2 * np.array([0.3, 1, 1])).sum(-1)
            out[i] = cand[int(np.argmin(d))]
        return out

    def dim_maps(self, levels=(0.25, 0.5, 0.75, 1.0), keep_red=True):
        """Lamp-dimming maps per level s (0..1 = how much of the lamp is lost): each colour -> a darker colour of the
        same hue family that is never warmer (losing lamp light can only cool a surface). Reds stay red."""
        P = self.pal.astype(int)
        PL = self.PL
        n = len(self.pal)
        maps = {}
        for s in levels:
            m = np.arange(n)
            for i in range(n):
                Li = PL[i, 0]
                tgt = Li * (1 - 0.6 * s)
                cand = [j for j in range(n) if PL[j, 0] < Li - 0.5 and (P[j, 0] - P[j, 2]) <= (P[i, 0] - P[i, 2]) + 2]
                if keep_red and PL[i, 1] > 15:
                    reds = [j for j in cand if PL[j, 1] > 12]
                    cand = reds or cand
                if not cand:
                    continue
                r = tgt / max(Li, 1e-3)
                T_ = np.array([tgt, PL[i, 1] * r, PL[i, 2] * r - 2 * s])
                sc = [(max(PL[j, 0] - tgt, 0) * 0.6) ** 2 + (min(PL[j, 0] - tgt, 0) * 0.35) ** 2 + 2.5 * ((PL[j, 1:] - T_[1:]) ** 2).sum() for j in cand]
                m[i] = cand[int(np.argmin(sc))]
            maps[s] = m
        return maps

    def render(self, I):
        return self.pal[I]


# ---------------- effects: take an index frame I (H,W) and phase u in [0,1) ----------------
def ripple(S, I, base, mask, u, amp=1.0, cycles=2, rowk=0.37, seed=0, band=1):
    """Water: horizontal row shifts inside mask. Sources must also be inside mask, so shorelines, posts, rails and
    boats never bend (keep rigid things OUT of the mask and 2-3 px away from it)."""
    rng = np.random.default_rng(seed)
    ph = rng.random(S.H)
    out = I.copy()
    for y in np.nonzero(mask.any(1))[0]:
        g = y // band
        a0 = 2 * np.pi * (ph[g] + g * rowk)
        dx = int(np.round(amp * 0.5 * (np.sin(2 * np.pi * cycles * u + a0) - np.sin(a0))))   # 0 at u=0
        if dx == 0:
            continue
        row = mask[y]
        xs = np.nonzero(row)[0]
        src = xs - dx
        ok = (src >= 0) & (src < S.W)
        ok[ok] &= row[src[ok]]
        ok[ok] &= S.vlev[y, src[ok]] == S.vlev[y, xs[ok]]
        out[y, xs[ok]] = base[y, src[ok]]
    return out


def sparkle(S, I, mask, u, upmap, rate=0.05, hold=3, seed=1):
    """Glints: some pixels in mask step one shade brighter; pattern changes every `hold` frames. Keep rate low -
    random twinkle at high rates reads as noise."""
    t = int(round(u * S.T))
    k = (t // hold) % (S.T // hold)
    if k == 0:
        return I
    rng = np.random.default_rng(seed * 1000 + k)
    m = mask & (rng.random((S.H, S.W)) < rate)
    out = I.copy()
    out[m] = upmap[I[m]]
    return out


def flicker(S, I, mask, level, maps):
    """Hand-timed lamp flicker. level: 1.0 = fully on, 0.5 = half the lamp light lost, ...
    maps: {s: index map} from S.dim_maps(), where s = share of the lamp light lost."""
    if level >= 0.999:
        return I
    k = min(maps, key=lambda v: abs(v - (1.0 - level)))
    out = I.copy()
    out[mask] = maps[k][I[mask]]
    return out


def flicker_radial(S, I, cand, center, R, amount, dimmap):
    """Lamp dip that falls off with distance through ordered dither (no hard box edge). amount 0..1."""
    if amount <= 0:
        return I
    w = np.clip(1 - np.hypot(S.xx - center[0], S.yy - center[1]) / R, 0, 1) ** 0.6 * amount
    m = cand & (w > BAYER4[S.yy % 4, S.xx % 4])
    out = I.copy()
    out[m] = dimmap[I[m]]
    return out


def wisps(S, I, weight, u, fmap, period=160, cycles=1, seed=3, thr=0.6, sx=24, sy=1.2, drift=None):
    """Pixel-art mist: flat, horizontally stretched wisps (no dither stipple) sliding sideways, tileable -> seamless.
    drift: px moved per loop (default = one period, i.e. cycles*period). For mist that must stay attached to a
    scrolling ground use a small drift (8-16 px per loop) and cross-fade (see parallax notes)."""
    rng = np.random.default_rng(seed)
    n = gaussian_filter(rng.random((S.H, period)), (sy, sx), mode='wrap')
    n = (n - n.min()) / (n.max() - n.min())
    shift = int(round((drift if drift is not None else period * cycles) * u))
    f = n[S.yy, (S.xx - shift) % period] * weight
    m = f > thr
    out = I.copy()
    out[m] = fmap[I[m]]
    return out


def shift_region(S, I, base, mask, dx, dy):
    """Move the pixels of mask by (dx,dy) as one rigid block (breathing body, bobbing boat)."""
    out = I.copy()
    ys, xs = np.nonzero(mask)
    ty, tx = ys + dy, xs + dx
    ok = (ty >= 0) & (ty < S.H) & (tx >= 0) & (tx < S.W)
    out[ty[ok], tx[ok]] = base[ys[ok], xs[ok]]
    return out


def sway(S, I, base, mask, u, amp, weight, cycles=1, phase=0.0):
    """Foliage / grass / reeds: each ROW of the mask shifts as one rigid run (so a blade keeps its width and its
    head stays on its stem). weight: (H,) 0 at the anchored end .. 1 at the free end. Keep amp <= 1 px for leaves."""
    out = I.copy()
    for y in np.nonzero(mask.any(1))[0]:
        dx = int(np.round(amp * weight[y] * (np.sin(2 * np.pi * (cycles * u + phase)) - np.sin(2 * np.pi * phase))))
        if dx == 0:
            continue
        xs = np.nonzero(mask[y])[0]
        src = xs - dx
        ok = (src >= 0) & (src < S.W)
        srcm = np.zeros_like(xs, bool)
        srcm[ok] = mask[y, src[ok]] & (S.vlev[y, src[ok]] == S.vlev[y, xs[ok]])
        out[y, xs[ok & srcm]] = base[y, src[ok & srcm]]
    return out


class Leaves:
    """Falling leaves on periodic paths: each crosses its vertical range k times per loop. occl: pixels leaves may
    not cover (e.g. a door frame). Leaves should leave the frame or land, never vanish mid-air."""
    def __init__(self, S, n, xrange, yrange, colors, seed=5, kmin=1, kmax=2, sway=(3, 9), tumble=True, colors2=None):
        rng = np.random.default_rng(seed)
        self.p = []
        for _ in range(n):
            self.p.append(dict(x0=rng.uniform(*xrange), y0=rng.random(), k=int(rng.integers(kmin, kmax + 1)),
                               sa=rng.uniform(*sway), sc=int(rng.integers(1, 3)), sp=rng.random(),
                               col=colors[int(rng.integers(len(colors)))],
                               col2=(colors2 or colors)[int(rng.integers(len(colors2 or colors)))],
                               yr=yrange, drift=rng.uniform(-1, 1) * 30))
        self.S = S
        self.tumble = tumble

    def draw(self, I, u, occl=None):
        out = I.copy()
        S = self.S
        t = int(round(u * S.T))
        for q in self.p:
            y0, y1 = q['yr']
            f = (q['y0'] + q['k'] * u) % 1.0
            y = y0 + (y1 - y0) * f
            x = q['x0'] + q['sa'] * np.sin(2 * np.pi * (q['sc'] * u + q['sp'])) + q['drift'] * f
            xi, yi = int(round(x)), int(round(y))
            shape = [(0, 0), (1, 0)] if (not self.tumble or (t // 2 + int(q['sp'] * 7)) % 3) else [(0, 0), (0, 1)]
            for j, (ax, ay) in enumerate(shape):
                X, Y = xi + ax, yi + ay
                if 0 <= X < S.W and 0 <= Y < S.H and (occl is None or not occl[Y, X]):
                    out[Y, X] = S.vcol(q['col'] if j == 0 else q['col2'], Y, X)
        return out


class Dust:
    """Slowly floating dust in a lit room. No blinking (a blinking single pixel reads as a dead pixel). Each mote
    wanders on a smooth closed path and is drawn one palette step brighter than what is behind it (two steps inside
    `light`), so it shows in the lamp light and fades into the dark."""
    def __init__(self, S, n, sampler, seed=41, amp=(5, 14), light=None):
        rng = np.random.default_rng(seed)
        self.S = S
        self.light = light
        self.up = S.step_map(True)
        self.m = []
        for _ in range(n):
            cx, cy = sampler(rng)
            self.m.append(dict(cx=cx, cy=cy, ax=rng.uniform(*amp), ay=rng.uniform(amp[0] * 0.6, amp[1] * 0.7),
                               bx=rng.uniform(1, 4), by=rng.uniform(1, 3), p=rng.random(4),
                               s=rng.choice([-1, 1]), c2=int(rng.integers(2, 4))))

    def draw(self, I, u):
        out = I.copy()
        S = self.S
        a = 2 * np.pi * u
        for m in self.m:
            x = m['cx'] + m['ax'] * np.sin(m['s'] * a + 2 * np.pi * m['p'][0]) + m['bx'] * np.sin(m['c2'] * a + 2 * np.pi * m['p'][1])
            y = m['cy'] + m['ay'] * np.cos(a + 2 * np.pi * m['p'][2]) + m['by'] * np.sin(m['c2'] * a + 2 * np.pi * m['p'][3])
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < S.W and 0 <= yi < S.H:
                k = self.up[I[yi, xi]]
                if self.light is not None and self.light[yi, xi]:
                    k = self.up[k]
                out[yi, xi] = k
        return out


class Birds:
    """Small birds circling: 2-3 px 'v' that flaps (2 poses), on closed elliptical paths. sky: bool mask where
    birds may be drawn (keep them above ridgelines)."""
    def __init__(self, S, n, centers, color, seed=7, r=(10, 30), sky=None):
        rng = np.random.default_rng(seed)
        self.S, self.color, self.sky = S, color, sky
        self.b = [dict(c=centers[i % len(centers)], rx=rng.uniform(*r), ry=rng.uniform(r[0] * 0.3, r[1] * 0.4),
                       ph=rng.random(), d=rng.choice([-1, 1]), fl=int(rng.integers(0, 4))) for i in range(n)]

    def draw(self, I, u):
        out = I.copy()
        S = self.S
        t = int(round(u * S.T))
        for b in self.b:
            a = 2 * np.pi * (b['d'] * u + b['ph'])
            x = int(round(b['c'][0] + b['rx'] * np.cos(a)))
            y = int(round(b['c'][1] + b['ry'] * np.sin(a)))
            up = ((t + b['fl']) // 3) % 2 == 0
            pts = [(0, 0), (-1, -1 if up else 0), (1, -1 if up else 0)]
            for dx, dy in pts:
                X, Y = x + dx, y + dy
                if 0 <= X < S.W and 0 <= Y < S.H and (self.sky is None or self.sky[Y, X]):
                    out[Y, X] = S.vcol(self.color, Y, X)
        return out


# ---------------- output + checks ----------------
def write_loop(name, frames, pal, outdir, fps=12, review_scale=3, repeats=3, mp4=True):
    """frames: list of index arrays (or RGB arrays). Writes frames_native/<name>_LOOP_NNNN.png and a review mp4
    (`repeats` loops, exact integer nearest upscale)."""
    nd = os.path.join(outdir, name, 'frames_native')
    os.makedirs(nd, exist_ok=True)
    paths = []
    for i, I in enumerate(frames):
        img = pal[I] if I.ndim == 2 else I
        p = os.path.join(nd, f'{name}_LOOP_{i:04d}.png')
        Image.fromarray(img.astype(np.uint8)).save(p)
        paths.append(p)
    if mp4:
        lst = os.path.join(outdir, name, '_list.txt')
        with open(lst, 'w') as fh:
            for _ in range(repeats):
                for i in range(len(frames)):
                    fh.write(f"file 'frames_native/{name}_LOOP_{i:04d}.png'\nduration {1 / fps}\n")
        H, W = (frames[0].shape[:2])
        try:
            subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-vf',
                            f'scale={W * review_scale}:{H * review_scale}:flags=neighbor,fps={fps}', '-c:v', 'libx264',
                            '-crf', '12', '-pix_fmt', 'yuv420p', os.path.join(outdir, name, f'{name}_LOOP_review_{W * review_scale}.mp4')],
                           check=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            print('ffmpeg review video skipped:', e)
        finally:
            if os.path.exists(lst):
                os.remove(lst)
    return paths


def loop_stats(frames, still_idx=None):
    """Numbers for the README / QA:
    seam = changed px from the last frame back to frame 0, compared with the mean of ordinary neighbour pairs
    (should be about the same); frame0_vs_still; max_toggles = most colour changes any single pixel makes per loop
    (high values on isolated pixels = flicker); moving_px = pixels that ever change."""
    F = np.stack(frames)
    d = [(F[i] != F[i + 1]).sum() for i in range(len(F) - 1)]
    seam = int((F[-1] != F[0]).sum())
    tog = (F != np.roll(F, -1, 0)).sum(0)
    out = dict(frames=len(F), seam_changed_px=seam, mean_neighbour_changed_px=float(np.mean(d)) if d else 0.0,
               moving_px=int((tog > 0).sum()), max_toggles_per_px=int(tog.max()))
    if still_idx is not None:
        out['frame0_vs_still_px'] = int((F[0] != still_idx).sum())
    return out
