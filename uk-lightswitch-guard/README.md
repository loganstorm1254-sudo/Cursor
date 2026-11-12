# UK Light Switch Guard (STL)

Hinged cover that stops a UK 1-gang rocker being toggled by accident — same idea as the popular MakerWorld [Switch Guard](https://makerworld.com/en/models/255143-switch-guard), but sized for a British `86×86 mm` faceplate with **60.3 mm** fixing centres.

## What you get

| File | Use |
|------|-----|
| `stl/uk_switch_guard_base.stl` | Mounts under the two faceplate screws |
| `stl/uk_switch_guard_lid.stl` | Flip-up scoop that covers the rocker |
| `stl/uk_switch_guard_plate.stl` | Both parts laid out for one plate |
| `stl/uk_switch_guard_wide_rocker_plate.stl` | Same, with a wider rocker window |
| `uk_switch_guard.scad` | Parametric source (OpenSCAD) |

## Fit

Designed for a typical **single-gang UK rocker** (MK Logic Plus / Crabtree Capital style):

- Faceplate ~86×86 mm
- Screw centres **60.3 mm** (vertical)
- Default rocker window **28×38 mm** (narrow rocker + clearance)
- Wide variant window **34×40 mm**

Measure your rocker before printing. If it is a big accessible/wide rocker, use the wide STL or bump `rocker_w` / `rocker_h` in the `.scad`.

## Print settings

- Material: PLA or PETG
- Layer height: 0.2 mm
- Walls: 2–3
- Infill: 15–25%
- Supports: none (print base and lid flat as in `*_plate.stl`)
- Orientation: flat on the build plate

## Assembly

1. Print base + lid.
2. Snap the lid knuckles onto the base hinge balls. If a snap wears out, push a short length of **1.75 mm filament** through the aligned pin holes as a hinge pin (trim flush).
3. Loosen the two faceplate screws, slide the base slots under the screw heads, and retighten. Do not overtighten into the plastic — snug is enough.
4. Close the lid. The small catch at the bottom resists a pure upward tug (same idea as the MakerWorld G3 variants); pull the tab slightly out, then up, to open.

## Customising

```bash
openscad -o stl/custom.stl -D 'part="plate"' -D 'rocker_w=32' -D 'rocker_h=40' uk_switch_guard.scad
```

Useful parameters: `rocker_w`, `rocker_h`, `rocker_protrusion`, `screw_centres`, `catch_enabled`, `part` (`base` / `lid` / `plate` / `assembly`).

## Licence / attribution

Original geometry in this folder. Concept inspired by Marc Plays with Printing’s Switch Guard on MakerWorld (CC BY-NC). Keep any redistribution non-commercial if you treat this as a derivative of that idea, and credit the inspiration.
