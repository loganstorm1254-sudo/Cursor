# UK Light Switch Guard (STL)

Hinged cover for a **classic UK 1-gang rocker** — the square white moulded plate with **screws left & right** of the rocker (60.3 mm centres), as in a typical BG / MK / Logic Plus style switch.

Inspired by the MakerWorld [Switch Guard](https://makerworld.com/en/models/255143-switch-guard) hinged-scoop idea, re-laid-out for British horizontal fixings.

## Print this

| File | Use |
|------|-----|
| `stl/uk_switch_guard_plate.stl` | **Print this** — base + lid on one plate |
| `stl/uk_switch_guard_base.stl` | Base only |
| `stl/uk_switch_guard_lid.stl` | Lid only |
| `stl/uk_switch_guard_wide_rocker_plate.stl` | Wider rocker window |
| `uk_switch_guard.scad` | Parametric source |

## Fit (matches your switch)

- Faceplate ~**86 × 86 mm**
- Screws **left & right**, centres **60.3 mm** apart
- Default rocker window **24 × 34 mm** (narrow rocker + clearance)
- Wide variant **30 × 38 mm**

Measure your rocker face before printing if it looks oversized / accessible-style.

## Print settings

- PLA or PETG
- 0.2 mm layers, 2–3 walls, 15–25% infill
- No supports — print flat as in `*_plate.stl`

## Install

1. Print base + lid; snap the lid knuckles onto the base hinge balls.
2. Optional: push short **1.75 mm filament** pins through the hinge holes and trim flush.
3. Loosen the two faceplate screws, slide the base slots under the screw heads, retighten snug (don’t crush the plastic).
4. Close the lid. Pull the bottom tab slightly out, then up, to open past the catch.

## Customise

```bash
openscad -o stl/custom.stl -D 'part="plate"' -D 'rocker_w=26' -D 'rocker_h=36' uk_switch_guard.scad
```

## Attribution

Original geometry here. Concept inspired by Marc Plays with Printing’s Switch Guard on MakerWorld (CC BY-NC) — keep redistribution non-commercial if you treat this as a derivative of that idea.
