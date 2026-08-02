"""
Discord TTS Robot Voice Engine — all in one file.

Joins a voice channel and speaks text with a robotic TTS voice.
Free: Microsoft Edge TTS (no API key) + ffmpeg robot FX.

Setup:
  pip install "discord.py[voice]" edge-tts PyNaCl
  # need ffmpeg on PATH (pkg install ffmpeg / apt install ffmpeg)

  python bot_tts.py            # start bot
  python bot_tts.py --selftest # synthesize a sample WAV without Discord

Discord setup:
  1. https://discord.com/developers/applications → New Application → Bot
  2. Copy the bot token into TOKEN below (or export DISCORD_TOKEN=...)
  3. Enable MESSAGE CONTENT INTENT
  4. Invite with scopes: bot + applications.commands
     Permissions: Connect, Speak, Send Messages, Use Voice Activity

Commands:
  !join / !leave              Join / leave your voice channel
  !tts / !say <text>          Speak text in VC (robot voice)
  !voice <preset>             robot | android | dalek | chip | clean
  !speaker <name>             List/set Edge TTS speaker
  !speed <0.7-1.4>            Speaking rate multiplier
  !auto on|off                Auto-read new messages in this text channel
  !stop                       Stop speaking / clear queue
  !ttshelp                    Help
  @Bot <text>                 Same as !tts
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque, Optional

try:
    import discord
    from discord import app_commands
    from discord.ext import commands
except ImportError:
    raise SystemExit(
        "Missing packages. Run:\n"
        '  pip install "discord.py[voice]" edge-tts PyNaCl\n'
        "Then run this file again."
    )

try:
    import edge_tts
except ImportError:
    raise SystemExit(
        "Missing edge-tts. Run:\n"
        "  pip install edge-tts\n"
        "Then run this file again."
    )

# Paste your Discord bot token here (from the Developer Portal).
# Leave empty to use the DISCORD_TOKEN environment variable instead.
TOKEN = ""

OWNER_ID = 1257060226029584459
COOLDOWN_SECONDS = 2.0
MAX_TTS_CHARS = 500
MAX_QUEUE = 8
DEFAULT_VOICE = "en-US-GuyNeural"
DEFAULT_PRESET = "robot"
DEFAULT_RATE = 1.0

# Edge speakers that work well with robot FX
SPEAKERS = {
    "guy": "en-US-GuyNeural",
    "ryan": "en-GB-RyanNeural",
    "christopher": "en-US-ChristopherNeural",
    "davis": "en-US-DavisNeural",
    "tony": "en-US-TonyNeural",
    "sonia": "en-GB-SoniaNeural",
    "aria": "en-US-AriaNeural",
    "jenny": "en-US-JennyNeural",
}

# ffmpeg filter chains for robot-ish voice colors
PRESETS = {
    "robot": {
        "label": "Classic robot (metallic, mid pitch)",
        # slight pitch down + tremolo + thin bandpass for metallic tone
        "af": (
            "asetrate=24000*0.92,aresample=24000,atempo=1.087,"
            "highpass=f=180,lowpass=f=3400,"
            "tremolo=f=28:d=0.55,"
            "afftfilt=real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)':win_size=512:overlap=0.75,"
            "volume=1.35"
        ),
    },
    "android": {
        "label": "Android assistant (bright digital)",
        "af": (
            "asetrate=24000*1.12,aresample=24000,atempo=0.893,"
            "highpass=f=250,lowpass=f=4200,"
            "tremolo=f=35:d=0.35,"
            "volume=1.25"
        ),
    },
    "dalek": {
        "label": "Dalek / deep ring-mod",
        "af": (
            "asetrate=24000*0.78,aresample=24000,atempo=1.282,"
            "highpass=f=120,lowpass=f=2800,"
            "tremolo=f=22:d=0.7,"
            "afftfilt=real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)':win_size=256:overlap=0.5,"
            "volume=1.4"
        ),
    },
    "chip": {
        "label": "Tiny chip / toy robot",
        "af": (
            "asetrate=24000*1.35,aresample=24000,atempo=0.741,"
            "highpass=f=400,lowpass=f=5000,"
            "tremolo=f=45:d=0.4,"
            "volume=1.2"
        ),
    },
    "clean": {
        "label": "Clean TTS (no robot FX)",
        "af": "volume=1.0",
    },
}

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
MENTION_RE = re.compile(r"<@!?\d+>|<@&\d+>|<#\d+>")
EMOJI_RE = re.compile(r"<a?:\w+:\d+>")
WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class GuildTTS:
    preset: str = DEFAULT_PRESET
    speaker: str = DEFAULT_VOICE
    rate: float = DEFAULT_RATE
    auto_channel: Optional[int] = None
    queue: Deque[str] = field(default_factory=deque)
    playing: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
guild_state: dict[int, GuildTTS] = defaultdict(GuildTTS)
cooldowns: dict[int, float] = {}


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError(
            "ffmpeg not found on PATH. Install it:\n"
            "  Termux: pkg install ffmpeg\n"
            "  Debian/Ubuntu: sudo apt install ffmpeg\n"
            "  macOS: brew install ffmpeg"
        )
    return path


def sanitize_text(text: str) -> str:
    text = text or ""
    text = URL_RE.sub(" link ", text)
    text = MENTION_RE.sub(" ", text)
    text = EMOJI_RE.sub(" ", text)
    text = text.replace("@everyone", " everyone ").replace("@here", " here ")
    text = WHITESPACE_RE.sub(" ", text).strip()
    if len(text) > MAX_TTS_CHARS:
        text = text[: MAX_TTS_CHARS - 1].rstrip() + "…"
    return text


def rate_to_edge(rate: float) -> str:
    # edge-tts wants ±N%
    pct = int(round((rate - 1.0) * 100))
    pct = max(-50, min(100, pct))
    return f"{pct:+d}%"


async def synthesize_raw(text: str, speaker: str, rate: float) -> bytes:
    """Generate MP3 bytes with edge-tts."""
    communicate = edge_tts.Communicate(text, voice=speaker, rate=rate_to_edge(rate))
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    data = buf.getvalue()
    if not data:
        raise RuntimeError("TTS produced no audio. Try different text or speaker.")
    return data


def apply_robot_fx(mp3_bytes: bytes, preset: str, out_wav: Path) -> None:
    """Run ffmpeg robot filter → 48kHz stereo WAV (Discord-friendly)."""
    ffmpeg = require_ffmpeg()
    af = PRESETS.get(preset, PRESETS[DEFAULT_PRESET])["af"]
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(mp3_bytes)
        src = tmp.name
    try:
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            src,
            "-af",
            af,
            "-ac",
            "2",
            "-ar",
            "48000",
            "-sample_fmt",
            "s16",
            str(out_wav),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not out_wav.exists() or out_wav.stat().st_size == 0:
            err = (proc.stderr or proc.stdout or "unknown ffmpeg error").strip()
            raise RuntimeError(f"ffmpeg robot FX failed: {err[:400]}")
    finally:
        try:
            os.unlink(src)
        except OSError:
            pass


async def make_speech_file(text: str, speaker: str, rate: float, preset: str) -> Path:
    mp3 = await synthesize_raw(text, speaker, rate)
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    out = Path(path)
    try:
        await asyncio.to_thread(apply_robot_fx, mp3, preset, out)
    except Exception:
        out.unlink(missing_ok=True)
        raise
    return out


def on_cooldown(user_id: int) -> Optional[float]:
    now = time.monotonic()
    last = cooldowns.get(user_id, 0.0)
    left = COOLDOWN_SECONDS - (now - last)
    if left > 0:
        return left
    cooldowns[user_id] = now
    return None


async def ensure_voice(ctx: commands.Context) -> Optional[discord.VoiceClient]:
    if not ctx.author or not isinstance(ctx.author, discord.Member):
        await ctx.send("Join a voice channel first.")
        return None
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("Join a voice channel first, then use `!join` or `!tts`.")
        return None

    channel = ctx.author.voice.channel
    vc = ctx.guild.voice_client if ctx.guild else None
    if vc and vc.is_connected():
        if vc.channel and vc.channel.id != channel.id:
            await vc.move_to(channel)
        return vc
    try:
        return await channel.connect(reconnect=True, timeout=15.0)
    except Exception as exc:
        await ctx.send(f"Could not join voice: `{exc}`")
        return None


async def play_next(guild_id: int, vc: discord.VoiceClient) -> None:
    state = guild_state[guild_id]
    async with state.lock:
        if state.playing:
            return
        if not state.queue:
            return
        text = state.queue.popleft()
        state.playing = True

    wav_path: Optional[Path] = None
    try:
        wav_path = await make_speech_file(text, state.speaker, state.rate, state.preset)

        def _after(err: Optional[Exception]) -> None:
            async def _cleanup() -> None:
                state.playing = False
                if wav_path:
                    wav_path.unlink(missing_ok=True)
                if err:
                    print(f"[tts] playback error: {err}", file=sys.stderr)
                if guild_id in guild_state and state.queue and vc.is_connected():
                    await play_next(guild_id, vc)

            try:
                asyncio.run_coroutine_threadsafe(_cleanup(), bot.loop)
            except Exception as e:
                state.playing = False
                print(f"[tts] cleanup error: {e}", file=sys.stderr)

        source = discord.FFmpegPCMAudio(
            str(wav_path),
            options="-loglevel error",
        )
        # volume boost wrapper
        source = discord.PCMVolumeTransformer(source, volume=1.0)
        vc.play(source, after=_after)
    except Exception as exc:
        state.playing = False
        if wav_path:
            wav_path.unlink(missing_ok=True)
        print(f"[tts] synthesize/play failed: {exc}", file=sys.stderr)
        # try next item so one bad clip doesn't stall the queue
        if state.queue and vc.is_connected():
            await play_next(guild_id, vc)


async def enqueue_tts(
    guild: discord.Guild,
    vc: discord.VoiceClient,
    text: str,
    *,
    notify_channel: Optional[discord.abc.Messageable] = None,
) -> None:
    clean = sanitize_text(text)
    if not clean:
        if notify_channel:
            await notify_channel.send("Nothing to say after cleaning the text.")
        return
    state = guild_state[guild.id]
    if len(state.queue) >= MAX_QUEUE:
        if notify_channel:
            await notify_channel.send(f"Queue full ({MAX_QUEUE}). Use `!stop` or wait.")
        return
    was_busy = state.playing or bool(state.queue)
    state.queue.append(clean)
    if notify_channel:
        extra = f" · queued ({len(state.queue)})" if was_busy else ""
        await notify_channel.send(f"🔊 `{state.preset}` · {len(clean)} chars{extra}")
    await play_next(guild.id, vc)


# ── Commands ───────────────────────────────────────────────────────────────


@bot.event
async def on_ready():
    try:
        require_ffmpeg()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as exc:
        print(f"Slash sync failed: {exc}", file=sys.stderr)
    print(f"Logged in as {bot.user} — TTS Robot Voice Engine ready")


@bot.command(name="join")
async def join_cmd(ctx: commands.Context):
    vc = await ensure_voice(ctx)
    if vc and vc.channel:
        await ctx.send(f"Joined **{vc.channel.name}**. Use `!tts <text>` to speak.")


@bot.command(name="leave", aliases=["disconnect", "dc"])
async def leave_cmd(ctx: commands.Context):
    if not ctx.guild:
        return
    state = guild_state[ctx.guild.id]
    state.queue.clear()
    vc = ctx.guild.voice_client
    if vc and vc.is_connected():
        if vc.is_playing():
            vc.stop()
        await vc.disconnect()
        await ctx.send("Left voice channel.")
    else:
        await ctx.send("Not in a voice channel.")


@bot.command(name="tts", aliases=["say", "speak", "robot"])
async def tts_cmd(ctx: commands.Context, *, text: str = ""):
    left = on_cooldown(ctx.author.id)
    if left:
        await ctx.send(f"Slow down — try again in {left:.1f}s.")
        return
    if not text.strip():
        await ctx.send("Usage: `!tts <text>`")
        return
    if not ctx.guild:
        await ctx.send("TTS only works in servers.")
        return
    vc = await ensure_voice(ctx)
    if not vc:
        return
    await enqueue_tts(ctx.guild, vc, text, notify_channel=ctx.channel)


@bot.command(name="voice", aliases=["preset", "fx"])
async def voice_cmd(ctx: commands.Context, name: str = ""):
    if not ctx.guild:
        return
    name = name.strip().lower()
    state = guild_state[ctx.guild.id]
    if not name:
        lines = [f"**Current preset:** `{state.preset}`", ""]
        for key, meta in PRESETS.items():
            mark = "←" if key == state.preset else ""
            lines.append(f"`{key}` — {meta['label']} {mark}")
        await ctx.send("\n".join(lines))
        return
    if name not in PRESETS:
        choices = ", ".join(f"`{k}`" for k in PRESETS)
        await ctx.send(f"Unknown preset. Choose: {choices}")
        return
    state.preset = name
    await ctx.send(f"Voice preset set to **{name}** — {PRESETS[name]['label']}")


@bot.command(name="speaker")
async def speaker_cmd(ctx: commands.Context, name: str = ""):
    if not ctx.guild:
        return
    name = name.strip().lower()
    state = guild_state[ctx.guild.id]
    if not name:
        lines = [f"**Current speaker:** `{state.speaker}`", "", "Shortcuts:"]
        for short, full in SPEAKERS.items():
            mark = "←" if full == state.speaker else ""
            lines.append(f"`{short}` → `{full}` {mark}")
        lines.append("\nOr paste any Edge voice id, e.g. `en-US-GuyNeural`.")
        await ctx.send("\n".join(lines))
        return
    speaker = SPEAKERS.get(name, name)
    state.speaker = speaker
    await ctx.send(f"Speaker set to `{speaker}`")


@bot.command(name="speed", aliases=["rate"])
async def speed_cmd(ctx: commands.Context, value: str = ""):
    if not ctx.guild:
        return
    state = guild_state[ctx.guild.id]
    if not value:
        await ctx.send(f"Current speed: `{state.rate:.2f}` (range 0.7–1.4)")
        return
    try:
        rate = float(value)
    except ValueError:
        await ctx.send("Usage: `!speed 1.0` (0.7–1.4)")
        return
    rate = max(0.7, min(1.4, rate))
    state.rate = rate
    await ctx.send(f"Speed set to `{rate:.2f}` ({rate_to_edge(rate)})")


@bot.command(name="auto")
async def auto_cmd(ctx: commands.Context, mode: str = ""):
    if not ctx.guild or not ctx.channel:
        return
    mode = mode.strip().lower()
    state = guild_state[ctx.guild.id]
    if mode not in {"on", "off"}:
        status = "on" if state.auto_channel == ctx.channel.id else "off"
        await ctx.send(f"Auto-read is **{status}** here. Usage: `!auto on` / `!auto off`")
        return
    if mode == "on":
        state.auto_channel = ctx.channel.id
        vc = await ensure_voice(ctx)
        if not vc:
            state.auto_channel = None
            return
        await ctx.send(
            "Auto-read **on** for this channel. I'll speak new messages in VC. "
            "`!auto off` to stop."
        )
    else:
        state.auto_channel = None
        await ctx.send("Auto-read **off**.")


@bot.command(name="stop", aliases=["skip", "shutup"])
async def stop_cmd(ctx: commands.Context):
    if not ctx.guild:
        return
    state = guild_state[ctx.guild.id]
    cleared = len(state.queue)
    state.queue.clear()
    vc = ctx.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
    state.playing = False
    await ctx.send(f"Stopped. Cleared {cleared} queued line(s).")


@bot.command(name="ttshelp", aliases=["tts?", "robothelp"])
async def help_cmd(ctx: commands.Context):
    await ctx.send(
        "**TTS Robot Voice Engine**\n"
        "`!join` / `!leave` — voice channel\n"
        "`!tts <text>` — speak with robot voice (`!say` works too)\n"
        "`!voice [robot|android|dalek|chip|clean]` — FX preset\n"
        "`!speaker [guy|ryan|…]` — TTS speaker\n"
        "`!speed <0.7-1.4>` — speaking rate\n"
        "`!auto on|off` — auto-read this text channel in VC\n"
        "`!stop` — stop + clear queue\n"
        "Mention me with text to speak it."
    )


@bot.tree.command(name="tts", description="Speak text in your voice channel (robot voice)")
@app_commands.describe(text="What the robot should say")
async def tts_slash(interaction: discord.Interaction, text: str):
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Server only.", ephemeral=True)
        return
    left = on_cooldown(interaction.user.id)
    if left:
        await interaction.response.send_message(
            f"Slow down — try again in {left:.1f}s.", ephemeral=True
        )
        return
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message(
            "Join a voice channel first.", ephemeral=True
        )
        return
    await interaction.response.defer(thinking=True)
    channel = interaction.user.voice.channel
    vc = interaction.guild.voice_client
    try:
        if vc and vc.is_connected():
            if vc.channel and vc.channel.id != channel.id:
                await vc.move_to(channel)
        else:
            vc = await channel.connect(reconnect=True, timeout=15.0)
    except Exception as exc:
        await interaction.followup.send(f"Could not join voice: `{exc}`")
        return
    assert vc is not None
    await enqueue_tts(interaction.guild, vc, text, notify_channel=None)
    state = guild_state[interaction.guild.id]
    await interaction.followup.send(
        f"🔊 Speaking with `{state.preset}` ({len(sanitize_text(text))} chars)"
    )


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # @Bot <text> → TTS
    if bot.user and bot.user.mentioned_in(message) and not message.mention_everyone:
        if message.guild and isinstance(message.author, discord.Member):
            text = message.content
            for mention in message.mentions:
                text = text.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
            text = text.strip()
            if text:
                left = on_cooldown(message.author.id)
                if left:
                    await message.channel.send(f"Slow down — try again in {left:.1f}s.")
                    return
                # fake a minimal context for ensure_voice
                ctx = await bot.get_context(message)
                vc = await ensure_voice(ctx)
                if vc:
                    await enqueue_tts(message.guild, vc, text, notify_channel=message.channel)
                return

    # auto-read channel
    if message.guild and message.channel:
        state = guild_state[message.guild.id]
        if state.auto_channel == message.channel.id:
            vc = message.guild.voice_client
            if vc and vc.is_connected():
                clean = sanitize_text(message.content)
                if clean and not message.content.startswith("!"):
                    # prefix with display name so listeners know who
                    name = message.author.display_name[:24]
                    line = f"{name} says: {clean}"
                    if len(state.queue) < MAX_QUEUE:
                        state.queue.append(sanitize_text(line))
                        await play_next(message.guild.id, vc)

    await bot.process_commands(message)


# ── Self-test (no Discord token) ───────────────────────────────────────────


async def selftest(out_dir: Path) -> int:
    require_ffmpeg()
    out_dir.mkdir(parents=True, exist_ok=True)
    sample = "Hello. I am a robot voice engine for Discord."
    print(f"Synthesizing with speaker={DEFAULT_VOICE} …")
    mp3 = await synthesize_raw(sample, DEFAULT_VOICE, 1.0)
    ok = 0
    for name in PRESETS:
        wav = out_dir / f"tts_{name}.wav"
        print(f"  preset={name} → {wav}")
        apply_robot_fx(mp3, name, wav)
        size = wav.stat().st_size
        if size < 1000:
            print(f"  FAIL: {name} too small ({size} bytes)")
            return 1
        print(f"  ok ({size} bytes)")
        ok += 1
    print(f"Selftest passed — {ok} presets written to {out_dir}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Discord TTS Robot Voice Engine")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Generate sample WAVs for each voice preset (no Discord token needed)",
    )
    parser.add_argument(
        "--outdir",
        default="tts_selftest",
        help="Output folder for --selftest (default: tts_selftest)",
    )
    args = parser.parse_args()

    if args.selftest:
        raise SystemExit(asyncio.run(selftest(Path(args.outdir))))

    token = (TOKEN or os.getenv("DISCORD_TOKEN", "")).strip()
    if not token:
        raise SystemExit(
            "Add your Discord bot token:\n"
            "  1. Open bot_tts.py\n"
            "  2. Paste it into TOKEN = \"...\" near the top\n"
            "  Or: export DISCORD_TOKEN=\"your-token\"\n"
            "Get a free token at https://discord.com/developers/applications"
        )
    bot.run(token)


if __name__ == "__main__":
    main()
