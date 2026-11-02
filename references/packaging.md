# Packaging and delivery

## Contents
1. Versioning
2. Scene / CG pack layout
3. Sprite pack layout and formats
4. README template
5. Review PDF
6. Delivery

---

## 1. Versioning

- `<NAME>_V01`, `_V02`, … or `_v2`, `_v3`. Follow the project's existing style. Every delivery is a new folder plus
  a zip. Never overwrite.
- The README starts with the newest changelog section, `━━ V05 改动：… ━━` (in the user's language), and keeps
  older sections below it as history.
- After a targeted fix, re-verify that everything else is pixel-identical to the previous version and say so
  ("颜色图、图集、json、时长都和 V17 一样").

## 2. Scene / CG pack layout

```
CG_NAME/
  still/CG_NAME.png, CG_NAME_1920.png           # still = loop frame 0
  loop/frames_native/CG_NAME_LOOP_0000.png …    # (or loop/<shot>/frames_native/ for multi-shot packs)
  CG_NAME_preview_1920.mp4                      # loops played 3×, exact 3× nearest
  CG_NAME_review.pdf
  alt_<variant>/                                # optional alternative stills (warm / cold / …)
  README.md
```

For a parallax pack add `layers/`, `loops/<layer>/`, `sheets/` (band sheets + json), `parallax.json`,
`video/` (pan + sway reviews, v-old vs v-new comparisons), `overlay/` (camera vignette), `preview/` and `unity/`.

## 3. Sprite pack layout and formats

Written by `pixkit.pack.write_pack` (see its docstring for the tree).

- `animations/<Clip>_sheet.json` is TexturePacker style: a `frames` list where each frame has `filename`,
  `frame{x,y,w,h}`, `duration` (ms) and `note`. `meta` holds `image`, `size`, `pivot_normalized`, `loop`, `state`,
  `view`, `frameTags`, and optionally `root_motion.dx_px_per_frame`.
- `timing.csv` columns: clip, state, frame, duration_ms, start_ms, start_frame@60fps, length_frames@60fps, note.
- `manifest.json` holds character, version, canvas, pivot, foot line, PPU, neutral, states (with sha256), views,
  animations (state, loop, durations, files, notes) and transitions (the hand-off rules).
- `audit.json` comes from `build_character.py`. Quote its numbers in the README.
- `previews/interactive_preview.html` is a single self-contained file. One tab plays the clips. The other plays the
  expression buttons through the real From_/To_ routes, with a talk toggle and performance buttons. The UI comes in
  zh / en (`lang`).

## 4. README template

Write the README in the user's language and keep it scannable. Section pattern (Chinese example headings; translate
them as needed):

```
<name> <version> —— <one-line description>（<scope>，格式同 <existing packs>）

━━ 规格 ━━          canvas / foot line / pivot / PPU / colours / outline / same scale as the cast
━━ <Vxx> 改动 ━━     newest first: what changed, why (the feedback), what was verified
━━ 从原图到 1x ━━    (characters) how it was converted, what was redrawn, what was cleaned
━━ 表情 ━━ / ━━ 动画 ━━   tables: name, what it looks like / frames, duration, content
━━ 法线图 ━━         method in 3–5 bullets, encoding, preview files
━━ 文件 ━━           path → purpose
━━ Unity ━━          numbered steps; say the scripts are untested if they never ran in Unity
━━ 切换规则 ━━       hand-offs
━━ 核对 ━━           audit numbers
━━ 需要确认 / 还没做 ━━   open questions with options; deferred scope
```

For scenes: 规格 / 文件 / 每张的循环 (table: shot | what moves | frame 0 vs still) / 修掉的 AI 痕迹 / 不合逻辑的地方
(fixed and "checked, not changed") / 调色 / 需要确认 / Unity.

Style: concrete numbers and coordinates, short bullets, no marketing. Name what deliberately does NOT move or did
NOT change.

## 5. Review PDF

Every background / CG pack gets one (`scripts/make_review_pdf.py`). Typical pages:

1. a cover: title, version, spec line, date, an overview image;
2. the method and the AI artifacts fixed (text from the README);
3. per shot: source → result side by side, then 2–4 detail crops (source crop vs pixel crop) for the fixes;
4. loop keyframes 0 / 12 / 24 / 36 with the loop spec in the subtitle;
5. alternatives side by side, if any;
6. an overview of all shots.

Check the PDF: render the pages to PNG and look at them for overlapping labels and clipped text.

## 6. Delivery

- Zip the pack folder. Send the zip and 1–3 key previews (expressions board, scale check, a GIF or keyframes)
  directly to the user. Do not publish the user's art to public pages unless asked.
- The final message is short. It covers what is in the pack, the 2–3 decisions the user should confirm, and what
  is deferred.
