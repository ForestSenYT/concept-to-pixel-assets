"""Post-process an external image-to-video clip into a palette-locked pixel sequence that matches a finished still.

Use when a motion is too complex to hand-animate (e.g. a forward drive). Steps:
  1. decode at the target fps and area-scale to the native grid (fits the pixel grid)
  2. 3-frame temporal median to kill AI shimmer
  3. snap every pixel to the still's own palette
  4. paste rigid regions from the still on every frame (car interior, UI frame, anything that must never wobble)
Generating the clip with an online service usually costs the user credits: confirm before generating, and let the
user sign in themselves.
"""
import os
import subprocess
import numpy as np
from PIL import Image
from .palette import quantize, unique_colors


def postprocess_clip(video, still, out_dir, rigid_mask=None, fps=12, name='CLIP', median=True):
    base = np.array(Image.open(still).convert('RGB')) if isinstance(still, str) else np.asarray(still)
    H, W = base.shape[:2]
    pal = unique_colors(base)
    raw = os.path.join(out_dir, 'raw')
    nat = os.path.join(out_dir, 'frames_native')
    os.makedirs(raw, exist_ok=True)
    os.makedirs(nat, exist_ok=True)
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', video, '-vf', f'fps={fps},scale={W}:{H}:flags=area',
                    os.path.join(raw, '%04d.png')], check=True)
    names = sorted(os.listdir(raw))
    fr = np.stack([np.array(Image.open(os.path.join(raw, n)).convert('RGB')) for n in names]).astype(np.int16)
    if median and len(fr) >= 3:
        med = fr.copy()
        med[1:-1] = np.median(np.stack([fr[:-2], fr[1:-1], fr[2:]]), 0)
        fr = med
    out = []
    for i, f in enumerate(fr):
        q = quantize(f.astype(np.uint8), pal)
        if rigid_mask is not None:
            q[rigid_mask] = base[rigid_mask]
        Image.fromarray(q).save(os.path.join(nat, f'{name}_{i:04d}.png'))
        out.append(q)
    return out
