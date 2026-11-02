"""pixkit - concept art -> pixel-art game assets (scenes, ambient loops, parallax, sprite packs with expressions).

Modules:
  palette   Lab colour helpers, palette reduce / quantize, ordered dither
  scene     concept -> native pixel scene: stylize (hand-drawn simplification), fixes, grade, vignette, palette lock
  loopfx    seamless palette-locked ambient loop effects (water, glints, flicker, mist, sway, leaves, dust, birds)
  parallax  layered scenes: compose, animated bands, band sheets, review videos
  video     post-process an external image-to-video clip into a palette-locked sequence
  sprite    concept character -> 1x sprite on a fixed canvas, material ramps, ASCII edit tools, zoom grids
  face      data-driven face rig (expressions as small character grids)
  motion    breathing, head moves, standard front clip set, continuity checks
  normals   pixel-art normal maps (volume method) + quick lit previews
  pack      write a sprite pack (sheets, json, gifs, manifest, timing, interactive preview, Unity scripts)
  audit     QA for sprite packs and scene loops
  review_pdf  review PDF for background / CG packs
"""
__version__ = '1.0.0'
