"""Package the trained model into the Android app:

  - nova_config.json  -> app/src/main/assets/nova_config.txt (plain)
  - nova_model.bin    -> app/src/main/assets/nova_model.enc  (AES-256-GCM,
                         key = SHA-256(master API key))
  - testvector.json   -> app/src/test/resources/testvector.txt
"""
import hashlib
import json
import os

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
print(f"encrypted model: {len(plain)} -> {len(iv) + len(ct)} bytes")

tv = json.load(open(os.path.join(HERE, "testvector.json")))
res = os.path.join(APP, "src", "test", "resources")
os.makedirs(res, exist_ok=True)
with open(os.path.join(res, "testvector.txt"), "w") as f:
    f.write(" ".join(map(str, tv["prompt_ids"])) + "\n")
    f.write(" ".join(map(str, tv["logits_first16"])) + "\n")
    f.write(str(tv["argmax"]) + "\n")
print("assets written")
