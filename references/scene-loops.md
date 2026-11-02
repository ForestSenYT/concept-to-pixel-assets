# Scene loops, CG loops and parallax

## Contents
1. Loop contract
2. Masks
3. Effect catalogue (what to use for what, and safe parameters)
4. Known failure modes (each one was flagged in review)
5. Lamps and flicker
6. CGs with people
7. Stills-only requests, memories, alternatives
8. Complex motion: image-to-video clips and procedural camera moves
9. Parallax scenes
10. Unity delivery for loops

---

## 1. Loop contract

- 48 frames at 12 fps = 4 s; frame 47 flows into frame 0.
- Every effect is a function of phase `u = t/T` with whole-number cycles, and is 0 at `u = 0`.
- Effects work on palette indices (`loopfx.Scene`), so the output never leaves the still's palette.
- Content moves only between pixels of the same vignette level, otherwise the dither ring crawls.
- Ship `frames_native/` plus the still = frame 0 (`*_STILL_frame0.png`).
- Make a review mp4: 3 loops at 3× nearest, `crf 12`. For tiny bright lights also make a 4:4:4 version so the
  codec does not smear them.
- The README needs a table with one row per shot, listing what moves. Say what deliberately does not move and why.

## 2. Masks

Masks are bool arrays or PNGs at the still's size. Build them in code from colours, positions and polygons, then
**overlay them on the still at zoom** before using them. Most loop bugs are mask bugs. Typical recipes:

- water: palette colours of the lake below the shoreline row, minus everything rigid, eroded 2–3 px from the
  shore, posts, boats and reeds;
- foliage / grass / reeds: **the whole band the blades sway in**, meaning the blades plus the background between
  them (sky or water behind thin blades), minus rocks and anything rigid. `sway` shifts each row of the mask
  sideways and only takes source pixels from inside the mask, so a mask of blade colours only moves nothing. The
  anchor is the bottom row (`anchor_weight`);
- rigid: every structure that must not move (rails, posts, docks, rocks, car interior, furniture, characters lying still).
  Re-stamp it last (`static`).
- person (CG breathing): the difference between this CG and an empty-room version, plus the hair. Restrict it to
  the upper body that would actually rise.
- water that was repainted with `ramp_paint`: either paint it with `band=0` (solid bands with no dither), or keep
  the dither band pixels out of the ripple mask. Rippling ordered dither makes the dither crawl.

## 3. Effect catalogue

| Need | Effect | Safe parameters / notes |
|---|---|---|
| Lake / river surface | `ripple` | amp 1, cycles 2. Rows shift as rigid runs; sources must be inside the mask |
| Sun or lamp glints on water or wet ground | `sparkle` with `S.step_map(True)` | rate ≤ 0.05, hold 3. Higher reads as noise |
| Mist / fog | `wisps` | flat horizontal wisps, thr ~0.6, sx 24, sy 1.2. Never dither stipple. On a scrolling ground use a small `drift` (8–16 px per loop) so the mist travels with the ground |
| Grass, reeds, ferns, tree crowns | `sway` | amp ≤ 1 px at the free end, 0 at the anchor. Each row moves as one rigid run so blades keep their width and heads stay on stems. The mask is the whole band including the background between blades (see §2). Gusts: two sways with different cycles / phases |
| Falling leaves | `Leaves` | 2 px leaves on periodic paths; they leave the frame or land. Never vanish mid-air; clip with `occl` (door frames) |
| Dust in a lit room | `Dust(light=pool)` | about 60–100 motes on slow closed paths, one palette step brighter (two inside the light pool). No blinking |
| Birds | `Birds(sky=mask)` | 3–7 birds circling, flapping between 2 poses; only drawn in the sky above ridgelines |
| Bobbing boat, breathing body | `shift` / `shift_region` | the whole block 1 px, on chosen frames |
| Lamp dips | `flicker` / `flicker_radial` with `S.dim_maps()` | hand-timed frames (see §5) |
| Steam, smoke | `wisps` with a vertical-ish weight mask, or hand-drawn frames | slow, low contrast |
| Clouds | per-cloud wisps that grow and thin as they drift | cross-faded global noise barely moves and flickers |

Say in the README which elements can be switched off individually (birds, clouds and sway are the usual
candidates).

## 4. Known failure modes

- Ripple or mist running through rails, posts and shorelines bends them. Lock rigid things pixel for pixel and keep
  the water mask 2–3 px away.
- Reeds or grass that change thickness while swaying: rows were warped per pixel instead of moving as rigid runs.
- Crawling dither speckle as mist: use flat wisps.
- Twinkling glints at high rates, and blinking dust motes: both read as dead pixels or noise.
- Strobing lights: at most 2 flicker bursts per loop.
- Wet ground that wobbles: only the reflections should ripple, never the ground.
- Leaves spawning or vanishing mid-frame, or drawn over door frames: clip them and let them exit or land.
- A seam at the loop point: audit `seam_changed_px` against `mean_neighbour_changed_px` and play the loop
  several times.
- Content dragging the vignette dither along: `Scene(vig=...)` must match the still's vignette.
- Road or path animated when the user said not to: lock it with `static`. Animate other things instead, such as
  foliage, birds, clouds, water and falling leaves.

## 5. Lamps and flicker

- Hand-time the flicker with a short schedule. Example from a set of shots in one room:
  - burst 1: frames 26 off, 27 on, 28–29 off, 30 on;
  - burst 2: frames 39 off, 40 on, 41 off, 42 on, 43 off, 44 on.
- **Sync across shots** that share a light. Every CG in the same room uses the same schedule and the same light
  model, so cuts stay continuous.
- The light model: closer and warmer surfaces lose more light. Use `dim_maps()`, which picks darker colours of the
  same hue family that are never warmer and keeps reds red. Use mostly solid colour changes, with ordered dither
  only in the soft edge of the light pool.
- Calm scenes (an ending, a closed case) usually should not flicker. Offer the flicker as an option.

## 6. CGs with people

- People in CGs move as rigid blocks: breathing or panting lifts the back, head and the hand on them by 1 px,
  1–2 times per loop. Floors and furniture never move.
- A CG that shares a camera with an existing BG / CG reuses that shot's pixels for the room. Only the new elements
  are redone, with the same simplification, and mapped into the existing palette. If the new palette needs a
  colour, merge two near-duplicate colours to free a slot instead of growing the palette.
- Give fine regions (hands, faces, fingers, closed eyes) a finer simplification pass than the room.

## 7. Stills-only requests, memories, alternatives

- If the user asks for stills only, deliver clean stills (frame 0 without particles) and stop animating that set.
- Flashbacks and memories: keep a distinct tone (the `memory` grade, or the source's own desaturated look). Offer the
  present-day grade as `alt_*` stills.
- If something in the concept contradicts the action (dark monitors while someone is typing, for example), ask
  whether to change it. Offer options such as a screen glow, scrolling code or a UI.

## 8. Complex motion: image-to-video clips and procedural camera moves

**External image-to-video** (a forward drive, for example): generate the clip with a video tool, then use
`video.postprocess_clip(mp4, still, out, rigid_mask=car_interior)`. It decodes at 12 fps, area-scales, applies a
3-frame temporal median, snaps to the still's palette and pastes rigid regions from the still.
- Generating usually costs the user credits: confirm before generating.
- Never type the user's passwords; they sign in themselves.

**Procedural camera moves** (a tunnel drive, for example):
- Compute geometry from one vanishing point.
- Draw lamps as stable sprites whose shape is computed from perspective. Distant 1–2 px lamps are short lines whose
  length only grows, so they never pop in and out.
- Make light bands fixed in the world (painted bands), so pixels change only when a band edge really passes.
- Omit detail that is too far away to draw cleanly instead of letting it flicker.
- Count "pop" pixels (pixels that turn off for a single frame) and drive that number toward 0.

## 9. Parallax scenes

Lessons from a 4-layer forest path:

- **The ground the characters walk on is one layer**, together with everything standing on it (trees, bushes,
  rocks). Per-row ground speeds shred the path into stripes after some scrolling.
- **Depth comes from the back layers**: sky / far hills / far shore + water / main.
  - Factors 0.30 / 0.45 / 0.60 / 1.0 read as one world.
  - 0.04 / 0.12 / 0.25 / 1.0 make the back layers look pinned.
  - Floor all offsets to whole pixels.
- **Fill what the front layers hid** with complete, horizontally tiling panoramas, using only the scene's colours:
  - the sky from the row-wise colour statistics of the visible sky;
  - hills with periods that divide the board width;
  - a shoreline with the original middle part kept.

  Compose at camera 0 and check it equals the flat version except inside tree gaps.
- **Every layer animates seamlessly in time and tiles horizontally in every frame.** Mist on the ground must stay
  attached to the ground: a slow drift plus cross-fade, never a fast slide that cancels the camera motion.
- **The camera vignette** is an overlay that does not darken the moving ground.
- **Ship**:
  - static layers (= frame 0 of each layer);
  - only the animated row bands as sheets (`parallax.animated_bands` + `write_band_sheets`, each ≤ 4096 px);
  - `parallax.json` with speed factors and draw order;
  - two review videos: a constant pan and a slow back-and-forth sway (the sway shows layer separation best).
- **Report numbers**: moving pixels per layer, and the seam change versus the mean neighbour change per layer.

## 10. Unity delivery for loops

- `frames_native/*.png` (point filter, no compression, PPU 32). Play in order at 12 fps.
- For a big loop also provide a sprite sheet, a 2× GIF for quick review, and the mp4s. Name every file with the
  shot ID.
- Parallax: band sheets with `band_rows_top_origin` in their json, plus a small scroller script (optional). Mark it
  untested if it was never run in Unity.
