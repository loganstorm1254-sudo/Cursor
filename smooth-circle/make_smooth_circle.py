#!/usr/bin/env python3
"""Generate an ultra-smooth circular disk as a binary STL — fast."""

from __future__ import annotations

import argparse
import math
import struct
import time
from pathlib import Path


def write_binary_stl(
    path: Path,
    *,
    radius: float = 20.0,
    height: float = 1.0,
    segments: int = 8192,
) -> dict:
    """Disk with top/bottom fans + side wall. Normals are exact per triangle."""
    if segments < 3:
        raise ValueError("segments must be >= 3")

    t0 = time.perf_counter()

    # Precompute rim points once (vectorized-ish via list, still O(N) and tiny).
    two_pi = 2.0 * math.pi
    cos = math.cos
    sin = math.sin
    xs = [0.0] * segments
    ys = [0.0] * segments
    for i in range(segments):
        a = two_pi * i / segments
        xs[i] = radius * cos(a)
        ys[i] = radius * sin(a)

    z0 = 0.0
    z1 = height
    n_tri = 4 * segments  # top + bottom + 2*segments side

    # Binary STL: 80-byte header, uint32 count, then 50 bytes/triangle
    header = b"smooth-circle: disk r=%.3f h=%.3f n=%d" % (radius, height, segments)
    header = header[:80].ljust(80, b"\0")

    pack_tri = struct.Struct("<12fH").pack  # nx,ny,nz + 9 verts + attr
    out = bytearray()
    out += header
    out += struct.pack("<I", n_tri)

    append = out.extend

    # Top face (z = z1), outward +Z. Fan from center; CCW when viewed from above.
    for i in range(segments):
        j = (i + 1) % segments
        append(pack_tri(0.0, 0.0, 1.0, 0.0, 0.0, z1, xs[i], ys[i], z1, xs[j], ys[j], z1, 0))

    # Bottom face (z = z0), outward -Z. CW from above = CCW from below.
    for i in range(segments):
        j = (i + 1) % segments
        append(pack_tri(0.0, 0.0, -1.0, 0.0, 0.0, z0, xs[j], ys[j], z0, xs[i], ys[i], z0, 0))

    # Side wall: two triangles per segment, outward radial normals.
    for i in range(segments):
        j = (i + 1) % segments
        x0, y0 = xs[i], ys[i]
        x1, y1 = xs[j], ys[j]
        # Flat normal of the quad (average of edge midpoints direction).
        mx = (x0 + x1) * 0.5
        my = (y0 + y1) * 0.5
        inv = 1.0 / math.hypot(mx, my)
        nx, ny = mx * inv, my * inv
        # Lower triangle
        append(pack_tri(nx, ny, 0.0, x0, y0, z0, x1, y1, z0, x1, y1, z1, 0))
        # Upper triangle
        append(pack_tri(nx, ny, 0.0, x0, y0, z0, x1, y1, z1, x0, y0, z1, 0))

    path.write_bytes(out)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "path": str(path),
        "segments": segments,
        "triangles": n_tri,
        "bytes": len(out),
        "radius_mm": radius,
        "height_mm": height,
        "chord_error_mm": radius * (1.0 - math.cos(math.pi / segments)),
        "elapsed_ms": round(elapsed_ms, 3),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-o", "--output", type=Path, default=Path(__file__).with_name("smooth_circle.stl"))
    p.add_argument("-r", "--radius", type=float, default=20.0, help="radius in mm")
    p.add_argument("--height", type=float, default=1.0, help="disk thickness in mm")
    p.add_argument(
        "-n",
        "--segments",
        type=int,
        default=8192,
        help="rim segments (higher = smoother; 8192 is visually perfect)",
    )
    args = p.parse_args()
    info = write_binary_stl(
        args.output,
        radius=args.radius,
        height=args.height,
        segments=args.segments,
    )
    print(
        f"Wrote {info['path']}\n"
        f"  segments={info['segments']}  triangles={info['triangles']}\n"
        f"  size={info['bytes']} bytes  chord_error={info['chord_error_mm']:.6e} mm\n"
        f"  generated in {info['elapsed_ms']} ms"
    )


if __name__ == "__main__":
    main()
