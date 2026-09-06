#!/usr/bin/env python3
"""Seekara Status Bot — one command: !status / /status"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from typing import Any, Dict

import discord
from discord.ext import commands

TOKEN = ""

STATUS_URL = os.environ.get(
    "SEEKARA_STATUS_URL",
    "http://13.140.151.124:5055/status",
).strip()

FALLBACKS = {
    "beacon": "http://13.140.151.124:5000/health",
    "capsule": "",
    "seekdesk": "",
}

WATCH = ["beacon", "capsule", "seekdesk"]


def http_get_json(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "SeekaraStatusBot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw or "{}")


def fetch_status() -> Dict[str, bool]:
    """Return {name: online bool} for each watched service."""
    try:
        data = http_get_json(STATUS_URL)
        services = data.get("services") or {}
        out = {}
        for name in WATCH:
            s = services.get(name) or {}
            out[name] = bool(s.get("up"))
        return out
    except Exception:
        pass

    out: Dict[str, bool] = {}
    for name in WATCH:
        url = FALLBACKS.get(name) or ""
        if not url:
            out[name] = False
            continue
        try:
            payload = http_get_json(url)
            out[name] = bool(payload.get("ok") or payload.get("status") == "online")
        except Exception:
            out[name] = False
    return out


def format_status(states: Dict[str, bool]) -> str:
    lines = []
    for name in WATCH:
        online = states.get(name, False)
        lines.append(f"**{name}**: {'online' if online else 'offline'}")
    return "\n".join(lines)


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Seekara Status Bot online as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"synced {len(synced)} slash command(s)")
    except Exception as e:
        print("slash sync failed:", e)


@bot.hybrid_command(name="status", description="Show beacon / capsule / seekdesk online or offline")
async def status(ctx: commands.Context):
    states = await asyncio.to_thread(fetch_status)
    await ctx.send(format_status(states))


def main() -> None:
    if not TOKEN or TOKEN.startswith("PUT_"):
        raise SystemExit("Set TOKEN in bot.py")
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
