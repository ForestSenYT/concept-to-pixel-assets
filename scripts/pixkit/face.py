"""Data-driven face rig: expressions are drawn as small character grids on a featureless face.

Config (JSON-able):
{
  "colors": {"K": [21,4,3], "t": [232,156,120], "m": [204,128,98], "L": [150,88,72]},
  "only_on": {"t": [[250,182,143], [232,156,120]]},          # 't' (lid shade) is only drawn over these colours
  "features": {                                              # drawn in this order, each box cleared first
     "eyeL":  {"x": 41, "y": 22, "states": {"open": ["....","KKKK","..K.","..K.","...."], ...}},
     "eyeR":  {"x": 48, "y": 22, "mirror_of": "eyeL"},       # same states, each row reversed
     "mouth": {"x": 44, "y": 28, "states": {"neutral": ["......", "..mm..", "......", "......"], ...}},
     "brows": {"x": 43, "y": 21, "states": {"none": ["......"], "knit": [".m..m."]}}
  },
  "expressions": {"CL01_Neutral": {"eyeL": "open", "eyeR": "open", "mouth": "neutral", "brows": "none"}, ...},
  "eye_features": ["eyeL", "eyeR"],
  "blink": {"full": [["half", 60], ["closed", 100], ["half", 60]], "short": [["closed", 120]]},
  "blink_kind": {"open": "full", "wide": "full"},            # eye state -> blink kind (default "short")
  "no_blink": ["closed", "smile"]                            # eye states that never blink
}
Required states: every eye feature needs 'half' and 'closed' (blinks, transitions); the mouth needs 'half' and 'open'
(talk cycle; per-expression replacements go in talk_map). The constructor checks this.
In a pattern '.' keeps the featureless face pixel; any other character is a colour from "colors".
The featureless face (face_base) is the neutral sprite with eyes / mouth / brows painted over with skin; draw it
once by hand. Keep every state of one feature the same size.
"""
import numpy as np


class FaceRig:
    def __init__(self, face_base, cfg):
        self.base = np.asarray(face_base).copy()
        self.cfg = cfg
        self.colors = {k: np.array(list(v) + [255], np.uint8) for k, v in cfg['colors'].items()}
        self.only_on = {k: [tuple(c) for c in v] for k, v in cfg.get('only_on', {}).items()}
        self.features = {}
        for name, f in cfg['features'].items():
            if 'mirror_of' in f:
                src = cfg['features'][f['mirror_of']]
                states = {s: [r[::-1] for r in rows] for s, rows in src['states'].items()}
            else:
                states = f['states']
            hs = {len(r) for r in states.values()}
            ws = {len(row) for r in states.values() for row in r}
            assert len(hs) == 1 and len(ws) == 1, f'feature {name}: all states must have the same size'
            self.features[name] = dict(x=f['x'], y=f['y'], h=hs.pop(), w=ws.pop(), states=states)
        self.expressions = cfg['expressions']
        self.eyes = cfg.get('eye_features', [n for n in self.features if n.startswith('eye')])
        self.mouth = cfg.get('mouth_feature', 'mouth')
        # states the clip builders rely on
        need = {e: ('half', 'closed') for e in self.eyes}
        if self.mouth in self.features:
            need[self.mouth] = ('half', 'open')
        for feat, sts in need.items():
            miss = [s for s in sts if s not in self.features[feat]['states']]
            assert not miss, f'feature {feat} needs states {miss} (blinks / transitions use eye half+closed, talking uses mouth half+open)'
        for n, st in self.expressions.items():
            for feat, s in st.items():
                assert feat in self.features and s in self.features[feat]['states'], f'expression {n}: unknown {feat} state {s!r}'
        self.blink = cfg.get('blink', {'full': [['half', 60], ['closed', 100], ['half', 60]], 'short': [['closed', 120]]})
        self.blink_kind = cfg.get('blink_kind', {'open': 'full'})
        self.no_blink = set(cfg.get('no_blink', ['closed']))

    def clear(self, a):
        for f in self.features.values():
            a[f['y']:f['y'] + f['h'], f['x']:f['x'] + f['w']] = self.base[f['y']:f['y'] + f['h'], f['x']:f['x'] + f['w']]
        return a

    def draw(self, a, feature, state):
        f = self.features[feature]
        rows = f['states'][state]
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                if ch == '.':
                    continue
                y, x = f['y'] + j, f['x'] + i
                if ch in self.only_on and tuple(int(v) for v in self.base[y, x, :3]) not in self.only_on[ch]:
                    continue
                a[y, x] = self.colors[ch]
        return a

    def states(self, expr, **override):
        st = dict(self.expressions[expr])
        st.update({k: v for k, v in override.items() if v is not None})
        return st

    def face(self, expr, eyes=None, **override):
        """Render an expression on the unmoved sprite (apply breathing / head moves afterwards).
        eyes='closed' closes every eye; eyes='half' half-closes every eye that can blink (eyes in no_blink keep
        their state); any other value sets every eye. Override single features by name, e.g. mouth='open'."""
        st = self.states(expr, **override)
        for e in self.eyes:
            if e not in st or eyes is None:
                continue
            if eyes == 'half' and st[e] in self.no_blink:
                continue
            st[e] = eyes
        a = self.clear(self.base.copy())
        for name in self.features:
            if name in st:
                self.draw(a, name, st[name])
        return a

    def blink_seq(self, expr):
        """[(eye_state, ms, note)] for one blink of this expression ([] if its eyes never blink)."""
        st = self.expressions[expr]
        eye_states = [st[e] for e in self.eyes if e in st]
        if not eye_states or all(s in self.no_blink for s in eye_states):
            return []
        kind = 'full' if any(self.blink_kind.get(s) == 'full' for s in eye_states) else 'short'
        seq = self.blink[kind]
        notes = {'half': 'blink: lid halfway', 'closed': 'blink: closed'}
        return [(s, ms, notes.get(s, f'blink: {s}')) for s, ms in seq]

    def eyes_open_like(self, expr):
        """True if this expression's eyes are 'open-ish' (a half-lid frame is used when opening into it)."""
        st = self.expressions[expr]
        return any(self.blink_kind.get(st[e]) == 'full' for e in self.eyes if e in st)

    def feature_box(self, *names):
        """(y0, y1, x0, x1) union box of the named features (for QA: 'talk frames only change the mouth')."""
        fs = [self.features[n] for n in names]
        return (min(f['y'] for f in fs), max(f['y'] + f['h'] for f in fs) - 1,
                min(f['x'] for f in fs), max(f['x'] + f['w'] for f in fs) - 1)
