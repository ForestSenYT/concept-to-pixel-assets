# Scene pipeline: concept → native pixel still

## Contents
1. Native grid and pre-cleaning
2. Hand-drawn simplification (`stylize`)
3. Hand fixes: AI artifacts
4. Logic and continuity checks
5. Grade, vignette, palette lock
6. Paired shots, alternatives, story time
7. Code skeleton for a scene script

---

## 1. Native grid and pre-cleaning

- Area-resize the concept to the native size: `scene.to_native(src, (640, 360))`. Area averaging lines up with the
  pixel grid; Lanczos rings.
- Noisy sources need smoothing first: GIF dither, JPEG blocks, AI grain. Use `to_native(src, smooth=(8, 16))`
  (mean shift) so the noise does not survive as speckle.
- If the concept is not 16:9, crop to the composition the user cares about before resizing. Never stretch.

## 2. Hand-drawn simplification (`stylize`)

```python
t, pal, protected = scene.stylize(nat, k=22, scale=400, min_size=50, ntones=3, min_island=12, de_merge=20,
                                  keep_boxes=[(x0, y0, x1, y1)])
```

The goal is that the scene's level of detail moves toward the characters': big flat shapes, few tones, no texture
noise. Steps:

1. **Palette reduce** to about 22 colours by k-means in Lab. Each centre snaps to a colour that exists in the source,
   so there are no muddy averages.
2. **Object-level flattening**: felzenszwalb segments of `scale` 400 (try 600 for flatter). Each segment keeps its
   `ntones` most used colours. Use 3 normally, 4 for dark interiors so objects do not merge, 2 for very flat
   results.
3. **Speck merge**: components smaller than `min_island` (12; raise to 20 for simpler) are absorbed into their
   dominant neighbour, but only if that neighbour is within `de_merge` ΔE. Clearly different specks are structure.
4. **Protected**: small bright features that carry meaning (lit windows, lamps, the sun, highlights) and thin
   elongated lines (road marks, rails, window frames, fences).
5. **Reserved slots** (`reserve=3`, and `finish(reserve=2)`): small bright features get dedicated palette colours.
   Without them, k-means over the whole image averages a lamp bulb into the sunset orange.
6. **Check `<name>_protected.png`** (written by stage 1). Ridge or shore edges sometimes qualify as "thin lines" and
   survive as stray coloured lines. Inpaint them, or run with `--no-protect-lines` / `protect_lines=False`.
7. **`keep_boxes`**: props whose exact shape matters to the story or puzzle. Examples: a fence, crates on a dock, the
   books and pen holder on a desk. These are only palette-reduced, never flattened.

Stage 1 also writes `<name>_native.png`, the area-resized source. Use it as the light source for `ramp_paint` and
for masks, instead of recomputing it.

Large smooth gradients (sky, still water, floors) can turn into "camouflage" blotches when merged. Either let
`ramp_paint` repaint them as clean bands, or keep the quantized original there.

## 3. Hand fixes: AI artifacts

Inspect every shot at 4× zoom, region by region. Use `sprite.grid_zoom` on the RGB image converted to RGBA, or
crop and upscale yourself. Typical AI artifacts, with the fix that the reviewers accepted:

| Artifact | Fix |
|---|---|
| Mottled or stained floor, desk or wall | `ramp_paint(t, mask, light, tones)`: 3 flat lit bands with ordered dither only in a narrow band at each step. `light` = `masked_blur(lab(src)[...,0], mask, 7)` or `cdf_light` for a lamp pool. Draw plank seams back with `line_mask_src` |
| Diamond or mesh pattern between branches | inpaint to sky / foliage |
| Shapeless coloured blob under a beam or on a table | remove (`inpaint`), or redraw as a plausible object; say which in the README |
| Pseudo-text on papers or signs | clean the paper; keep at most 2–3 unreadable strokes |
| Floating frame lines, broken roof ridges | delete and reconnect |
| Wood grain or texture that turns into stripes at 24 colours | redraw panels, drawers and handles pixel by pixel following the structure |
| Decorations that make no sense (stars on shoe soles, logos) | plain material |
| Anatomy: a sleeve with no hand, fused fingers | add the hand, separate the fingers with a finer simplification on that region |
| Hands and keyboards mushed by the coarse pass | re-run that region with a finer `stylize` (smaller scale / min_island) and paste it in |

Only use colours that already exist in the image (`inpaint` and `ramp_paint` never invent colours).

## 4. Logic and continuity checks

Check, and fix or ask:

- **Light direction**: shadows match the lamp or sun position.
  - Sunlight cannot fall on the wall that holds the window it comes through.
  - A sunset on the left lights the faces that point left.
- **Reachability and scale**: things a character interacts with must be reachable. Example: a mark a character
  wrote with a finger must be within the arm's reach.
- **Continuity between shots**:
  - the same car interior in every driving shot;
  - the same room pixels when the camera is the same;
  - props that do not appear or vanish between cuts;
  - a character or prop that does not change position between two shots with the same camera. If it does, offer
    options:
    accept it, move it in the other shot, or reframe this one.
- **Story time**: keep the script's time of day (for example "last minutes of sunset"). A night-looking reference
  does not make the scene night.
- **Clean plates**: a background that will host separate overlay layers (characters, clues, interactables) must
  not bake those layers in.
- Story-relevant edits ("subtle wrongness" such as a dead lamp or an ajar door) are only made when the user asks.
  List them in a table.

## 5. Grade, vignette, palette lock

```python
fin = scene.finish(fixed, grade='cold_dusk', k=24, vig=True)
```

- `grade_palette` grades the palette, not the pixels, so flat areas stay flat.
- `cold_dusk`: darker, crushed shadows, desaturated and cold blue-green. Only warm lights keep their warmth (lamps,
  lit windows, the last sunset glow; the rule is Lab L>58 and b>12). Use it for a tense, moody dusk.
- `warm`: keeps a golden-hour source bright. Offer it as an alternative for endings or "too good to be true"
  scenes.
- `memory`: a desaturated cool grey for flashbacks, so memories read differently from the present.
- `none`.
- The vignette has 4 levels darkening L by 12% steps, through a 4×4 Bayer dither. It is part of the image, so loop
  effects keep content inside one vignette level (`Scene(vig=...)` must use the same parameters).
- In a scrolling (parallax) scene the vignette belongs to the camera. Fade it out above the moving ground
  (`vignette(rows_off=...)`), otherwise the static dither reads as dirt on the moving road.
- Characters are not darkened to match a dark scene. Recommend engine lighting or tint instead.

## 6. Paired shots, alternatives, story time

- **Paired shots** (a door closed and open, the same room in two CGs) share one palette:
  `finish(a, extra=[b])`. Keep them pixel-identical outside the region of interest. Assert that in code and report
  the count.
- **Alternatives**: when a creative choice is genuinely open, ship the main version plus a small `alt_*` folder of
  stills and put the comparison in the PDF. Make the loops only after the user picks. Examples: a warm ending versus
  the house grade, or cold memories versus the original memory tone.
- **Text and stamps** (documents, signs): re-letter by hand at native size. Swap only the words that changed
  between versions (for example OPEN → CLOSED), so everything else stays pixel-identical.

## 7. Code skeleton for a scene script

```python
import numpy as np
from PIL import Image
from pixkit import scene as SC
from pixkit.palette import lab

src = np.array(Image.open('src/BG07.png').convert('RGB'))
nat = SC.to_native(src, (640, 360))
t, pal, prot = SC.stylize(nat, keep_boxes=[(55, 85, 190, 170)])
floor = SC.poly_mask([(0, 250), (640, 230), (640, 360), (0, 360)], 360, 640)
light = SC.masked_blur(lab(nat)[..., 0], floor, 7)
t = SC.ramp_paint(t, floor, light, SC.common_tones(t, floor, 3))
t[SC.line_mask_src(src, floor)] = SC.common_tones(t, floor, 3)[0]      # plank seams back as 1 px lines
blob = SC.box_mask(64, 278, 100, 322, 360, 640)
t = SC.inpaint(t, blob)
fin = SC.finish(t, grade='cold_dusk', k=24)
Image.fromarray(fin).save('still/BG07.png')
Image.fromarray(SC.upscale(fin, 3)).save('still/BG07_1920.png')
```

Keep one script per shot under `work/` with its masks, so later feedback can be applied by changing one line and
re-running.
