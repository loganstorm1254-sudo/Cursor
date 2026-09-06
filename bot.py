"""
Discord AI bot — one file, Termux-friendly, no AI API keys.

Termux setup:
  pkg update && pkg install python
  pip install discord.py g4f
  python bot.py

Discord setup:
  1. https://discord.com/developers/applications → New Application → Bot
  2. Copy the bot token into TOKEN below
  3. Enable MESSAGE CONTENT INTENT under Bot → Privileged Gateway Intents
  4. Invite the bot (OAuth2 → URL Generator → scopes: bot + applications.commands)

User commands:
  !ai / /ai <prompt>          Ask the AI (attach an image to analyze it)
  !see / /see [question]      Image recognition (attach or reply to an image)
  !imagine / /imagine <prompt> Generate an image
  !persona <name>             default | funny | serious | coder
  !clear                      Clear your own chat memory
  !help                       Show help
  @Bot <prompt>               Chat by mention (reply/image context supported)

Owner-only (user id 1257060226029584459):
  !off / !shutdown            Pause AI replies (bot stays online)
  !on / !start                Resume AI replies
  !status                     Show bot status
  !aichannel on|off           Enable/disable AI in this channel
  !resetmemory [user]         Reset memory for a user, or everyone if no user
  !premium add|remove|list    Grant / revoke / list premium (also !prem)

Premium (free users vs premium):
  !premium / !prem            Check your premium status
  Perks: shorter cooldowns, longer memory, premium personas, larger images
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import time
import urllib.parse
import uuid
from collections import defaultdict, deque

try:
    import aiohttp
    import discord
    from discord import app_commands
    from discord.ext import commands
    from g4f.client import AsyncClient
except ImportError:
    raise SystemExit(
        "Missing packages. In Termux run:\n"
        "  pip install discord.py g4f\n"
        "Then run this file again."
    )

# Paste your Discord bot token here (from the Developer Portal).
# Leave empty to use the DISCORD_TOKEN environment variable instead.
TOKEN = ""

OWNER_ID = 1257060226029584459
# Optional seed IDs (ints). Merged into premium_users.json on startup.
# Prefer !premium add <id> so grants persist without editing this file.
PREMIUM_SEED_IDS: list[int] = []
MEMORY_TURNS = 8
PREMIUM_MEMORY_TURNS = 16
COOLDOWN_SECONDS = 4.0
PREMIUM_COOLDOWN_SECONDS = 1.0
IMAGE_COOLDOWN_SECONDS = 8.0
PREMIUM_IMAGE_COOLDOWN_SECONDS = 3.0
MAX_PROMPT_CHARS = 2000
PREMIUM_MAX_PROMPT_CHARS = 4000
MAX_REPLY_CHARS = 1900
AI_RETRIES = 2
MAX_IMAGE_BYTES = 8 * 1024 * 1024
PREMIUM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "premium_users.json")
MENTION_RE = re.compile(r"<@!?(\d+)>")
DIGIT_ID_RE = re.compile(r"^\d{5,25}$")

# Free Florence-2 Gradio space for real image recognition (no API key)
FLORENCE_HOST = "https://gokaygokay-florence-2.hf.space"
# Free Pollinations image generation (no API key)
IMAGE_GEN_URL = (
    "https://image.pollinations.ai/prompt/{prompt}"
    "?width={width}&height={height}&nologo=true&model=flux&enhance=true"
)

PERSONAS = {
    "default": (
        "You are a helpful Discord bot assistant. "
        "Keep replies concise and friendly. Use Discord markdown when useful."
    ),
    "funny": (
        "You are a witty Discord bot. Be funny and light, but still helpful. "
        "Keep replies fairly short. Use Discord markdown when useful."
    ),
    "serious": (
        "You are a precise, professional Discord assistant. "
        "Be direct, clear, and concise. Avoid jokes. Use Discord markdown when useful."
    ),
    "coder": (
        "You are a coding assistant in Discord. Prefer clear explanations and "
        "fenced code blocks. Keep answers practical and concise."
    ),
}

# Premium-only personas
PREMIUM_PERSONAS = {
    "poet": (
        "You are a lyrical Discord assistant. Answer helpfully, but with vivid "
        "imagery and a poetic touch. Keep it readable in chat — not a full poem every time."
    ),
    "roast": (
        "You are a playful roast comic in Discord. Tease lightly and answer the question. "
        "Stay fun, never cruel or hateful. Keep replies short."
    ),
}
ALL_PERSONAS = {**PERSONAS, **PREMIUM_PERSONAS}

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
ai = AsyncClient()
http: aiohttp.ClientSession | None = None

# Runtime state
ai_enabled = True
disabled_channels: set[int] = set()
memory: dict[int, deque] = {}
personas: dict[int, str] = defaultdict(lambda: "default")
cooldowns: dict[int, float] = {}
image_cooldowns: dict[int, float] = {}
premium_users: set[int] = set()


def is_owner(user_id: int) -> bool:
    return int(user_id) == OWNER_ID


def owner_only():
    async def predicate(ctx: commands.Context) -> bool:
        if not is_owner(ctx.author.id):
            await ctx.send("Owner only.")
            return False
        return True

    return commands.check(predicate)


def parse_user_id(raw: str | int | None) -> int | None:
    """Accept raw snowflake, <@id>, or <@!id>. Always return int or None."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw if raw > 0 else None
    text = str(raw).strip()
    if not text:
        return None
    mention = MENTION_RE.fullmatch(text) or MENTION_RE.search(text)
    if mention:
        text = mention.group(1)
    text = text.strip().strip("\"'`")
    if not DIGIT_ID_RE.fullmatch(text):
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def load_premium_users() -> set[int]:
    """Load premium IDs from disk. Coerce every entry to int (fixes str/int bug)."""
    loaded: set[int] = set()
    for seed in PREMIUM_SEED_IDS:
        uid = parse_user_id(seed)
        if uid is not None:
            loaded.add(uid)
    if os.path.isfile(PREMIUM_FILE):
        try:
            with open(PREMIUM_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Warning: could not read {PREMIUM_FILE}: {exc}")
            data = []
        if isinstance(data, dict):
            data = data.get("users", data.get("premium_users", []))
        if not isinstance(data, list):
            data = []
        for item in data:
            uid = parse_user_id(item)
            if uid is not None:
                loaded.add(uid)
    return loaded


def save_premium_users() -> None:
    # Persist as ints in a plain JSON list — reload always coerces to int.
    payload = sorted(int(uid) for uid in premium_users)
    tmp = PREMIUM_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, PREMIUM_FILE)


def is_premium(user_id: int) -> bool:
    uid = int(user_id)
    return is_owner(uid) or uid in premium_users


def add_premium_user(user_id: int) -> bool:
    """Add a premium user and save immediately. Returns True if newly added."""
    uid = int(user_id)
    if uid in premium_users:
        return False
    premium_users.add(uid)
    save_premium_users()
    # Upgrade in-memory chat buffer length right away
    ensure_memory(uid)
    return True


def remove_premium_user(user_id: int) -> bool:
    uid = int(user_id)
    if uid not in premium_users:
        return False
    premium_users.discard(uid)
    save_premium_users()
    ensure_memory(uid)
    return True


def memory_turns_for(user_id: int) -> int:
    return PREMIUM_MEMORY_TURNS if is_premium(user_id) else MEMORY_TURNS


def ensure_memory(user_id: int) -> deque:
    """Per-user memory with the right maxlen for free vs premium."""
    uid = int(user_id)
    want = memory_turns_for(uid) * 2
    existing = memory.get(uid)
    if existing is None or existing.maxlen != want:
        old = list(existing) if existing is not None else []
        memory[uid] = deque(old[-want:], maxlen=want)
    return memory[uid]


def cooldown_for(user_id: int) -> float:
    return PREMIUM_COOLDOWN_SECONDS if is_premium(user_id) else COOLDOWN_SECONDS


def image_cooldown_for(user_id: int) -> float:
    return (
        PREMIUM_IMAGE_COOLDOWN_SECONDS
        if is_premium(user_id)
        else IMAGE_COOLDOWN_SECONDS
    )


def prompt_limit_for(user_id: int) -> int:
    return PREMIUM_MAX_PROMPT_CHARS if is_premium(user_id) else MAX_PROMPT_CHARS


def is_image_attachment(att: discord.Attachment) -> bool:
    ctype = (att.content_type or "").lower()
    name = att.filename.lower()
    return ctype.startswith("image/") or name.endswith(IMAGE_EXTS)


def chunk_text(text: str, limit: int = MAX_REPLY_CHARS) -> list[str]:
    text = (text or "").strip() or "No response from AI."
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    return chunks


async def send_chunks(destination, text: str, reply_to: discord.Message | None = None):
    parts = chunk_text(text)
    first = True
    for part in parts:
        if first and reply_to is not None:
            await reply_to.reply(part, mention_author=False)
        else:
            await destination.send(part)
        first = False


def check_cooldown(store: dict[int, float], user_id: int, seconds: float) -> float | None:
    now = time.monotonic()
    ready_at = store.get(user_id, 0.0)
    if now < ready_at:
        return ready_at - now
    store[user_id] = now + seconds
    return None


def ai_blocked(channel_id: int | None) -> str | None:
    if not ai_enabled:
        return "AI is currently paused by the owner. Try again later."
    if channel_id is not None and channel_id in disabled_channels:
        return "AI is disabled in this channel."
    return None


async def ensure_http() -> aiohttp.ClientSession:
    global http
    if http is None or http.closed:
        http = aiohttp.ClientSession(
            headers={"User-Agent": "Mozilla/5.0 DiscordAIBot/1.0"},
            timeout=aiohttp.ClientTimeout(total=120),
        )
    return http


async def download_bytes(url: str) -> tuple[bytes, str]:
    session = await ensure_http()
    async with session.get(url) as resp:
        if resp.status != 200:
            raise RuntimeError(f"download failed HTTP {resp.status}")
        data = await resp.read()
        if len(data) > MAX_IMAGE_BYTES:
            raise RuntimeError("image is too large (max 8MB)")
        ctype = resp.headers.get("Content-Type", "application/octet-stream")
        return data, ctype


def parse_florence_text(raw) -> str:
    """Normalize Florence output into plain text."""
    if raw is None:
        return ""
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else ""
    if not isinstance(raw, str):
        raw = str(raw)
    raw = raw.strip()
    if not raw:
        return ""
    try:
        obj = json.loads(raw.replace("'", '"'))
        if isinstance(obj, dict):
            for key in (
                "<MORE_DETAILED_CAPTION>",
                "<DETAILED_CAPTION>",
                "<CAPTION>",
                "<OCR>",
            ):
                if key in obj and str(obj[key]).strip() not in {"", "-"}:
                    return str(obj[key]).strip()
            for value in obj.values():
                if str(value).strip() not in {"", "-"}:
                    return str(value).strip()
    except Exception:
        pass
    return raw


async def florence_analyze(image_bytes: bytes, filename: str = "image.jpg") -> dict[str, str]:
    """Run Florence-2 caption + OCR on image bytes (no API key)."""
    session = await ensure_http()
    host = FLORENCE_HOST

    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode() + image_bytes + f"\r\n--{boundary}--\r\n".encode()

    upload_id = uuid.uuid4().hex
    async with session.post(
        f"{host}/upload?upload_id={upload_id}",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    ) as resp:
        if resp.status != 200:
            raise RuntimeError(f"vision upload failed HTTP {resp.status}")
        uploaded = await resp.json(content_type=None)

    file_path = uploaded[0] if isinstance(uploaded, list) else uploaded
    file_data = {
        "path": file_path,
        "url": f"{host}/file={file_path}",
        "orig_name": filename,
        "meta": {"_type": "gradio.FileData"},
    }

    results: dict[str, str] = {}
    for task in ("More Detailed Caption", "OCR"):
        payload = {
            "data": [file_data, task, "", "microsoft/Florence-2-base"]
        }
        async with session.post(f"{host}/call/process_image", json=payload) as resp:
            if resp.status != 200:
                continue
            event = await resp.json(content_type=None)
            event_id = event.get("event_id")
        if not event_id:
            continue

        async with session.get(f"{host}/call/process_image/{event_id}") as resp:
            text = await resp.text()

        parsed = None
        for line in text.splitlines():
            if line.startswith("event: error"):
                parsed = None
                break
            if line.startswith("data: "):
                data = line[6:].strip()
                if data in {"", "null"}:
                    continue
                try:
                    obj = json.loads(data)
                    parsed = parse_florence_text(obj)
                except Exception:
                    parsed = parse_florence_text(data)
        if parsed:
            results[task] = parsed

    if not results:
        raise RuntimeError("vision model returned no result (space may be waking up)")
    return results


async def recognize_image(
    image_bytes: bytes,
    question: str = "",
    filename: str = "image.jpg",
) -> str:
    """Describe an image, and answer a question about it when provided."""
    vision = await florence_analyze(image_bytes, filename=filename)
    caption = (
        vision.get("More Detailed Caption")
        or vision.get("Detailed Caption")
        or vision.get("Caption")
        or ""
    )
    ocr = vision.get("OCR", "")
    if ocr in {"-", ""}:
        ocr = ""

    details = caption
    if ocr:
        details = f"{caption}\n\nVisible text (OCR):\n{ocr}".strip()

    question = (question or "").strip()
    if not question or question.lower() in {"describe", "what is this", "what's this"}:
        return f"**Image recognition**\n{details}"

    # Answer the user's question using the vision description + text AI
    prompt = (
        "You are answering a question about an image. "
        "Use ONLY the image analysis below. If unsure, say so.\n\n"
        f"IMAGE ANALYSIS:\n{details}\n\n"
        f"QUESTION: {question}\n\n"
        "Answer clearly and concisely."
    )
    last_error = None
    for attempt in range(AI_RETRIES):
        try:
            response = await ai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
            )
            answer = (response.choices[0].message.content or "").strip()
            if answer:
                return f"**Answer**\n{answer}\n\n**Seen in image**\n{caption}"
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(1.0)
    return f"**Seen in image**\n{details}\n\n(Could not refine answer: {last_error})"


async def generate_image(prompt: str, width: int = 1024, height: int = 1024) -> tuple[bytes, str]:
    """Generate an image with Pollinations Flux (no API key). Returns (bytes, filename)."""
    prompt = prompt.strip()[:500]
    if not prompt:
        raise ValueError("prompt is empty")

    session = await ensure_http()
    url = IMAGE_GEN_URL.format(
        prompt=urllib.parse.quote(prompt),
        width=width,
        height=height,
    )
    # Bust caches so repeated prompts still regenerate
    url += f"&seed={uuid.uuid4().int % 1_000_000_000}"

    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if data and ("image" in ctype or data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"):
                    ext = "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "jpg"
                    return data, f"imagine.{ext}"
    except Exception:
        pass

    # Fallback: g4f image providers, then download the URL
    response = await ai.images.generate(
        model="flux",
        prompt=prompt,
        response_format="url",
    )
    image_url = response.data[0].url
    data, ctype = await download_bytes(image_url)
    ext = "webp" if "webp" in ctype else "png" if "png" in ctype else "jpg"
    return data, f"imagine.{ext}"


def build_messages(user_id: int, prompt: str) -> list[dict]:
    persona = personas[user_id]
    if persona in PREMIUM_PERSONAS and not is_premium(user_id):
        persona = "default"
    system = ALL_PERSONAS.get(persona, ALL_PERSONAS["default"])
    messages: list[dict] = [{"role": "system", "content": system}]
    messages.extend(list(ensure_memory(user_id)))
    messages.append({"role": "user", "content": prompt})
    return messages


async def ask_ai(user_id: int, prompt: str) -> str:
    prompt = prompt[: prompt_limit_for(user_id)]
    messages = build_messages(user_id, prompt)
    last_error = None
    for attempt in range(AI_RETRIES):
        try:
            response = await ai.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
            )
            text = (response.choices[0].message.content or "").strip()
            if not text:
                raise RuntimeError("empty AI response")
            hist = ensure_memory(user_id)
            hist.append({"role": "user", "content": prompt})
            hist.append({"role": "assistant", "content": text})
            return text
        except Exception as exc:
            last_error = exc
            if attempt + 1 < AI_RETRIES:
                await asyncio.sleep(1.0)
    return f"Could not reach the AI after retries. Try again in a moment. ({last_error})"


def collect_image_attachments(message: discord.Message | None) -> list[discord.Attachment]:
    images: list[discord.Attachment] = []
    if message is None:
        return images

    if message.reference and message.reference.resolved:
        ref = message.reference.resolved
        if isinstance(ref, discord.Message):
            for att in ref.attachments:
                if is_image_attachment(att):
                    images.append(att)

    for att in message.attachments:
        if is_image_attachment(att):
            images.append(att)
    return images


async def collect_prompt_context(
    message: discord.Message | None,
    raw_prompt: str,
) -> tuple[str, list[discord.Attachment]]:
    prompt = (raw_prompt or "").strip()
    images = collect_image_attachments(message)

    if message is not None and message.reference and message.reference.resolved:
        ref = message.reference.resolved
        if isinstance(ref, discord.Message) and not ref.author.bot:
            ref_text = (ref.content or "").strip()
            # Ignore image-only replies' empty content; keep text replies as context
            if ref_text and not images:
                prompt = f"Regarding this message: {ref_text}\n\n{prompt}".strip()
            elif ref_text and images:
                # Prefer using text as the vision question if user didn't type one
                if not prompt:
                    prompt = ref_text

    return prompt, images


async def handle_ai_request(
    *,
    user: discord.abc.User,
    channel: discord.abc.Messageable,
    channel_id: int | None,
    raw_prompt: str,
    source_message: discord.Message | None = None,
    interaction: discord.Interaction | None = None,
    slash_image: discord.Attachment | None = None,
):
    blocked = ai_blocked(channel_id)
    if blocked:
        if interaction:
            await interaction.followup.send(blocked, ephemeral=True)
        elif source_message:
            await source_message.reply(blocked, mention_author=False)
        else:
            await channel.send(blocked)
        return

    prompt, images = await collect_prompt_context(source_message, raw_prompt)
    if slash_image is not None and is_image_attachment(slash_image):
        images = [slash_image, *images]

    # Image attached → proper recognition path
    if images:
        wait = check_cooldown(
            image_cooldowns, user.id, image_cooldown_for(user.id)
        )
        if wait is not None:
            msg = f"Slow down — wait {wait:.1f}s."
            if interaction:
                await interaction.followup.send(msg, ephemeral=True)
            elif source_message:
                await source_message.reply(msg, mention_author=False)
            else:
                await channel.send(msg)
            return

        att = images[0]
        try:
            if interaction is None and hasattr(channel, "typing"):
                async with channel.typing():
                    data = await att.read()
                    reply = await recognize_image(data, prompt, filename=att.filename)
            else:
                data = await att.read()
                reply = await recognize_image(data, prompt, filename=att.filename)
        except Exception as exc:
            reply = f"Image recognition failed: {exc}"

        if interaction:
            parts = chunk_text(reply)
            await interaction.followup.send(parts[0])
            for part in parts[1:]:
                await interaction.followup.send(part)
        else:
            await send_chunks(channel, reply, reply_to=source_message)
        return

    wait = check_cooldown(cooldowns, user.id, cooldown_for(user.id))
    if wait is not None:
        msg = f"Slow down — wait {wait:.1f}s."
        if interaction:
            await interaction.followup.send(msg, ephemeral=True)
        elif source_message:
            await source_message.reply(msg, mention_author=False)
        else:
            await channel.send(msg)
        return

    if not prompt.strip():
        tip = "Usage: `!ai <question>` — or attach an image to analyze it."
        if interaction:
            await interaction.followup.send(tip, ephemeral=True)
        elif source_message:
            await source_message.reply(tip, mention_author=False)
        else:
            await channel.send(tip)
        return

    if interaction is None and source_message is not None:
        async with channel.typing():
            reply = await ask_ai(user.id, prompt)
        await send_chunks(channel, reply, reply_to=source_message)
    else:
        reply = await ask_ai(user.id, prompt)
        parts = chunk_text(reply)
        if interaction:
            await interaction.followup.send(parts[0])
            for part in parts[1:]:
                await interaction.followup.send(part)
        else:
            await send_chunks(channel, reply)


async def handle_imagine(
    *,
    user: discord.abc.User,
    channel: discord.abc.Messageable,
    channel_id: int | None,
    prompt: str,
    source_message: discord.Message | None = None,
    interaction: discord.Interaction | None = None,
):
    blocked = ai_blocked(channel_id)
    if blocked:
        if interaction:
            await interaction.followup.send(blocked, ephemeral=True)
        elif source_message:
            await source_message.reply(blocked, mention_author=False)
        else:
            await channel.send(blocked)
        return

    wait = check_cooldown(
        image_cooldowns, user.id, image_cooldown_for(user.id)
    )
    if wait is not None:
        msg = f"Slow down — wait {wait:.1f}s."
        if interaction:
            await interaction.followup.send(msg, ephemeral=True)
        elif source_message:
            await source_message.reply(msg, mention_author=False)
        else:
            await channel.send(msg)
        return

    prompt = (prompt or "").strip()
    if not prompt:
        tip = "Usage: `!imagine <what to draw>`"
        if interaction:
            await interaction.followup.send(tip, ephemeral=True)
        elif source_message:
            await source_message.reply(tip, mention_author=False)
        else:
            await channel.send(tip)
        return

    # Premium gets a larger canvas
    size = 1280 if is_premium(user.id) else 1024
    try:
        if interaction is None and hasattr(channel, "typing"):
            async with channel.typing():
                data, filename = await generate_image(prompt, width=size, height=size)
        else:
            data, filename = await generate_image(prompt, width=size, height=size)
        file = discord.File(io.BytesIO(data), filename=filename)
        content = f"**Imagine:** {prompt[:200]}"
        if interaction:
            await interaction.followup.send(content=content, file=file)
        elif source_message:
            await source_message.reply(content=content, file=file, mention_author=False)
        else:
            await channel.send(content=content, file=file)
    except Exception as exc:
        err = f"Image generation failed: {exc}"
        if interaction:
            await interaction.followup.send(err)
        elif source_message:
            await source_message.reply(err, mention_author=False)
        else:
            await channel.send(err)


async def handle_see(
    *,
    user: discord.abc.User,
    channel: discord.abc.Messageable,
    channel_id: int | None,
    question: str,
    source_message: discord.Message | None = None,
    interaction: discord.Interaction | None = None,
    slash_image: discord.Attachment | None = None,
):
    blocked = ai_blocked(channel_id)
    if blocked:
        if interaction:
            await interaction.followup.send(blocked, ephemeral=True)
        elif source_message:
            await source_message.reply(blocked, mention_author=False)
        else:
            await channel.send(blocked)
        return

    wait = check_cooldown(
        image_cooldowns, user.id, image_cooldown_for(user.id)
    )
    if wait is not None:
        msg = f"Slow down — wait {wait:.1f}s."
        if interaction:
            await interaction.followup.send(msg, ephemeral=True)
        elif source_message:
            await source_message.reply(msg, mention_author=False)
        else:
            await channel.send(msg)
        return

    images = collect_image_attachments(source_message)
    if slash_image is not None and is_image_attachment(slash_image):
        images = [slash_image, *images]

    if not images:
        tip = "Attach an image, or reply to an image, then use `!see [question]`."
        if interaction:
            await interaction.followup.send(tip, ephemeral=True)
        elif source_message:
            await source_message.reply(tip, mention_author=False)
        else:
            await channel.send(tip)
        return

    att = images[0]
    try:
        if interaction is None and hasattr(channel, "typing"):
            async with channel.typing():
                data = await att.read()
                reply = await recognize_image(data, question, filename=att.filename)
        else:
            data = await att.read()
            reply = await recognize_image(data, question, filename=att.filename)
    except Exception as exc:
        reply = f"Image recognition failed: {exc}"

    if interaction:
        parts = chunk_text(reply)
        await interaction.followup.send(parts[0])
        for part in parts[1:]:
            await interaction.followup.send(part)
    else:
        await send_chunks(channel, reply, reply_to=source_message)


@bot.event
async def on_ready():
    global premium_users
    premium_users = load_premium_users()
    # Persist seed + file merge so IDs you add are never string-typed on disk
    save_premium_users()
    await ensure_http()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as exc:
        print(f"Slash sync failed: {exc}")
    print(f"Logged in as {bot.user} (id={bot.user.id})")
    print(f"Ready. Premium users loaded: {len(premium_users)} ({PREMIUM_FILE})")
    print("Image gen + recognition enabled (no AI API keys).")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, (commands.CheckFailure, commands.CommandNotFound)):
        return
    await ctx.send(f"Error: {error}")


@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    await ctx.send(
        "**Commands**\n"
        "`!ai <prompt>` / `/ai` — ask the AI (attach an image to analyze it)\n"
        "`!see [question]` / `/see` — image recognition\n"
        "`!imagine <prompt>` / `/imagine` — generate an image\n"
        "`!persona default|funny|serious|coder` — set your style\n"
        "`!persona poet|roast` — premium personas\n"
        "`!premium` / `!prem` — check your premium status\n"
        "`!clear` — clear your chat memory\n"
        "`!help` — show this message\n"
        f"Or mention me: `@{bot.user.display_name} <prompt>`\n\n"
        "**Owner**\n"
        "`!off` / `!on` — pause / resume AI\n"
        "`!status` — bot status\n"
        "`!aichannel on|off` — AI in this channel\n"
        "`!resetmemory [@user]` — wipe memory\n"
        "`!premium add|remove <id|@user>` / `!premium list` — manage premium"
    )


@bot.command(name="ai")
async def ai_cmd(ctx: commands.Context, *, prompt: str = ""):
    await handle_ai_request(
        user=ctx.author,
        channel=ctx.channel,
        channel_id=ctx.channel.id if ctx.channel else None,
        raw_prompt=prompt,
        source_message=ctx.message,
    )


@bot.tree.command(name="ai", description="Ask the AI (optionally analyze an image)")
@app_commands.describe(prompt="Your question", image="Optional image to analyze")
async def ai_slash(
    interaction: discord.Interaction,
    prompt: str = "",
    image: discord.Attachment | None = None,
):
    await interaction.response.defer(thinking=True)
    await handle_ai_request(
        user=interaction.user,
        channel=interaction.channel,
        channel_id=interaction.channel_id,
        raw_prompt=prompt,
        interaction=interaction,
        slash_image=image,
    )


@bot.command(name="see", aliases=["describe", "vision", "imgdesc"])
async def see_cmd(ctx: commands.Context, *, question: str = ""):
    await handle_see(
        user=ctx.author,
        channel=ctx.channel,
        channel_id=ctx.channel.id if ctx.channel else None,
        question=question,
        source_message=ctx.message,
    )


@bot.tree.command(name="see", description="Recognize / describe an image")
@app_commands.describe(image="Image to analyze", question="Optional question about the image")
async def see_slash(
    interaction: discord.Interaction,
    image: discord.Attachment,
    question: str = "",
):
    await interaction.response.defer(thinking=True)
    if not is_image_attachment(image):
        await interaction.followup.send("Please upload an image file.", ephemeral=True)
        return
    await handle_see(
        user=interaction.user,
        channel=interaction.channel,
        channel_id=interaction.channel_id,
        question=question,
        interaction=interaction,
        slash_image=image,
    )


@bot.command(name="imagine", aliases=["draw", "genimage", "generate"])
async def imagine_cmd(ctx: commands.Context, *, prompt: str = ""):
    await handle_imagine(
        user=ctx.author,
        channel=ctx.channel,
        channel_id=ctx.channel.id if ctx.channel else None,
        prompt=prompt,
        source_message=ctx.message,
    )


@bot.tree.command(name="imagine", description="Generate an image from a text prompt")
@app_commands.describe(prompt="What to generate")
async def imagine_slash(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer(thinking=True)
    await handle_imagine(
        user=interaction.user,
        channel=interaction.channel,
        channel_id=interaction.channel_id,
        prompt=prompt,
        interaction=interaction,
    )


@bot.command(name="persona")
async def persona_cmd(ctx: commands.Context, name: str = ""):
    name = name.strip().lower()
    free = ", ".join(PERSONAS)
    prem = ", ".join(PREMIUM_PERSONAS)
    if name not in ALL_PERSONAS:
        await ctx.send(
            f"Choose one of: `{free}`\n"
            f"Premium: `{prem}`"
        )
        return
    if name in PREMIUM_PERSONAS and not is_premium(ctx.author.id):
        await ctx.send(
            f"**{name}** is premium-only. Ask the owner to run "
            f"`!premium add {ctx.author.id}` (or check `!premium`)."
        )
        return
    personas[ctx.author.id] = name
    await ctx.send(f"Persona set to **{name}**.")


@bot.command(name="clear")
async def clear_cmd(ctx: commands.Context):
    memory.pop(ctx.author.id, None)
    await ctx.send("Your chat memory was cleared.")


@bot.command(name="premium", aliases=["prem"])
async def premium_cmd(ctx: commands.Context, action: str = "", target: str = ""):
    """Check status, or (owner) add/remove/list premium users.

    Adding accepts a raw snowflake OR an @mention. Grants apply immediately
    and are saved to premium_users.json (ints only — no str/int mismatch).
    """
    action = (action or "").strip().lower()
    target = (target or "").strip()

    if action in {"", "status", "me", "check"}:
        prem = is_premium(ctx.author.id)
        await ctx.send(
            f"{ctx.author.mention} premium: **{'yes' if prem else 'no'}**\n"
            f"Perks when premium: `{PREMIUM_COOLDOWN_SECONDS:g}s` AI cooldown, "
            f"`{PREMIUM_IMAGE_COOLDOWN_SECONDS:g}s` image cooldown, "
            f"`{PREMIUM_MEMORY_TURNS}` memory turns, "
            f"`{PREMIUM_MAX_PROMPT_CHARS}` char prompts, "
            f"1280px imagine, personas `{', '.join(PREMIUM_PERSONAS)}`."
        )
        return

    if action in {"add", "remove", "rm", "del", "delete", "list", "ls"}:
        if not is_owner(ctx.author.id):
            await ctx.send("Owner only.")
            return

    if action == "list" or action == "ls":
        if not premium_users:
            await ctx.send("No premium users yet. Use `!premium add <id|@user>`.")
            return
        lines = [f"<@{uid}> `{uid}`" for uid in sorted(premium_users)]
        await ctx.send("**Premium users**\n" + "\n".join(lines))
        return

    if action in {"add", "remove", "rm", "del", "delete"}:
        uid = None
        if ctx.message.mentions:
            uid = int(ctx.message.mentions[0].id)
        if uid is None:
            uid = parse_user_id(target)
        if uid is None:
            await ctx.send(
                "Usage: `!premium add <user_id|@user>` or "
                "`!premium remove <user_id|@user>`\n"
                "Tip: enable Developer Mode → right-click user → Copy User ID."
            )
            return
        if action == "add":
            if is_owner(uid):
                await ctx.send("Owner is always premium.")
                return
            added = add_premium_user(uid)
            # Prove the live check works with the same int path users hit
            live = is_premium(uid)
            if added:
                await ctx.send(
                    f"Granted premium to <@{uid}> (`{uid}`). "
                    f"Live check: **{'yes' if live else 'no'}**."
                )
            else:
                await ctx.send(
                    f"<@{uid}> (`{uid}`) already had premium. "
                    f"Live check: **{'yes' if live else 'no'}**."
                )
            return

        if is_owner(uid):
            await ctx.send("Can't remove premium from the owner.")
            return
        removed = remove_premium_user(uid)
        if removed:
            await ctx.send(f"Removed premium from <@{uid}> (`{uid}`).")
        else:
            await ctx.send(f"<@{uid}> (`{uid}`) was not premium.")
        return

    await ctx.send(
        "Usage: `!premium` · `!premium add <id|@user>` · "
        "`!premium remove <id|@user>` · `!premium list`"
    )


@bot.command(name="off", aliases=["shutdown"])
@owner_only()
async def off_cmd(ctx: commands.Context):
    global ai_enabled
    ai_enabled = False
    await ctx.send("AI paused. Use `!on` to turn it back on.")


@bot.command(name="on", aliases=["start"])
@owner_only()
async def on_cmd(ctx: commands.Context):
    global ai_enabled
    ai_enabled = True
    await ctx.send("AI is on again.")


@bot.command(name="status")
@owner_only()
async def status_cmd(ctx: commands.Context):
    channel_state = (
        "disabled here"
        if ctx.channel and ctx.channel.id in disabled_channels
        else "enabled here"
    )
    await ctx.send(
        f"**Status**\n"
        f"AI global: `{'on' if ai_enabled else 'paused'}`\n"
        f"This channel: `{channel_state}`\n"
        f"Tracked memories: `{len(memory)}`\n"
        f"Disabled channels: `{len(disabled_channels)}`\n"
        f"Premium users: `{len(premium_users)}`\n"
        f"Premium file: `{PREMIUM_FILE}`"
    )


@bot.command(name="aichannel")
@owner_only()
async def aichannel_cmd(ctx: commands.Context, mode: str = ""):
    mode = mode.strip().lower()
    if mode not in {"on", "off"}:
        await ctx.send("Usage: `!aichannel on` or `!aichannel off`")
        return
    if not ctx.channel:
        await ctx.send("No channel.")
        return
    if mode == "off":
        disabled_channels.add(ctx.channel.id)
        await ctx.send("AI disabled in this channel.")
    else:
        disabled_channels.discard(ctx.channel.id)
        await ctx.send("AI enabled in this channel.")


@bot.command(name="resetmemory")
@owner_only()
async def resetmemory_cmd(ctx: commands.Context, member: discord.Member | None = None):
    if member is None:
        memory.clear()
        await ctx.send("Cleared memory for everyone.")
    else:
        memory.pop(member.id, None)
        await ctx.send(f"Cleared memory for {member.mention}.")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if bot.user and bot.user.mentioned_in(message) and not message.mention_everyone:
        prompt = message.content
        for mention in message.mentions:
            prompt = prompt.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
        prompt = prompt.strip()
        if prompt or message.attachments or (message.reference and message.reference.resolved):
            await handle_ai_request(
                user=message.author,
                channel=message.channel,
                channel_id=message.channel.id,
                raw_prompt=prompt,
                source_message=message,
            )
            return

    await bot.process_commands(message)


def main():
    token = (TOKEN or os.getenv("DISCORD_TOKEN", "")).strip()
    if not token:
        raise SystemExit(
            "Add your Discord bot token:\n"
            "  1. Open bot.py\n"
            "  2. Paste it into TOKEN = \"...\" near the top\n"
            "  Or: export DISCORD_TOKEN=\"your-token\"\n"
            "Get a free token at https://discord.com/developers/applications"
        )
    bot.run(token)


if __name__ == "__main__":
    main()
