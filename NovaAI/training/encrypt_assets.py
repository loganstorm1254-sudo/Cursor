"""Package the trained model into the Android app and the Discord bot:

  - nova_config.json  -> app/src/main/assets/nova_config.txt (plain)
  - nova_model.bin    -> app/src/main/assets/nova_model.enc  (AES-256-GCM,
                         key = SHA-256(master API key))
  - nova_model.bin    -> embedded into ../../bot3.py as MODEL_B85
                         (float16 + zlib + BLAKE2b-keystream/HMAC scheme,
                         same master key — makes bot3.py a single file)
  - testvector.json   -> app/src/test/resources/testvector.txt
"""
import base64
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

master_key = open(os.path.join(HERE, "..", "MASTER_KEY.txt")).read().strip()
aes_key = hashlib.sha256(master_key.encode()).digest()

cfg = json.load(open(os.path.join(HERE, "nova_config.json")))
assets = os.path.join(APP, "src", "main", "assets")
os.makedirs(assets, exist_ok=True)
with open(os.path.join(assets, "nova_config.txt"), "w") as f:
    f.write(f"{cfg['n_layer']} {cfg['n_head']} {cfg['n_embd']} {cfg['block_size']}\n")
    f.write("\n".join(cfg["vocab"]) + "\n")

plain = open(os.path.join(HERE, "nova_model.bin"), "rb").read()
iv = os.urandom(12)
ct = AESGCM(aes_key).encrypt(iv, plain, None)
with open(os.path.join(assets, "nova_model.enc"), "wb") as f:
    f.write(iv + ct)
print(f"encrypted model (app, AES-GCM): {len(plain)} -> {len(iv) + len(ct)} bytes")

# --- bot3.py: embed the model into the single Python file --------------------
# payload = config + float16 weights, zlib-compressed, then the stdlib
# encryption scheme (BLAKE2b keystream + HMAC-SHA256), then base85 text.
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

k_enc = hashlib.sha256(b"nova-enc" + master_key.encode()).digest()
k_mac = hashlib.sha256(b"nova-mac" + master_key.encode()).digest()
nonce = os.urandom(16)
blocks = []
for i in range((len(compressed) + 63) // 64):
    blocks.append(hashlib.blake2b(nonce + i.to_bytes(8, "little"),
                                  key=k_enc, digest_size=64).digest())
ks = b"".join(blocks)[:len(compressed)]
ct2 = (int.from_bytes(compressed, "little") ^ int.from_bytes(ks, "little")
       ).to_bytes(len(compressed), "little")
tag = hmac_mod.new(k_mac, nonce + ct2, hashlib.sha256).digest()
b85 = base64.b85encode(nonce + ct2 + tag).decode()

bot_path = os.path.join(HERE, "..", "..", "bot3.py")
src = open(bot_path).read()
new_src, n_subs = re.subn(r'(?s)(MODEL_B85 = ")[^"]*(")',
                          lambda m: m.group(1) + b85 + m.group(2), src)
assert n_subs == 1, "MODEL_B85 marker not found in bot3.py"
open(bot_path, "w").write(new_src)
print(f"embedded model into bot3.py: {len(plain)} bytes fp32 -> "
      f"{len(b85)} chars base85 (fp16+zlib+encrypted)")

tv = json.load(open(os.path.join(HERE, "testvector.json")))
res = os.path.join(APP, "src", "test", "resources")
os.makedirs(res, exist_ok=True)
with open(os.path.join(res, "testvector.txt"), "w") as f:
    f.write(" ".join(map(str, tv["prompt_ids"])) + "\n")
    f.write(" ".join(map(str, tv["logits_first16"])) + "\n")
    f.write(str(tv["argmax"]) + "\n")
print("assets written")
