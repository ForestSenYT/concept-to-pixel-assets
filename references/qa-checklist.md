# QA checklist (run before every delivery)

## Automated

Scenes (`make_loop.py` writes `<name>_loop_audit.json`; `audit.audit_loop(frames, still)` does the same in code):
- [ ] `new_colours == 0`. Every frame stays in the still's palette.
- [ ] `seam_changed_px` (frame 47 → 0) is of the same order as `mean_neighbour_changed_px`.
- [ ] The still that ships is frame 0 (`*_STILL_frame0.png`), or `frame0_vs_still_px` is explained (particles only).
- [ ] `px_toggling_more_than_8` is small and the pixels are inside water or glints, not lone pixels in dark areas
      (that would be flicker).
- [ ] Paired shots are pixel-identical outside their region of interest. Assert it and report the count.
- [ ] Rigid masks are pixel-identical in every frame.

Sprites (`build_character.py` writes `audit.json`):
- [ ] `ok: true` (`where` lists the clip, frame and (y,x) of each stray pixel or hole): binary alpha, 0 stray pixels, 0 enclosed 1–3 px holes, normal alpha matches colour alpha, normals
      deterministic, every loop starts on its still, every one-shot ends on its state's still, talk frames change
      only the mouth box, blink frames change only the eye box.
- [ ] The colour count matches the plan and the outline colour is the cast's.
- [ ] The neutral rig face equals the base. The build refuses otherwise.

## Visual (look at the images; the numbers miss these)

- [ ] **Zoom 4–8×** on every changed region: no 2×2 black lumps at layer seams, no 1 px orphans, no broken outlines.
- [ ] **Play every loop and clip several times**, including the hand-offs in the interactive preview.
- [ ] Nothing that should be rigid moves: rails, posts, rocks, roads, docks, furniture, car interiors, characters that should lie still.
- [ ] Swaying things keep their width, and heads stay on stems.
- [ ] Mist travels with its ground; the vignette dither does not crawl.
- [ ] Lights flicker at most twice per loop, in sync with other shots of the same room.
- [ ] Faces:
  - expressions read at 1x and 2x;
  - half-blinks move the lid down, never jump;
  - closed lines sit where the eyes were;
  - mouths do not touch the chin outline;
  - glasses frames are intact in every frame.
- [ ] Hair moves only with the head or body.
- [ ] Every frame of every front clip has the same feet / legs rows as the still.
- [ ] Scale image: the new character next to the cast on one foot line.
- [ ] The source-vs-result comparison still tells the same story: nothing important lost, nothing invented.
- [ ] Review PDF pages rendered and looked at; labels do not overlap.

## Failure modes seen in review, and their fixes

| Symptom | Cause | Fix |
|---|---|---|
| Eyes or mouth vanish in the sprite | mode / area downscale | skeleton downscale + redraw the face by hand |
| Face looks wider or older than the concept | lost proportions | compare at 5× with the concept head; adjust the jaw line and bangs |
| Hem dips and merges with the pants | conversion noise | one straight outline row; pants start below |
| Normals look flat | per-part edge bulge only | cylinder per run + whole-figure blend + head sphere |
| Eyes punch holes in the lighting | head not a single unit | `head.parts` + `above_part` |
| Upper body tears during walks | row-wise lean | move the body as one block |
| Prop arm smears | row-wise warp | move the forearm + hand as one rigid block; rotate the prop instead |
| Walk start pops | idle legs drawn differently | build the idle from the walk rig |
| Wide sheet blurry in Unity | default Max Size 2048 | Max Size 4096 in the import script |
| Sky barely moves and flickers | cross-faded global noise | per-cloud wisps |
| Fern sway catches the rocks | mask too wide | exclude rock regions |
| Breathing drags floor dither | breathing mask included the floor | mask = person only (diff vs the empty room + hair) |
| Sleeves of a new figure turn pink | palette mapping | merge 2 near-duplicate colours, add the needed tone |
| Light pool too small / contrast off | linear mapping | CDF + linear hybrid (`cdf_light`), blur σ≈7 |
| Quantile tones collapse to 1 tone | fractions passed as percentiles | multiply by 100 |
| frame 0 ≠ still | particles at frame 0 | ship frame 0 as the still |
| Importing a helper script runs its body | module code without a main guard | `if __name__ == '__main__':` |
