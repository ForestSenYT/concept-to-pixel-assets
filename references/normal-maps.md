# Pixel-art normal maps and 2D lighting

## Method (`pixkit.normals.normals`)

The first version only bulged each part near its edges: 3–7 px rounded and flat in the middle. Under a side light
the body barely changed and still looked like a flat sticker. The method that was accepted:

1. **Per-row cylinders per part.** In each row, every run of one part (sleeve, coat, leg, hand, cane) gets
   x-normals from −1 at its left edge to +1 at its right edge. This is blended 0.62 : 0.38 with the run of the whole
   figure, so the body as a whole also has a lit side and a shadow side.
2. **Column ends turn.** Only the top and bottom ends of vertical runs (shoulders, tops of shoes, hems) turn up or
   down. Bodies are tall cylinders.
3. **The head is one sphere.** Skin, hair and face lines form one unit, so blinking, expression swaps and glasses
   glints never punch holes in the lighting.
   - Configure it with `head: {"parts": [...], "above_part": "shirt"}`. The head ends where the torso part starts,
     and follows breathing and nods.
4. **Outlines.** Silhouette pixels point outward (a rim light under side light). Interior outline pixels copy the
   nearest part's normal.
5. **Snap and despeckle.** Normals snap to x and y in {−0.82, −0.5, −0.2, 0, 0.2, 0.5, 0.82}, then a 3×3 median per
   part removes single-pixel speckle. Light falls in clean bands with no gradients.
6. **Flat parts.** Eye whites, teeth and lens glare (`flat` parts) sit flat on the face. Without this they would be
   shaded as hair or collar bumps.

Encoding: tangent space, R = +x right, G = +y up, B = z toward the camera, so RGB = n·0.5+0.5. Transparent pixels
are (128,128,255,0).

## Part rules

```json
"normals": {"rules": [
   {"part": "hair",  "colors": [[64,49,46],[92,65,58]], "region": [0,0,96,36]},
   {"part": "apron", "colors": [[64,49,46],[92,65,58]]},
   {"part": "skin",  "colors": [[204,128,98],[232,156,120],[250,182,143],[150,88,72]]},
   {"part": "shoe",  "colors": [[250,229,211],[182,158,146]], "region": [0,140,96,160]},
   {"part": "apron", "colors": [[250,229,211]], "region": [47,45,59,55]},
   {"part": "shirt", "colors": [[250,229,211],[182,158,146]]},
   {"part": "pants", "colors": [[60,47,45],[82,63,59]]}],
 "head": {"parts": ["hair", "skin"], "above_part": "shirt"},
 "flat": []}
```

- The first matching rule wins, so put the narrow region rules before the general ones. In the example, a name tag
  on the apron is shaded as the apron, not as a bump.
- Unmatched opaque pixels count as lines.
- Mouth and lid colours belong to skin.

## Guarantees to check (the audit does)

- Frames with identical colours get identical normals. Loops and hand-offs never pop under lights.
- Normal alpha equals colour alpha.
- A blink changes the normals only near the eyes.

## Previews

- `previews/normals_lit_3x.png`: colour / normals / left light / right light / top light.
- `previews/gif/LIT_*_moving_light_3x.gif`: a light circling the character over Idle and Talk.

These use a quick Lambert preview. The real look comes from the game's shader.

## Unity setup

1. Import the sheets with `<Class>ClipBuilder` (Point filter, no compression, no mipmaps, Max Size 4096, PPU).
   - Max Size matters: Unity's default of 2048 silently downscales wide sheets and blurs them.
2. Run `<Class>NormalMaps` with the character folder selected. It imports `_n` textures as Normal Map (Point,
   uncompressed) and assigns them as the secondary texture `_NormalMap` of the matching sheet, still or view.
   - It only touches the selected folder, because every character uses the same clip names.
3. Enable Normal Map on the Light 2D (Quality = Accurate; Distance about 1–3 units).

## Stepped lighting (recommended shader behaviour)

If only the characters take light (the backgrounds have their light painted in), the lit result must stay pixel art:

- Split the light into intensity `I = max(r, g, b)` and a chroma. Step `I` into about 4 bands.
- Use a 4×4 Bayer dither only within `_DitherWidth` (0.06–0.12) of each band edge.
- **Use texel coordinates for the dither, not screen coordinates.** Then the pattern moves with the character
  instead of swimming. Frame origins are multiples of 96 / 160, which are divisible by 4, so the Bayer phase is
  identical in every frame.
- Do not step the chroma, because warm lamp edges would band. Optionally tint the lowest bands toward the scene's
  cold shadow colour.
- Each texel gets exactly one colour at any output resolution. Sample the light at the texel centre when an
  upscale render texture is off.

```hlsl
static const float bayer4[16] = {0,8,2,10, 12,4,14,6, 3,11,1,9, 15,7,13,5};
float Bayer(int2 t) { return (bayer4[(t.y & 3) * 4 + (t.x & 3)] + 0.5) / 16.0; }
float PixelStepIntensity(float I, int2 texel) {
    float b = Bayer(texel); float level = _Bands.x;
    [unroll] for (int k = 0; k < 3; k++) {
        float e = _BandEdges[k];
        float t = saturate((I - (e - _DitherWidth * 0.5)) / max(_DitherWidth, 1e-4));
        level = (t > b) ? _Bands[k + 1] : level; }
    return level; }
// col.rgb = albedo.rgb * chroma * PixelStepIntensity(I, texel);
```

The acceptance tests:
- with a static scene, consecutive frames are pixel-identical;
- moving the character does not make the dither swim;
- each texel has exactly one colour.
