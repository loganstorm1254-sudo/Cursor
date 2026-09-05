#!/usr/bin/env python3
"""Build an obfuscated single-file Beacon bot from clear smmod.py."""
from __future__ import annotations

import base64
import hashlib
import marshal
import os
import random
import sys
import zlib
from pathlib import Path


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _rand_name(n: int = 12) -> str:
    alphabet = "O0Il1ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz"
    return "_" + "".join(random.choice(alphabet) for _ in range(n))


def obfuscate_source(source: str, out_path: Path) -> None:
    # Compile as if it were smmod.py so traceback/__file__ semantics stay sane.
    code = compile(source, "smmod.py", "exec", dont_inherit=True)
    raw = marshal.dumps(code)
    compressed = zlib.compress(raw, 9)

    # Layered transforms: zlib -> xor -> zlib -> b85
    key = hashlib.sha256(os.urandom(32)).digest()
    xored = _xor(compressed, key)
    wrapped = zlib.compress(xored, 9)
    payload = base64.b85encode(wrapped).decode("ascii")

    # Split payload so the blob is not one obvious string.
    chunk_size = 96
    chunks = [payload[i : i + chunk_size] for i in range(0, len(payload), chunk_size)]
    chunks_literal = ",\n".join(f"    {c!r}" for c in chunks)

    n_marshal = _rand_name()
    n_zlib = _rand_name()
    n_b85 = _rand_name()
    n_bytes = _rand_name()
    n_key = _rand_name()
    n_parts = _rand_name()
    n_blob = _rand_name()
    n_tmp = _rand_name()
    n_code = _rand_name()
    n_g = _rand_name()
    n_xor = _rand_name()
    n_i = _rand_name()
    n_k = _rand_name()

    key_b85 = base64.b85encode(key).decode("ascii")

    loader = f'''# Beacon runtime (generated). Do not edit.
# Clear source is maintained separately; this file is intentionally opaque.
from __future__ import annotations
import base64 as {n_b85}
import marshal as {n_marshal}
import sys as _sys
import zlib as {n_zlib}

{n_parts} = (
{chunks_literal}
)
{n_key} = {n_b85}.b85decode({key_b85!r})

def {n_xor}({n_bytes}, {n_k}):
    return bytes(({n_i} ^ {n_k}[{n_tmp} % len({n_k})]) for {n_tmp}, {n_i} in enumerate({n_bytes}))

{n_blob} = "".join({n_parts})
{n_tmp} = {n_zlib}.decompress({n_b85}.b85decode({n_blob}.encode("ascii")))
{n_tmp} = {n_xor}({n_tmp}, {n_key})
{n_tmp} = {n_zlib}.decompress({n_tmp})
{n_code} = {n_marshal}.loads({n_tmp})
{n_g} = globals()
try:
    {n_i} = __file__
except NameError:
    {n_i} = "smmod.py"
{n_g}.update({{
    "__name__": "__main__",
    "__file__": {n_i},
    "__package__": None,
    "__cached__": None,
    "__doc__": None,
    "__builtins__": __builtins__,
}})
exec({n_code}, {n_g}, {n_g})
'''
    out_path.write_text(loader, encoding="utf-8")
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes, {len(chunks)} chunks)")


def inject_secrets(source: str, token: str, secret: str) -> str:
    out = source.replace(
        'TOKEN = ""  # paste bot token, or set DISCORD_TOKEN',
        f'TOKEN = "{token}"  # paste bot token, or set DISCORD_TOKEN',
        1,
    )
    out = out.replace(
        'DISCORD_CLIENT_SECRET = ""  # paste OAuth client secret',
        f'DISCORD_CLIENT_SECRET = "{secret}"  # paste OAuth client secret',
        1,
    )
    if 'TOKEN = ""' in out or 'DISCORD_CLIENT_SECRET = ""' in out:
        raise SystemExit("secret inject failed — blank markers still present")
    return out


def main() -> None:
    random.seed()
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/workspace")
    src_path = root / "smmod.py"
    source = src_path.read_text(encoding="utf-8")

    token = os.environ.get("BEACON_TOKEN", "").strip()
    secret = os.environ.get("BEACON_CLIENT_SECRET", "").strip()

    art = Path("/opt/cursor/artifacts")
    art.mkdir(parents=True, exist_ok=True)

    # Always build blank (safe) obfuscated copy for the repo / GitHub.
    blank_out = root / "smmod_obfuscated.py"
    obfuscate_source(source, blank_out)
    blank_txt = blank_out.read_text(encoding="utf-8")
    if token and (token in blank_txt):
        raise SystemExit("FATAL: secrets leaked into blank obfuscated file")
    if secret and (secret in blank_txt):
        raise SystemExit("FATAL: secrets leaked into blank obfuscated file")

    # Optional: obfuscated WITH secrets for local Pi artifact (never commit).
    if token and secret:
        secret_src = inject_secrets(source, token, secret)
        for name in ("smmod_obfuscated.py", "DOWNLOAD_ME_smmod_obfuscated.py"):
            obfuscate_source(secret_src, art / name)
        secret_txt = (art / "smmod_obfuscated.py").read_text(encoding="utf-8")
        if f'TOKEN = "{token}"' in secret_txt:
            raise SystemExit("FATAL: clear TOKEN assignment still visible in obfuscated output")
        print("ok: blank repo obfuscated + secret artifact obfuscated")
    else:
        print("ok: blank repo obfuscated (set BEACON_TOKEN + BEACON_CLIENT_SECRET for secret artifact)")


if __name__ == "__main__":
    main()
