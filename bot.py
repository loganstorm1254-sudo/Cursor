"""
Discord AI bot — one file, Termux-friendly, no AI API keys.

Termux setup:
  pkg update && pkg install python
  pip install discord.py
  python bot.py

Discord setup:
  1. https://discord.com/developers/applications → New Application → Bot
  2. Copy the bot token into TOKEN below
  3. Enable MESSAGE CONTENT INTENT under Bot → Privileged Gateway Intents
  4. Invite the bot (OAuth2 → URL Generator → bot + Send Messages)

Commands:
  !ai <prompt>   Ask the AI
  !help          Show help
  @Bot <prompt>  Chat by mention
"""

from __future__ import annotations

import asyncio
import os
import urllib.parse

try:
    import aiohttp
    import discord
    from discord.ext import commands
except ImportError:
    raise SystemExit(
        "Missing packages. In Termux run:\n"
        "  pip install discord.py\n"
        "Then run this file again."
    )

# Paste your Discord bot token here (from the Developer Portal).
# Leave empty to use the DISCORD_TOKEN environment variable instead.
TOKEN = ""

# Free AI — no OpenAI / API key needed
AI_URL = "https://text.pollinations.ai/{prompt}?model=openai&system={system}"
SYSTEM_PROMPT = (
    "You are a helpful Discord bot assistant. "
    "Keep replies concise and friendly. "
    "Use Discord markdown when useful."
)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
http_session = None  # type: aiohttp.ClientSession | None


async def ask_ai(prompt: str) -> str:
    """Call the free Pollinations text API (no token required)."""
    if http_session is None or http_session.closed:
        return "HTTP session is not ready yet. Try again in a moment."

    url = AI_URL.format(
        prompt=urllib.parse.quote(prompt[:2000]),
        system=urllib.parse.quote(SYSTEM_PROMPT),
    )
    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with http_session.get(url, timeout=timeout) as resp:
            if resp.status != 200:
                return f"AI request failed (HTTP {resp.status}). Try again in a moment."
            text = await resp.text()
            return (text or "No response from AI.").strip()[:1900]
    except asyncio.TimeoutError:
        return "The AI took too long to respond. Try again."
    except Exception as exc:
        return f"Could not reach the AI: {exc}"


@bot.event
async def on_ready():
    global http_session
    if http_session is None or http_session.closed:
        http_session = aiohttp.ClientSession()
    print(f"Logged in as {bot.user} (id={bot.user.id})")
    print("Ready. Use !ai or mention me. AI needs no API key.")


@bot.event
async def on_close():
    global http_session
    if http_session and not http_session.closed:
        await http_session.close()


@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    await ctx.send(
        "**Commands**\n"
        "`!ai <prompt>` — ask the AI anything\n"
        "`!help` — show this message\n"
        f"Or mention me: `@{bot.user.display_name} <prompt>`"
    )


@bot.command(name="ai")
async def ai_cmd(ctx: commands.Context, *, prompt: str = ""):
    if not prompt.strip():
        await ctx.send("Usage: `!ai <your question>`")
        return

    async with ctx.typing():
        reply = await ask_ai(prompt)
    await ctx.send(reply)


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
            async with message.channel.typing():
                reply = await ask_ai(prompt)
            await message.reply(reply, mention_author=False)
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
