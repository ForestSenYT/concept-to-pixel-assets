"""Body motion and the standard front-view clip set (idle / talk / expression transitions / nod / head shake).

Motion rules (learned the hard way - see references/character-animation.md):
  * every move is a whole-pixel move of a rigid block: breathing lifts everything above the chest row by 1 px,
    a nod moves the head block 1 px; never shear row by row (that tears outlines)
  * eyes only blink (no glances) unless the user asks for a specific look
  * hair moves only with the head / body that carries it (no wind, no flutter on breaths)
  * expression changes are hidden inside a blink: the face swaps while the eyes are closed
  * every one-shot clip starts on some Idle frame 0 and ends exactly on its target Idle frame 0; every loop starts
    on its expression still, so any clip can follow any other without a jump
  * identical consecutive frames are merged (durations added)
"""
import numpy as np

TALK = [('closed', 110), ('half', 90), ('open', 120), ('half', 80), ('closed', 100), ('open', 110), ('half', 90),
        ('closed', 140), ('half', 90), ('open', 100), ('closed', 160)]   # 11 frames, 1190 ms


def breathe(a, chest_row, up=1):
    """Lift every row above chest_row by `up` px (row chest_row-1 is doubled, inside the torso)."""
    if not up:
        return a
    n = a.copy()
    n[0:chest_row - up] = a[up:chest_row]
    return n


def best_breath_row(a, lo, hi):
    """Chest row in [lo, hi) whose doubling is least visible (row y-1 most similar to row y)."""
    a = np.asarray(a).astype(int)
    scores = [((a[y - 1] != a[y]).any(-1).sum(), y) for y in range(lo, hi)]
    return min(scores)[1]


def head_mask_from(a, max_row, extra=None):
    """Default head block: every opaque pixel above max_row, plus `extra` (bool mask: hair locks / ponytail that hang
    lower but belong to the head). Exclude the collar so it does not move with the head."""
    op = a[..., 3] > 0
    m = np.zeros(op.shape, bool)
    m[:max_row + 1] = op[:max_row + 1]
    if extra is not None:
        m |= op & extra
    return m


def move_head(a, dx, dy, mask, line=(21, 4, 3)):
    """Move the head block by whole pixels. Pixels it leaves behind become transparent, except where they sit on the
    body (neck / collar right below) - those close with the outline colour instead of leaving a hole."""
    n = a.copy()
    ys, xs = np.nonzero(mask)
    newm = np.zeros_like(mask)
    newm[ys + dy, xs + dx] = True
    vac = mask & ~newm
    n[vac] = 0
    op = a[..., 3] > 0
    H = a.shape[0]
    for y, x in zip(*np.nonzero(vac)):
        if y + 1 < H and op[y + 1, x] and not mask[y + 1, x] and y >= ys.max() - 4:
            n[y, x, :3] = line
            n[y, x, 3] = 255
    n[ys + dy, xs + dx] = a[ys, xs]
    # any vacated pixel that ended up as a tiny enclosed hole (e.g. beside a hair lock during a shake) -> outline
    from scipy import ndimage as ndi
    lab, k = ndi.label(n[..., 3] == 0)
    if k:
        sz = np.bincount(lab.ravel())
        for i in np.unique(lab[vac & (n[..., 3] == 0)]):
            if i == 0 or sz[i] > 3:
                continue
            m = lab == i
            yy, xx = np.nonzero(m)
            if yy.min() > 0 and xx.min() > 0 and yy.max() < n.shape[0] - 1 and xx.max() < n.shape[1] - 1:
                n[m, :3] = line
                n[m, 3] = 255
    return n


class Clips:
    def __init__(self):
        self.clips = {}

    def add(self, name, frames, loop=True, state=None, view='front'):
        out = []
        for img, ms, note in frames:
            if out and (out[-1][0] == img).all():
                out[-1] = (out[-1][0], out[-1][1] + ms, out[-1][2] + ' + ' + note)
            else:
                out.append((img, ms, note))
        self.clips[name] = dict(frames=out, loop=loop, state=state, view=view)
        return self.clips[name]


def short(expr):
    """'CL04_Surprised' -> 'Surprised' (clip suffix)."""
    return expr.split('_', 1)[1] if '_' in expr else expr


def build_front_set(rig, chest_row, head_mask, neutral=None, talk_map=None, talk=TALK, mouth_feature='mouth',
                    idle=(1150, 850, 450), include=('idle', 'talk', 'transitions', 'nod', 'shake'), performances=None,
                    shake_expr=None):
    """Standard front clip set for every expression in the rig.
    head_mask: bool mask of the head block on the neutral sprite. talk_map: {expr: {'half': state, 'open': state}}
    to replace the generic talk mouths (e.g. a laughing open mouth for a happy face).
    performances: {clip_name: {'state': end_expr, 'steps': [{'expr':..,'eyes':..,'mouth':..,'head':[dx,dy],
    'breath':0/1,'ms':..,'note':..}, ...]}} for extra one-shots such as a slowly growing smile."""
    exprs = list(rig.expressions)
    neutral = neutral or exprs[0]
    C = Clips()
    f = rig.face(neutral)
    talk_map = talk_map or {}
    if 'idle' in include:
        for n in exprs:
            a = rig.face(n)
            seq = [(a, idle[0], 'rest'), (breathe(a, chest_row), idle[1], 'breath in: head + shoulders up 1px'), (a, idle[2], 'breath out')]
            for st, ms, note in rig.blink_seq(n):
                seq.append((rig.face(n, eyes=st), ms, note))
            C.add(f'Idle_{short(n)}', seq, state=n)
    if 'talk' in include:
        for n in exprs:
            seq = []
            for mk, ms in talk:
                k = rig.expressions[n][mouth_feature] if mk == 'closed' else talk_map.get(n, {}).get(mk, mk)
                seq.append((rig.face(n, **{mouth_feature: k}), ms, f'mouth {mk}'))
            C.add(f'Talk_{short(n)}', seq, state=n)
    if 'nod' in include:
        down = move_head(f, 0, 1, head_mask)
        C.add('Nod', [(f, 160, 'rest'), (down, 130, 'head down 1px'), (down, 180, 'hold'), (f, 120, 'back up'), (f, 220, 'rest')],
              loop=False, state=neutral)
        closed = [n for n in exprs if all(rig.expressions[n].get(e) == 'closed' for e in rig.eyes)]
        shut = rig.face(closed[0]) if closed else rig.face(neutral, eyes='closed')
        C.add('Nod_Slow', [(f, 200, 'rest'), (down, 220, 'head down'), (move_head(shut, 0, 1, head_mask), 420, 'eyes close, hold'),
                           (down, 160, 'eyes open'), (f, 200, 'back up'), (f, 260, 'rest')], loop=False, state=neutral)
    if 'shake' in include:
        e = shake_expr or neutral
        b = rig.face(e)
        L, R = move_head(b, -1, 0, head_mask), move_head(b, 1, 0, head_mask)
        C.add('HeadShake', [(b, 160, 'rest'), (L, 110, 'left 1px'), (b, 90, 'centre'), (R, 110, 'right 1px'), (b, 90, 'centre'),
                            (L, 110, 'left'), (b, 90, 'centre'), (R, 110, 'right'), (b, 260, 'rest')], loop=False, state=e)
    if 'transitions' in include:
        for n in exprs:
            if n == neutral:
                continue
            # always 680 ms: neutral -> half -> closed (face switches) -> half of the target -> target. For eyes that
            # never half-close (closed, smile arcs, already half-lidded) the 'half' frame equals the target and the
            # identical frames merge, so they open straight into their shape.
            tgt = rig.face(n)
            half_t = rig.face(n, eyes='half')
            seq = [(f, 140, f'from {short(neutral)}'), (rig.face(neutral, eyes='half'), 60, 'blink'),
                   (rig.face(n, eyes='closed'), 100, 'closed: face switches'), (half_t, 60, 'opening'), (tgt, 320, f'{short(n)} hold')]
            C.add(f'To_{short(n)}', seq, loop=False, state=n)
            back = [(tgt, 140, f'from {short(n)}'), (half_t, 60, 'blink'), (rig.face(n, eyes='closed'), 100, 'blink: closed, switch back'),
                    (rig.face(neutral, eyes='half'), 60, 'opening'), (f, 320, f'{short(neutral)} hold')]
            C.add(f'From_{short(n)}', back, loop=False, state=neutral)
    for name, p in (performances or {}).items():
        seq = []
        for s in p['steps']:
            kw = {k: v for k, v in s.items() if k not in ('expr', 'eyes', 'head', 'breath', 'ms', 'note')}
            a = rig.face(s.get('expr', neutral), eyes=s.get('eyes'), **kw)
            if s.get('head'):
                a = move_head(a, s['head'][0], s['head'][1], head_mask)
            if s.get('breath'):
                a = breathe(a, chest_row)
            seq.append((a, s['ms'], s.get('note', '')))
        C.add(name, seq, loop=p.get('loop', False), state=p['state'])
    return C


def continuity_issues(clips):
    """Loops (Idle_/Talk_) must start on their Idle frame 0; one-shots must start on SOME Idle frame 0 and end on
    their state's Idle frame 0. Returns a list of (clip, problem)."""
    idle0 = {c['state']: c['frames'][0][0] for k, c in clips.items() if k.startswith('Idle_')}
    bad = []
    for k, c in clips.items():
        f0, fl = c['frames'][0][0], c['frames'][-1][0]
        st = c['state']
        if st not in idle0:
            bad.append((k, f'no Idle clip for state {st}'))
            continue
        if c['loop']:
            if not (f0 == idle0[st]).all():
                bad.append((k, 'loop does not start on its Idle frame 0'))
        else:
            if not (fl == idle0[st]).all():
                bad.append((k, 'one-shot does not end on its state Idle frame 0'))
            if not any((f0 == v).all() for v in idle0.values()):
                bad.append((k, 'one-shot does not start on any Idle frame 0'))
    return bad
