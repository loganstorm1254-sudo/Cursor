"""
Simple Discord AI bot — no AI API keys needed.
Uses Pollinations free text API for replies.

Setup:
  1. pip install -r requirements.txt
  2. Create a bot at https://discord.com/developers/applications
  3. Enable Message Content Intent under Bot settings
  4. export DISCORD_TOKEN="your-bot-token"
  5. python bot.py

Commands:
  !ai <prompt>     Ask the AI anything
  !help            Show commands
  @Bot <prompt>    Mention the bot to chat
"""

from __future__ import annotations

import asyncio
import os
import urllib.parse

import aiohttp
import discord
from discord.ext import commands

# Free AI endpoint — no API token required
AI_URL = "https://text.pollinations.ai/{prompt}?model=openai&system={system}"

SYSTEM_PROMPT = (
    "You are a helpful Discord bot assistant. "
    "Keep replies concise and friendly. "
    "Use Discord markdown when useful."
)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
http_session: aiohttp.ClientSession | None = None


async def ask_ai(prompt: str) -> str:
    """Call the free Pollinations text API (no token required)."""
    if http_session is None or http_session.closed:
        return "HTTP session is not ready yet. Try again in a moment."

    url = AI_URL.format(
        prompt=urllib.parse.quote(prompt[:2000]),
        system=urllib.parse.quote(SYSTEM_PROMPT),
    )
    try:
        async with http_session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
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
    print("AI ready — no AI API token needed. Use !ai or mention me.")


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

    # Allow chatting by mentioning the bot
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
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "Set DISCORD_TOKEN to your Discord bot token.\n"
            "Get one free at https://discord.com/developers/applications\n"
            "AI itself needs no API key."
        )
    bot.run(token)


if __name__ == "__main__":
    main()
