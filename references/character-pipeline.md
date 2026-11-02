# Character pipeline: concept → finished 1x base sprite

## Contents
1. Scale and canvas
2. Automatic draft (`pixelize`, `place_on_canvas`)
3. Materials and ramps
4. Hand finishing with text dumps
5. Redrawing the face
6. Hands, props, hems, holes
7. The featureless face base
8. Final checks on the base

---

## 1. Scale and canvas

- Every character of a cast shares the canvas (default 96×160 RGBA), the foot line (y=155), feet centred at x=48,
  pivot (0.5, 0.025), PPU 32, binary alpha and one outline colour (for example (21,4,3)).
- Pick the figure height in 1x px from the cast's scale. Example: an adult who should stand as tall as an existing adult of
  the cast → `--height 148`. Children are shorter by real proportions. Always produce
  `previews/scale_with_cast_3x.png` (pass `cast` in the config) and look at it.
- Keep 1x density. A "2x density" version looks like a different game next to 1x backgrounds.

## 2. Automatic draft

```bash
python scripts/sprite_from_concept.py concept.png WORK --height 148
```

Why a skeleton downscale: a plain mode or area downscale loses thin dark strokes. Eyes, mouths and fold lines
vanish, or become blobs that are 2–3 px thick. `pixelize` instead:

- finds the dark strokes (lum < `dark_lum`, 52 works for most line art);
- skeletonizes them and turns cells with enough skeleton (≥ 0.45 px per cell) or dark coverage (> 0.6) into 1 px
  lines;
- fills every other cell with the most common quantized non-line colour of that cell;
- forces an outline around the whole silhouette.

Cells covered less than 45% by the figure become transparent. Raise `cover` if thin protrusions get noisy, and
lower it if a ponytail or fingers disappear.

`info.json` holds the scale and offsets: `sprite.src_to_canvas(x, y, info, offset)` maps a concept pixel to the
canvas. Use it to place eyes and other features where the concept has them.

## 3. Materials and ramps

The concept's flat colours become a few fixed ramps, one per material (dark → light). Example materials file
(`assets/examples/materials.example.json`):

```json
{"_soft_line": ["hair", "apron", "pants"],
 "hair":  {"ramp": [[64,49,46],[92,65,58],[118,88,76]], "region": [0,0,96,37]},
 "skin":  {"ramp": [[204,128,98],[232,156,120],[250,182,143],[253,204,172]]},
 "apron": {"ramp": [[64,49,46],[92,65,58],[112,82,70]], "region": [0,37,96,105]}}
```

- Each pixel goes to the allowed material whose ramp has the nearest colour. `region` decides between materials of
  the same colour, for example brown hair above the collar row and a brown apron below it.
- `_soft_line`: interior black strokes whose neighbours are all one of these materials (hair strands, cloth
  folds) become that material's darkest tone. Black inside a material looks harsh at 1x. Silhouette outlines stay
  black.
- Materials may share colours (hair and apron, shirt and shoes). Merge near-duplicates (`merge_colors`) to keep
  the pack palette small. Normal maps classify by colour + region, so sharing is fine.

## 4. Hand finishing with text dumps

The sprite is small enough to read and edit as text. This is the most reliable way to make precise edits:

```python
from pixkit.sprite import Symbols, grid_zoom
sym = Symbols(fixed={'K': (21,4,3), 'S': (250,182,143), 't': (232,156,120), 'H': (92,65,58), 'd': (64,49,46)})
print(sym.dump(a, (30, 8, 66, 40)))            # x0, y0, x1, y1; prints an x ruler + row numbers
sym.paint(a, 40, 22, ['KKKK', '  K ', '  K '])  # '.' = transparent, ' ' = keep
grid_zoom(a, (30, 8, 66, 40), 14).save('z_head.png')   # then look at it
```

Letters without `fixed` are assigned in order of first appearance and mean nothing. Always read the legend line,
or fix your own letters before the first dump, as above, so letters from your notes paint the colours you expect.

Work in small passes: dump, edit, render a zoom with the concept crop next to it, look, then repeat. Keep each
edit in a script (`head.py`, `hands.py`, …) so it can be re-run when an earlier stage changes.

## 5. Redrawing the face

The face is always redrawn by hand.

- **Keep the concept's eye language.**
  - "T-shaped eyes" (a lash line plus a 1 px pupil) stay T-shaped.
  - Dark 2 px eyes stay 2 px.
  - Eyes with whites need at least 4 px of width.
- **Keep the eyes symmetric about the face centre.** Pupils sit at the same distance from the centre column on
  both sides.
- **Bangs**:
  - draw the outline row per column (a jagged edge with 1–2 px strand tips), with hair above it and skin below;
  - add 1 shade row ('t') directly under the bang edge;
  - keep any parting sliver from the concept.

  Bangs usually cover the brows. Plan for expressions that are carried by the eyes and mouth.
- **Shading**: a jaw shadow on the side away from the light, an inner ear shade, and a shadow under the chin onto
  the neck. Keep it to one tone darker than the skin.
- **Mouth**: if the concept has no mouth, add a subtle 2 px mouth only one tone darker than the skin. Expressions
  and talking need it. Say so in the README and offer to remove it from the neutral face. Keep the mouth ≥ 1 row
  above the chin line; a mouth that touches the jaw outline reads as a beard or a crack.
- **Compare** a 5× render of the sprite next to the concept head at the same size. Do not stop while the
  expression reads differently (sleepy versus annoyed, for example).

## 6. Hands, props, hems, holes

- **Hands**: check that thumb lines and finger separation read at 1x. Use skin shades, not black, between the
  fingers.
- **Props held or hung on the body** (rags, bags, tools): keep them if they are in the concept, and keep them rigid.
- **Hems and seams**: make apron, coat and shirt hems straight or smoothly curved, with one outline row; pants start
  under it. Shorten seam lines to where the concept has them.
- **Holes**: `fill_enclosed_holes(a, 3)` closes 1–3 px transparent specks that are surrounded by the figure. Real
  gaps (between an arm and the body) should be wider, or closed with the outline colour. Asymmetric one-sided slits
  look like errors.
- **Colour merges**: conversion leaves near-duplicates such as (249,229,211) next to (250,229,211). Merge them.

## 7. The featureless face base

Save a copy of the finished neutral sprite with every expression feature painted over with the surrounding skin
(and the bang-shade row where it belongs): eyes, mouth, and brow marks if any. Permanent features stay: the nose,
blush, scars, glasses frames (frames are better as a separate overlay). `build_character.py` checks that
"face_base + neutral patterns == base" pixel for pixel and names the differing pixels. A missing nose is the
classic cause.

## 8. Final checks on the base

- 5× comparison with the concept; the scale image with the cast.
- Palette: count the colours and check that the outline colour is the cast's.
- `stray_pixels(a)` is empty; there are no enclosed holes; alpha is binary.
- The silhouette and proportions match the concept: head size, leg length, how far the hands hang.
