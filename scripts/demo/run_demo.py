#!/usr/bin/env python3
"""End-to-end smoke test on synthetic inputs (no real artwork is shipped with this repo).

    python scripts/demo/run_demo.py /tmp/pixkit_demo

1. paints a fake 1280x720 lakeside "concept" (sky, hills, lake, dock, lamp) with AI-like grain
2. scene_to_pixel.py --all  -> 640x360 24-colour still + 1920 copy
3. derives masks from the known geometry, writes a loop spec, make_loop.py -> 48-frame seamless loop + audit
4. make_review_pdf.py -> review PDF
5. paints a fake character concept -> sprite_from_concept.py (pixelize + materials)
6. paints a 1x demo sprite + featureless face -> build_character.py -> full sprite pack + audit
Exits non-zero if any audit fails.
"""
import json
import os
import subprocess
import sys
import numpy as np
import cv2
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
ROOT = os.path.dirname(SCRIPTS)


def run(*args):
    print('$', ' '.join(os.path.basename(a) if i == 1 else a for i, a in enumerate(args)))
    r = subprocess.run([sys.executable] + list(args), capture_output=True, text=True)
    print(r.stdout.strip()[-1500:])
    if r.returncode != 0:
        print(r.stderr[-3000:])
        raise SystemExit(f'failed: {args[0]}')
    return r.stdout


def paint_scene(path):
    W, H = 1280, 720
    rng = np.random.default_rng(0)
    yy, xx = np.mgrid[0:H, 0:W]
    img = np.zeros((H, W, 3), float)
    t = yy / 300.0
    sky = np.stack([70 + 150 * t, 80 + 90 * t, 120 - 20 * t], -1)
    img[:] = sky
    hills = 300 + 40 * np.sin(xx / 140.0) + 20 * np.sin(xx / 47.0)
    img[yy > hills] = (52, 62, 58)
    lake = yy > 380
    img[lake] = np.stack([60 + 0 * yy, 82 + 0.05 * (yy - 380), 100 + 0.08 * (yy - 380)], -1)[lake]
    glow = lake & (np.abs(xx - 900) < 60 - (yy - 380) * 0.1)
    img[glow] = (220, 160, 90)
    dock = (yy > 520) & (yy < 545) & (xx > 200) & (xx < 640)
    img[dock] = (96, 70, 52)
    for x in range(220, 640, 70):
        img[(yy >= 545) & (yy < 640) & (xx >= x) & (xx < x + 10)] = (70, 52, 40)
    img[(xx >= 1100) & (xx < 1108) & (yy > 200) & (yy < 520)] = (40, 40, 44)
    cv2.circle(img, (1104, 196), 14, (255, 220, 150), -1)
    reeds = (yy > 560) & (xx > 900) & (xx < 1260) & ((xx // 9) % 2 == 0) & (yy > 690 - 120 * np.abs(np.sin(xx / 31.0)))
    img[reeds] = (120, 110, 60)
    img += rng.normal(0, 7, img.shape)            # AI-ish grain the stylize pass must remove
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(path)


def scene_masks(still, d):
    """masks in native 640x360 coordinates of the painted geometry"""
    H, W = still.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    os.makedirs(d, exist_ok=True)
    rigid = ((yy >= 258) & (yy < 322) & (xx >= 98) & (xx < 322)) | ((xx >= 547) & (xx < 557) & (yy > 95) & (yy < 262))
    water = (yy > 194) & ~rigid
    water &= ~((yy > 275) & (xx > 445))          # keep 2-3 px away from the reeds
    masks = {
        'water': water,
        'glint': water & (np.abs(xx - 450) < 34),
        'mist': (yy > 190) & (yy < 214),
        'reeds': (yy > 280) & (xx > 450) & (xx < 630),
        'sky': yy < 140,
        'lamp_pool': np.hypot(xx - 552, yy - 98) < 60,
        'lamp': np.hypot(xx - 552, yy - 98) < 70,
        'rigid': rigid,
    }
    for k, m in masks.items():
        Image.fromarray((m * 255).astype(np.uint8)).save(os.path.join(d, f'{k}.png'))


def paint_character(path):
    W, H = 600, 1000
    img = np.zeros((H, W, 4), np.uint8)
    K = (20, 10, 10, 255)

    def ell(c, ax, col):
        cv2.ellipse(img, c, ax, 0, 0, 360, col, -1)
        cv2.ellipse(img, c, ax, 0, 0, 360, K, 6)

    def rect(p0, p1, col):
        cv2.rectangle(img, p0, p1, col, -1)
        cv2.rectangle(img, p0, p1, K, 6)
    rect((215, 560), (285, 930), (70, 72, 110, 255))     # legs
    rect((315, 560), (385, 930), (70, 72, 110, 255))
    rect((200, 930), (290, 975), (235, 230, 220, 255))   # shoes
    rect((310, 930), (400, 975), (235, 230, 220, 255))
    rect((190, 230), (410, 580), (180, 70, 60, 255))     # coat
    rect((140, 240), (190, 520), (180, 70, 60, 255))     # arms
    rect((410, 240), (460, 520), (180, 70, 60, 255))
    ell((300, 140), (95, 110), (90, 60, 50, 255))        # hair
    ell((300, 160), (70, 80), (245, 190, 150, 255))      # face
    cv2.line(img, (255, 150), (285, 150), K, 6)          # eyes
    cv2.line(img, (315, 150), (345, 150), K, 6)
    cv2.line(img, (290, 205), (310, 205), (150, 80, 70, 255), 5)
    Image.fromarray(img).save(path)


def paint_sprite_1x(d):
    """1x demo sprite (96x160) whose face matches the example face rig (eyes x41-44 / x48-51 at y22-26,
    mouth box x44-49 y28-31), plus the featureless face base."""
    C = lambda *v: np.array(list(v) + [255], np.uint8)
    K, HAIR, HAIRD = C(21, 4, 3), C(92, 65, 58), C(64, 49, 46)
    SK, ST, SM = C(250, 182, 143), C(232, 156, 120), C(204, 128, 98)
    SH, SHD = C(250, 229, 211), C(182, 158, 146)
    PA, PAD = C(82, 63, 59), C(60, 47, 45)
    a = np.zeros((160, 96, 4), np.uint8)
    yy, xx = np.mgrid[0:160, 0:96]
    hair = ((xx - 46.5) / 11.5) ** 2 + ((yy - 22) / 13) ** 2 <= 1
    a[hair] = HAIR
    a[hair & (xx < 41) & (yy > 20)] = HAIRD
    face = ((xx - 46.5) / 7.2) ** 2 + ((yy - 25.5) / 8.2) ** 2 <= 1
    face &= yy >= 20
    a[face] = SK
    a[face & (yy == 20)] = ST
    a[(yy >= 33) & (yy <= 36) & (xx >= 44) & (xx <= 49)] = ST          # neck
    torso = (yy >= 37) & (yy <= 100) & (xx >= 34) & (xx <= 59)
    a[torso] = SH
    a[torso & (xx >= 55)] = SHD
    arms = (yy >= 39) & (yy <= 88) & (((xx >= 29) & (xx <= 33)) | ((xx >= 60) & (xx <= 64)))
    a[arms] = SH
    a[(yy >= 85) & (yy <= 90) & (((xx >= 29) & (xx <= 33)) | ((xx >= 60) & (xx <= 64)))] = SK
    legs = (yy >= 101) & (yy <= 150) & (((xx >= 37) & (xx <= 45)) | ((xx >= 48) & (xx <= 56)))
    a[legs] = PA
    a[legs & ((xx == 37) | (xx == 48))] = PAD
    shoes = (yy >= 151) & (yy <= 155) & (((xx >= 35) & (xx <= 46)) | ((xx >= 47) & (xx <= 58)))
    a[shoes] = SHD
    op = a[..., 3] > 0
    from scipy import ndimage as ndi
    sil = op & ~ndi.binary_erosion(op)
    a[sil] = K
    a[(yy == 36) & (xx >= 36) & (xx <= 57) & op] = K                    # collar line
    a[(yy == 100) & (xx >= 34) & (xx <= 59)] = K                        # hem
    face_base = a.copy()
    # neutral features (exactly what the example rig draws for H01_Neutral)
    for x in range(41, 45):
        a[23, x] = K
    for x in range(48, 52):
        a[23, x] = K
    a[24, 43] = a[25, 43] = a[24, 49] = a[25, 49] = K
    a[29, 46] = a[29, 47] = SM
    Image.fromarray(a).save(os.path.join(d, 'H_base.png'))
    Image.fromarray(face_base).save(os.path.join(d, 'H_face_base.png'))


def main():
    out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else 'pixkit_demo')
    os.makedirs(out, exist_ok=True)
    ok = True
    # ---------------- scene
    paint_scene(os.path.join(out, 'concept_lake.png'))
    run(os.path.join(SCRIPTS, 'scene_to_pixel.py'), os.path.join(out, 'concept_lake.png'), out, '--name', 'DEMO_LAKE', '--all', '--smooth', '8,16')
    still = np.array(Image.open(os.path.join(out, 'DEMO_LAKE.png')).convert('RGB'))
    scene_masks(still, os.path.join(out, 'masks'))
    pal = np.unique(still.reshape(-1, 3), axis=0)
    lum = pal @ [0.3, 0.59, 0.11]
    warm = pal[np.argsort(-(pal[:, 0].astype(int) - pal[:, 2]))[:2]].tolist()
    dark = pal[np.argsort(lum)[0]].tolist()
    spec = {'still': 'DEMO_LAKE.png', 'name': 'DEMO_LAKE', 'out': 'loops', 'frames': 48, 'fps': 12, 'vignette': [0.36, 0.55],
            'effects': [{'type': 'ripple', 'mask': 'masks/water.png', 'amp': 1, 'cycles': 2},
                        {'type': 'sparkle', 'mask': 'masks/glint.png', 'rate': 0.04},
                        {'type': 'wisps', 'mask': 'masks/mist.png', 'thr': 0.62},
                        {'type': 'sway', 'mask': 'masks/reeds.png', 'amp': 1, 'anchor': 'bottom', 'cycles': 2},
                        {'type': 'leaves', 'n': 8, 'x': [440, 630], 'y': [10, 300], 'colors': warm},
                        {'type': 'birds', 'n': 3, 'centers': [[300, 60]], 'color': dark, 'sky': 'masks/sky.png'},
                        {'type': 'flicker', 'mask': 'masks/lamp.png', 'frames': {'26': 0.5, '28': 0.75, '29': 0.5}},
                        {'type': 'dust', 'n': 20, 'box': [500, 60, 600, 200], 'light': 'masks/lamp_pool.png'},
                        {'type': 'static', 'mask': 'masks/rigid.png'}]}
    json.dump(spec, open(os.path.join(out, 'loop_spec.json'), 'w'), indent=1)
    rep = json.loads(run(os.path.join(SCRIPTS, 'make_loop.py'), os.path.join(out, 'loop_spec.json')).strip().split('\n')[-1])
    ok &= rep['ok']
    fr = lambda i: f'loops/DEMO_LAKE/frames_native/DEMO_LAKE_LOOP_{i:04d}.png'
    rv = {'out': 'DEMO_LAKE_review.pdf', 'title': 'DEMO_LAKE review', 'footer': 'DEMO_LAKE',
          'cover': {'title': 'DEMO_LAKE', 'subtitle': 'still + 48-frame loop', 'lines': ['640x360, 24 colours'], 'image': 'DEMO_LAKE.png'},
          'pages': [{'type': 'compare', 'title': 'concept -> pixel', 'left': 'concept_lake.png', 'right': 'DEMO_LAKE.png', 'llabel': 'concept', 'rlabel': 'result'},
                    {'type': 'detail', 'title': 'detail: dock', 'src': 'concept_lake.png', 'out': 'DEMO_LAKE.png', 'box': [90, 240, 340, 330]},
                    {'type': 'keyframes', 'title': 'loop keyframes', 'frames': [fr(0), fr(12), fr(24), fr(36)], 'labels': ['0', '12', '24', '36']}]}
    json.dump(rv, open(os.path.join(out, 'review_spec.json'), 'w'), indent=1)
    run(os.path.join(SCRIPTS, 'make_review_pdf.py'), os.path.join(out, 'review_spec.json'))
    # ---------------- character
    paint_character(os.path.join(out, 'concept_char.png'))
    mats = {'_soft_line': ['hair', 'coat', 'pants'],
            'hair': {'ramp': [[64, 49, 46], [92, 65, 58], [118, 88, 76]], 'region': [0, 0, 96, 30]},
            'skin': {'ramp': [[204, 128, 98], [232, 156, 120], [250, 182, 143]], 'region': [0, 0, 96, 40]},
            'coat': {'ramp': [[120, 46, 42], [160, 62, 54], [192, 84, 68]], 'region': [0, 30, 96, 100]},
            'pants': {'ramp': [[48, 50, 78], [70, 72, 110]], 'region': [0, 95, 96, 150]},
            'shoe': {'ramp': [[182, 158, 146], [235, 230, 220]], 'region': [0, 148, 96, 160]}}
    json.dump(mats, open(os.path.join(out, 'materials.json'), 'w'), indent=1)
    run(os.path.join(SCRIPTS, 'sprite_from_concept.py'), os.path.join(out, 'concept_char.png'), os.path.join(out, 'sprite_draft'), '--height', '148',
        '--materials', os.path.join(out, 'materials.json'))
    work = os.path.join(out, 'work')
    os.makedirs(work, exist_ok=True)
    paint_sprite_1x(work)
    cfg = json.load(open(os.path.join(ROOT, 'assets', 'examples', 'character.example.json')))
    cfg.pop('_doc', None)
    cfg['cast'] = []
    cfg['normals']['rules'] = [
        {'part': 'hair', 'colors': [[64, 49, 46], [92, 65, 58]]},
        {'part': 'skin', 'colors': [[204, 128, 98], [232, 156, 120], [250, 182, 143], [150, 88, 72]]},
        {'part': 'shoe', 'colors': [[182, 158, 146]], 'region': [0, 150, 96, 160]},
        {'part': 'shirt', 'colors': [[250, 229, 211], [182, 158, 146]]},
        {'part': 'pants', 'colors': [[60, 47, 45], [82, 63, 59]]}]
    cfg['normals']['head'] = {'parts': ['hair', 'skin'], 'above_part': 'shirt'}
    cfg['head'] = {'max_row': 35, 'extra_boxes': []}
    cfg['chest_row'] = 'auto'
    json.dump(cfg, open(os.path.join(out, 'character.json'), 'w'), indent=1, ensure_ascii=False)
    try:
        run(os.path.join(SCRIPTS, 'build_character.py'), os.path.join(out, 'character.json'))
    except SystemExit as e:
        print(e)
        ok = False
    print('\nDEMO', 'OK' if ok else 'FAILED', '->', out)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
