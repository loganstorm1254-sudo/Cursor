"""
Nova Discord bot — your own from-scratch AI on Discord. One file.

This is the SAME neural network that lives in the Android app
(releases/NovaAI.apk): a 3.46M-parameter GPT transformer trained from zero in
this repo (NovaAI/training/). The weights are AES-256 encrypted; the bot needs
the MASTER API KEY to decrypt and run them — no key, no AI. Unknown topics are
answered live from Wikipedia, exactly like the app.

Setup (Termux-friendly):
  pip install discord.py numpy cryptography
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
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Paste your Discord bot token here, or leave empty to use DISCORD_TOKEN env.
TOKEN = ""

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "NovaAI", "app", "src", "main", "assets")

MAX_NEW_TOKENS = 68
TEMPERATURE = 0.8
TOP_K = 40
WIKI_UA = "NovaAI-DiscordBot/1.1 (personal from-scratch AI companion)"


# ---------------------------------------------------------------- model ----

class NovaEngine:
    """NumPy port of the app's pure-Kotlin transformer inference engine.

    Weight layout matches NovaAI/training/train.py exactly:
    tok_emb, pos_emb, then per layer ln1 w/b, qkv W/b, proj W/b, ln2 w/b,
    fc W/b, fc2 W/b, then final layernorm w/b. Output head is tied to tok_emb.
    """

    def __init__(self, config_text: str, weight_bytes: bytes):
        lines = config_text.strip().splitlines()
        self.n_layer, self.n_head, self.n_embd, self.block = (
            int(x) for x in lines[0].split())
        self.vocab = [w.strip() for w in lines[1:]]
        self.stoi = {w: i for i, w in enumerate(self.vocab)}
        self.end_id = self.stoi["<end>"]
        self.unk_id = self.stoi["<unk>"]

        flat = np.frombuffer(weight_bytes, dtype="<f4")
        d, v, t = self.n_embd, len(self.vocab), self.block
        o = 0

        def take(*shape):
            nonlocal o
            n = int(np.prod(shape))
            arr = flat[o:o + n].reshape(shape)
            o += n
            return arr

        self.tok_emb = take(v, d)
        self.pos_emb = take(t, d)
        self.layers = []
        for _ in range(self.n_layer):
            self.layers.append({
                "ln1w": take(d), "ln1b": take(d),
                "qkvW": take(3 * d, d), "qkvB": take(3 * d),
                "projW": take(d, d), "projB": take(d),
                "ln2w": take(d), "ln2b": take(d),
                "fcW": take(4 * d, d), "fcB": take(4 * d),
                "fc2W": take(d, 4 * d), "fc2B": take(d),
            })
        self.lnfw = take(d)
        self.lnfb = take(d)
        assert o == flat.size, f"weight size mismatch: {o} != {flat.size}"

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

    # --- forward pass (KV cache) ---

    @staticmethod
    def _ln(x, w, b):
        m = x.mean()
        v = ((x - m) ** 2).mean()
        return (x - m) / np.sqrt(v + 1e-5) * w + b

    @staticmethod
    def _gelu(x):
        return 0.5 * x * (1.0 + np.tanh(0.7978845608028654 * (x + 0.044715 * x ** 3)))

    def _step(self, tok_id: int, pos: int, kcache, vcache) -> np.ndarray:
        d, h = self.n_embd, self.n_head
        hd = d // h
        x = self.tok_emb[tok_id] + self.pos_emb[pos]
        for li, L in enumerate(self.layers):
            hh = self._ln(x, L["ln1w"], L["ln1b"])
            qkv = L["qkvW"] @ hh + L["qkvB"]
            q, k, v = qkv[:d], qkv[d:2 * d], qkv[2 * d:]
            kcache[li][pos] = k
            vcache[li][pos] = v
            K = kcache[li][:pos + 1].reshape(pos + 1, h, hd)
            V = vcache[li][:pos + 1].reshape(pos + 1, h, hd)
            Q = q.reshape(h, hd)
            scores = np.einsum("thd,hd->th", K, Q) / math.sqrt(hd)
            scores -= scores.max(axis=0, keepdims=True)
            p = np.exp(scores)
            p /= p.sum(axis=0, keepdims=True)
            att = np.einsum("th,thd->hd", p, V).reshape(d)
            x = x + L["projW"] @ att + L["projB"]
            hh = self._ln(x, L["ln2w"], L["ln2b"])
            x = x + L["fc2W"] @ self._gelu(L["fcW"] @ hh + L["fcB"]) + L["fc2B"]
        hf = self._ln(x, self.lnfw, self.lnfb)
        return self.tok_emb @ hf

    def generate(self, history_ids: list[int], rng: np.random.Generator | None = None
                 ) -> list[int]:
        rng = rng or np.random.default_rng()
        d = self.n_embd
        kcache = [np.zeros((self.block, d), dtype=np.float32) for _ in self.layers]
        vcache = [np.zeros((self.block, d), dtype=np.float32) for _ in self.layers]
        room = self.block - MAX_NEW_TOKENS
        prompt = history_ids[-room:]
        logits = None
        for pos, tid in enumerate(prompt):
            logits = self._step(tid, pos, kcache, vcache)
        pos = len(prompt)
        out: list[int] = []
        for _ in range(MAX_NEW_TOKENS):
            scaled = logits / TEMPERATURE
            top = np.argpartition(scaled, -TOP_K)[-TOP_K:]
            probs = np.exp(scaled[top] - scaled[top].max())
            probs /= probs.sum()
            nxt = int(rng.choice(top, p=probs))
            tok = self.vocab[nxt]
            if tok in ("<end>", "<user>", "<bot>"):
                break
            out.append(nxt)
            if pos >= self.block:
                break
            logits = self._step(nxt, pos, kcache, vcache)
            pos += 1
        return out


def load_engine() -> NovaEngine:
    """Unlock Nova with the master API key the user inputs.

    The key you type is hashed to the AES-256 key that decrypts the model —
    exactly like the app's lock screen. Wrong key, no AI.
    """
    blob = open(os.path.join(ASSETS, "nova_model.enc"), "rb").read()
    config = open(os.path.join(ASSETS, "nova_config.txt")).read()

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
        aes = AESGCM(hashlib.sha256(key.encode()).digest())
        try:
            weights = aes.decrypt(blob[:12], blob[12:], None)
            print("✅ Master API key accepted — Nova unlocked.")
            return NovaEngine(config, weights)
        except Exception:
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
        raise SystemExit("Missing packages. Run:\n  pip install discord.py numpy cryptography")

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    histories: dict[tuple[int, int], list[int]] = defaultdict(list)
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
        history = histories[key]
        history.append(engine.stoi["<user>"])
        history.extend(engine.encode(text))
        history.append(engine.stoi["<bot>"])

        loop = asyncio.get_running_loop()
        subject = wiki_subject(text, engine.knows_word)
        if subject is not None:
            res = await loop.run_in_executor(None, wiki_lookup_sync, subject)
            if res is not None:
                title, extract = res
                history.extend(engine.encode("i looked that up on wikipedia for you ."))
                history.append(engine.end_id)
                del history[:-512]
                return f"📖 **{title}**\n{extract}\n*— from Wikipedia*"

        async with gen_lock:
            out_ids = await loop.run_in_executor(None, engine.generate, list(history))
        history.extend(out_ids)
        history.append(engine.end_id)
        del history[:-512]
        if not out_ids:
            return "Hmm, I am not sure what to say. Try asking me for a joke or a fact!"
        return engine.decode(out_ids)

    @bot.event
    async def on_ready():
        print(f"Nova is online as {bot.user} — {engine.n_embd}d/"
              f"{engine.n_layer}L transformer, {len(engine.vocab)} vocab")

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
        removed = [k for k in histories if k[0] == ctx.channel.id]
        for k in removed:
            del histories[k]
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
    tv_path = os.path.join(HERE, "NovaAI", "app", "src", "test",
                           "resources", "testvector.txt")
    if os.path.exists(tv_path):
        lines = open(tv_path).read().splitlines()
        prompt = [int(x) for x in lines[0].split()]
        ref = np.array([float(x) for x in lines[1].split()])
        ref_argmax = int(lines[2])
        kc = [np.zeros((engine.block, engine.n_embd), np.float32) for _ in engine.layers]
        vc = [np.zeros((engine.block, engine.n_embd), np.float32) for _ in engine.layers]
        logits = None
        for pos, tid in enumerate(prompt):
            logits = engine._step(tid, pos, kc, vc)
        diff = np.abs(logits[:16] - ref).max()
        assert diff < 0.02, f"logit parity failed: {diff}"
        assert int(logits.argmax()) == ref_argmax, "argmax parity failed"
        print(f"parity vs PyTorch: OK (max diff {diff:.5f})")

    rng = np.random.default_rng(42)
    for q in ["hello", "tell me a joke", "name 3 colors", "what is 3 plus 4",
              "what are the seasons", "who are you"]:
        ids = [engine.stoi["<user>"]] + engine.encode(q) + [engine.stoi["<bot>"]]
        print(f"USER: {q}\nNOVA: {engine.decode(engine.generate(ids, rng))}\n")

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
          f"{len(eng.vocab)} vocab, {eng.block} context")
    if "--selftest" in sys.argv:
        selftest(eng)
    else:
        run_bot(eng)
