"""
Discord HTML Website Bot — free AI, HTML only.

Takes a user's description and returns a complete .html file.
Uses g4f (no AI API key required).

Setup:
  pip install discord.py g4f aiohttp
  python bot.py

Discord:
  1. https://discord.com/developers/applications → New Application → Bot
  2. Paste the bot token into TOKEN below (or set DISCORD_TOKEN)
  3. Enable MESSAGE CONTENT INTENT under Bot → Privileged Gateway Intents
  4. Invite: OAuth2 → URL Generator → scopes: bot + applications.commands
     Permissions: Send Messages, Attach Files, Read Message History

Commands:
  !html / /html <description>   Generate a website as an .html file
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
        "Then run this file again."
    )

# Paste your Discord bot token here, or set DISCORD_TOKEN in the environment.
TOKEN = ""

OWNER_ID = 1257060226029584459
COOLDOWN_SECONDS = 8.0
MAX_PROMPT_CHARS = 1500
AI_RETRIES = 3
MAX_HTML_CHARS = 100_000
DISCORD_FILE_LIMIT = 8 * 1024 * 1024  # 8 MB soft upload

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


async def generate_html(description: str) -> str:
    description = description.strip()[:MAX_PROMPT_CHARS]
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
            html = extract_html(raw)
            if len(html) > MAX_HTML_CHARS:
                html = html[:MAX_HTML_CHARS] + "\n</body>\n</html>"
            if "<html" not in html.lower():
                raise RuntimeError("response was not HTML")
            return html
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

    description = (description or "").strip()
    if not description:
        tip = (
            "Describe the website you want.\n"
            "Example: `!html a portfolio for a photographer with dark theme and a gallery`"
        )
        if interaction:
            await interaction.followup.send(tip, ephemeral=True)
        elif source_message:
            await source_message.reply(tip, mention_author=False)
        else:
            await channel.send(tip)
        return

    status = "Generating your HTML website… (free AI, may take a few seconds)"
    status_msg = None
    try:
        if interaction is None and source_message is not None:
            async with channel.typing():
                status_msg = await source_message.reply(status, mention_author=False)
                html = await generate_html(description)
        else:
            html = await generate_html(description)
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

    filename = f"{slugify(description)}.html"
    data = html.encode("utf-8")
    if len(data) > DISCORD_FILE_LIMIT:
        data = data[: DISCORD_FILE_LIMIT - 64] + b"\n</body>\n</html>"
        filename = "website-truncated.html"

    file = discord.File(io.BytesIO(data), filename=filename)
    caption = (
        f"**HTML website ready** — download `{filename}` and open it in a browser.\n"
        f"Prompt: {description[:200]}"
        + ("…" if len(description) > 200 else "")
    )

    if status_msg:
        await status_msg.delete()
    if interaction:
        await interaction.followup.send(content=caption, file=file)
    elif source_message:
        await source_message.reply(content=caption, file=file, mention_author=False)
    else:
        await channel.send(content=caption, file=file)


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
        "`!help` — show this message\n"
        f"Or mention me: `@{bot.user.display_name} a landing page for a coffee shop`\n\n"
        "Download the `.html` file and open it in your browser.\n"
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


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if bot.user and bot.user.mentioned_in(message) and not message.mention_everyone:
        prompt = message.content
        for mention in message.mentions:
            prompt = prompt.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
        prompt = prompt.strip()
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
            "  1. Open bot.py\n"
            "  2. Paste it into TOKEN = \"...\" near the top\n"
            "  Or: export DISCORD_TOKEN=\"your-token\"\n"
            "Get a free token at https://discord.com/developers/applications"
        )
    bot.run(token)


if __name__ == "__main__":
    main()
