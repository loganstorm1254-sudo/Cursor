"""
Discord HTML Website Bot — free unlimited AI, HTML only.

Takes a user's description and returns a complete .html file.
Uses free no-key AI backends with automatic failover
(Pollinations anonymous + g4f model rotation). No paid API / credit keys.

Setup (one file — no requirements.txt):
  pip install discord.py g4f aiohttp
  python bot2.py

Discord:
  1. https://discord.com/developers/applications → New Application → Bot
  2. Paste the bot token into TOKEN below (or set DISCORD_TOKEN)
  3. Enable MESSAGE CONTENT INTENT under Bot → Privileged Gateway Intents
  4. Invite: OAuth2 → URL Generator → scopes: bot + applications.commands
     Permissions: Send Messages, Attach Files, Read Message History

Commands:
  !html / /html <description>   Generate a website (code + .html file)
  !ping                         Check the bot is online
  Reply to my bot message       Continue editing that website
  !help                         Show help
  @Bot <description>            Same as !html

IMPORTANT: Enable MESSAGE CONTENT INTENT or !html / @mention / reply will silently fail.
  Developer Portal → Bot → Privileged Gateway Intents → Message Content Intent

Owner-only:
  !off / !on                    Pause / resume generation
  !status                       Show bot status
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import time
from collections import defaultdict

try:
    import aiohttp
    import discord
    from discord import app_commands
    from discord.ext import commands
    from g4f.client import AsyncClient
except ImportError:
    raise SystemExit(
        "Missing packages. Run:\n"
        "  pip install discord.py g4f aiohttp\n"
        "Then: python bot2.py"
    )

# Paste your Discord bot token here, or set DISCORD_TOKEN in the environment.
TOKEN = ""

OWNER_ID = 1257060226029584459
COOLDOWN_SECONDS = 60.0  # 1 minute per user
MAX_PROMPT_CHARS = 1500
MAX_HTML_CHARS = 100_000
MAX_CONTEXT_HTML_CHARS = 60_000
DISCORD_FILE_LIMIT = 8 * 1024 * 1024
CODE_CHUNK_CHARS = 1800
MAX_CODE_MESSAGES = 8

# Free backends (no paid API keys / credit packs).
# g4f first — handles long HTML. Pollinations anonymous often 402s on big prompts.
POLLINATIONS_URL = "https://text.pollinations.ai/openai"
POLLINATIONS_MODELS = ("openai", "openai-fast")  # only these work on anonymous legacy API
G4F_MODELS = (
    "gpt-4o-mini",
    "gpt-4o",
    "deepseek-r1",
    "llama-3.3-70b",
    "command-r",
)

HTML_SYSTEM = """You are an expert front-end developer who builds complete, polished, INTERACTIVE single-file HTML websites.

OUTPUT RULES (absolute):
1. Output ONLY HTML. No markdown fences, no explanations, no commentary.
2. Start with <!DOCTYPE html> and end with </html>.
3. One self-contained file: ALL CSS in <style>, ALL JS in <script> before </body>.
4. You may use CDN fonts/images (Google Fonts, unsplash, picsum). No React/Vue/build tools.

QUALITY / INTERACTIVITY (must do well):
5. Buttons MUST be real <button> or <a class="btn"> elements with visible styles:
   - hover, active, focus states
   - cursor:pointer
   - clear padding, contrast, border-radius
6. Every primary CTA button must DO something with JavaScript, e.g.:
   - scroll to a section, open/close a mobile nav, toggle a modal,
   - switch tabs, filter a gallery, show a toast, submit a form with preventDefault + success message,
   - light/dark theme toggle, accordion FAQ open/close.
7. Never ship dead placeholder buttons that look clickable but do nothing.
8. Forms need labels, validation feedback, and a working submit handler (even if demo-only).
9. Navigation: sticky header + working mobile hamburger that opens/closes a menu.
10. Responsive: mobile-first CSS, flex/grid, readable type, good spacing.
11. One strong visual composition (not a cluttered dashboard). Cohesive color variables in :root.
12. Smooth small animations (CSS transitions) — presence, not noise.
13. Include enough real-looking content for the theme (not just "Lorem ipsum" walls).
14. If revising an existing page: keep what works, apply the requested changes, return the FULL document.
15. If the user asks for non-website stuff, still return a tiny HTML page saying you only make websites.
16. SAFETY: Never create porn, nude, sexual, fetish, or adult-only websites. If asked, output a tiny HTML page that says adult content is not allowed.
"""

# Block NSFW / porn website requests (prompt filter).
NSFW_BLOCK_MESSAGE = (
    "Blocked — I won't make porn or adult/NSFW websites.\n"
    "Describe a normal site instead (portfolio, shop, blog, landing page, etc.)."
)

# Whole-word / phrase patterns (case-insensitive). Focused on sexual / illegal content.
_NSFW_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bporn\b",
        r"\bporno\b",
        r"\bpornography\b",
        r"\bxxx\b",
        r"\bnsfw\b",
        r"\bonlyfans\b",
        r"\bfansly\b",
        r"\bhentai\b",
        r"\brule\s*34\b",
        r"\br34\b",
        r"\berotic\b",
        r"\berotica\b",
        r"\bnaked\b",
        r"\bnude\b",
        r"\bnudes\b",
        r"\bnudity\b",
        r"\bsex\b",
        r"\bsexual\b",
        r"\bsmut\b",
        r"\bfetish\b",
        r"\bbdsm\b",
        r"\bmasturbat(?:e|ion|ing)\b",
        r"\bblowjob\b",
        r"\bhandjob\b",
        r"\bboobs?\b",
        r"\btits?\b",
        r"\btitties\b",
        r"\bpussy\b",
        r"\bdick\b",
        r"\bcock\b",
        r"\bpenis\b",
        r"\bvagina\b",
        r"\bthreesome\b",
        r"\borgy\b",
        r"\bescort\b",
        r"\bcamgirl\b",
        r"\bcamboy\b",
        r"\bstrip(?:per|ping|club)\b",
        r"\badult\s+(?:site|website|content|video|videos|film|films|store|shop|dating)\b",
        r"\b18\s*\+\s*(?:site|website|only|content)?\b",
        r"\bpornhub\b",
        r"\bxvideos?\b",
        r"\bxhamster\b",
        r"\bredtube\b",
        r"\bspankbang\b",
        r"\bchild\s*porn\b",
        r"\bloli\b",
        r"\bshota\b",
        r"\bunderage\b",
        r"\bpedophil",
        r"\bincest\b",
        r"\brape\b",
        r"\bnon[\s-]?consensual\b",
    )
)


def is_nsfw_request(text: str) -> bool:
    """Return True if the prompt looks like an adult/porn site request."""
    if not text:
        return False
    normalized = re.sub(r"[\W_]+", " ", text.lower())
    for hay in (text, normalized):
        for pattern in _NSFW_PATTERNS:
            if pattern.search(hay):
                return True
    return False


async def deny(
    message: str,
    *,
    interaction: discord.Interaction | None = None,
    source_message: discord.Message | None = None,
    channel: discord.abc.Messageable | None = None,
):
    if interaction:
        await interaction.followup.send(message, ephemeral=True)
    elif source_message:
        await source_message.reply(message, mention_author=False)
    elif channel is not None:
        await channel.send(message)


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
ai = AsyncClient()
http: aiohttp.ClientSession | None = None
_provider_cursor = 0
_last_provider = "none"

ai_enabled = True
cooldowns: dict[int, float] = defaultdict(float)


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def owner_only():
    async def predicate(ctx: commands.Context) -> bool:
        if not is_owner(ctx.author.id):
            await ctx.send("Owner only.")
            return False
        return True

    return commands.check(predicate)


def check_cooldown(user_id: int) -> float | None:
    now = time.monotonic()
    ready_at = cooldowns.get(user_id, 0.0)
    if now < ready_at:
        return ready_at - now
    cooldowns[user_id] = now + COOLDOWN_SECONDS
    return None


async def ensure_http() -> aiohttp.ClientSession:
    global http
    if http is None or http.closed:
        # Intentionally NO Authorization header — anonymous free Pollinations.
        http = aiohttp.ClientSession(
            headers={
                "User-Agent": "Mozilla/5.0 DiscordHTMLBot/2.0",
                "Accept": "application/json, text/plain, */*",
            },
            timeout=aiohttp.ClientTimeout(total=120),
        )
    return http


def extract_html(text: str) -> str:
    """Pull a complete HTML document out of a possibly messy AI reply."""
    text = (text or "").strip()
    if not text:
        raise RuntimeError("empty AI response")

    fence = re.search(
        r"```(?:html|HTML)?\s*\n?(.*?)```",
        text,
        flags=re.DOTALL,
    )
    if fence:
        text = fence.group(1).strip()

    lower = text.lower()
    start = lower.find("<!doctype html")
    if start < 0:
        start = lower.find("<html")
    end = lower.rfind("</html>")

    if start >= 0 and end > start:
        return text[start : end + len("</html>")].strip()

    if start >= 0:
        body = text[start:].strip()
        if "</html>" not in body.lower():
            body += "\n</html>"
        return body

    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"UTF-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        "<title>Generated</title>\n"
        "<style>body{font-family:system-ui,sans-serif;max-width:40rem;"
        "margin:2rem auto;padding:1rem;line-height:1.5}</style>\n"
        "</head>\n<body>\n<pre>"
        f"{escaped[:8000]}"
        "</pre>\n</body>\n</html>"
    )


def slugify(text: str, fallback: str = "website") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = slug[:40] or fallback
    return slug


def html_code_chunks(html: str) -> list[str]:
    """Split HTML into Discord ```html code-block messages (≤2000 chars each)."""
    html = html or ""
    if not html:
        return ["```html\n<!-- empty -->\n```"]

    lines = html.splitlines(keepends=True)
    raw_chunks: list[str] = []
    buf = ""
    for line in lines:
        if len(buf) + len(line) > CODE_CHUNK_CHARS and buf:
            raw_chunks.append(buf)
            buf = line
        elif len(line) > CODE_CHUNK_CHARS:
            if buf:
                raw_chunks.append(buf)
                buf = ""
            for i in range(0, len(line), CODE_CHUNK_CHARS):
                raw_chunks.append(line[i : i + CODE_CHUNK_CHARS])
        else:
            buf += line
    if buf:
        raw_chunks.append(buf)

    total = len(raw_chunks)
    messages: list[str] = []
    for i, chunk in enumerate(raw_chunks[:MAX_CODE_MESSAGES], start=1):
        label = f"HTML code ({i}/{min(total, MAX_CODE_MESSAGES)})"
        if total > MAX_CODE_MESSAGES and i == MAX_CODE_MESSAGES:
            label += " — truncated; full page is in the file"
        block = f"**{label}**\n```html\n{chunk.rstrip()}\n```"
        if len(block) > 2000:
            overhead = len(f"**{label}**\n```html\n\n```")
            block = f"**{label}**\n```html\n{chunk[: 2000 - overhead - 1].rstrip()}\n```"
        messages.append(block)

    if total > MAX_CODE_MESSAGES:
        messages.append(
            f"_Showing first {MAX_CODE_MESSAGES} of {total} code parts. "
            "Download the `.html` file for the full website._"
        )
    return messages


async def send_code_and_file(
    *,
    channel: discord.abc.Messageable,
    caption: str,
    file: discord.File,
    html: str,
    source_message: discord.Message | None = None,
    interaction: discord.Interaction | None = None,
):
    """Send downloadable file first, then the HTML source in chat."""
    if interaction:
        await interaction.followup.send(content=caption, file=file)
        for part in html_code_chunks(html):
            await interaction.followup.send(part)
    elif source_message:
        await source_message.reply(content=caption, file=file, mention_author=False)
        for part in html_code_chunks(html):
            await channel.send(part)
    else:
        await channel.send(content=caption, file=file)
        for part in html_code_chunks(html):
            await channel.send(part)


def is_html_attachment(att: discord.Attachment) -> bool:
    name = (att.filename or "").lower()
    ctype = (att.content_type or "").lower()
    return name.endswith(".html") or name.endswith(".htm") or "html" in ctype


def find_html_attachment(message: discord.Message | None) -> discord.Attachment | None:
    if message is None:
        return None
    for att in message.attachments:
        if is_html_attachment(att):
            return att
    return None


async def resolve_replied_message(message: discord.Message | None) -> discord.Message | None:
    """Get the message this one replies to (fetch if needed)."""
    if message is None or message.reference is None:
        return None
    resolved = message.reference.resolved
    if isinstance(resolved, discord.Message):
        return resolved
    if isinstance(resolved, discord.DeletedReferencedMessage):
        return None
    msg_id = message.reference.message_id
    if msg_id is None:
        return None
    try:
        return await message.channel.fetch_message(msg_id)
    except (discord.NotFound, discord.HTTPException, AttributeError):
        return None


async def load_html_from_message(message: discord.Message | None) -> str | None:
    """Download .html from a message attachment, if present."""
    att = find_html_attachment(message)
    if att is None:
        return None
    try:
        data = await att.read()
        text = data.decode("utf-8", errors="replace").strip()
        if not text:
            return None
        return text[:MAX_HTML_CHARS]
    except Exception:
        return None


async def get_previous_html(source_message: discord.Message | None) -> tuple[str | None, str | None]:
    """
    Find prior HTML to continue editing:
    1) attachment on the replied-to message
    2) walk one reply hop up
    3) recent bot messages in the channel that have an .html file
    """
    if source_message is None:
        return None, None

    replied = await resolve_replied_message(source_message)
    candidates: list[discord.Message] = []
    if replied is not None:
        candidates.append(replied)
        # one hop: reply → that message's parent
        parent = await resolve_replied_message(replied)
        if parent is not None:
            candidates.append(parent)

    for msg in candidates:
        html = await load_html_from_message(msg)
        if html:
            att = find_html_attachment(msg)
            return html, att.filename if att else "website.html"

    # If they replied to a bot code dump (no file), scan recent history for an .html
    if replied is not None and bot.user and (
        replied.author.id == bot.user.id or find_html_attachment(replied) is None
    ):
        try:
            async for msg in source_message.channel.history(limit=40, before=source_message):
                if bot.user and msg.author.id != bot.user.id:
                    continue
                html = await load_html_from_message(msg)
                if html:
                    att = find_html_attachment(msg)
                    return html, att.filename if att else "website.html"
        except (discord.Forbidden, discord.HTTPException):
            pass

    return None, None


def finish_html(raw: str) -> str:
    html = extract_html(raw)
    if len(html) > MAX_HTML_CHARS:
        html = html[:MAX_HTML_CHARS] + "\n</body>\n</html>"
    if "<html" not in html.lower():
        raise RuntimeError("response was not HTML")
    return html


def build_user_prompt(description: str, previous_html: str | None) -> str:
    description = description.strip()[:MAX_PROMPT_CHARS]
    extras = (
        "\n\nIMPORTANT QUALITY CHECK before you finish:\n"
        "- At least one real working button with JS behavior\n"
        "- Hover styles on buttons/links\n"
        "- Mobile-friendly layout\n"
        "- Output ONLY the full HTML document\n"
    )
    if previous_html:
        clipped = previous_html[:MAX_CONTEXT_HTML_CHARS]
        return (
            "Revise this existing single-file HTML website.\n"
            "Apply the user's changes. Keep the rest intact when it still fits.\n"
            "Make buttons/nav/forms actually work with JS if they should be interactive.\n"
            "Return the COMPLETE updated HTML document only.\n\n"
            f"CHANGES REQUESTED:\n{description}\n\n"
            f"EXISTING HTML:\n{clipped}\n"
            f"{extras}"
        )
    return (
        "Create a complete single-file HTML website for this description:\n\n"
        f"{description}\n"
        f"{extras}"
    )


def provider_queue() -> list[tuple[str, str]]:
    """Rotating list of (backend, model) free providers. g4f preferred for long HTML."""
    global _provider_cursor
    items: list[tuple[str, str]] = []
    for m in G4F_MODELS:
        items.append(("g4f", m))
    for m in POLLINATIONS_MODELS:
        items.append(("pollinations", m))
    if not items:
        return items
    # Rotate starting g4f model so one rate-limit doesn't stick forever
    g4f_n = len(G4F_MODELS)
    start = _provider_cursor % max(g4f_n, 1)
    _provider_cursor += 1
    rotated = items[start:g4f_n] + items[:start] + items[g4f_n:]
    return rotated


async def ask_pollinations(model: str, messages: list[dict]) -> str:
    session = await ensure_http()
    # Keep payloads smaller — anonymous Pollinations often 402s on huge prompts.
    slim = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            content = content[:2500]
        else:
            content = content[:12000]
        slim.append({"role": role, "content": content})
    payload = {
        "model": model,
        "messages": slim,
        "temperature": 0.7,
    }
    # Anonymous free tier — do NOT send Authorization (paid keys with $0 → 402).
    async with session.post(POLLINATIONS_URL, json=payload) as resp:
        text = await resp.text()
        if resp.status == 402:
            raise RuntimeError("pollinations rate/budget limit on this prompt size")
        if resp.status != 200:
            raise RuntimeError(f"pollinations HTTP {resp.status}: {text[:180]}")
    try:
        data = json.loads(text)
        content = data["choices"][0]["message"]["content"]
    except Exception:
        content = text
    content = (content or "").strip()
    if not content:
        raise RuntimeError("pollinations empty response")
    return content


async def ask_g4f(model: str, messages: list[dict]) -> str:
    # Prefer chat.completions; on failure, fold system into user (some providers hate system).
    try:
        response = await asyncio.wait_for(
            ai.chat.completions.create(model=model, messages=messages),
            timeout=90,
        )
        content = (response.choices[0].message.content or "").strip()
        if content:
            return content
    except Exception:
        pass

    combined = []
    sys_bits = [m["content"] for m in messages if m.get("role") == "system"]
    user_bits = [m["content"] for m in messages if m.get("role") != "system"]
    blob = ""
    if sys_bits:
        blob += "SYSTEM:\n" + "\n".join(sys_bits) + "\n\n"
    blob += "\n\n".join(user_bits)
    response = await asyncio.wait_for(
        ai.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": blob}],
        ),
        timeout=90,
    )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("g4f empty response")
    return content


async def ask_free_ai(messages: list[dict]) -> str:
    """Call free unlimited backends until one returns usable text."""
    global _last_provider
    errors: list[str] = []
    for backend, model in provider_queue():
        label = f"{backend}:{model}"
        try:
            if backend == "pollinations":
                text = await ask_pollinations(model, messages)
            else:
                text = await ask_g4f(model, messages)
            _last_provider = label
            print(f"AI OK via {_last_provider} ({len(text)} chars)")
            return text
        except Exception as exc:
            msg = f"{label}: {type(exc).__name__}: {exc}"
            errors.append(msg)
            print(f"AI fail {msg}")
            await asyncio.sleep(0.5)
    raise RuntimeError("All free AI providers failed. " + " | ".join(errors[:5]))


async def generate_html(description: str, previous_html: str | None = None) -> str:
    user_msg = build_user_prompt(description, previous_html)
    messages = [
        {"role": "system", "content": HTML_SYSTEM},
        {"role": "user", "content": user_msg},
    ]
    last_error: Exception | None = None
    # Two full sweeps across free providers
    for sweep in range(2):
        try:
            raw = await ask_free_ai(messages)
            return finish_html(raw)
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(1.0 + sweep)
    raise RuntimeError(f"AI failed after free-provider sweeps: {last_error}")


async def handle_html(
    *,
    user: discord.abc.User,
    channel: discord.abc.Messageable,
    description: str,
    source_message: discord.Message | None = None,
    interaction: discord.Interaction | None = None,
    previous_html: str | None = None,
    previous_filename: str | None = None,
):
    if not ai_enabled:
        await deny(
            "HTML generation is paused by the owner. Try again later.",
            interaction=interaction,
            source_message=source_message,
            channel=channel,
        )
        return

    if previous_html is None and source_message is not None:
        previous_html, previous_filename = await get_previous_html(source_message)

    description = (description or "").strip()
    if not description:
        if previous_html:
            tip = (
                "You're editing a previous site. Tell me what to change.\n"
                "Example: reply with `make the background dark and add working buttons`"
            )
        else:
            tip = (
                "Describe the website you want.\n"
                "Example: `!html a portfolio for a photographer with dark theme, gallery, and working menu buttons`\n"
                "To continue editing: **reply** to the message with the `.html` file and describe changes."
            )
        await deny(tip, interaction=interaction, source_message=source_message, channel=channel)
        return

    # Content filter — block porn / adult site requests (before cooldown so retries aren't punished)
    if is_nsfw_request(description):
        print(f"NSFW blocked from {user}: {description[:120]!r}")
        await deny(
            NSFW_BLOCK_MESSAGE,
            interaction=interaction,
            source_message=source_message,
            channel=channel,
        )
        return

    wait = check_cooldown(user.id)
    if wait is not None:
        await deny(
            f"Slow down — wait {wait:.1f}s.",
            interaction=interaction,
            source_message=source_message,
            channel=channel,
        )
        return

    revising = previous_html is not None
    status = (
        "Updating your HTML website… (free unlimited AI, may take a bit)"
        if revising
        else "Generating your HTML website… (free unlimited AI, may take a bit)"
    )
    status_msg = None
    try:
        if interaction is None and source_message is not None:
            async with channel.typing():
                status_msg = await source_message.reply(status, mention_author=False)
                html = await generate_html(description, previous_html=previous_html)
        else:
            html = await generate_html(description, previous_html=previous_html)
    except Exception as exc:
        err = f"Could not generate HTML: {exc}"
        if status_msg:
            await status_msg.edit(content=err)
        elif interaction:
            await interaction.followup.send(err)
        elif source_message:
            await source_message.reply(err, mention_author=False)
        else:
            await channel.send(err)
        return

    if revising and previous_filename:
        base = previous_filename.rsplit(".", 1)[0]
        filename = f"{slugify(base, fallback='website')}-updated.html"
    else:
        filename = f"{slugify(description)}.html"
    data = html.encode("utf-8")
    if len(data) > DISCORD_FILE_LIMIT:
        data = data[: DISCORD_FILE_LIMIT - 64] + b"\n</body>\n</html>"
        filename = "website-truncated.html"

    file = discord.File(io.BytesIO(data), filename=filename)
    action = "updated" if revising else "ready"
    caption = (
        f"**HTML website {action}** — code below + download `{filename}`.\n"
        f"{'Changes' if revising else 'Prompt'}: {description[:200]}"
        + ("…" if len(description) > 200 else "")
        + f"\n_AI: `{_last_provider}` (free)_ · Reply to this file message to keep editing._"
    )

    if status_msg:
        try:
            await status_msg.delete()
        except discord.HTTPException:
            pass

    await send_code_and_file(
        channel=channel,
        caption=caption,
        file=file,
        html=html,
        source_message=source_message,
        interaction=interaction,
    )


@bot.event
async def on_ready():
    await ensure_http()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as exc:
        print(f"Slash sync failed: {exc}")
    print(f"Logged in as {bot.user} (id={bot.user.id})")
    print("Ready — HTML generator (free unlimited AI: Pollinations + g4f).")
    if not intents.message_content:
        print("WARNING: message_content intent is OFF — !html / @mention / reply will NOT work.")
    else:
        print("Tip: In Discord Developer Portal enable MESSAGE CONTENT INTENT, then restart.")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CheckFailure):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: `!html <describe the website>`")
        return
    print(f"Command error in {ctx.command}: {error!r}")
    try:
        await ctx.send(f"Error: {error}")
    except discord.HTTPException:
        pass


@bot.command(name="ping")
async def ping_cmd(ctx: commands.Context):
    """Quick check that the bot can read messages / commands."""
    await ctx.send(
        f"Pong — `bot2` is online. Use `!html <description>` or `/html`.\n"
        f"Latency: `{round(bot.latency * 1000)}ms`"
    )


@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    await ctx.send(
        "**HTML Website Bot** (`bot2.py`) — I only make HTML websites.\n\n"
        "`!html <description>` / `/html` — generate a single-file website\n"
        "`!ping` — check the bot is online\n"
        "**Reply** to my message (or the `.html` file) + your changes — continue editing\n"
        f"Or mention me: `@{bot.user.display_name} a landing page for a coffee shop`\n\n"
        "If `!html` / @mention do nothing: enable **Message Content Intent** in the "
        "Developer Portal → Bot → Privileged Gateway Intents, then restart the bot.\n"
        "Free unlimited AI. Interactive buttons/nav/forms.\n"
        "Filter: no porn / adult / NSFW websites."
    )


@bot.command(name="html", aliases=["website", "site", "makehtml", "web", "gen", "build"])
async def html_cmd(ctx: commands.Context, *, description: str = ""):
    print(f"!html from {ctx.author} in #{getattr(ctx.channel, 'name', ctx.channel.id)}: {description[:80]!r}")
    await handle_html(
        user=ctx.author,
        channel=ctx.channel,
        description=description,
        source_message=ctx.message,
    )


@bot.tree.command(name="html", description="Generate a complete HTML website from a description")
@app_commands.describe(description="What the website should look like / be about")
async def html_slash(interaction: discord.Interaction, description: str):
    await interaction.response.defer(thinking=True)
    await handle_html(
        user=interaction.user,
        channel=interaction.channel,
        description=description,
        interaction=interaction,
    )


@bot.command(name="off", aliases=["shutdown"])
@owner_only()
async def off_cmd(ctx: commands.Context):
    global ai_enabled
    ai_enabled = False
    await ctx.send("HTML generation paused. Use `!on` to resume.")


@bot.command(name="on", aliases=["start"])
@owner_only()
async def on_cmd(ctx: commands.Context):
    global ai_enabled
    ai_enabled = True
    await ctx.send("HTML generation is on again.")


@bot.command(name="status")
@owner_only()
async def status_cmd(ctx: commands.Context):
    await ctx.send(
        f"**Status**\n"
        f"Generation: `{'on' if ai_enabled else 'paused'}`\n"
        f"Last AI: `{_last_provider}`\n"
        f"Message content intent: `{'on' if intents.message_content else 'OFF'}`\n"
        f"Mode: free unlimited AI (Pollinations + g4f) · HTML only"
    )


def strip_bot_mentions(content: str) -> str:
    prompt = content or ""
    if bot.user:
        uid = bot.user.id
        prompt = (
            prompt.replace(f"<@{uid}>", "")
            .replace(f"<@!{uid}>", "")
            .replace(f"@{bot.user}", "")
        )
        if bot.user.name:
            prompt = prompt.replace(f"@{bot.user.name}", "")
        if bot.user.display_name:
            prompt = prompt.replace(f"@{bot.user.display_name}", "")
    return prompt.strip()


def bot_was_mentioned(message: discord.Message) -> bool:
    if not bot.user:
        return False
    if message.mention_everyone:
        # still allow if bot is also explicitly mentioned
        pass
    if bot.user in message.mentions:
        return True
    try:
        if bot.user.mentioned_in(message):
            return True
    except Exception:
        pass
    # raw content fallback (sometimes mentions list is incomplete)
    content = message.content or ""
    return f"<@{bot.user.id}>" in content or f"<@!{bot.user.id}>" in content


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = (message.content or "").strip()

    # Prefix commands first (!html, !help, !ping, …)
    if content.startswith("!"):
        await bot.process_commands(message)
        return

    # Detect Message Content Intent disabled (common cause of "nothing works")
    mentioned = bot_was_mentioned(message)
    if mentioned and not content and not message.attachments:
        # Mentions arrive but content is empty → privileged intent usually off
        try:
            await message.channel.send(
                "I saw the ping, but message text is empty.\n"
                "Enable **Message Content Intent** here, then restart `bot2.py`:\n"
                "https://discord.com/developers/applications → your app → **Bot** → "
                "**Privileged Gateway Intents** → Message Content Intent → Save\n"
                "Or use the slash command: `/html`"
            )
        except discord.HTTPException:
            pass
        return

    # Continue editing by reply (to file message, code message, or related bot msg)
    if message.reference is not None and content:
        prev_html, prev_name = await get_previous_html(message)
        if prev_html:
            print(f"reply-edit from {message.author}: {content[:80]!r}")
            await handle_html(
                user=message.author,
                channel=message.channel,
                description=strip_bot_mentions(content),
                source_message=message,
                previous_html=prev_html,
                previous_filename=prev_name,
            )
            return

    # @Bot <description>
    if mentioned:
        prompt = strip_bot_mentions(content)
        if prompt:
            print(f"mention from {message.author}: {prompt[:80]!r}")
            await handle_html(
                user=message.author,
                channel=message.channel,
                description=prompt,
                source_message=message,
            )
            return
        if content:
            await message.reply(
                "Tell me what website to make.\n"
                f"Example: `@{bot.user.display_name} a coffee shop landing page with a menu`",
                mention_author=False,
            )
            return

    await bot.process_commands(message)


def main():
    token = (TOKEN or os.getenv("DISCORD_TOKEN", "")).strip()
    if not token:
        raise SystemExit(
            "Add your Discord bot token:\n"
            "  1. Open bot2.py\n"
            "  2. Paste it into TOKEN = \"...\" near the top\n"
            "  Or: export DISCORD_TOKEN=\"your-token\"\n"
            "Get a free token at https://discord.com/developers/applications"
        )
    bot.run(token)


if __name__ == "__main__":
    main()
