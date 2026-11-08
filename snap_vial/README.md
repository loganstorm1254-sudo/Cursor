# Snap vial (one-way waterproof lid)

Small medical-style liquid vial (~12 mm Ø × ~40 mm tall assembled).

## How it works

1. **Fill** the body with liquid.
2. Drop the **TPU gasket** (or a soft O-ring) into the groove on the neck.
3. **Screw the cap on hard** — ratchet pawls click; the taper + gasket crush into a liquid seal.
4. Cap **will not unscrew** (one-way ratchet).
5. To open: **snap** the thin scored neck (ampoule-style). That is the only intended way in.

## Files

| File | What |
|------|------|
| `stl/snap_vial_body.stl` | Vial with snap neck, O-ring groove, taper seat, threads, ratchet |
| `stl/snap_vial_cap.stl` | One-way screw lid with crush faces + pawls |
| `stl/snap_vial_gasket_tpu.stl` | Soft sealing ring (print in TPU) |
| `stl/snap_vial_assembly_preview.stl` | All parts spaced for viewing |
| `generate_vial.py` | Regenerates the STLs |

## Waterproofing

The lid seals three ways when screwed down:

- **O-ring / TPU gasket** crushed in the dedicated groove (primary seal)
- **Conical taper** seat between body and cap (secondary crush seal)
- **Flat face** land under the groove (third backup face)

For a real liquid hold:

- Print body/cap in **resin** or **PETG** (not porous PLA if you can avoid it)
- Use **100% infill** / thick walls, or seal the print with epoxy/food-safe coating
- Print the gasket in **TPU 85–95A**, or buy a ~**1.2 mm** cross-section O-ring (~**7 mm ID**)
- Tighten until the ratchet has clicked several times

## Print orientation

- Body: upright on the flat bottom
- Cap: top-down (open end up) with supports on pawls if needed
- Gasket: flat on the bed

## Regenerate

```bash
pip install trimesh manifold3d numpy scipy networkx
python3 generate_vial.py
```
