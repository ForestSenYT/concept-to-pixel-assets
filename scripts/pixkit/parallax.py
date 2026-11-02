"""Layered (parallax) scenes: compose, animated bands, Unity-friendly sheets.

A parallax scene is a list of RGBA layers, back to front, each W_board wide (horizontally tileable) and H high,
with a speed factor ("layer px moved per camera px"; 1.0 = the layer the characters walk on).
Lessons baked in:
  * keep the walkable ground and everything standing on it in ONE layer (per-row speeds shred the path)
  * factors that are too far apart make the back layers look pinned; ~0.3 / 0.45 / 0.6 / 1.0 read as one world
  * every offset is floor()-ed to whole pixels (no half-pixel shimmer)
  * occluded parts of back layers must be filled as complete, seamlessly tiling panoramas
"""
import json
import os
import subprocess
import numpy as np
from PIL import Image


def offset(cam, factor, W):
    return int(np.floor(cam * factor)) % W


def compose(layers, cam, view_w=640, x0=0, bg=(0, 0, 0)):
    """layers: list of (rgba (H,W,4) uint8, factor). Returns the camera view (H, view_w, 3)."""
    H = layers[0][0].shape[0]
    out = np.zeros((H, view_w, 3), np.uint8)
    out[:] = bg
    for img, f in layers:
        W = img.shape[1]
        cols = (np.arange(x0, x0 + view_w) + offset(cam, f, W)) % W
        src = img[:, cols]
        m = src[..., 3] > 0
        out[m] = src[m][:, :3]
    return out


def animated_bands(frames, pad=0, min_gap=8):
    """Row ranges [(y0,y1)] that change anywhere during the loop (frames: list of RGBA/RGB arrays). Only these rows
    need to ship as animated strips on top of the static layer."""
    F = np.stack([np.asarray(f) for f in frames])
    rows = np.nonzero((F != F[0:1]).any(axis=(0, 2, 3)) if F.ndim == 4 else (F != F[0:1]).any(axis=(0, 2)))[0]
    if len(rows) == 0:
        return []
    bands = []
    s = p = rows[0]
    for r in rows[1:]:
        if r - p > min_gap:
            bands.append((max(s - pad, 0), min(p + pad + 1, F.shape[1])))
            s = r
        p = r
    bands.append((max(s - pad, 0), min(p + pad + 1, F.shape[1])))
    return bands


def write_band_sheets(name, frames, bands, outdir, fps=12, max_w=4096):
    """For each band write <name>_band<i>_sheet.png (+ .json, TexturePacker-like) laying the 48 strips out in a grid
    no wider than max_w (Unity's Max Size 4096). Returns the list of written json paths."""
    os.makedirs(outdir, exist_ok=True)
    out = []
    for bi, (y0, y1) in enumerate(bands):
        strips = [np.asarray(f)[y0:y1] for f in frames]
        h, w = strips[0].shape[:2]
        cols = max(1, min(len(strips), max_w // w))
        rows = (len(strips) + cols - 1) // cols
        ch = strips[0].shape[2]
        sheet = np.zeros((rows * h, cols * w, ch), np.uint8)
        fr = []
        for i, s in enumerate(strips):
            X, Y = (i % cols) * w, (i // cols) * h
            sheet[Y:Y + h, X:X + w] = s
            fr.append({'filename': f'{name}_band{bi}_{i:02d}', 'frame': {'x': X, 'y': Y, 'w': w, 'h': h}, 'duration': int(round(1000 / fps))})
        png = f'{name}_band{bi}_sheet.png'
        Image.fromarray(sheet).save(os.path.join(outdir, png))
        meta = {'frames': fr, 'meta': {'image': png, 'size': {'w': cols * w, 'h': rows * h}, 'band_rows_top_origin': [int(y0), int(y1)], 'loop': True, 'fps': fps}}
        jp = os.path.join(outdir, f'{name}_band{bi}_sheet.json')
        json.dump(meta, open(jp, 'w'), indent=1)
        out.append(jp)
    return out


def write_parallax_json(path, layers_meta, board_px, ppu=32, camera_reference='1.0 = the layer the characters walk on'):
    """layers_meta: list of dicts back->front: {name, factor, animated_bands_rows}"""
    json.dump({'board_px': list(board_px), 'pixels_per_unit': ppu, 'camera_reference': camera_reference,
               'draw_order_back_to_front': [l['name'] for l in layers_meta],
               'layers': {l['name']: {k: v for k, v in l.items() if k != 'name'} for l in layers_meta}},
              open(path, 'w'), indent=1)


def scroll_review(layer_loops, path, seconds=12, px_per_s=40, view_w=640, scale=3, fps=60, loop_fps=12, sway=False):
    """Camera move review video. layer_loops: list of (list_of_rgba_frames, factor). sway=True swings back and forth
    (best for judging layer separation); otherwise a constant pan."""
    tmp = path + '_frames'
    os.makedirs(tmp, exist_ok=True)
    n = int(seconds * fps)
    for i in range(n):
        t = i / fps
        cam = (np.sin(2 * np.pi * t / seconds) * 120 + 120) if sway else t * px_per_s
        li = int(t * loop_fps)
        layers = [(fr[li % len(fr)], f) for fr, f in layer_loops]
        img = compose(layers, cam, view_w)
        Image.fromarray(np.repeat(np.repeat(img, scale, 0), scale, 1)).save(f'{tmp}/{i:05d}.png')
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-framerate', str(fps), '-i', f'{tmp}/%05d.png', '-c:v', 'libx264',
                    '-crf', '14', '-pix_fmt', 'yuv420p', path], check=True)
    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)
