#!/usr/bin/env python3
"""Finished 1x base + featureless face + character config -> full front sprite pack (clips, normals, previews,
Unity scripts) + audit.

    python build_character.py character.json

See assets/examples/character.example.json for every field. Paths in the config are relative to the config file.
Prints the audit; exits non-zero if the neutral face does not reproduce the base or the audit fails.
"""
import json
import os
import sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pixkit.face import FaceRig
from pixkit import motion as MO
from pixkit.normals import PartClassifier
from pixkit.pack import write_pack
from pixkit.audit import audit_sprite_pack


def load(p, d):
    p = p if os.path.isabs(p) else os.path.join(d, p)
    return np.load(p) if p.endswith('.npy') else np.array(Image.open(p).convert('RGBA'))


def main():
    cfg_path = sys.argv[1]
    d = os.path.dirname(os.path.abspath(cfg_path))
    cfg = json.load(open(cfg_path))
    base = load(cfg['base'], d)
    rig = FaceRig(load(cfg['face_base'], d), cfg['face'])
    neutral = cfg.get('neutral', list(cfg['face']['expressions'])[0])
    if not (rig.face(neutral) == base).all():
        diff = np.argwhere((rig.face(neutral) != base).any(-1))
        sys.exit(f'neutral face drawn by the rig differs from the base at {len(diff)} px, e.g. (y,x) {diff[:6].tolist()} - '
                 f'fix the face_base or the neutral patterns first')
    cr = cfg.get('chest_row', 'auto')
    if cr == 'auto' or isinstance(cr, list):
        lo, hi = (cr if isinstance(cr, list) else [int(base.shape[0] * 0.28), int(base.shape[0] * 0.42)])
        cr = MO.best_breath_row(base, lo, hi)
        print('chest row (auto):', cr)
    hd = cfg['head']
    extra = np.zeros(base.shape[:2], bool)
    for x0, y0, x1, y1 in hd.get('extra_boxes', []):
        extra[y0:y1, x0:x1] = True
    head = MO.head_mask_from(base, hd['max_row'], extra)
    C = MO.build_front_set(rig, cr, head, neutral=neutral, talk_map=cfg.get('talk_map'), shake_expr=cfg.get('shake_expr'),
                           performances=cfg.get('performances'), include=tuple(cfg.get('include', ('idle', 'talk', 'transitions', 'nod', 'shake'))))
    bad = MO.continuity_issues(C.clips)
    if bad:
        print('continuity issues:', bad)
    stills = {n: rig.face(n) for n in rig.expressions}
    nc = cfg['normals']
    cls = PartClassifier(nc['rules'], nc.get('head'), nc.get('flat', ()))
    cast = [(lab, load(p, d)) for lab, p in cfg.get('cast', [])]
    out = cfg['out'] if os.path.isabs(cfg['out']) else os.path.join(d, cfg['out'])
    pack_dir = os.path.join(out, f"{cfg['character']}_{cfg['version']}")
    pv = cfg.get('preview', {})
    u = cfg.get('unity', {})
    man = write_pack(pack_dir, cfg['character'], cfg['version'], C.clips, stills, base, cls, neutral,
                     expr_labels=pv.get('expr_labels'), performances=pv.get('performances', []), face_box=tuple(cfg['face_box']),
                     lang=cfg.get('lang', 'zh'), unity_class=u.get('class'), unity_menu=u.get('menu'), ppu=u.get('ppu', 32), cast=cast,
                     foot_y=cfg.get('foot_y', 155))
    mouth = rig.feature_box(cfg['face'].get('mouth_feature', 'mouth'))
    eyes = rig.feature_box(*rig.eyes)
    rep = audit_sprite_pack(pack_dir, mouth_box=mouth, eye_box=eyes)
    rep['chest_row'] = int(cr)
    rep['clips'] = len(man['animations'])
    json.dump(rep, open(os.path.join(pack_dir, 'audit.json'), 'w'), indent=1)
    print(json.dumps({k: v for k, v in rep.items() if k != 'palette'}, ensure_ascii=False))
    print('pack ->', pack_dir)
    sys.exit(0 if rep['ok'] and not bad else 1)


if __name__ == '__main__':
    main()
