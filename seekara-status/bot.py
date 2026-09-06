#!/usr/bin/env python3
"""
Seekara Status Bot — reports which of beacon / capsule / seekdesk
are up or down on 13.140.151.124
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import discord
from discord.ext import commands, tasks

# Put your Discord bot token here, or set env SEEKARA_STATUS_TOKEN
TOKEN = os.environ.get("SEEKARA_STATUS_TOKEN", "").strip()

STATUS_URL = os.environ.get(
    "SEEKARA_STATUS_URL",
    "http://13.140.151.124:5055/status",
).strip()

FALLBACKS = {
    "beacon": os.environ.get("SEEKARA_BEACON_URL", "http://13.140.151.124:5000/health"),
    "capsule": os.environ.get("SEEKARA_CAPSULE_URL", "").strip(),
    "seekdesk": os.environ.get("SEEKARA_SEEKDESK_URL", "").strip(),
}

WATCH = ["beacon", "capsule", "seekdesk"]
CHECK_SECONDS = int(os.environ.get("SEEKARA_STATUS_INTERVAL", "300"))
STATUS_CHANNEL_ID = int(os.environ.get("SEEKARA_STATUS_CHANNEL_ID", "0") or "0")
HOST = "13.140.151.124"


def http_get_json(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "SeekaraStatusBot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw or "{}")


def fetch_status() -> Dict[str, Any]:
    try:
        data = http_get_json(STATUS_URL)
        if isinstance(data.get("services"), dict):
            data.setdefault("host", HOST)
            data["source"] = "agent"
            return data
    except Exception as e:
        agent_error = str(e)
    else:
        agent_error = "invalid agent payload"

    services: Dict[str, Any] = {}
    for name in WATCH:
        url = FALLBACKS.get(name) or ""
        if not url:
            services[name] = {
                "name": name,
                "up": False,
                "status": "no-endpoint",
                "detail": "status agent unreachable and no fallback URL",
            }
            continue
        try:
            payload = http_get_json(url)
            up = bool(payload.get("ok") or payload.get("status") == "online")
            services[name] = {
                "name": name,
                "up": up,
                "status": "online" if up else "down",
                "detail": "fallback health check",
            }
        except Exception as err:
            services[name] = {
                "name": name,
                "up": False,
                "status": "down",
                "detail": str(err),
            }

    return {
        "ok": False,
        "host": HOST,
        "error": agent_error,
        "services": services,
        "source": "fallback",
    }


def format_memory(n: Any) -> str:
    try:
        n = int(n)
    except Exception:
        return "—"
    if n < 1024:
        return f"{n} B"
    if n < 1024**2:
        return f"{n / 1024:.1f} KB"
    if n < 1024**3:
        return f"{n / 1024**2:.1f} MB"
    return f"{n / 1024**3:.2f} GB"


def build_embed(data: Dict[str, Any]) -> discord.Embed:
    services = data.get("services") or {}
    up_count = sum(1 for s in services.values() if s.get("up"))
    total = len(WATCH)
    all_up = up_count == total

    if all_up:
        color = discord.Color.green()
    elif up_count == 0:
        color = discord.Color.red()
    else:
        color = discord.Color.orange()

    embed = discord.Embed(
        title="Seekara Status",
        description=f"Host `{data.get('host') or HOST}` · **{up_count}/{total}** up",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    for name in WATCH:
        s = services.get(name) or {"up": False, "status": "unknown"}
        icon = "🟢" if s.get("up") else "🔴"
        status = str(s.get("status") or ("online" if s.get("up") else "down"))
        lines = [f"{icon} **{status}**"]
        if s.get("cpu") is not None:
            lines.append(f"CPU: {s.get('cpu')}%")
        if s.get("memory") is not None:
            lines.append(f"Mem: {format_memory(s.get('memory'))}")
        if s.get("restarts") is not None:
            lines.append(f"Restarts: {s.get('restarts')}")
        if s.get("detail") and not s.get("up"):
            lines.append(f"_{s.get('detail')}_")
        embed.add_field(name=name, value="\n".join(lines), inline=True)

    footer = "Seekara Status Bot"
    if data.get("source") == "fallback":
        footer += " · fallback checks (install agent for full pm2 status)"
    embed.set_footer(text=footer)
    return embed


class StatusBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned_or("!", "?"),
            intents=intents,
        )

    async def setup_hook(self) -> None:
        await self.tree.sync()
        if STATUS_CHANNEL_ID:
            self.auto_status.start()

    async def on_ready(self) -> None:
        print(f"Seekara Status Bot online as {self.user}")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="beacon · capsule · seekdesk",
            )
        )


bot = StatusBot()


async def get_status_embed() -> Tuple[discord.Embed, Dict[str, Any]]:
    data = await asyncio.to_thread(fetch_status)
    return build_embed(data), data


@bot.hybrid_command(name="status", description="Check beacon / capsule / seekdesk on the VPS")
async def status_cmd(ctx: commands.Context) -> None:
    async with ctx.typing():
        embed, _ = await get_status_embed()
    await ctx.send(embed=embed)


@bot.tree.command(name="seekara", description="Seekara fleet status (beacon, capsule, seekdesk)")
async def seekara_slash(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    embed, _ = await get_status_embed()
    await interaction.followup.send(embed=embed)


@bot.command(name="pingbots")
async def pingbots(ctx: commands.Context) -> None:
    """Alias for !status"""
    await status_cmd(ctx)


@tasks.loop(seconds=CHECK_SECONDS)
async def auto_status() -> None:
    if not STATUS_CHANNEL_ID:
        return
    channel = bot.get_channel(STATUS_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(STATUS_CHANNEL_ID)
        except Exception:
            return
    embed, _ = await get_status_embed()
    try:
        await channel.send(embed=embed)
    except Exception as e:
        print("auto_status failed:", e)


@auto_status.before_loop
async def before_auto() -> None:
    await bot.wait_until_ready()


def main() -> None:
    if not TOKEN:
        raise SystemExit(
            "Set TOKEN in seekara-status/bot.py or env SEEKARA_STATUS_TOKEN"
        )
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
