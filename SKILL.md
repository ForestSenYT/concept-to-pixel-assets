---
name: concept-to-pixel-assets
description: Turn concept art (paintings, AI images, sketches) of scenes and characters into finished pixel-art game assets. For scenes that means native-resolution backgrounds / CGs with seamless palette-locked ambient loops and parallax layers. For characters it means a 1x sprite pack with expressions, idle / talk / expression-change / nod clips, normal maps, sprite sheets and Unity import scripts. Use it whenever someone pastes scene or character images and wants pixel versions ("做成像素风", "pixelize this"), wants a background or CG animated as a loop, wants expressions or talking animation for a character, wants normal maps for 2D lights, or wants sprites packaged for Unity, even if they never say "skill" or "pipeline".
---

# Concept art → pixel-art scenes, loops and character packs

This skill captures a production workflow that was refined over many review rounds with a game team. The scripts
do the mechanical parts. The rules below matter more: they are what the reviewers kept asking for, so follow them
by default and break one only when the user asks you to.

Two tracks share one toolkit (`scripts/pixkit`, plus the CLIs in `scripts/`):

| Track | Input | Output |
|---|---|---|
| **Scene** (background / CG) | 1 concept image per shot | native still + exact 3× copy, optional 48-frame seamless loop, optional parallax layers, review PDF, README |
| **Character** | 1 front concept of the character | 1x front sprite, 8–13 expressions, Idle/Talk per expression, To_/From_ transitions, Nod/Nod_Slow/HeadShake (+ custom one-shots), normal maps, sheets + json, previews, Unity scripts, README |

Setup: `pip install -r requirements.txt` (numpy, scipy, scikit-image, opencv-python-headless, Pillow, reportlab), plus
ffmpeg for review videos. Run `python scripts/demo/run_demo.py /tmp/demo` once to confirm everything works (it uses
synthetic art only).

## 0. Before you start

1. **Find the project's existing conventions and reuse them.** Look for earlier packs (READMEs, manifests, sprites).
   A new character must share the cast's canvas, foot line, pixels-per-unit, outline colour and height scale. A new
   background must share the native size, palette size, grade and vignette. Consistency across the set matters more
   than any single asset looking good alone. If nothing exists yet, propose the defaults below and say so.
2. **Settle scope only when it is genuinely open.** For a character, ask whether to do the front set only or also
   side / back / walk. For a scene, ask whether it should be animated if the request is unclear (some shots should
   stay still). Otherwise start working; do not ask permission for obvious next steps.
3. **Keep the user's art private.** Deliver files directly (zip + key preview images). Do not publish their art or
   derived sprites to public pages unless they ask.

Defaults (change them to match the project):

| | Scene | Character |
|---|---|---|
| Size | 640×360 native; 1920×1080 = exact 3× nearest | 96×160 canvas, foot line y=155, feet centred at x=48 |
| Colours | 24 per image (palette-locked) | few-colour ramp per material, about 10–30 for the whole pack |
| Lines | from the art | 1 px outline, one outline colour for the whole cast |
| Motion | 48 frames, 12 fps, 4 s, seamless | durations per frame in ms (60 fps grid friendly) |
| Unity | Point filter, no compression, Max Size 4096, PPU 32 | the same; pivot (0.5, 0.025) |

## 1. House rules

Each rule comes from a correction a reviewer made. They are not taste.

- **1x pixel density.** One art pixel equals one game pixel, so never double the detail density. Scenes are built at
  native size and scaled by whole numbers only.
- **Palette-locked everything.** Animation frames may only use the still's own colours. Every effect in `loopfx`
  works on palette indices, so new colours cannot appear.
- **Frame 0 = the still, and loops are seamless.** Every motion is a function of phase with whole-number cycles.
  Ship the loop's frame 0 as the still (`*_STILL_frame0.png`) so the two can swap without a jump.
- **Eyes only blink.** No glances, eye darts or looking around unless the user asks for one specific look. When
  they do, make that one look and nothing more (an example request was "look down for 1 second").
- **Hair moves only when something physically moves it**: the head nods, the body steps or turns. No wind gusts and
  no flutter on breaths, because a 1 px twitch on every breath reads as a glitch.
- **Rigid things never wobble.** Roads, guardrails, posts, docks, rocks, furniture and car interiors stay
  pixel-locked in every frame (`static` masks). Keep water ripples 2–3 px away from shorelines, posts and reeds.
- **No single-pixel blinking.** A lone pixel that blinks reads as a dead pixel. Dust drifts, it does not twinkle.
  Glints stay sparse.
- **Move whole blocks by whole pixels.** Breathing lifts everything above the chest row by 1 px. A nod moves the
  head block 1 px. Never shift rows independently; that tears outlines ("撕裂").
- **Swap expressions inside a blink.** The face changes while the eyes are closed. Every one-shot clip starts on an
  Idle frame 0 and ends exactly on its target Idle frame 0.
- **Fix what the AI got wrong, and leave the story alone.** Remove AI artifacts: mottled surfaces, pseudo-text,
  shapeless blobs, missing hands, impossible light, decorations on objects that would not have them. Do not add or
  move story-relevant content (characters, clues, writing) on your own. List those cases under "needs confirmation".
- **Same camera, same pixels.** When two shots share a camera or a location, reuse the established pixels. That
  applies to a room, a car interior, a lamp's flicker timing and a palette. Cuts between them must not jump.
- **Respect "don't animate X".** When the user says stills only, or not to move something, lock it and change
  nothing else.

## 2. Scene track

Read `references/scene-pipeline.md` before the first scene. Read `references/scene-loops.md` before animating,
and its parallax section before layering.

1. **Pixelize in two stages, so hand fixes can happen in between.**
   ```bash
   python scripts/scene_to_pixel.py concept.png OUT --name BG02 [--smooth 8,16] [--keep x0,y0,x1,y1]
   # -> OUT/BG02_stylized.png (ungraded) + OUT/BG02_compare.png
   ```
   `stylize` does the "hand-drawn simplification":
   - reduces to about 22 colours taken from the source;
   - flattens each object to at most 3 tones;
   - absorbs specks;
   - protects small bright features (lamps, windows) and thin lines (rails, road marks).

   Use `--keep` for props whose exact shape carries the scene's logic. Use `--smooth` for grainy, GIF or JPEG
   sources. Stage 1 also writes `BG02_native.png` (the resized source, for lights and masks) and
   `BG02_protected.png`. Check the protected mask for spurious lines.
2. **Inspect at zoom and hand-fix** with `pixkit.scene`:
   - `ramp_paint` turns mottled floors, desks and walls into flat lit bands;
   - `inpaint` removes things;
   - `line_mask_src` draws seams back in;
   - paste from earlier shots that share the camera.

   Check light direction, reachability and continuity (see the logic checklist in the reference).
3. **Finish**: `python scripts/scene_to_pixel.py OUT/BG02_fixed.png OUT --name BG02 --finish --grade cold_dusk`.
   This grades the palette, adds the 4-level dithered vignette and locks the result to 24 colours. Shots that cut
   together must share a palette: use `scene.finish(a, extra=[b])`.
4. **Loop** (if wanted):
   - Make masks as PNGs. Pick colours or draw polygons with numpy, then check them by overlaying them on the
     still.
   - Write a spec (`assets/examples/loop_spec.example.json`) and run `python scripts/make_loop.py spec.json`.
   - Read the audit. Expect `new_colours: 0`, a seam change similar to the mean change between neighbouring
     frames, and few pixels toggling more than 8 times.
   - Watch the review mp4. The numbers do not catch everything.
5. **Parallax** (if the camera scrolls): see the reference. In short:
   - keep the walkable ground and everything on it in one layer;
   - use speed factors of about 0.3 / 0.45 / 0.6 / 1.0;
   - fill hidden parts of back layers as complete, seamlessly tiling panoramas;
   - ship only the animated row bands as sheets (`pixkit.parallax`).
6. **Package** with `references/packaging.md`:
   - `still/`, `loop/<name>/frames_native/`, `_1920` copies and the review mp4;
   - a **review PDF for every scene pack** (`scripts/make_review_pdf.py`);
   - a README in the user's language.

## 3. Character track

Read `references/character-pipeline.md` first, then `references/character-animation.md`.

1. **First draft**:
   ```bash
   python scripts/sprite_from_concept.py concept.png WORK --height 148 [--materials materials.json]
   ```
   Use the same `--height` as the rest of the cast so everyone shares one scale. The script writes:
   - the raw sprite on the canvas;
   - a comparison with the concept;
   - ASCII dumps;
   - `info.json`, which maps concept coordinates onto the canvas.

   `--materials` snaps each material to a fixed ramp. Use regions to separate same-coloured materials (hair above
   the collar, apron below it). Interior strokes become the material's darkest tone.
2. **Finish the base by hand.** This is the real work, and the face always needs it, because a downscale destroys
   eyes and mouths.
   - Use `pixkit.sprite.Symbols` to dump and paint regions as text, and `grid_zoom` to view them.
   - Redraw the face, keeping the concept's eye style.
   - Clean hands and props; merge near-duplicate colours; `fill_enclosed_holes`.
   - Compare with the concept at 5× and with the cast at the same scale.
3. **Make the featureless face base**: the same sprite with eyes, mouth and brows painted over with skin. The nose
   and other permanent features stay.
4. **Write the character config** (`assets/examples/character.example.json`):
   - the face rig: each feature is a box, and each state is a small character grid;
   - the expressions;
   - talk-mouth overrides;
   - extra performances;
   - preview labels in the user's language;
   - the normal-map part rules;
   - the Unity names.

   Design the expressions at 4–8× zoom against each other before building. Eyes and mouth carry the expression
   when bangs hide the brows.
5. **Build + audit**: `python scripts/build_character.py character.json`.
   - The script refuses to run if the rig's neutral face does not reproduce the base pixel for pixel, because a
     mismatch means every transition would jump.
   - It writes the whole pack and `audit.json`, and exits non-zero on any problem: palette, stray pixels, holes,
     continuity, talk frames outside the mouth, blink frames outside the eyes, normal-map determinism.
6. **Look at it.**
   - Open `previews/expressions_2x.png`, `previews/frames/*`, `previews/scale_with_cast_3x.png` and
     `previews/normals_lit_3x.png`.
   - Play `previews/interactive_preview.html` with Playwright, or ask the user to open it.
   - Fix what looks wrong, then rebuild.

## 4. Delivering and iterating

- **Every delivery is a new version**: `name_V01`, then `V02`, and so on. Never overwrite an earlier one. Put a
  changelog at the top of the README:
  - what changed;
  - why (quote the feedback being addressed);
  - what was checked.

  Keep everything you did not intend to change pixel-identical, verify that, and say so.
- **README in the user's language.** Use the section pattern in `references/packaging.md`: spec, files, what moves,
  AI artifacts fixed, logic issues found, needs confirmation, Unity steps, checks. Use concrete numbers ("264
  frames scanned, 13 colours, 0 stray pixels"). Mark scripts that were never run inside Unity as untested.
- **Raise open questions instead of guessing.** Examples: a mouth added where the concept had none; a character
  or prop that moved between two shots with the same camera; a decorative element that contradicts the story's time of day.
  Offer options.
- **Send** the zip plus 1–3 key preview images, and give a short summary. Do not narrate every step.

## 5. QA

Run through `references/qa-checklist.md` before every delivery. The audits automate most of it. The visual pass at
zoom catches the rest: tears, crawling dither, shapes that change thickness while swaying, mist that does not move
with its ground, mouths that touch the chin line, and half-blinks that jump.

## Reference files

| File | Read when |
|---|---|
| `references/scene-pipeline.md` | pixelizing any scene: stylize parameters, AI-artifact and logic fixes, grades, shared palettes |
| `references/scene-loops.md` | animating a still: effect catalogue and parameters, known failure modes, lamp flicker, CG people, image-to-video clips, procedural camera moves, parallax |
| `references/character-pipeline.md` | concept → 1x base sprite, face redraw, ASCII editing |
| `references/character-animation.md` | the face rig, expression design, clip set and timings, motion rules, side / back / walk extensions |
| `references/normal-maps.md` | normal-map method, part rules, Unity lighting setup |
| `references/packaging.md` | folder layouts, json / manifest formats, README template, review PDF |
| `references/qa-checklist.md` | before every delivery |
