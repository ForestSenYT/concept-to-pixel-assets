"""Write a character sprite pack in the shared format (same layout for every character of a cast).

<char>_<VER>/
  expressions/<Expr>.png            stills (= Idle_<Expr> frame 0)
  views/<CHAR>_front.png            neutral base
  animations/<Clip>/NN.png          frames
  animations/<Clip>_sheet.png/.json horizontal sheet + TexturePacker-style json (duration per frame, loop, state, view)
  animations/<Clip>_sheet_n.png     normal-map sheet, same layout
  normals/...                       per-frame / per-still normal maps
  previews/gif/<Clip>_3x.gif, previews/frames/<Clip>_frames.png, previews/expressions_2x.png,
  previews/all_clips_board.png, previews/scale_with_cast_3x.png, previews/normals_lit_3x.png,
  previews/gif/LIT_<Clip>_moving_light_3x.gif, previews/interactive_preview.html
  timing.csv, manifest.json, unity/Editor/*.cs
"""
import base64
import csv
import hashlib
import json
import os
import shutil
import numpy as np
from PIL import Image, ImageDraw
from . import normals as NM

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'assets')
BG = (36, 39, 44, 255)


def _save(O, a, p):
    os.makedirs(os.path.dirname(os.path.join(O, p)), exist_ok=True)
    Image.fromarray(np.asarray(a).astype(np.uint8), 'RGBA').save(os.path.join(O, p))


def _sha(O, p):
    return hashlib.sha256(open(os.path.join(O, p), 'rb').read()).hexdigest()


def _on_bg(a):
    b = Image.new('RGBA', (a.shape[1], a.shape[0]), BG)
    b.alpha_composite(Image.fromarray(np.asarray(a).astype(np.uint8), 'RGBA'))
    return b.convert('RGB')


def write_pack(out_dir, character, version, clips, stills, base, classifier, neutral, expr_labels=None,
               performances=(), face_box=None, lang='zh', unity_class=None, unity_menu=None, ppu=32,
               cast=(), lit_clips=None, transitions=None, foot_y=155, pivot=(0.5, 0.025)):
    """clips: {name: {'frames': [(rgba, ms, note)], 'loop', 'state', 'view'}} (motion.Clips().clips)
    stills: {expr_name: rgba}; base: neutral rgba; classifier: normals.PartClassifier
    neutral: expression name of the neutral face (e.g. 'CL01_Neutral')
    expr_labels: {short_name: label} for the preview buttons (default = short names)
    performances: [{'name': 'Nod', 'label': '点头', 'need': 'Neutral', 'end': 'Neutral'}] buttons in the preview
    face_box: (x0, y0, x1, y1) crop used for face previews; cast: [(label, rgba)] other characters for the scale check
    Returns the manifest dict."""
    O = out_dir.rstrip('/') + '/'
    shutil.rmtree(O, ignore_errors=True)
    os.makedirs(O)
    H, W = base.shape[:2]
    face_box = face_box or (0, 0, W, min(H, W))
    short = lambda n: n.split('_', 1)[1] if '_' in n else n
    cache = {}

    def nrm(a):
        k = a.tobytes()
        if k not in cache:
            cache[k] = NM.normals(a, classifier)
        return cache[k]

    man = {'character': character, 'version': version, 'canvas': [W, H], 'pivot_normalized': list(pivot), 'foot_line_y': foot_y,
           'ppu': ppu, 'neutral': neutral, 'states': [], 'views': [], 'animations': {}, 'transitions': None}
    for n, a in stills.items():
        _save(O, a, f'expressions/{n}.png')
        _save(O, nrm(a), f'normals/expressions/{n}_n.png')
        man['states'].append({'name': n, 'file': f'expressions/{n}.png', 'idle': f'Idle_{short(n)}', 'sha256': _sha(O, f'expressions/{n}.png')})
    vname = f'{character.split("_")[0].upper()}_front'
    _save(O, base, f'views/{vname}.png')
    _save(O, nrm(base), f'normals/views/{vname}_n.png')
    man['views'].append({'view': 'front', 'file': f'views/{vname}.png', 'sha256': _sha(O, f'views/{vname}.png')})
    rows, boards = [], []
    for n, c in clips.items():
        fr = c['frames']
        N = len(fr)
        sh = np.zeros((H, W * N, 4), np.uint8)
        shn = np.zeros_like(sh)
        shn[...] = (128, 128, 255, 0)
        for i, (a, ms, note) in enumerate(fr):
            a = a.astype(np.uint8)
            _save(O, a, f'animations/{n}/{i:02d}.png')
            sh[:, W * i:W * i + W] = a
            nn = nrm(a)
            _save(O, nn, f'normals/{n}/{i:02d}_n.png')
            shn[:, W * i:W * i + W] = nn
        Image.fromarray(sh, 'RGBA').save(O + f'animations/{n}_sheet.png')
        Image.fromarray(shn, 'RGBA').save(O + f'animations/{n}_sheet_n.png')
        json.dump({'frames': [{'filename': f'{n}_{i:02d}', 'frame': {'x': W * i, 'y': 0, 'w': W, 'h': H}, 'rotated': False, 'trimmed': False,
                               'spriteSourceSize': {'x': 0, 'y': 0, 'w': W, 'h': H}, 'sourceSize': {'w': W, 'h': H}, 'duration': ms, 'note': note}
                              for i, (_, ms, note) in enumerate(fr)],
                   'meta': {'app': f'{character} {version}', 'image': f'{n}_sheet.png', 'format': 'RGBA8888', 'size': {'w': W * N, 'h': H}, 'scale': '1',
                            'pivot_normalized': list(pivot), 'loop': c['loop'], 'state': c['state'], 'view': c.get('view', 'front'),
                            'frameTags': [{'name': n, 'from': 0, 'to': N - 1, 'direction': 'forward'}]}},
                  open(O + f'animations/{n}_sheet.json', 'w'), indent=1, ensure_ascii=False)
        g = []
        for a, ms, _ in fr:
            if g and (g[-1][0] == a).all():
                g[-1][1] += ms
            else:
                g.append([a, ms])
        gi = [_on_bg(a).resize((W * 3, H * 3), Image.NEAREST) for a, _ in g]
        os.makedirs(O + 'previews/gif', exist_ok=True)
        gi[0].save(O + f'previews/gif/{n}_3x.gif', save_all=True, append_images=gi[1:], duration=[x[1] for x in g], loop=0 if c['loop'] else 1, disposal=1)
        x0, y0, x1, y1 = face_box
        z = 4
        w, h = (x1 - x0) * z, (y1 - y0) * z
        cols = min(N, 8)
        R = (N + cols - 1) // cols
        im = Image.new('RGB', (cols * (w + 4), R * (h + 18)), (24, 26, 30))
        dr = ImageDraw.Draw(im)
        for i, (a, ms, note) in enumerate(fr):
            X, Y = (i % cols) * (w + 4), (i // cols) * (h + 18)
            im.paste(_on_bg(a).crop(face_box).resize((w, h), Image.NEAREST), (X, Y + 18))
            dr.text((X + 3, Y + 4), f'{i:02d} {ms}ms', fill=(255, 214, 120))
        os.makedirs(O + 'previews/frames', exist_ok=True)
        im.save(O + f'previews/frames/{n}_frames.png')
        t = 0
        for i, (_, ms, note) in enumerate(fr):
            rows.append([n, c['state'], i, ms, t, round(t * 60 / 1000), max(1, round(ms * 60 / 1000)), note])
            t += ms
        man['animations'][n] = {'state': c['state'], 'view': c.get('view', 'front'), 'loop': c['loop'], 'durations_ms': [ms for _, ms, _ in fr], 'total_ms': t,
                                'sheet': f'animations/{n}_sheet.png', 'sheet_normal': f'animations/{n}_sheet_n.png',
                                'frames': [{'file': f'animations/{n}/{i:02d}.png', 'note': note} for i, (_, _, note) in enumerate(fr)]}
        boards.append((n, fr[0][0]))
    nshort = short(neutral)
    man['transitions'] = transitions or {
        'Idle_<E> <-> Talk_<E>': 'any frame boundary; frame 0 of both is the expression still',
        f'Idle_{nshort} -> To_<E> -> Idle_<E>': f'To_<E> frame 0 == Idle_{nshort} frame 0; last frame == Idle_<E> frame 0',
        f'Idle_<E> -> From_<E> -> Idle_{nshort}': f'From_<E> frame 0 == Idle_<E> frame 0; last frame == Idle_{nshort} frame 0',
        '<E1> -> <E2>': f'From_<E1> then To_<E2> (both pass through {nshort})',
        'one-shots': 'first frame == some Idle frame 0, last frame == Idle frame 0 of the clip state'}
    with open(O + 'timing.csv', 'w', newline='', encoding='utf-8-sig') as f:
        wr = csv.writer(f)
        wr.writerow(['clip', 'state', 'frame', 'duration_ms', 'start_ms', 'start_frame@60fps', 'length_frames@60fps', 'note'])
        wr.writerows(rows)
    # ---- previews
    x0, y0, x1, y1 = face_box
    fw, fh = (x1 - x0) * 2, (y1 - y0) * 2
    ex = list(stills.items())
    E = Image.new('RGB', (len(ex) * (fw + 4), fh + 20), BG[:3])
    dr = ImageDraw.Draw(E)
    for i, (n, a) in enumerate(ex):
        E.paste(_on_bg(a).crop(face_box).resize((fw, fh), Image.NEAREST), (i * (fw + 4) + 2, 2))
        dr.text((i * (fw + 4) + 4, fh + 5), short(n), fill=(230, 230, 230))
    E.resize((E.width * 2, E.height * 2), Image.NEAREST).save(O + 'previews/expressions_2x.png')
    cols = 10
    R = (len(boards) + cols - 1) // cols
    B = Image.new('RGB', (cols * (W + 4), R * (H + 20)), BG[:3])
    dr = ImageDraw.Draw(B)
    for i, (n, a) in enumerate(boards):
        B.paste(_on_bg(a), ((i % cols) * (W + 4) + 2, (i // cols) * (H + 20)))
        dr.text(((i % cols) * (W + 4) + 3, (i // cols) * (H + 20) + H + 3), n[:16], fill=(230, 230, 230))
    B.save(O + 'previews/all_clips_board.png')
    if cast:
        people = list(cast) + [(character, base)]
        S = Image.new('RGBA', (len(people) * (W + 10) + 20, H + 10), BG)
        for i, (lab_, im_) in enumerate(people):
            S.alpha_composite(Image.fromarray(np.asarray(im_).astype(np.uint8), 'RGBA'), (10 + i * (W + 10), 6))
        dr = ImageDraw.Draw(S)
        dr.line([(0, 6 + foot_y), (S.width, 6 + foot_y)], fill=(120, 110, 90, 255))
        S = S.convert('RGB').resize((S.width * 3, S.height * 3), Image.NEAREST)
        dr = ImageDraw.Draw(S)
        for i, (lab_, _) in enumerate(people):
            dr.text(((10 + i * (W + 10)) * 3 + 6, 4), lab_, fill=(255, 214, 120))
        S.save(O + 'previews/scale_with_cast_3x.png')
    bgf = np.array(BG[:3], float)

    def lit_img(a, n, L):
        l = NM.lit(a, n, L)
        return np.where(a[..., 3:] > 0, l, bgf).astype(np.uint8)
    nb = nrm(base)
    row = np.concatenate([np.where(base[..., 3:] > 0, base[..., :3], bgf).astype(np.uint8), np.where(base[..., 3:] > 0, nb[..., :3], bgf).astype(np.uint8)] +
                         [lit_img(base, nb, L) for L in ([-1, 0.25, 0.6], [1, 0.25, 0.6], [0, 1, 0.5])], 1)
    Image.fromarray(row).resize((row.shape[1] * 3, row.shape[0] * 3), Image.NEAREST).save(O + 'previews/normals_lit_3x.png')
    for cn in (lit_clips or [f'Idle_{nshort}', f'Talk_{nshort}']):
        if cn not in clips:
            continue
        fr = clips[cn]['frames']
        tl, t = [], 0
        for a, ms, _ in fr:
            tl.append((t, a))
            t += ms
        steps = 36
        per = max(t * 2 // steps, 60)
        frames = []
        for k in range(steps):
            tt = (k * per) % t
            a = [x for s, x in tl if s <= tt][-1]
            ang = 2 * np.pi * k / steps
            frames.append(Image.fromarray(lit_img(a, nrm(a), [np.cos(ang), 0.35 * np.sin(ang) + 0.2, 0.55])).resize((W * 3, H * 3), Image.NEAREST))
        frames[0].save(O + f'previews/gif/LIT_{cn}_moving_light_3x.gif', save_all=True, append_images=frames[1:], duration=per, loop=0)
    json.dump(man, open(O + 'manifest.json', 'w'), indent=2, ensure_ascii=False)
    # ---- interactive preview (single file, sheets embedded)
    data = {k: dict(img=base64.b64encode(open(O + f'animations/{k}_sheet.png', 'rb').read()).decode(), n=len(v['frames']), ms=v['durations_ms'],
                    notes=[f['note'] for f in v['frames']], loop=v['loop'], view=v['view'], state=v['state']) for k, v in man['animations'].items()}
    labels = expr_labels or {}
    cfg = dict(title=f'{character} {version}', lang=lang, w=W, h=H, neutral=nshort, face_crop=[x0, y0, x1 - x0, y1 - y0],
               expr={short(n): labels.get(short(n), short(n)) for n in stills}, perform=list(performances))
    html = open(os.path.join(ASSETS, 'preview_template.html'), encoding='utf-8').read()
    html = html.replace('/*__DATA__*/null', json.dumps(data, ensure_ascii=False)).replace('/*__CFG__*/null', json.dumps(cfg, ensure_ascii=False))
    html = html.replace('__TITLE__', f'{character} {version}').replace('__LANG__', lang)
    open(O + 'previews/interactive_preview.html', 'w', encoding='utf-8').write(html)
    # ---- unity editor scripts
    cls = unity_class or ''.join(p.capitalize() for p in character.replace('-', '_').split('_'))
    menu = unity_menu or character.replace('_', ' ')
    os.makedirs(O + 'unity/Editor', exist_ok=True)
    for t_, outn in (('ClipBuilder.cs.tmpl', f'{cls}ClipBuilder.cs'), ('NormalMaps.cs.tmpl', f'{cls}NormalMaps.cs')):
        s = open(os.path.join(ASSETS, 'unity', t_)).read()
        s = s.replace('__CLASS__', cls).replace('__MENU__', menu).replace('__CHAR__', f'{character}_{version}').replace('__PPU__', str(ppu))
        open(O + 'unity/Editor/' + outn, 'w').write(s)
    return man
