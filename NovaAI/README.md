# Nova — your own AI, trained from scratch

Nova is a **real neural network trained from zero** (not an API wrapper, not a
fine-tune of someone else's model). The AI itself runs **on your phone** and
is locked with a **master API key**: the model weights inside the APK are
AES-256-GCM encrypted and the key is the only way to decrypt them. Without the
key the AI mathematically cannot run.

When you ask about something beyond her training ("what is a black hole?",
"who is albert einstein?", or "search …"), Nova **looks it up on Wikipedia**
and answers with the article summary. Everything she was trained on stays
on-device; the internet is only used for these lookups, and she still works
fully offline without it.

## Master API keys

Either of these unlocks Nova (app + Discord bot):

```
sk-nova-m00ny4xe
sk-nova-58d58cec6b35ee0abfea1452f7e7d11d6a4f16b8e936220f
```

(Also in [`MASTER_KEY.txt`](MASTER_KEY.txt).) The short one is easiest to type.
Enter it once on the app's lock screen; it is remembered on the phone until
you press the lock button.

## Install

1. Install [`releases/NovaAI.apk`](../releases/NovaAI.apk).
2. Open **Nova AI**, paste the master API key, tap **Unlock Nova**.
3. Chat! Try: `tell me a joke`, `tell me a fact`, `tell me a story`,
   `what is 7 plus 5`, `name 3 colors`, `what are the seasons`,
   `what is the opposite of hot`, `what is the capital of japan`,
   `who are you`, `i am sad` — or anything at all, like
   `what is a black hole?` (answered live from Wikipedia).

Nova is a small model with a small brain — she is great at chat, jokes, facts,
stories, lists, definitions, capitals and small math. For everything else she
checks Wikipedia, and she honestly tells you when she cannot help.

## The model

| | |
|---|---|
| Architecture | GPT-style decoder-only transformer (pre-norm, GELU, weight-tied head) |
| Size | 6 layers · 8 heads · 256 dim · 128 context · **~5.9M parameters** |
| Tokenizer | word-level, 4,500-token vocabulary (capped) |
| Training data | Synthetic drills + Hugging Face: TinyStories, Dolly-15k, Alpaca, SciQ, BoolQ, WikiQA (~230k conversations, ~7.7M tokens). Math uses a deterministic calculator; unknown topics fall back to Wikipedia. |
| Training | 6,000 steps AdamW, batch 32×128, cosine LR schedule — from random init |
| Inference | pure Kotlin (`NovaEngine.kt`), KV-cached, no libraries, runs on any phone |
| Wikipedia | unknown "who is / what is / search …" questions are answered from the live Wikipedia REST API (`WikiClient.kt` / `WikiRouter.kt`) |

## How the API key lock works

- Build time: `sha256(master_key)` → AES-256 key → the raw weights
  (`nova_model.bin`, 7.9 MB) are encrypted with AES-GCM into
  `app/src/main/assets/nova_model.enc`.
- Run time: the key you type is hashed the same way and used to decrypt the
  weights in memory. GCM authentication means a wrong key is always detected
  and rejected — there is no way to load the network without the key.

## Reproduce / retrain

```bash
cd NovaAI/training
pip install torch datasets --index-url https://download.pytorch.org/whl/cpu
# (datasets from PyPI: pip install datasets)
python3 fetch_hf.py          # pull TinyStories, Dolly, Alpaca, SciQ, BoolQ, WikiQA
python3 make_corpus.py       # synthetic drills + HF merge (vocab capped at 4500)
MAX_STEPS=9000 python3 train.py
python3 encrypt_assets.py    # multi-key encrypt into the app + bot3 model file
cd .. && ./gradlew assembleDebug
```

The model is encrypted under a random data key; each master API key in
`MASTER_KEY.txt` only wraps that key, so any listed key unlocks the same brain.

## Nova on Discord

The same model also runs as a Discord bot: [`../bot3.py`](../bot3.py) — one
small file that auto-downloads the encrypted network ([`nova_model.sc`](nova_model.sc),
~6 MB) from this repo on first run and caches it locally. It unlocks with the
master API key you input and has the same Wikipedia fallback. It needs
**only `pip install discord.py`** — inference is pure Python, no numpy/torch.
`python bot3.py --selftest` verifies it without Discord.

## Tests

`./gradlew test` runs the checks against the real encrypted asset:

- a wrong master API key is rejected,
- the Kotlin engine reproduces the PyTorch reference logits (parity test),
- the model generates non-empty replies for a set of prompts,
- the Wikipedia router sends unknown questions to Wikipedia and keeps known
  ones local (plus JSON parsing tests).

`./gradlew test -DrunLiveTests=true` additionally hits the real Wikipedia API.
