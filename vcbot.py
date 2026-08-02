"""
Discord permanent voice-channel bot — stays in VC 24/7, owner-only control.

Termux / PC setup:
  pkg update && pkg install python   # Termux
  pip install "discord.py[voice]"
  python vcbot.py

Discord setup:
  1. https://discord.com/developers/applications → New Application → Bot
  2. Copy the bot token into TOKEN below (or export DISCORD_TOKEN=...)
  3. Enable MESSAGE CONTENT INTENT under Bot → Privileged Gateway Intents
  4. Invite with scopes: bot
     Permissions: Connect, Speak, View Channels, Send Messages
  5. Join a voice channel, then run: !join
     The bot saves that channel and rejoins forever (restart + disconnects).

Owner-only commands (user id 1257060226029584459):
  !join [channel_id]   Join your current VC, or a channel id
  !leave               Leave VC and stop auto-rejoin for this session
  !stay                Re-enable permanent stay / rejoin the saved channel
  !vcstatus            Show current VC + reconnect state
  !vchelp              Show help
"""

from __future__ import annotations

import asyncio
import json
import os
import traceback
from pathlib import Path

try:
    import discord
    from discord.ext import commands, tasks
except ImportError:
    raise SystemExit(
        "Missing packages. Run:\n"
        '  pip install "discord.py[voice]"\n'
        "Then run this file again."
    )

# Paste your Discord bot token here (from the Developer Portal).
# Leave empty to use the DISCORD_TOKEN environment variable instead.
TOKEN = ""

# Only this Discord user can control the bot.
OWNER_ID = 1257060226029584459

# Optional: hardcode a channel id so the bot joins on first boot with no !join.
# Leave 0 to rely on !join (which saves the channel for next boots).
DEFAULT_VOICE_CHANNEL_ID = 0

STATE_FILE = Path(__file__).with_name("vcbot_state.json")
RECONNECT_DELAY_SECONDS = 3.0
WATCHDOG_INTERVAL_SECONDS = 15.0
COMMAND_PREFIX = "!"


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(data: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"[vcbot] failed to save state: {exc}")


intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

# Runtime flags
_stay_enabled = True
_reconnecting = False
_target_channel_id: int | None = None


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def owner_only():
    async def predicate(ctx: commands.Context) -> bool:
        if is_owner(ctx.author.id):
            return True
        # Silent ignore for everyone else — no reply, no hint that the bot exists.
        return False

    return commands.check(predicate)


def get_target_channel_id() -> int | None:
    global _target_channel_id
    if _target_channel_id:
        return _target_channel_id
    if DEFAULT_VOICE_CHANNEL_ID:
        return int(DEFAULT_VOICE_CHANNEL_ID)
    state = load_state()
    raw = state.get("voice_channel_id")
    if raw:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    return None


def set_target_channel_id(channel_id: int | None) -> None:
    global _target_channel_id
    _target_channel_id = channel_id
    state = load_state()
    if channel_id:
        state["voice_channel_id"] = channel_id
    else:
        state.pop("voice_channel_id", None)
    save_state(state)


async def resolve_voice_channel(channel_id: int) -> discord.VoiceChannel | None:
    channel = bot.get_channel(channel_id)
    if isinstance(channel, discord.VoiceChannel):
        return channel
    try:
        fetched = await bot.fetch_channel(channel_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None
    if isinstance(fetched, discord.VoiceChannel):
        return fetched
    return None


async def ensure_in_voice(reason: str = "ensure") -> bool:
    """Join / rejoin the saved voice channel. Returns True if connected."""
    global _reconnecting, _stay_enabled

    if not _stay_enabled:
        return False

    channel_id = get_target_channel_id()
    if not channel_id:
        print(f"[vcbot] no target channel ({reason})")
        return False

    channel = await resolve_voice_channel(channel_id)
    if channel is None:
        print(f"[vcbot] channel {channel_id} not found ({reason})")
        return False

    guild = channel.guild
    voice = guild.voice_client

    if voice and voice.is_connected():
        if voice.channel and voice.channel.id == channel.id:
            return True
        try:
            await voice.move_to(channel)
            print(f"[vcbot] moved to #{channel.name} ({reason})")
            return True
        except Exception as exc:
            print(f"[vcbot] move failed: {exc}")
            try:
                await voice.disconnect(force=True)
            except Exception:
                pass

    if _reconnecting:
        return False

    _reconnecting = True
    try:
        # Self-deafen keeps the bot "in" the channel with less audio overhead.
        await channel.connect(reconnect=True, self_deaf=True, self_mute=False)
        print(f"[vcbot] joined #{channel.name} ({reason})")
        return True
    except Exception as exc:
        print(f"[vcbot] join failed ({reason}): {exc}")
        traceback.print_exc()
        return False
    finally:
        _reconnecting = False


async def reconnect_loop(reason: str) -> None:
    """Keep trying until we are back in the target VC."""
    global _stay_enabled
    attempt = 0
    while _stay_enabled and not bot.is_closed():
        attempt += 1
        ok = await ensure_in_voice(reason=f"{reason}#{attempt}")
        if ok:
            return
        await asyncio.sleep(RECONNECT_DELAY_SECONDS)


@tasks.loop(seconds=WATCHDOG_INTERVAL_SECONDS)
async def voice_watchdog() -> None:
    if not _stay_enabled:
        return
    channel_id = get_target_channel_id()
    if not channel_id:
        return

    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.VoiceChannel):
        # Cache miss — still try ensure (it will fetch).
        await ensure_in_voice(reason="watchdog-fetch")
        return

    voice = channel.guild.voice_client
    if voice is None or not voice.is_connected():
        print("[vcbot] watchdog: not connected — rejoining")
        await reconnect_loop("watchdog")
    elif voice.channel is None or voice.channel.id != channel_id:
        print("[vcbot] watchdog: wrong channel — moving back")
        await ensure_in_voice(reason="watchdog-wrong-channel")


@voice_watchdog.before_loop
async def before_watchdog() -> None:
    await bot.wait_until_ready()


@bot.event
async def on_ready() -> None:
    print(f"[vcbot] logged in as {bot.user} (id={bot.user.id if bot.user else '?'})")
    print(f"[vcbot] owner-only control: {OWNER_ID}")
    if not voice_watchdog.is_running():
        voice_watchdog.start()
    # Join the permanently saved channel (or DEFAULT_VOICE_CHANNEL_ID).
    await reconnect_loop("startup")


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    """If the bot is disconnected or moved, snap back immediately."""
    if bot.user is None or member.id != bot.user.id:
        return
    if not _stay_enabled:
        return

    target = get_target_channel_id()
    if not target:
        return

    # Disconnected entirely
    if before.channel is not None and after.channel is None:
        print("[vcbot] disconnected from VC — reconnecting")
        await asyncio.sleep(0.5)
        await reconnect_loop("disconnect")
        return

    # Dragged to another channel
    if after.channel is not None and after.channel.id != target:
        print(f"[vcbot] moved to #{after.channel.name} — returning to locked channel")
        await asyncio.sleep(0.5)
        await ensure_in_voice(reason="moved")


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    # Swallow CheckFailure (non-owner) silently.
    if isinstance(error, commands.CheckFailure):
        return
    if isinstance(error, commands.CommandNotFound):
        return
    if is_owner(ctx.author.id):
        await ctx.reply(f"Error: {error}", mention_author=False)
    print(f"[vcbot] command error: {error}")


@bot.command(name="join")
@owner_only()
async def cmd_join(ctx: commands.Context, channel_id: int | None = None) -> None:
    """Join your current voice channel, or a given channel id. Locks permanent stay."""
    global _stay_enabled
    _stay_enabled = True

    target: discord.VoiceChannel | None = None

    if channel_id is not None:
        target = await resolve_voice_channel(channel_id)
        if target is None:
            await ctx.reply("That channel id is not a voice channel I can see.", mention_author=False)
            return
    else:
        if not isinstance(ctx.author, discord.Member) or ctx.author.voice is None or ctx.author.voice.channel is None:
            await ctx.reply(
                "Join a voice channel first, or use `!join <channel_id>`.",
                mention_author=False,
            )
            return
        ch = ctx.author.voice.channel
        if not isinstance(ch, discord.VoiceChannel):
            await ctx.reply("You need to be in a normal voice channel (not stage).", mention_author=False)
            return
        target = ch

    set_target_channel_id(target.id)
    ok = await ensure_in_voice(reason="!join")
    if ok:
        await ctx.reply(
            f"Staying permanently in **{target.name}** (`{target.id}`). "
            "I'll rejoin on disconnect and on restart.",
            mention_author=False,
        )
    else:
        await ctx.reply(
            "Couldn't connect. Check Connect/Speak permissions and try again.",
            mention_author=False,
        )


@bot.command(name="leave")
@owner_only()
async def cmd_leave(ctx: commands.Context) -> None:
    """Leave VC and pause permanent stay until !stay or !join."""
    global _stay_enabled
    _stay_enabled = False

    left_any = False
    for guild in bot.guilds:
        voice = guild.voice_client
        if voice and voice.is_connected():
            try:
                await voice.disconnect(force=True)
                left_any = True
            except Exception as exc:
                print(f"[vcbot] leave error: {exc}")

    # Keep the saved channel id so !stay can restore without re-picking.
    await ctx.reply(
        "Left voice. Permanent stay paused. Use `!stay` or `!join` to lock in again."
        + ("" if left_any else " (I wasn't in a VC.)"),
        mention_author=False,
    )


@bot.command(name="stay")
@owner_only()
async def cmd_stay(ctx: commands.Context) -> None:
    """Re-enable permanent stay and join the saved channel."""
    global _stay_enabled
    _stay_enabled = True

    channel_id = get_target_channel_id()
    if not channel_id:
        await ctx.reply("No saved channel yet. Use `!join` while in a VC.", mention_author=False)
        return

    ok = await ensure_in_voice(reason="!stay")
    if ok:
        channel = await resolve_voice_channel(channel_id)
        name = channel.name if channel else str(channel_id)
        await ctx.reply(f"Permanent stay ON — locked to **{name}**.", mention_author=False)
    else:
        await ctx.reply("Couldn't rejoin the saved channel. Check permissions.", mention_author=False)


@bot.command(name="vcstatus")
@owner_only()
async def cmd_vcstatus(ctx: commands.Context) -> None:
    """Show connection / lock status."""
    channel_id = get_target_channel_id()
    lines = [
        f"Owner: `{OWNER_ID}`",
        f"Permanent stay: `{'ON' if _stay_enabled else 'OFF'}`",
        f"Saved channel id: `{channel_id or 'none'}`",
    ]

    connected = []
    for guild in bot.guilds:
        voice = guild.voice_client
        if voice and voice.is_connected() and voice.channel:
            connected.append(f"{guild.name} → **{voice.channel.name}** (`{voice.channel.id}`)")
    if connected:
        lines.append("Connected: " + "; ".join(connected))
    else:
        lines.append("Connected: none")

    await ctx.reply("\n".join(lines), mention_author=False)


@bot.command(name="vchelp")
@owner_only()
async def cmd_vchelp(ctx: commands.Context) -> None:
    await ctx.reply(
        "**VC stay bot (owner only)**\n"
        "`!join` — join your current VC and lock permanent stay\n"
        "`!join <channel_id>` — join / lock a specific voice channel\n"
        "`!leave` — leave and pause auto-rejoin\n"
        "`!stay` — re-enable permanent stay on the saved channel\n"
        "`!vcstatus` — show status\n"
        "`!vchelp` — this help",
        mention_author=False,
    )


def main() -> None:
    token = (TOKEN or os.environ.get("DISCORD_TOKEN") or "").strip()
    if not token:
        raise SystemExit(
            "No bot token set. Paste it into TOKEN in vcbot.py, "
            "or: export DISCORD_TOKEN='your_token_here'"
        )

    # Ensure PyNaCl is available for voice; discord.py[voice] installs it.
    try:
        import nacl  # noqa: F401
    except ImportError:
        raise SystemExit(
            "Voice support missing. Install with:\n"
            '  pip install "discord.py[voice]"\n'
            "(that pulls in PyNaCl)"
        )

    print("[vcbot] starting — permanent VC stay, owner-only access")
    bot.run(token)


if __name__ == "__main__":
    main()
