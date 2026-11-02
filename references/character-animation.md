# Character animation: face rig, expressions, clips, motion rules

## Contents
1. Face rig config
2. Designing expressions
3. Blinks
4. The standard clip set and timings
5. Motion rules
6. Performances (extra one-shots)
7. Side / back / walk (when the scope includes them)
8. Hand-offs and the state map

---

## 1. Face rig config

`pixkit.face.FaceRig(face_base, cfg)` draws an expression by clearing every feature box on the featureless face and
then drawing each feature's state grid:

```json
"face": {
  "colors": {"K": [21,4,3], "t": [232,156,120], "m": [204,128,98], "L": [150,88,72]},
  "only_on": {"t": [[250,182,143], [232,156,120]]},
  "features": {
    "eyeL":  {"x": 41, "y": 22, "states": {
       "open":   ["....", "KKKK", "..K.", "..K.", "...."],
       "half":   ["....", "tttt", "KKKK", "..K.", "...."],
       "closed": ["....", "tttt", "KKKK", "....", "...."],
       "wide":   ["KKKK", "....", "..K.", "..K.", "...."],
       "smile":  ["....", ".KK.", "K..K", "....", "...."]}},
    "eyeR":  {"x": 48, "y": 22, "mirror_of": "eyeL"},
    "mouth": {"x": 44, "y": 28, "states": {"neutral": ["......", "..mm..", "......", "......"]}},
    "brows": {"x": 44, "y": 22, "states": {"none": ["....."], "knit": ["m...m"]}}},
  "expressions": {"H01_Neutral": {"eyeL": "open", "eyeR": "open", "mouth": "neutral", "brows": "none"}},
  "blink": {"full": [["half", 60], ["closed", 100], ["half", 60]], "short": [["closed", 120]]},
  "blink_kind": {"open": "full", "wide": "full", "worried": "full", "stern": "full"},
  "no_blink": ["closed", "smile"]
}
```

- **Required states**: every eye needs `half` and `closed` (blinks and transitions); the mouth needs `half` and
  `open` (the talk cycle). Per-expression replacements go in `talk_map`. The rig checks this when it loads.
- '.' keeps the featureless face pixel. All states of a feature share one size.
- `mirror_of` reverses each row, so the right eye is the exact mirror of the left one.
- `only_on` keeps lid shade off the bangs.
- Features are drawn in order. Later ones (brows) can overlap earlier ones (eyes).
- Name expressions `<PREFIX><NN>_<Name>` (H01_Neutral, H04_Surprised). Clips use the part after the underscore
  (Idle_Surprised).

## 2. Designing expressions

Design all expressions side by side at 4–8×, and also check them at 1x and 2x. Each must read at game scale and be
clearly different from the others. A working set of about 10 for a non-protagonist:

| Expression | Eyes | Mouth | Notes |
|---|---|---|---|
| Neutral | concept's eyes | concept's (or a subtle 2 px) | must equal the base |
| Smile (polite) | unchanged | corners up | open eyes look friendlier than half-lids |
| Happy | upward arcs `^ ^` | slightly open grin | arcs never blink |
| Surprised | lash raised a row, a skin gap, small pupils | small O | a raised lash beats a longer pupil |
| Worried | inner corners raised (八字) | wavy line | |
| Frown | inner corners lowered | corners down | + 2 knit pixels under the bangs |
| Suspicious | one normal, one narrowed (lower lid up) | flat line | **no glance**: the asymmetry carries it |
| Cold | both half-lidded | flat line | "dead fish" eyes; blink = closed only |
| Sad | half-lidded, outer ends drooping | corners down | |
| EyesClosed | closed line | neutral | |

More, from other characters:
- Serious: the lid presses the white into shadow, the mouth is tight. 4 black pixels in a row read as sunglasses,
  so avoid that.
- Squint: a slit, with the lower lid pushed up.
- Beam: crescent eyes, cheeks raised.
- Glint: a light band sweeping across glasses lenses.

Rules for the details:
- **Brows hidden by bangs**: only small cues show (knit pixels, a raised lash). Do not draw brows over the hair.
- **Glasses**: draw the frames as a final overlay, so blinks and brow changes never erase them. Brows must clear
  the frame row; move a brow up rather than let the frame cut it.
- **The mouth stays ≥ 1 row above the chin outline.**
- **Talk mouths must fit the expression**: laugh mouths for Happy / Beam, the open O for Surprised (`talk_map`).
  The mouth cycle must never touch wrinkles or other permanent face lines, so clear only the mouth box.

## 3. Blinks

- **Half-blink**: the upper lid comes down. The lash line moves down 1 px and only the lower part of the pupil
  shows. The next frame is fully closed, lower still. The eye moves in one direction only; a half-blink that
  removes the bottom row first makes the eye jump.
- **Closed line**: it lies where the open eye was, and is never offset sideways.
- **Kinds**: open-ish eyes do half (60) → closed (100) → half (60). Half-lidded or narrow eyes do closed (120) only.
  Closed eyes and smile arcs never blink.
- Use one blink per idle loop. Nervous characters may blink more often; sleepy ones blink more slowly.

## 4. The standard clip set and timings

`motion.build_front_set` builds (durations in ms):

| Clip | Frames | Total | Content |
|---|---|---|---|
| Idle_<E> (loop) | 4–6 | 2450–2670 | rest 1150 → breath in 850 (above the chest row +1 px) → out 450 → blink |
| Talk_<E> (loop) | 11 | 1190 | mouth cycle closed / half / open; only the mouth changes |
| To_<E> | 3–5 | 680 | neutral 140 → half 60 → closed 100 (the face switches) → half 60 → target 320 |
| From_<E> | 3–5 | 680 | the reverse, ending on the neutral still |
| Nod | 3 | 810 | head down 1 px, hold, back |
| Nod_Slow | 4–5 | 1460 | head down, eyes close and hold, open, back |
| HeadShake | 9 | 1130 | head ±1 px twice |

Identical neighbouring frames are merged (their durations are added), which is why the frame counts vary.

## 5. Motion rules

- **Breathing**: everything above the chest row lifts 1 px, and the row above it is doubled inside the torso.
  `best_breath_row` picks the row whose doubling is least visible (`chest_row: "auto"`).
  - A nicer variant for a main character: the torso first, the head one frame later, a hanging accessory one more
    frame later. Every step is still 1 px.
- **Head moves**: the head block includes hair locks and ponytails (`extra_boxes`) and excludes the collar.
  Pixels it leaves behind on the body are closed with the outline colour, never left as holes.
- **Hair**: it moves only with the head or body. Allowed: a strand trailing for 1 frame during a real sideways move
  (a step or a head tilt). Not allowed: wind gusts, flaring on breaths, lifting on nods. When hair does move, only
  the hanging tips move, by 1 px, without stretching; gaps that open are filled with hair colour.
- **Eyes**: they only blink. If a look is requested ("look down for 1 second"), make exactly that.
- **No tearing**: never shear rows separately. The upper body moves as one block.
- **Feet stay planted**: in all front clips, every row below the knees is pixel-identical to the still.

## 6. Performances (extra one-shots)

Define them in the config as steps. Each step has an expression and optional overrides for eyes / mouth / head
[dx,dy] / breath, plus ms and a note. The last step must be the end state's still. Examples that worked:

- **Smile_Grow**: neutral → lips press → corners rise → mouth opens → eyes crease into the Happy hold. There is no
  blink; the change is gradual.
- **Squint_Look**: lids lower step by step → brows draw in → slit → lean in 1 px → Squint hold.
- **Laugh** (loop from Beam): each "ha" lifts the head and shoulders 1 px with the mouth open; the eyes stay
  creased.
- **Glint on / off** (glasses): a light band enters at the lower left and crosses the lenses → the lenses flash
  white → hold. Off is the reverse, then a blink back to neutral.
- **Gestures with props** (for example a hat grip): keep the amplitudes small. One review halved a hat lift.

## 7. Side / back / walk (when the scope includes them)

- Side idle should use the same leg construction as the walk. Otherwise the cut from idle to walk jumps.
- **Walk_Side** loops at a constant speed with root motion: dx px per frame is written into the json, and planted
  feet move back at exactly that speed, so there is no foot sliding. Face left and flipX for right.
- **Walk_Start**: the idle pose → heel lifts → toe pushes off → Walk_Side frame 0.
- **Walk_Stop**: enters at a fixed frame of the walk (for example after frame 7) → the front foot lands → idle pose.
  Write per-frame root dx for both.
- **Arms**:
  - move the forearm + hand as one block; do not warp them;
  - a free arm swings about ±2 px;
  - a cane or prop arm moves 0–3 px, and the prop rotates instead;
  - a sleeve may slide behind the coat front (draw 5 px of hidden sleeve so no gap opens).
- Back view: no face, so blinks do not apply. Small details matter here (glasses temples above the ears, for
  example).
- Unity: per-frame AnimationEvents call a root-motion component; an animator builder wires
  Idle_Side → Walk_Start → Walk_Side → (Walking=false, exit after frame N) → Walk_Stop → Idle_Side.

## 8. Hand-offs and the state map

- Loops start on their expression still, and one-shots end on their state's Idle frame 0. `continuity_issues` and
  the audit verify both.
- Expression A → B always goes From_A → To_B, passing through neutral.
- Write the state → clip map into the manifest and the README, along with the frame each clip may be entered on.
  The interactive preview plays exactly these routes, so reviewers see the real hand-offs.
