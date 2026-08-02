"""Package the trained model into the Android app and the Discord bot.

Supports multiple master API keys (one per line in MASTER_KEY.txt). The model
is encrypted once under a random data key (DEK); each API key only wraps that
DEK, so any listed key unlocks the same brain.

  - nova_config.json  -> app/src/main/assets/nova_config.txt (plain)
  - nova_model.bin    -> app/src/main/assets/nova_model.enc
      format NOVAK: magic|n_keys|wraps…|iv|AES-GCM(DEK, weights)
  - nova_model.bin    -> ../nova_model.sc for bot3.py
      format NOVA2: magic|n_keys|wraps…|nonce|xor-ct|hmac  (DEK-based)
  - testvector.json   -> app/src/test/resources/testvector.txt
"""
import hashlib
import hmac as hmac_mod
import json
import os
import re
import struct
import zlib

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "..", "app")

keys = [ln.strip() for ln in open(os.path.join(HERE, "..", "MASTER_KEY.txt"))
        if ln.strip() and not ln.strip().startswith("#")]
if not keys:
    raise SystemExit("MASTER_KEY.txt has no keys")
print(f"master API keys: {len(keys)}")
for k in keys:
    print(f"  - {k}")

DEK = os.urandom(32)  # random data-encryption key


def wrap_dek(api_key: str, dek: bytes) -> bytes:
    """80-byte wrap: nonce(16) || xor-ct(32) || hmac(32). Stdlib-only."""
    k_enc = hashlib.sha256(b"nova-wrap-enc" + api_key.encode()).digest()
    k_mac = hashlib.sha256(b"nova-wrap-mac" + api_key.encode()).digest()
    nonce = os.urandom(16)
    ks = hashlib.sha256(k_enc + nonce + b"\x00").digest()
    ct = bytes(a ^ b for a, b in zip(dek, ks))
    tag = hmac_mod.new(k_mac, nonce + ct, hashlib.sha256).digest()
    return nonce + ct + tag


wraps = b"".join(wrap_dek(k, DEK) for k in keys)

cfg = json.load(open(os.path.join(HERE, "nova_config.json")))
assets = os.path.join(APP, "src", "main", "assets")
os.makedirs(assets, exist_ok=True)
with open(os.path.join(assets, "nova_config.txt"), "w") as f:
    f.write(f"{cfg['n_layer']} {cfg['n_head']} {cfg['n_embd']} {cfg['block_size']}\n")
    f.write("\n".join(cfg["vocab"]) + "\n")

plain = open(os.path.join(HERE, "nova_model.bin"), "rb").read()

# --- Android: NOVAK envelope + AES-GCM(DEK) --------------------------------
iv = os.urandom(12)
ct = AESGCM(DEK).encrypt(iv, plain, None)
enc = b"NOVAK" + bytes([len(keys)]) + wraps + iv + ct
with open(os.path.join(assets, "nova_model.enc"), "wb") as f:
    f.write(enc)
print(f"encrypted model (app, NOVAK/{len(keys)} keys): "
      f"{len(plain)} -> {len(enc)} bytes")

# --- bot3.py: NOVA2 envelope + blake2b keystream under DEK -----------------
config_txt = open(os.path.join(assets, "nova_config.txt"), "rb").read()

n_floats = len(plain) // 4
f16 = bytearray()
CH = 65536
for off in range(0, n_floats, CH):
    cnt = min(CH, n_floats - off)
    vals = struct.unpack_from(f"<{cnt}f", plain, off * 4)
    f16 += struct.pack(f"<{cnt}e", *vals)

payload = len(config_txt).to_bytes(4, "little") + config_txt + bytes(f16)
compressed = zlib.compress(payload, 9)

k_enc = hashlib.sha256(b"nova-enc" + DEK).digest()
k_mac = hashlib.sha256(b"nova-mac" + DEK).digest()
nonce = os.urandom(16)
blocks = []
for i in range((len(compressed) + 63) // 64):
    blocks.append(hashlib.blake2b(nonce + i.to_bytes(8, "little"),
                                  key=k_enc, digest_size=64).digest())
ks = b"".join(blocks)[:len(compressed)]
ct2 = (int.from_bytes(compressed, "little") ^ int.from_bytes(ks, "little")
       ).to_bytes(len(compressed), "little")
tag = hmac_mod.new(k_mac, nonce + ct2, hashlib.sha256).digest()
sc_body = wraps + nonce + ct2 + tag
sc = b"NOVA2" + bytes([len(keys)]) + sc_body
sc_path = os.path.join(HERE, "..", "nova_model.sc")
with open(sc_path, "wb") as f:
    f.write(sc)
print(f"bot model NovaAI/nova_model.sc: {len(plain)} bytes fp32 -> "
      f"{len(sc)} bytes (NOVA2/{len(keys)} keys, fp16+zlib)")

bot_path = os.path.join(HERE, "..", "..", "bot3.py")
src = open(bot_path).read()
src2 = re.sub(r"^MODEL_SIZE = \d+$", f"MODEL_SIZE = {len(sc)}", src,
              count=1, flags=re.M)
src2 = re.sub(r'^MODEL_MAGIC = b"[^"]*"$', 'MODEL_MAGIC = b"NOVA2"', src2,
              count=1, flags=re.M)
if src2 != src:
    open(bot_path, "w").write(src2)
    print(f"bot3.py MODEL_SIZE={len(sc)}, MODEL_MAGIC=NOVA2")

tv = json.load(open(os.path.join(HERE, "testvector.json")))
res = os.path.join(APP, "src", "test", "resources")
os.makedirs(res, exist_ok=True)
with open(os.path.join(res, "testvector.txt"), "w") as f:
    f.write(" ".join(map(str, tv["prompt_ids"])) + "\n")
    f.write(" ".join(map(str, tv["logits_first16"])) + "\n")
    f.write(str(tv["argmax"]) + "\n")
print("assets written")
