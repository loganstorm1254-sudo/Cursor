#!/usr/bin/env python3
"""
One STL: PLA snap vial + one-way waterproof screw lid.

Small medical-style vial. Cap screws on and locks (won't unscrew).
Thin scored neck snaps to open. Designed as a single PLA print file
(body + cap laid side-by-side on the bed).

Units: mm. Print in PLA at 100% infill / 5+ walls for liquid hold.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import trimesh
from trimesh.creation import cone, cylinder
from trimesh.transformations import rotation_matrix

OUT = Path(__file__).resolve().parent / "stl"
SEG = 64

# PLA-friendly thicker walls (less weep-through)
BODY_OD, BODY_ID, BODY_H = 14.0, 9.0, 24.0
BOTTOM = 2.4

NECK_OD, NECK_ID, NECK_H = 5.4, 2.8, 2.8
SCORE_W, SCORE_DEPTH = 0.55, 0.85

SEAL_OD = 11.0
# PLA crush-lip seat (no separate gasket) — tall tapered interference ring
LIP_BOT, LIP_TOP, LIP_H = 10.2, 8.4, 2.4
COLLAR_OD, COLLAR_H = 10.4, 6.5
THREAD_PITCH, THREAD_H, THREAD_DEPTH = 1.6, 4.2, 0.65
THREAD_Z0 = 1.0

RATCHET_TEETH, RATCHET_OD, RATCHET_H = 14, 11.8, 1.8

CAP_OD, CAP_TOP = 15.5, 2.0
CLEAR = 0.35  # FDM/PLA clearance
PAWLS = 6


def C(r: float, h: float, z0: float = 0.0, sec: int = SEG) -> trimesh.Trimesh:
    m = cylinder(radius=r, height=h, sections=sec)
    m.apply_translation([0.0, 0.0, z0 + h / 2.0])
    return m


def tube(ro: float, ri: float, h: float, z0: float = 0.0) -> trimesh.Trimesh:
    return C(ro, h, z0).difference(C(ri, h + 0.6, z0 - 0.3))


def frustum(r_bot: float, r_top: float, h: float, z0: float = 0.0) -> trimesh.Trimesh:
    if abs(r_bot - r_top) < 1e-6:
        return C(r_bot, h, z0)
    if r_bot > r_top:
        full_h = h * r_bot / (r_bot - r_top)
        m = cone(radius=r_bot, height=full_h, sections=SEG)
        m = m.difference(C(r_bot * 1.25, full_h - h + 1.0, h))
        m.apply_translation([0, 0, z0])
        return m
    full_h = h * r_top / (r_top - r_bot)
    m = cone(radius=r_top, height=full_h, sections=SEG)
    m.apply_transform(rotation_matrix(math.pi, [1, 0, 0]))
    m.apply_translation([0, 0, full_h])
    m = m.difference(C(r_top * 1.25, full_h - h + 1.0, -(full_h - h + 1.0)))
    m.apply_translation([0, 0, z0 - m.bounds[0][2]])
    return m


def u(a: trimesh.Trimesh, b: trimesh.Trimesh) -> trimesh.Trimesh:
    return a.union(b)


def d(a: trimesh.Trimesh, b: trimesh.Trimesh) -> trimesh.Trimesh:
    return a.difference(b)


def thread_blobs(
    major: float,
    minor: float,
    pitch: float,
    height: float,
    z0: float,
    internal: bool,
    clearance: float = 0.0,
) -> trimesh.Trimesh:
    if internal:
        major += clearance
        minor += clearance
    else:
        major -= clearance
        minor -= clearance

    steps = int((height / pitch) * 28)
    blobs = []
    depth = abs(major - minor)
    for i in range(steps + 1):
        t = i / 28.0
        ang = t * 2 * math.pi
        z = z0 + t * pitch
        if z < z0 - 0.05 or z > z0 + height + 0.05:
            continue
        r = 0.5 * (major + minor)
        box = trimesh.creation.box(extents=[depth + 0.3, 0.75, pitch * 0.55])
        T = rotation_matrix(ang, [0, 0, 1])
        T[:3, 3] = [r * math.cos(ang), r * math.sin(ang), z]
        box.apply_transform(T)
        blobs.append(box)

    acc = blobs[0]
    for i, b in enumerate(blobs[1:], 1):
        acc = acc.union(b)
        if i % 30 == 0:
            acc.merge_vertices()
    return acc


def ratchet(od: float, id_: float, h: float, teeth: int, z0: float) -> trimesh.Trimesh:
    ring = tube(od * 0.88, id_, h * 0.5, z0 + h * 0.25)
    for i in range(teeth):
        a0 = 2 * math.pi * i / teeth
        a1 = a0 + 2 * math.pi * 0.7 / teeth
        pts = np.array(
            [
                [id_ * math.cos(a0), id_ * math.sin(a0), z0],
                [od * math.cos(a0 + 0.1), od * math.sin(a0 + 0.1), z0],
                [id_ * math.cos(a1), id_ * math.sin(a1), z0],
                [id_ * math.cos(a0), id_ * math.sin(a0), z0 + h],
                [od * math.cos(a0 + 0.1), od * math.sin(a0 + 0.1), z0 + h],
                [id_ * math.cos(a1), id_ * math.sin(a1), z0 + h],
            ]
        )
        ring = ring.union(trimesh.Trimesh(vertices=pts).convex_hull)
    return ring


def pawls(n: int, r_in: float, r_out: float, h: float, z0: float) -> trimesh.Trimesh:
    parts = []
    for i in range(n):
        ang = 2 * math.pi * i / n
        pts = np.array(
            [
                [r_in, 0.05, z0],
                [r_in, 0.85, z0],
                [r_out, -0.4, z0],
                [r_out, 0.65, z0],
                [r_in, 0.05, z0 + h],
                [r_in, 0.85, z0 + h],
                [r_out, -0.4, z0 + h],
                [r_out, 0.65, z0 + h],
            ]
        )
        p = trimesh.Trimesh(vertices=pts).convex_hull
        p.apply_transform(rotation_matrix(ang, [0, 0, 1]))
        parts.append(p)
    acc = parts[0]
    for p in parts[1:]:
        acc = acc.union(p)
    return acc


def build_body() -> trimesh.Trimesh:
    z = 0.0
    body = u(tube(BODY_OD / 2, BODY_ID / 2, BODY_H, z), C(BODY_OD / 2, BOTTOM, z))
    z = BODY_H

    sh = d(frustum(BODY_OD / 2, NECK_OD / 2 + 0.4, 2.2, z), C(NECK_ID / 2, 2.6, z - 0.2))
    body = u(body, sh)
    z += 2.2

    body = u(body, tube(NECK_OD / 2, NECK_ID / 2, NECK_H, z))
    score_z = z + NECK_H * 0.42
    body = d(
        body,
        tube(NECK_OD / 2 + 0.12, NECK_OD / 2 - SCORE_DEPTH, SCORE_W, score_z - SCORE_W / 2),
    )
    z += NECK_H

    flare = d(frustum(NECK_OD / 2 + 0.2, SEAL_OD / 2, 1.6, z), C(NECK_ID / 2, 2.0, z - 0.2))
    body = u(body, flare)
    z += 1.6

    # flat land
    body = u(body, tube(SEAL_OD / 2, NECK_ID / 2, 0.7, z))
    z += 0.7

    # male taper crush seal (PLA interference with cap)
    taper = d(
        frustum(LIP_BOT / 2, LIP_TOP / 2, LIP_H, z),
        C(NECK_ID / 2, LIP_H + 0.4, z - 0.2),
    )
    body = u(body, taper)
    z += LIP_H

    collar = tube(COLLAR_OD / 2, NECK_ID / 2, COLLAR_H, z)
    body = u(body, collar)
    body = u(
        body,
        thread_blobs(
            COLLAR_OD / 2,
            COLLAR_OD / 2 - THREAD_DEPTH,
            THREAD_PITCH,
            THREAD_H,
            z + THREAD_Z0,
            internal=False,
        ),
    )

    rz = z + COLLAR_H - RATCHET_H
    body = u(body, ratchet(RATCHET_OD / 2, COLLAR_OD / 2 - 0.1, RATCHET_H, RATCHET_TEETH, rz))
    body = u(body, tube(LIP_TOP / 2 + 0.25, NECK_ID / 2, 0.5, z + COLLAR_H - 0.15))

    body.merge_vertices()
    body.process(validate=True)
    return body


def build_cap() -> trimesh.Trimesh:
    stack = 0.7 + LIP_H + COLLAR_H + 0.55
    outer_h = stack + CAP_TOP
    inner_r = COLLAR_OD / 2 + CLEAR

    cap = d(C(CAP_OD / 2, outer_h, 0), C(inner_r, stack + 0.25, CAP_TOP - 0.05))

    # grip ribs
    rib = None
    for i in range(16):
        ang = 2 * math.pi * i / 16
        r = trimesh.creation.box(extents=[0.8, 1.2, outer_h * 0.78])
        T = rotation_matrix(ang, [0, 0, 1])
        T[:3, 3] = [
            (CAP_OD / 2) * math.cos(ang),
            (CAP_OD / 2) * math.sin(ang),
            CAP_TOP + stack * 0.42,
        ]
        r.apply_transform(T)
        rib = r if rib is None else rib.union(r)
    rib = rib.intersection(C(CAP_OD / 2 + 0.45, outer_h, 0))
    cap = u(cap, rib)

    # internal threads
    thr = thread_blobs(
        COLLAR_OD / 2,
        COLLAR_OD / 2 - THREAD_DEPTH,
        THREAD_PITCH,
        THREAD_H,
        CAP_TOP + 0.7 + LIP_H + THREAD_Z0,
        internal=True,
        clearance=CLEAR,
    )
    thr = thr.intersection(C(inner_r + 1.0, outer_h, 0))
    thr = thr.difference(C(COLLAR_OD / 2 - THREAD_DEPTH - 0.2, outer_h, 0))
    cap = u(cap, thr)

    # female taper — slightly tighter than male for PLA crush seal
    tz = CAP_TOP + 0.7
    plug = frustum(
        LIP_BOT / 2 + CLEAR - 0.12,
        LIP_TOP / 2 + CLEAR - 0.12,
        LIP_H,
        tz,
    )
    plug = d(plug, C(NECK_ID / 2 + 0.5, LIP_H + 0.5, tz - 0.25))
    plug = plug.intersection(C(inner_r - 0.02, outer_h, 0))
    cap = u(cap, plug)

    # flat face land
    face = tube(SEAL_OD / 2 - 0.1, NECK_ID / 2 + 0.6, 0.45, CAP_TOP + 0.2)
    face = face.intersection(C(inner_r - 0.02, outer_h, 0))
    cap = u(cap, face)

    # thin PLA crush lip ring (deforms a little when screwed tight)
    lip = tube(LIP_BOT / 2 - 0.15, LIP_TOP / 2 + 0.1, 0.55, CAP_TOP + 0.55)
    lip = lip.intersection(C(inner_r - 0.02, outer_h, 0))
    cap = u(cap, lip)

    pz = outer_h - RATCHET_H - 0.1
    p = pawls(PAWLS, COLLAR_OD / 2 + 0.05, RATCHET_OD / 2 - 0.1, RATCHET_H * 0.85, pz)
    p = p.intersection(C(CAP_OD / 2 - 0.25, outer_h + 0.5, -0.2))
    cap = u(cap, p)

    cap.merge_vertices()
    cap.process(validate=True)
    return cap


def export(mesh: trimesh.Trimesh, path: Path) -> None:
    m = mesh.copy()
    try:
        m.update_faces(m.unique_faces())
        m.update_faces(m.nondegenerate_faces())
    except Exception:
        pass
    m.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(m)
    try:
        trimesh.repair.fill_holes(m)
    except Exception:
        pass
    trimesh.repair.fix_normals(m)
    m.export(path)
    print(f"wrote {path}  V={m.volume:.1f} mm^3  watertight={m.is_watertight}  extents={m.extents}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    print("Building PLA body...")
    body = build_body()
    print("Building PLA one-way cap...")
    cap = build_cap()

    # Single print plate: body + cap side by side, both flat on bed
    body.apply_translation([-10.0, 0.0, 0.0])
    # Cap open-end up already; shift beside body
    gap = 3.0
    cap_x = body.bounds[1][0] + gap + (cap.extents[0] / 2.0)
    cap.apply_translation([cap_x, 0.0, 0.0])

    plate = trimesh.util.concatenate([body, cap])
    # Drop so both sit on z=0
    plate.apply_translation([0, 0, -plate.bounds[0][2]])

    out = OUT / "snap_vial_pla.stl"
    export(plate, out)

    # Remove older multi-file STLs so the folder is just the one file
    for old in OUT.glob("*.stl"):
        if old.name != out.name:
            old.unlink()
            print(f"removed {old.name}")


if __name__ == "__main__":
    main()
