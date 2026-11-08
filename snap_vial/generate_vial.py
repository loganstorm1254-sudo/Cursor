#!/usr/bin/env python3
"""
Tiny medical-style snap vial + one-way waterproof screw lid (STL).

- Thin scored neck: snap to open (intended failure point)
- Screw-on lid with ratchet pawls: installs, will not unscrew
- Liquid-tight stack: O-ring groove + conical crush taper + flat face

Units: mm.

Print notes
- Body/cap: resin or PETG, 100% infill walls, waterproof coating optional
- Gasket: print in TPU *or* use a store O-ring (~1.2 mm CS, ~7 mm ID)
- Seat the O-ring/gasket in the body groove before screwing the cap on hard
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import trimesh
from trimesh.creation import cone, cylinder
from trimesh.transformations import rotation_matrix

OUT = Path(__file__).resolve().parent / "stl"
SEG = 72

# reservoir
BODY_OD, BODY_ID, BODY_H = 12.0, 8.8, 26.0
BOTTOM = 1.8

# snap neck
NECK_OD, NECK_ID, NECK_H = 5.0, 3.0, 2.6
SCORE_W, SCORE_DEPTH = 0.5, 0.75

# sealing / collar
SEAL_OD = 10.0
ORING_OD, ORING_ID, ORING_H = 9.3, 6.9, 1.4
TAPER_BOT, TAPER_TOP, TAPER_H = 9.5, 8.0, 1.9
COLLAR_OD, COLLAR_H = 9.8, 6.2
THREAD_PITCH, THREAD_H, THREAD_DEPTH = 1.5, 4.0, 0.6
THREAD_Z0 = 0.9

# ratchet
RATCHET_TEETH, RATCHET_OD, RATCHET_H = 16, 11.0, 1.7

# cap
CAP_OD, CAP_TOP, CLEAR = 14.0, 1.6, 0.28
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
        cut = C(r_bot * 1.25, full_h - h + 1.0, h)
        m = m.difference(cut)
        m.apply_translation([0, 0, z0])
        return m
    full_h = h * r_top / (r_top - r_bot)
    m = cone(radius=r_top, height=full_h, sections=SEG)
    m.apply_transform(rotation_matrix(math.pi, [1, 0, 0]))
    m.apply_translation([0, 0, full_h])
    cut = C(r_top * 1.25, full_h - h + 1.0, -(full_h - h + 1.0))
    m = m.difference(cut)
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
    """Helical thread approximated by overlapping boxes (robust unions)."""
    if internal:
        major = major + clearance
        minor = minor + clearance
    else:
        major = major - clearance
        minor = minor - clearance

    turns = height / pitch
    steps = int(turns * 36)
    blobs = []
    depth = abs(major - minor)
    for i in range(steps + 1):
        t = i / 36.0
        ang = t * 2 * math.pi
        z = z0 + t * pitch
        if z < z0 - 0.05 or z > z0 + height + 0.05:
            continue
        r = 0.5 * (major + minor)
        box = trimesh.creation.box(
            extents=[depth + 0.25, 0.65, pitch * 0.55]
        )
        # rotate around Z then move to helix point
        T = rotation_matrix(ang, [0, 0, 1])
        T[:3, 3] = [r * math.cos(ang), r * math.sin(ang), z]
        box.apply_transform(T)
        blobs.append(box)

    mesh = trimesh.util.concatenate(blobs)
    # fuse via convex hulls of neighborhoods for cleaner volume
    # Manifold union in chunks
    acc = blobs[0]
    for i, b in enumerate(blobs[1:], 1):
        acc = acc.union(b)
        if i % 40 == 0:
            acc.merge_vertices()
    return acc


def ratchet(od: float, id_: float, h: float, teeth: int, z0: float) -> trimesh.Trimesh:
    base = tube(od * 0.88, id_, h * 0.5, z0 + h * 0.25)
    teeth_m = []
    for i in range(teeth):
        a0 = 2 * math.pi * i / teeth
        a1 = a0 + 2 * math.pi * 0.7 / teeth
        # asymmetric tooth points (steep lock face at a0)
        pts = np.array(
            [
                [id_ * math.cos(a0), id_ * math.sin(a0), z0],
                [od * math.cos(a0 + 0.08), od * math.sin(a0 + 0.08), z0],
                [id_ * math.cos(a1), id_ * math.sin(a1), z0],
                [id_ * math.cos(a0), id_ * math.sin(a0), z0 + h],
                [od * math.cos(a0 + 0.08), od * math.sin(a0 + 0.08), z0 + h],
                [id_ * math.cos(a1), id_ * math.sin(a1), z0 + h],
            ]
        )
        teeth_m.append(trimesh.Trimesh(vertices=pts).convex_hull)
    ring = base
    for t in teeth_m:
        ring = ring.union(t)
    return ring


def pawls(n: int, r_in: float, r_out: float, h: float, z0: float) -> trimesh.Trimesh:
    parts = []
    for i in range(n):
        ang = 2 * math.pi * i / n
        pts = np.array(
            [
                [r_in, 0.05, z0],
                [r_in, 0.7, z0],
                [r_out, -0.35, z0],
                [r_out, 0.55, z0],
                [r_in, 0.05, z0 + h],
                [r_in, 0.7, z0 + h],
                [r_out, -0.35, z0 + h],
                [r_out, 0.55, z0 + h],
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

    # shoulder -> neck
    sh = d(frustum(BODY_OD / 2, NECK_OD / 2 + 0.35, 2.0, z), C(NECK_ID / 2, 2.4, z - 0.2))
    body = u(body, sh)
    z += 2.0

    neck = tube(NECK_OD / 2, NECK_ID / 2, NECK_H, z)
    body = u(body, neck)
    # score groove
    score_z = z + NECK_H * 0.42
    body = d(body, tube(NECK_OD / 2 + 0.1, NECK_OD / 2 - SCORE_DEPTH, SCORE_W, score_z - SCORE_W / 2))
    z += NECK_H

    flare = d(frustum(NECK_OD / 2 + 0.15, SEAL_OD / 2, 1.5, z), C(NECK_ID / 2, 1.9, z - 0.2))
    body = u(body, flare)
    z += 1.5

    # flat seal land
    body = u(body, tube(SEAL_OD / 2, ORING_ID / 2 - 0.15, 0.65, z))
    z += 0.65

    # O-ring groove section: outer lands + inner core, channel between
    # Build solid cylinder then cut the groove channel
    band = tube(SEAL_OD / 2, NECK_ID / 2, ORING_H, z)
    groove = tube(ORING_OD / 2 + 0.02, ORING_ID / 2, ORING_H * 0.78, z + ORING_H * 0.11)
    # open groove to outside by cutting outer wall in the middle band
    outer_cut = tube(SEAL_OD / 2 + 0.2, ORING_OD / 2, ORING_H * 0.78, z + ORING_H * 0.11)
    band = d(band, outer_cut)
    # ensure groove floor exists (inner wall)
    band = u(band, tube(ORING_ID / 2, NECK_ID / 2, ORING_H, z))
    body = u(body, band)
    z += ORING_H

    # conical waterproof seat
    taper = d(frustum(TAPER_BOT / 2, TAPER_TOP / 2, TAPER_H, z), C(NECK_ID / 2, TAPER_H + 0.4, z - 0.2))
    body = u(body, taper)
    z += TAPER_H

    # threaded collar
    collar = tube(COLLAR_OD / 2, NECK_ID / 2, COLLAR_H, z)
    body = u(body, collar)
    thr = thread_blobs(
        COLLAR_OD / 2,
        COLLAR_OD / 2 - THREAD_DEPTH,
        THREAD_PITCH,
        THREAD_H,
        z + THREAD_Z0,
        internal=False,
    )
    body = u(body, thr)

    # ratchet near top
    rz = z + COLLAR_H - RATCHET_H
    body = u(body, ratchet(RATCHET_OD / 2, COLLAR_OD / 2 - 0.1, RATCHET_H, RATCHET_TEETH, rz))

    # mouth lip
    body = u(body, tube(TAPER_TOP / 2 + 0.2, NECK_ID / 2, 0.45, z + COLLAR_H - 0.15))

    body.merge_vertices()
    body.process(validate=True)
    return body


def build_cap() -> trimesh.Trimesh:
    stack = 0.65 + ORING_H + TAPER_H + COLLAR_H + 0.5
    outer_h = stack + CAP_TOP
    inner_r = COLLAR_OD / 2 + CLEAR

    cap = d(C(CAP_OD / 2, outer_h, 0), C(inner_r, stack + 0.25, CAP_TOP - 0.05))

    # grip ribs
    ribs = []
    for i in range(18):
        ang = 2 * math.pi * i / 18
        rib = trimesh.creation.box(extents=[0.75, 1.15, outer_h * 0.78])
        T = rotation_matrix(ang, [0, 0, 1])
        T[:3, 3] = [
            (CAP_OD / 2) * math.cos(ang),
            (CAP_OD / 2) * math.sin(ang),
            CAP_TOP + stack * 0.42,
        ]
        rib.apply_transform(T)
        ribs.append(rib)
    ribmesh = ribs[0]
    for r in ribs[1:]:
        ribmesh = ribmesh.union(r)
    ribmesh = ribmesh.intersection(C(CAP_OD / 2 + 0.4, outer_h, 0))
    cap = u(cap, ribmesh)

    # internal threads
    thr = thread_blobs(
        COLLAR_OD / 2,
        COLLAR_OD / 2 - THREAD_DEPTH,
        THREAD_PITCH,
        THREAD_H,
        CAP_TOP + 0.65 + ORING_H + TAPER_H + THREAD_Z0,
        internal=True,
        clearance=CLEAR,
    )
    thr = thr.intersection(C(inner_r + 0.9, outer_h, 0))
    # clip to annular region inside wall
    thr = thr.difference(C(COLLAR_OD / 2 - THREAD_DEPTH - 0.15, outer_h, 0))
    cap = u(cap, thr)

    # female taper crush face (mates with body taper)
    tz = CAP_TOP + 0.65 + ORING_H
    plug = frustum(TAPER_BOT / 2 + CLEAR + 0.12, TAPER_TOP / 2 + CLEAR + 0.12, TAPER_H, tz)
    plug = d(plug, C(NECK_ID / 2 + 0.45, TAPER_H + 0.5, tz - 0.25))
    plug = plug.intersection(C(inner_r - 0.02, outer_h, 0))
    cap = u(cap, plug)

    # O-ring crush annulus
    crush = tube(ORING_OD / 2 + 0.12, ORING_ID / 2 + 0.12, 0.85, CAP_TOP + 0.65)
    crush = crush.intersection(C(inner_r - 0.02, outer_h, 0))
    cap = u(cap, crush)

    # flat sealing face
    face = tube(SEAL_OD / 2 - 0.15, ORING_ID / 2 + 0.05, 0.4, CAP_TOP + 0.2)
    face = face.intersection(C(inner_r - 0.02, outer_h, 0))
    cap = u(cap, face)

    # pawls at open end
    pz = outer_h - RATCHET_H - 0.1
    p = pawls(PAWLS, COLLAR_OD / 2 + 0.05, RATCHET_OD / 2 - 0.08, RATCHET_H * 0.85, pz)
    p = p.intersection(C(CAP_OD / 2 - 0.3, outer_h + 0.5, -0.2))
    cap = u(cap, p)

    cap.merge_vertices()
    cap.process(validate=True)
    return cap


def build_gasket() -> trimesh.Trimesh:
    # Print in TPU for waterproofing without a store O-ring
    g = tube(ORING_OD / 2 - 0.05, ORING_ID / 2 + 0.05, 1.15, 0)
    g.merge_vertices()
    g.process(validate=True)
    return g


def export(mesh: trimesh.Trimesh, path: Path) -> None:
    m = mesh.copy()
    try:
        m.update_faces(m.unique_faces())
    except Exception:
        pass
    try:
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
    print(f"wrote {path.name:32s}  V={m.volume:8.1f} mm^3  watertight={m.is_watertight}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    print("Building body...")
    body = build_body()
    export(body, OUT / "snap_vial_body.stl")

    print("Building waterproof one-way cap...")
    cap = build_cap()
    export(cap, OUT / "snap_vial_cap.stl")

    print("Building TPU gasket...")
    gasket = build_gasket()
    export(gasket, OUT / "snap_vial_gasket_tpu.stl")

    print("Building assembly preview...")
    preview_cap = cap.copy()
    preview_cap.apply_translation([0, 0, body.bounds[1][2] + 4.0])
    g2 = gasket.copy()
    g2.apply_translation([22.0, 0.0, 0.0])
    preview = trimesh.util.concatenate([body, preview_cap, g2])
    export(preview, OUT / "snap_vial_assembly_preview.stl")


if __name__ == "__main__":
    main()
