# Snap vial (PLA, one STL)

One printable STL: small medical-style liquid vial + one-way screw lid.

## File

**`stl/snap_vial_pla.stl`** — body and cap on one plate (print both in PLA).

## How it works

1. Fill the vial.
2. Screw the cap on hard until the ratchet clicks — taper crush seal locks liquid in.
3. Cap will **not unscrew**.
4. Snap the thin scored neck to open.

## PLA print settings (important for no leaks)

- Material: **PLA**
- **100% infill** (or ≥5 solid walls + solid top/bottom)
- Layer height 0.12–0.2 mm
- Body upright; cap open-end up
- Optional: brush the inside with a thin coat of epoxy / nail hardener / food-safe sealer for extra waterproofing

## Regenerate

```bash
pip install -r requirements.txt
python3 generate_vial.py
```
