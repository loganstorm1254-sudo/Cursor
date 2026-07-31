"""
Discord HTML Website Bot — free AI, HTML only.

Takes a user's description and returns a complete .html file.
Uses g4f (no AI API key required).

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
  Reply to the .html file msg   Continue editing that website
  !help                         Show help
  @Bot <description>            Same as !html

Owner-only:
  !off / !on                    Pause / resume generation
  !status                       Show bot status
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import time
from collections import defaultdict

try:
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
COOLDOWN_SECONDS = 8.0
MAX_PROMPT_CHARS = 1500
AI_RETRIES = 3
MAX_HTML_CHARS = 100_000
MAX_CONTEXT_HTML_CHARS = 80_000  # how much existing HTML to send back to the AI
DISCORD_FILE_LIMIT = 8 * 1024 * 1024  # 8 MB soft upload
# Discord message limit is 2000; leave room for ```html fences and part labels
CODE_CHUNK_CHARS = 1800
MAX_CODE_MESSAGES = 8  # after this, point users to the file

HTML_SYSTEM = """You are an HTML website generator. You ONLY create complete, self-contained HTML websites.

STRICT RULES:
1. Output ONLY HTML. No explanations, no markdown fences, no commentary before or after.
2. Start with <!DOCTYPE html> and end with </html>.
3. Put ALL CSS in a <style> tag in <head>. Put ALL JavaScript in a <script> tag before </body> if needed.
4. One single file only — no external CSS/JS files, no build tools, no React/Vue.
5. You may use CDN links for fonts or images (e.g. Google Fonts, unsplash, placeholder images).
6. Make the page look polished: responsive layout, good typography, cohesive colors, clear sections.
7. If the user asks for anything that is NOT a website/HTML page (chat, code review, recipes, hacking, etc.),
   still reply with a tiny HTML page that politely says you only generate websites.
8. Never output Python, JSON, shell, or any non-HTML content.
9. Keep the page focused on the user's description. Prefer one strong visual composition over cluttered dashboards.
10. When revising an existing page, keep what still works and apply the requested changes. Return the FULL updated HTML document, not a patch or diff.
"""

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
ai = AsyncClient()

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


def extract_html(text: str) -> str:
    """Pull a complete HTML document out of a possibly messy AI reply."""
    text = (text or "").strip()
    if not text:
        raise RuntimeError("empty AI response")

    # Strip common markdown fences
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
        # Missing closing tag — wrap what we have
        body = text[start:].strip()
        if "</html>" not in body.lower():
            body += "\n</html>"
        return body

    # Model ignored instructions — wrap as a minimal page containing the text
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

    # Prefer splitting on newlines so blocks stay readable
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
            # Absolute safety: trim code so the message fits
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
    # Deleted / failed resolve
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
        if "<html" not in text.lower() and "<!doctype" not in text.lower():
            # Still treat as HTML source if it's clearly a page-ish file
            if not text:
                return None
        return text[:MAX_HTML_CHARS]
    except Exception:
        return None


async def get_previous_html(source_message: discord.Message | None) -> tuple[str | None, str | None]:
    """
    If the user replied to a message with an .html file, return (html, filename).
    """
    replied = await resolve_replied_message(source_message)
    html = await load_html_from_message(replied)
    if html is None:
        return None, None
    att = find_html_attachment(replied)
    name = att.filename if att else "website.html"
    return html, name


def finish_html(raw: str) -> str:
    html = extract_html(raw)
    if len(html) > MAX_HTML_CHARS:
        html = html[:MAX_HTML_CHARS] + "\n</body>\n</html>"
    if "<html" not in html.lower():
        raise RuntimeError("response was not HTML")
    return html


async def generate_html(description: str, previous_html: str | None = None) -> str:
    description = description.strip()[:MAX_PROMPT_CHARS]
    if previous_html:
        clipped = previous_html[:MAX_CONTEXT_HTML_CHARS]
        user_msg = (
            "Revise this existing single-file HTML website.\n"
            "Apply the user's changes. Keep the rest intact when it still fits.\n"
            "Return the COMPLETE updated HTML document only.\n\n"
            f"CHANGES REQUESTED:\n{description}\n\n"
            f"EXISTING HTML:\n{clipped}\n"
        )
    else:
        user_msg = (
            "Create a complete single-file HTML website for this description:\n\n"
            f"{description}\n\n"
            "Remember: output ONLY the HTML document, starting with <!DOCTYPE html>."
        )
    last_error: Exception | None = None
    for attempt in range(AI_RETRIES):
        try:
            response = await ai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": HTML_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
            )
            raw = (response.choices[0].message.content or "").strip()
            return finish_html(raw)
        except Exception as exc:
            last_error = exc
            if attempt + 1 < AI_RETRIES:
                await asyncio.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"AI failed after retries: {last_error}")


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
        msg = "HTML generation is paused by the owner. Try again later."
        if interaction:
            await interaction.followup.send(msg, ephemeral=True)
        elif source_message:
            await source_message.reply(msg, mention_author=False)
        else:
            await channel.send(msg)
        return

    wait = check_cooldown(user.id)
    if wait is not None:
        msg = f"Slow down — wait {wait:.1f}s."
        if interaction:
            await interaction.followup.send(msg, ephemeral=True)
        elif source_message:
            await source_message.reply(msg, mention_author=False)
        else:
            await channel.send(msg)
        return

    # Auto-load previous HTML when the user replied to a .html file message
    if previous_html is None and source_message is not None:
        previous_html, previous_filename = await get_previous_html(source_message)

    description = (description or "").strip()
    if not description:
        if previous_html:
            tip = (
                "You're editing a previous site. Tell me what to change.\n"
                "Example: reply with `make the background dark and add a contact form`"
            )
        else:
            tip = (
                "Describe the website you want.\n"
                "Example: `!html a portfolio for a photographer with dark theme and a gallery`\n"
                "To continue editing: **reply** to the message with the `.html` file and describe changes."
            )
        if interaction:
            await interaction.followup.send(tip, ephemeral=True)
        elif source_message:
            await source_message.reply(tip, mention_author=False)
        else:
            await channel.send(tip)
        return

    revising = previous_html is not None
    status = (
        "Updating your HTML website from the previous file… (free AI, may take a few seconds)"
        if revising
        else "Generating your HTML website… (free AI, may take a few seconds)"
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
        + "\n_Reply to this message (the one with the file) to keep editing._"
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
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as exc:
        print(f"Slash sync failed: {exc}")
    print(f"Logged in as {bot.user} (id={bot.user.id})")
    print("Ready — HTML website generator (free AI via g4f).")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, (commands.CheckFailure, commands.CommandNotFound)):
        return
    await ctx.send(f"Error: {error}")


@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    await ctx.send(
        "**HTML Website Bot** — I only make HTML websites.\n\n"
        "`!html <description>` / `/html` — generate a single-file website\n"
        "**Reply** to the message with the `.html` file + your changes — continue editing\n"
        "`!help` — show this message\n"
        f"Or mention me: `@{bot.user.display_name} a landing page for a coffee shop`\n\n"
        "Replies with the HTML **code in chat** plus a downloadable `.html` file.\n"
        "Free AI (no OpenAI key). HTML only — I won't chat or write other code."
    )


@bot.command(name="html", aliases=["website", "site", "makehtml", "web"])
async def html_cmd(ctx: commands.Context, *, description: str = ""):
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
        f"Mode: HTML websites only (free AI)"
    )


def strip_bot_mentions(content: str) -> str:
    prompt = content or ""
    if bot.user:
        prompt = prompt.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "")
    return prompt.strip()


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Continue editing: reply to a message that has the downloadable .html file
    if message.reference is not None:
        # Don't steal !commands — let process_commands handle those (they still load previous HTML)
        content = (message.content or "").strip()
        is_command = content.startswith("!")
        if not is_command:
            replied = await resolve_replied_message(message)
            if find_html_attachment(replied) is not None:
                prompt = strip_bot_mentions(content)
                if prompt:
                    await handle_html(
                        user=message.author,
                        channel=message.channel,
                        description=prompt,
                        source_message=message,
                    )
                    return

    if bot.user and bot.user.mentioned_in(message) and not message.mention_everyone:
        prompt = strip_bot_mentions(message.content)
        if prompt:
            await handle_html(
                user=message.author,
                channel=message.channel,
                description=prompt,
                source_message=message,
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
