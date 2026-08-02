"""
Nova Discord bot — your own from-scratch AI on Discord. One file.
NO heavy downloads: only discord.py is needed (no numpy, no torch).

This is the SAME neural network that lives in the Android app
(releases/NovaAI.apk): a 3.46M-parameter GPT transformer trained from zero in
this repo (NovaAI/training/). The weights are encrypted; the bot needs the
MASTER API KEY to decrypt and run them — no key, no AI. Unknown topics are
answered live from Wikipedia, exactly like the app.

Setup (Termux-friendly):
  pip install discord.py
  python bot3.py
  → it asks for your master API key (sk-nova-…), just like the app's
    lock screen. Wrong key = Nova stays locked.

For servers / automation you can skip the prompt with:
  export NOVA_MASTER_KEY="sk-nova-..."

Discord setup:
  1. https://discord.com/developers/applications → New Application → Bot
  2. Copy the bot token into TOKEN below (or export DISCORD_TOKEN=...)
  3. Enable MESSAGE CONTENT INTENT under Bot → Privileged Gateway Intents
  4. Invite with scopes bot + applications.commands (Send Messages)

Use:
  @Nova <message>          chat by mention
  !nova <message>          chat by command
  DM the bot               chat directly, no prefix needed
  !clear                   forget the conversation in this channel
  !novahelp                show help

Self-test without Discord:
  python bot3.py --selftest
"""

from __future__ import annotations

import asyncio
import getpass
import hashlib
import hmac
import json
import math
import os
import random
import re
import sys
import urllib.parse
import urllib.request
from array import array
from heapq import nlargest
from operator import mul

# Paste your Discord bot token here, or leave empty to use DISCORD_TOKEN env.
TOKEN = ""

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_FILE = os.path.join(HERE, "NovaAI", "nova_model.sc")
CONFIG_FILE = os.path.join(HERE, "NovaAI", "app", "src", "main", "assets",
                           "nova_config.txt")

MAX_NEW_TOKENS = 60
TEMPERATURE = 0.8
TOP_K = 40
WIKI_UA = "NovaAI-DiscordBot/1.2 (personal from-scratch AI companion)"


# ---------------------------------------------------------------- model ----

class NovaEngine:
    """Pure standard-library port of the app's transformer inference engine.

    Weight layout matches NovaAI/training/train.py exactly:
    tok_emb, pos_emb, then per layer ln1 w/b, qkv W/b, proj W/b, ln2 w/b,
    fc W/b, fc2 W/b, then final layernorm w/b. Output head is tied to tok_emb.
    Matrices are stored as lists of array('f') rows so a 3.46M-param model
    stays ~14 MB in RAM, and dot products run in C via sum(map(mul, ...)).
    """

    def __init__(self, config_text: str, weight_bytes: bytes):
        lines = config_text.strip().splitlines()
        self.n_layer, self.n_head, self.n_embd, self.block = (
            int(x) for x in lines[0].split())
        self.vocab = [w.strip() for w in lines[1:]]
        self.stoi = {w: i for i, w in enumerate(self.vocab)}
        self.end_id = self.stoi["<end>"]
        self.unk_id = self.stoi["<unk>"]

        flat = array("f")
        flat.frombytes(weight_bytes)
        if sys.byteorder == "big":
            flat.byteswap()
        d, v, t = self.n_embd, len(self.vocab), self.block
        pos = 0

        def rows(n, width):
            nonlocal pos
            out = [flat[pos + i * width:pos + (i + 1) * width] for i in range(n)]
            pos += n * width
            return out

        def vec(n):
            nonlocal pos
            out = flat[pos:pos + n]
            pos += n
            return out

        self.tok_emb = rows(v, d)
        self.pos_emb = rows(t, d)
        self.layers = []
        for _ in range(self.n_layer):
            self.layers.append({
                "ln1w": vec(d), "ln1b": vec(d),
                "qkvW": rows(3 * d, d), "qkvB": vec(3 * d),
                "projW": rows(d, d), "projB": vec(d),
                "ln2w": vec(d), "ln2b": vec(d),
                "fcW": rows(4 * d, d), "fcB": vec(4 * d),
                "fc2W": rows(d, 4 * d), "fc2B": vec(d),
            })
        self.lnfw = vec(d)
        self.lnfb = vec(d)
        assert pos == len(flat), f"weight size mismatch: {pos} != {len(flat)}"

    # --- tokenizer ---

    def encode(self, text: str) -> list[int]:
        cleaned = re.sub(r"([.,!?;:'+])", r" \1 ", text.lower())
        return [self.stoi.get(w, self.unk_id) for w in cleaned.split()]

    def knows_word(self, word: str) -> bool:
        return word in self.stoi

    def decode(self, ids: list[int]) -> str:
        parts: list[str] = []
        for i in ids:
            tok = self.vocab[i]
            if tok in ("<end>", "<user>", "<bot>"):
                continue
            if parts and ((len(tok) == 1 and tok in ".,!?;:'") or parts[-1].endswith("'")):
                parts[-1] += tok
            else:
                parts.append(tok)
        s = " ".join(parts)
        s = re.sub(r"\bi\b", "I", s)
        out, cap = [], True
        for c in s:
            out.append(c.upper() if cap and c.isalpha() else c)
            if c.isalpha():
                cap = False
            if c in ".!?":
                cap = True
        return "".join(out)

    # --- forward pass (one token, KV cached) ---

    @staticmethod
    def _ln(x, w, b):
        n = len(x)
        m = sum(x) / n
        var = sum((xi - m) ** 2 for xi in x) / n
        inv = 1.0 / math.sqrt(var + 1e-5)
        return [(xi - m) * inv * wi + bi for xi, wi, bi in zip(x, w, b)]

    def step(self, tok_id: int, kcache: list[list], vcache: list[list]) -> list[float]:
        d, nh = self.n_embd, self.n_head
        hd = d // nh
        scale = 1.0 / math.sqrt(hd)
        pos = len(kcache[0])
        x = list(map(sum, zip(self.tok_emb[tok_id], self.pos_emb[pos])))

        for li, L in enumerate(self.layers):
            h = self._ln(x, L["ln1w"], L["ln1b"])
            qkv = [sum(map(mul, row, h)) + bb
                   for row, bb in zip(L["qkvW"], L["qkvB"])]
            q, k, v = qkv[:d], qkv[d:2 * d], qkv[2 * d:]
            kcache[li].append(k)
            vcache[li].append(v)
            klist, vlist = kcache[li], vcache[li]

            att = [0.0] * d
            for hi in range(nh):
                base = hi * hd
                end = base + hd
                qh = q[base:end]
                scores = [sum(map(mul, kv[base:end], qh)) * scale for kv in klist]
                mx = max(scores)
                exps = [math.exp(s - mx) for s in scores]
                total = sum(exps)
                for e, vv in zip(exps, vlist):
                    p = e / total
                    seg = vv[base:end]
                    for j in range(hd):
                        att[base + j] += p * seg[j]

            for i, (row, bb) in enumerate(zip(L["projW"], L["projB"])):
                x[i] += sum(map(mul, row, att)) + bb

            h = self._ln(x, L["ln2w"], L["ln2b"])
            f = [sum(map(mul, row, h)) + bb
                 for row, bb in zip(L["fcW"], L["fcB"])]
            f = [0.5 * fi * (1.0 + math.tanh(0.7978845608028654 *
                                             (fi + 0.044715 * fi ** 3)))
                 for fi in f]
            for i, (row, bb) in enumerate(zip(L["fc2W"], L["fc2B"])):
                x[i] += sum(map(mul, row, f)) + bb

        hf = self._ln(x, self.lnfw, self.lnfb)
        return [sum(map(mul, row, hf)) for row in self.tok_emb]

    def sample(self, logits: list[float], rng: random.Random) -> int:
        top = nlargest(TOP_K, range(len(logits)), key=logits.__getitem__)
        mx = logits[top[0]]
        weights = [math.exp((logits[i] - mx) / TEMPERATURE) for i in top]
        return rng.choices(top, weights=weights)[0]


class ChatSession:
    """One conversation. Keeps the KV cache alive between messages so each
    reply only has to process the NEW tokens — crucial for pure-Python speed."""

    def __init__(self, engine: NovaEngine):
        self.e = engine
        self.reset()

    def reset(self):
        self.kcache = [[] for _ in range(self.e.n_layer)]
        self.vcache = [[] for _ in range(self.e.n_layer)]
        self.ids: list[int] = []

    @property
    def pos(self) -> int:
        return len(self.kcache[0])

    def _feed(self, ids: list[int]) -> list[float] | None:
        logits = None
        for tid in ids:
            logits = self.e.step(tid, self.kcache, self.vcache)
            self.ids.append(tid)
        return logits

    def reply(self, text: str, rng: random.Random | None = None) -> list[int]:
        rng = rng or random.Random()
        e = self.e
        new_ids = [e.stoi["<user>"]] + e.encode(text) + [e.stoi["<bot>"]]
        # if the context window would overflow, restart from recent history
        if self.pos + len(new_ids) + MAX_NEW_TOKENS >= e.block:
            keep = e.block - MAX_NEW_TOKENS - len(new_ids) - 1
            tail = self.ids[-keep:] if keep > 0 else []
            self.reset()
            if tail:
                self._feed(tail)
        logits = self._feed(new_ids)
        out: list[int] = []
        for _ in range(MAX_NEW_TOKENS):
            nxt = e.sample(logits, rng)
            tok = e.vocab[nxt]
            if tok in ("<end>", "<user>", "<bot>"):
                break
            out.append(nxt)
            if self.pos >= e.block - 1:
                break
            logits = self._feed([nxt])
        self._feed([e.end_id]) if self.pos < e.block - 1 else None
        return out

    def note(self, text: str):
        """Record an in-vocabulary bot reply (e.g. after a Wikipedia answer)."""
        e = self.e
        ids = e.encode(text) + [e.end_id]
        if self.pos + len(ids) < e.block - MAX_NEW_TOKENS:
            self._feed(ids)


# ------------------------------------------------------------ decryption ----

def decrypt_model(master_key: str, blob: bytes) -> bytes | None:
    """Stdlib scheme: BLAKE2b-keystream XOR + HMAC-SHA256 authentication.
    Returns None when the key is wrong (HMAC mismatch)."""
    k_enc = hashlib.sha256(b"nova-enc" + master_key.encode()).digest()
    k_mac = hashlib.sha256(b"nova-mac" + master_key.encode()).digest()
    nonce, ct, tag = blob[:16], blob[16:-32], blob[-32:]
    want = hmac.new(k_mac, nonce + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(want, tag):
        return None
    blocks = [hashlib.blake2b(nonce + i.to_bytes(8, "little"),
                              key=k_enc, digest_size=64).digest()
              for i in range((len(ct) + 63) // 64)]
    ks = b"".join(blocks)[:len(ct)]
    return (int.from_bytes(ct, "little") ^ int.from_bytes(ks, "little")
            ).to_bytes(len(ct), "little")


def load_engine() -> NovaEngine:
    """Unlock Nova with the master API key the user inputs.

    The key you type derives both the decryption keystream and the
    authentication key — exactly like the app's lock screen. Wrong key, no AI.
    """
    if not os.path.exists(MODEL_FILE):
        raise SystemExit(
            f"Model file not found: {MODEL_FILE}\n"
            "Pull the repo again, or regenerate it with "
            "NovaAI/training/encrypt_assets.py")
    blob = open(MODEL_FILE, "rb").read()
    config = open(CONFIG_FILE).read()

    from_env = os.getenv("NOVA_MASTER_KEY", "").strip()
    attempts = 0
    while True:
        if from_env:
            key = from_env
        else:
            try:
                key = getpass.getpass(
                    "🔑 Enter your master API key (sk-nova-…, input is hidden): ").strip()
            except (EOFError, KeyboardInterrupt):
                raise SystemExit("\nNo key entered — Nova stays locked.")
            if not key:
                continue
        weights = decrypt_model(key, blob)
        if weights is not None:
            print("✅ Master API key accepted — Nova unlocked.")
            return NovaEngine(config, weights)
        if from_env:
            raise SystemExit(
                "Wrong master API key in NOVA_MASTER_KEY — "
                "the model cannot be decrypted.")
        attempts += 1
        print("❌ Wrong master API key — the model cannot be decrypted.")
        if attempts >= 3:
            raise SystemExit("Too many wrong attempts — Nova stays locked.")


# ------------------------------------------------------------- wikipedia ----

WIKI_EXPLICIT = re.compile(
    r"^(?:search|wiki|wikipedia|look ?up|google)(?: for| up| about)?\s+(.+)$")
WIKI_QUESTION = re.compile(
    r"^(?:who is|who was|who are|who were|what is|what are|what was|whats|"
    r"tell me about|what do you know about|define|explain)\s+(.+)$")

# Words marking multi-word subjects Nova handles locally
# (trained question shapes and multi-word definitions).
LOCAL_HINTS = {
    "capital", "opposite", "plus", "minus", "times", "favorite", "favourite",
    "weather", "time", "news", "name", "your", "you", "neural", "machine",
    "artificial", "api", "nova", "seasons", "days", "months", "planets",
    "colors", "colours", "rainbow", "week", "year"}


def _clean_subject(s: str) -> str:
    s = s.strip().rstrip("?!. ")
    for art in ("a ", "an ", "the "):
        if s.startswith(art):
            s = s[len(art):]
            break
    return s.strip()


def wiki_subject(message: str, knows_word) -> str | None:
    t = message.strip().lower().rstrip("?!. ")
    if not t:
        return None
    m = WIKI_EXPLICIT.match(t)
    if m:
        return _clean_subject(m.group(1))
    m = WIKI_QUESTION.match(t)
    if not m:
        return None
    subject = _clean_subject(m.group(1))
    words = [w for w in re.split(r"[^a-z0-9]+", subject) if w]
    if not words:
        return None
    has_unknown = any(not knows_word(w) for w in words)
    novel_multi_word = (len(words) >= 2
                        and not any(w in LOCAL_HINTS for w in words)
                        and not any(w.isdigit() for w in words))
    return subject if has_unknown or novel_multi_word else None


def wiki_lookup_sync(query: str) -> tuple[str, str] | None:
    """Returns (title, extract) or None. Blocking — call in an executor."""
    def get(url):
        req = urllib.request.Request(url, headers={
            "User-Agent": WIKI_UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode())
    try:
        q = urllib.parse.quote(query)
        search = get(f"https://en.wikipedia.org/w/rest.php/v1/search/title?q={q}&limit=1")
        pages = search.get("pages") or []
        if not pages:
            return None
        key = urllib.parse.quote(pages[0]["key"])
        summary = get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{key}")
        extract = (summary.get("extract") or "").strip()
        if not extract:
            return None
        if len(extract) > 700:
            cut = extract.rfind(". ", 0, 700)
            extract = extract[:cut + 1] if cut > 200 else extract[:700] + "…"
        return summary.get("title") or pages[0]["key"].replace("_", " "), extract
    except Exception:
        return None


# ---------------------------------------------------------------- discord ---

def run_bot(engine: NovaEngine) -> None:
    try:
        import discord
        from discord.ext import commands
    except ImportError:
        raise SystemExit("Missing package. Run:\n  pip install discord.py")

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    sessions: dict[tuple[int, int], ChatSession] = {}
    gen_lock = asyncio.Lock()

    HELP = (
        "**Nova — your own from-scratch AI** (the same brain as the Android app)\n"
        "• `@Nova <message>` or `!nova <message>` — chat\n"
        "• DM me — no prefix needed\n"
        "• `!clear` — forget this channel's conversation\n"
        "• Ask about anything (`what is a black hole?`) and I check Wikipedia\n"
        "• Try: `tell me a joke`, `name 3 colors`, `what is 7 plus 5`, `tell me a story`"
    )

    async def reply_to(message, text: str) -> str:
        text = text.strip()
        if not text:
            return HELP
        key = (message.channel.id, message.author.id)
        session = sessions.setdefault(key, ChatSession(engine))
        loop = asyncio.get_running_loop()

        subject = wiki_subject(text, engine.knows_word)
        if subject is not None:
            res = await loop.run_in_executor(None, wiki_lookup_sync, subject)
            if res is not None:
                title, extract = res
                async with gen_lock:
                    await loop.run_in_executor(
                        None, session.note,
                        "i looked that up on wikipedia for you .")
                return f"📖 **{title}**\n{extract}\n*— from Wikipedia*"

        async with gen_lock:
            out_ids = await loop.run_in_executor(None, session.reply, text)
        if not out_ids:
            return "Hmm, I am not sure what to say. Try asking me for a joke or a fact!"
        return engine.decode(out_ids)

    @bot.event
    async def on_ready():
        print(f"Nova is online as {bot.user} — {engine.n_embd}d/"
              f"{engine.n_layer}L transformer, {len(engine.vocab)} vocab, "
              "pure-Python inference")

    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
        content = message.content.strip()
        lowered = content.lower()
        if lowered.startswith(("!nova ", "!clear", "!novahelp")) or lowered == "!nova":
            await bot.process_commands(message)
            return
        is_dm = message.guild is None
        mentioned = bot.user is not None and bot.user.mentioned_in(message) \
            and not message.mention_everyone
        if not (is_dm or mentioned):
            return
        if mentioned:
            content = re.sub(rf"<@!?{bot.user.id}>", "", content).strip()
        async with message.channel.typing():
            answer = await reply_to(message, content)
        await message.reply(answer, mention_author=False)

    @bot.command(name="nova")
    async def nova_cmd(ctx, *, text: str = ""):
        async with ctx.channel.typing():
            answer = await reply_to(ctx.message, text)
        await ctx.reply(answer, mention_author=False)

    @bot.command(name="clear")
    async def clear_cmd(ctx):
        for k in [k for k in sessions if k[0] == ctx.channel.id]:
            del sessions[k]
        await ctx.reply("🧠 Fresh start! I forgot our conversation here.",
                        mention_author=False)

    @bot.command(name="novahelp")
    async def help_cmd(ctx):
        await ctx.reply(HELP, mention_author=False)

    token = (TOKEN or os.getenv("DISCORD_TOKEN", "")).strip()
    if not token:
        raise SystemExit(
            "No Discord token.\n"
            "  1. Create a bot at https://discord.com/developers/applications\n"
            "  2. Paste it into TOKEN = \"...\" near the top of bot3.py\n"
            "  Or: export DISCORD_TOKEN=\"your-token\"")
    bot.run(token)


# --------------------------------------------------------------- selftest ---

def selftest(engine: NovaEngine) -> None:
    import time

    tv_path = os.path.join(HERE, "NovaAI", "app", "src", "test",
                           "resources", "testvector.txt")
    if os.path.exists(tv_path):
        lines = open(tv_path).read().splitlines()
        prompt = [int(x) for x in lines[0].split()]
        ref = [float(x) for x in lines[1].split()]
        ref_argmax = int(lines[2])
        kc = [[] for _ in range(engine.n_layer)]
        vc = [[] for _ in range(engine.n_layer)]
        logits = None
        for tid in prompt:
            logits = engine.step(tid, kc, vc)
        diff = max(abs(a - b) for a, b in zip(logits[:16], ref))
        assert diff < 0.02, f"logit parity failed: {diff}"
        assert logits.index(max(logits)) == ref_argmax, "argmax parity failed"
        print(f"parity vs PyTorch: OK (max diff {diff:.5f})")

    rng = random.Random(42)
    t0 = time.time()
    n_tokens = 0
    for q in ["hello", "tell me a joke", "name 3 colors", "what is 3 plus 4",
              "what are the seasons", "who are you"]:
        session = ChatSession(engine)
        out = session.reply(q, rng)
        n_tokens += len(out) + len(engine.encode(q)) + 3
        print(f"USER: {q}\nNOVA: {engine.decode(out)}\n")
    dt = time.time() - t0
    print(f"speed: {n_tokens / dt:.1f} tokens/s pure Python")

    # multi-turn session reuses its KV cache — second turn must be faster
    session = ChatSession(engine)
    session.reply("hello", rng)
    t0 = time.time()
    out = session.reply("tell me a joke", rng)
    dt = time.time() - t0
    print(f"cached follow-up: {engine.decode(out)!r} in {dt:.1f}s")

    assert wiki_subject("what is a black hole", engine.knows_word) == "black hole"
    assert wiki_subject("tell me a joke", engine.knows_word) is None
    res = wiki_lookup_sync("black hole")
    if res:
        print(f"wikipedia: OK — {res[0]}: {res[1][:100]}…")
    else:
        print("wikipedia: unreachable (offline?) — bot will fall back to the model")
    print("selftest passed")


if __name__ == "__main__":
    eng = load_engine()
    print(f"Nova loaded: {eng.n_layer} layers, {eng.n_embd} dim, "
          f"{len(eng.vocab)} vocab, {eng.block} context — no numpy needed")
    if "--selftest" in sys.argv:
        selftest(eng)
    else:
        run_bot(eng)
