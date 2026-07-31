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
  !ai / /ai <prompt>     Ask the AI
  !persona <name>        Set persona: default, funny, serious, coder
  !clear                 Clear your own chat memory
  !help                  Show help
  @Bot <prompt>          Chat by mention (uses reply context if you reply to a msg)

Owner-only (user id 1257060226029584459):
  !off / !shutdown       Pause AI replies (bot stays online)
  !on / !start           Resume AI replies
  !status                Show bot status
  !aichannel on|off      Enable/disable AI in this channel
  !resetmemory [user]    Reset memory for a user, or everyone if no user
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict, deque

try:
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
MEMORY_TURNS = 8          # user+assistant pairs kept per user
COOLDOWN_SECONDS = 4.0
MAX_PROMPT_CHARS = 2000
MAX_REPLY_CHARS = 1900
AI_RETRIES = 2

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

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
ai = AsyncClient()

# Runtime state
ai_enabled = True
disabled_channels: set[int] = set()
memory: dict[int, deque] = defaultdict(lambda: deque(maxlen=MEMORY_TURNS * 2))
personas: dict[int, str] = defaultdict(lambda: "default")
cooldowns: dict[int, float] = {}


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def owner_only():
    async def predicate(ctx: commands.Context) -> bool:
        if not is_owner(ctx.author.id):
            await ctx.send("Owner only.")
            return False
        return True

    return commands.check(predicate)


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


def check_cooldown(user_id: int) -> float | None:
    """Return remaining seconds if on cooldown, else None."""
    now = time.monotonic()
    ready_at = cooldowns.get(user_id, 0.0)
    if now < ready_at:
        return ready_at - now
    cooldowns[user_id] = now + COOLDOWN_SECONDS
    return None


def ai_blocked(channel_id: int | None) -> str | None:
    if not ai_enabled:
        return "AI is currently paused by the owner. Try again later."
    if channel_id is not None and channel_id in disabled_channels:
        return "AI is disabled in this channel."
    return None


def build_messages(
    user_id: int,
    prompt: str,
    image_urls: list[str] | None = None,
) -> list[dict]:
    persona = personas[user_id]
    system = PERSONAS.get(persona, PERSONAS["default"])
    messages: list[dict] = [{"role": "system", "content": system}]
    messages.extend(list(memory[user_id]))

    if image_urls:
        content: list[dict] = [{"type": "text", "text": prompt}]
        for url in image_urls[:3]:
            content.append({"type": "image_url", "image_url": {"url": url}})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": prompt})
    return messages


async def ask_ai(
    user_id: int,
    prompt: str,
    image_urls: list[str] | None = None,
) -> str:
    """Get an AI reply via g4f, with memory + retry fallback."""
    prompt = prompt[:MAX_PROMPT_CHARS]
    last_error = None

    # Try multimodal first when images exist; fall back to text + image URLs.
    attempts: list[tuple[str, list[str] | None]] = []
    if image_urls:
        attempts.append((prompt, image_urls))
        linked = prompt + "\n\nImage URL(s):\n" + "\n".join(image_urls[:3])
        attempts.append((linked[:MAX_PROMPT_CHARS], None))
    else:
        attempts.append((prompt, None))

    for content, images in attempts:
        messages = build_messages(user_id, content, images)
        for attempt in range(AI_RETRIES):
            try:
                response = await ai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                )
                text = (response.choices[0].message.content or "").strip()
                if not text:
                    raise RuntimeError("empty AI response")

                memory[user_id].append({"role": "user", "content": prompt})
                memory[user_id].append({"role": "assistant", "content": text})
                return text
            except Exception as exc:
                last_error = exc
                if attempt + 1 < AI_RETRIES:
                    await asyncio.sleep(1.0)

    return (
        f"Could not reach the AI after retries. Try again in a moment. ({last_error})"
    )

async def collect_prompt_and_images(
    message: discord.Message | None,
    raw_prompt: str,
) -> tuple[str, list[str]]:
    prompt = (raw_prompt or "").strip()
    image_urls: list[str] = []

    if message is not None:
        # Reply-to context
        if message.reference and message.reference.resolved:
            ref = message.reference.resolved
            if isinstance(ref, discord.Message) and not ref.author.bot:
                ref_text = (ref.content or "").strip()
                if ref_text:
                    prompt = f"Regarding this message: {ref_text}\n\n{prompt}".strip()
                for att in ref.attachments:
                    if (att.content_type or "").startswith("image/") or att.filename.lower().endswith(
                        (".png", ".jpg", ".jpeg", ".gif", ".webp")
                    ):
                        image_urls.append(att.url)

        for att in message.attachments:
            if (att.content_type or "").startswith("image/") or att.filename.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp")
            ):
                image_urls.append(att.url)

    if not prompt and image_urls:
        prompt = "Please describe and explain this image."
    return prompt, image_urls


async def handle_ai_request(
    *,
    user: discord.abc.User,
    channel: discord.abc.Messageable,
    channel_id: int | None,
    raw_prompt: str,
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

    prompt, image_urls = await collect_prompt_and_images(source_message, raw_prompt)
    if not prompt.strip() and not image_urls:
        tip = "Usage: `!ai <your question>` (you can also attach an image)."
        if interaction:
            await interaction.followup.send(tip, ephemeral=True)
        elif source_message:
            await source_message.reply(tip, mention_author=False)
        else:
            await channel.send(tip)
        return

    if interaction is None and source_message is not None:
        async with channel.typing():
            reply = await ask_ai(user.id, prompt, image_urls)
        await send_chunks(channel, reply, reply_to=source_message)
    else:
        reply = await ask_ai(user.id, prompt, image_urls)
        parts = chunk_text(reply)
        if interaction:
            await interaction.followup.send(parts[0])
            for part in parts[1:]:
                await interaction.followup.send(part)
        else:
            await send_chunks(channel, reply)


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as exc:
        print(f"Slash sync failed: {exc}")
    print(f"Logged in as {bot.user} (id={bot.user.id})")
    print("Ready. Owner can use !off / !on / !status / !resetmemory")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CheckFailure):
        return
    if isinstance(error, commands.CommandNotFound):
        return
    await ctx.send(f"Error: {error}")


@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    await ctx.send(
        "**Commands**\n"
        "`!ai <prompt>` / `/ai` — ask the AI\n"
        "`!persona default|funny|serious|coder` — set your style\n"
        "`!clear` — clear your chat memory\n"
        "`!help` — show this message\n"
        f"Or mention me / reply to a message: `@{bot.user.display_name} <prompt>`\n"
        "Attach an image with your question to ask about it.\n\n"
        "**Owner**\n"
        "`!off` / `!on` — pause / resume AI\n"
        "`!status` — bot status\n"
        "`!aichannel on|off` — AI in this channel\n"
        "`!resetmemory [@user]` — wipe memory"
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


@bot.tree.command(name="ai", description="Ask the AI anything")
@app_commands.describe(prompt="Your question or prompt", image="Optional image to ask about")
async def ai_slash(
    interaction: discord.Interaction,
    prompt: str,
    image: discord.Attachment | None = None,
):
    await interaction.response.defer(thinking=True)
    image_urls: list[str] = []
    if image is not None:
        ctype = image.content_type or ""
        if ctype.startswith("image/") or image.filename.lower().endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".webp")
        ):
            image_urls.append(image.url)
        else:
            await interaction.followup.send("Attachment must be an image.", ephemeral=True)
            return

    blocked = ai_blocked(interaction.channel_id)
    if blocked:
        await interaction.followup.send(blocked, ephemeral=True)
        return

    wait = check_cooldown(interaction.user.id)
    if wait is not None:
        await interaction.followup.send(f"Slow down — wait {wait:.1f}s.", ephemeral=True)
        return

    if not prompt.strip() and not image_urls:
        await interaction.followup.send("Give a prompt or an image.", ephemeral=True)
        return

    final_prompt = prompt.strip() or "Please describe and explain this image."
    reply = await ask_ai(interaction.user.id, final_prompt, image_urls or None)
    parts = chunk_text(reply)
    await interaction.followup.send(parts[0])
    for part in parts[1:]:
        await interaction.followup.send(part)


@bot.command(name="persona")
async def persona_cmd(ctx: commands.Context, name: str = ""):
    name = name.strip().lower()
    if name not in PERSONAS:
        await ctx.send(f"Choose one of: `{', '.join(PERSONAS)}`")
        return
    personas[ctx.author.id] = name
    await ctx.send(f"Persona set to **{name}**.")


@bot.command(name="clear")
async def clear_cmd(ctx: commands.Context):
    memory.pop(ctx.author.id, None)
    await ctx.send("Your chat memory was cleared.")


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
        f"Disabled channels: `{len(disabled_channels)}`"
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

    # Mention / reply chat
    if bot.user and bot.user.mentioned_in(message) and not message.mention_everyone:
        prompt = message.content
        for mention in message.mentions:
            prompt = prompt.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
        prompt = prompt.strip()
        # Allow image-only mentions
        if prompt or message.attachments or (
            message.reference and message.reference.resolved
        ):
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
