# ============================================================
# Beacon Discord Bot
# Full build:
# - Slash commands + * prefix commands
# - Warnings/moderation
# - Channel tools
# - Backups saved on Raspberry Pi
# - Saves server name + icon bytes
# - Antinuke trigger ONLY: 5 channel creates in 10 seconds
# - On trigger: punish, wipe server structure, restore from backup, then re-backup
# Free: sticky, polls, reminders, basic XP, economy, AI image generation, emoji steal
# Premium: temprole, autoresponder, invite tracker
# ============================================================

TOKEN = ""  # paste bot token, or set DISCORD_TOKEN
PREFIX = "*"

DASHBOARD_PORT = 5000
DASHBOARD_HTML_FILE = "/home/logsto/smmod/dashboard.html"

# Discord OAuth dashboard login
# Put these from Discord Developer Portal > OAuth2
DISCORD_CLIENT_ID = "1470483724909936823"
DISCORD_CLIENT_SECRET = ""  # paste OAuth client secret
DISCORD_REDIRECT_URI = "https://dashboard.locker-rover.dev/callback"
DISCORD_API = "https://discord.com/api/v10"

# Offline / power-loss announce target
POWER_ALERT_GUILD_ID = 1511411841421807839
POWER_ALERT_MESSAGE = "BOT LOST POWER, OWNER WILL RESTART SOON"
# Optional Discord webhook URL in that server (used by external uptime monitors for HARD power cuts)
POWER_ALERT_WEBHOOK_URL = ""

import discord
from discord.ext import commands
from discord import app_commands
from discord.errors import ConnectionClosed
import json
import logging
import os
import random
import re
import signal
import time
import tempfile
from pathlib import Path
import asyncio
import base64
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from http.cookies import SimpleCookie
import urllib.request
import urllib.parse
import secrets
import sqlite3
import hashlib
import math
import struct
import zlib
import io

# Always read/write premium next to this script (not the shell's cwd).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREMIUM_FILE = os.path.join(BASE_DIR, "premium_users.txt")
STAFF_FILE = os.path.join(BASE_DIR, "seekara_staff.txt")
BOT_OWNER_ID = 1257060226029584459
MENTION_ID_RE = re.compile(r"<@!?(\d+)>")


def normalize_premium_id(value):
    """Turn raw id / mention / quoted paste into a digits-only snowflake string."""
    if value is None:
        return None
    text = str(value).strip().strip("\ufeff").strip().strip("\"'`")
    if not text:
        return None
    mention = MENTION_ID_RE.fullmatch(text) or MENTION_ID_RE.search(text)
    if mention:
        text = mention.group(1)
    # Keep digits only (handles accidental commas/spaces/labels)
    digits = "".join(ch for ch in text if ch.isdigit())
    if 5 <= len(digits) <= 25:
        return digits
    return None


def load_premium_ids():
    ids = set()
    try:
        with open(PREMIUM_FILE, "r", encoding="utf-8") as f:
            for line in f:
                uid = normalize_premium_id(line)
                if uid:
                    ids.add(uid)
    except FileNotFoundError:
        pass
    return ids


def save_premium_ids(ids):
    tmp = PREMIUM_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for uid in sorted(ids, key=lambda x: int(x)):
            f.write(f"{uid}\n")
    os.replace(tmp, PREMIUM_FILE)


def is_premium(user_id):
    """True if this Discord user id has Beacon Premium."""
    uid = normalize_premium_id(user_id)
    if not uid:
        return False
    # Bot owner is always premium
    if uid == str(BOT_OWNER_ID):
        return True
    return uid in load_premium_ids()


def has_premium_access(guild, user=None):
    """Custom-command unlock: acting premium user OR premium server owner."""
    if user is not None and is_premium(getattr(user, "id", user)):
        return True
    if guild is not None and is_premium(getattr(guild, "owner_id", None)):
        return True
    return False


def add_premium_user(user_id):
    uid = normalize_premium_id(user_id)
    if not uid:
        return False, None
    ids = load_premium_ids()
    if uid in ids:
        return False, uid
    ids.add(uid)
    save_premium_ids(ids)
    return True, uid


def remove_premium_user(user_id):
    uid = normalize_premium_id(user_id)
    if not uid:
        return False, None
    ids = load_premium_ids()
    if uid not in ids:
        return False, uid
    ids.discard(uid)
    save_premium_ids(ids)
    return True, uid


def load_staff_ids():
    ids = set()
    try:
        with open(STAFF_FILE, "r", encoding="utf-8") as f:
            for line in f:
                uid = normalize_premium_id(line)
                if uid:
                    ids.add(uid)
    except FileNotFoundError:
        pass
    return ids


def save_staff_ids(ids):
    tmp = STAFF_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for uid in sorted(ids, key=lambda x: int(x)):
            f.write(f"{uid}\n")
    os.replace(tmp, STAFF_FILE)


def is_bot_owner(user_id) -> bool:
    uid = normalize_premium_id(user_id)
    return uid == str(BOT_OWNER_ID)


def is_seekara_staff(user_id) -> bool:
    """Owner + Seekara staff can use former owner-only bot commands."""
    uid = normalize_premium_id(user_id)
    if not uid:
        return False
    if uid == str(BOT_OWNER_ID):
        return True
    return uid in load_staff_ids()


def add_staff_user(user_id):
    uid = normalize_premium_id(user_id)
    if not uid:
        return False, None
    if uid == str(BOT_OWNER_ID):
        return False, uid  # owner already staff
    ids = load_staff_ids()
    if uid in ids:
        return False, uid
    ids.add(uid)
    save_staff_ids(ids)
    return True, uid


def remove_staff_user(user_id):
    uid = normalize_premium_id(user_id)
    if not uid:
        return False, None
    ids = load_staff_ids()
    if uid not in ids:
        return False, uid
    ids.discard(uid)
    save_staff_ids(ids)
    return True, uid


intents = discord.Intents.all()
# Allow User Install + Guild Install for app commands (e.g. /emojisteal)
bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=None,
    allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
    allowed_contexts=app_commands.AppCommandContext(
        guild=True, dm_channel=True, private_channel=True
    ),
)
tree = bot.tree


def user_app_install_url() -> str:
    cid = str(DISCORD_CLIENT_ID or "").strip() or str(getattr(bot.user, "id", "") or "")
    return (
        "https://discord.com/oauth2/authorize"
        f"?client_id={cid}&scope=applications.commands&integration_type=1"
    )




async def sync_slash_commands(
    force_print: bool = True,
    clear_guild_dupes: bool = True,
    push_to_guilds: bool = False,
):
    """Publish slash commands globally.

    Default: global sync + clear per-guild copies.
    Guild copies caused 'Application command emojisteal not found' when an old
    bot process was connected (Discord still had the guild command, local tree didn't).
    """
    for cmd in tree.get_commands():
        if getattr(cmd, "name", None) == "emojisteal":
            cmd.allowed_installs = app_commands.AppInstallationType(guild=True, user=True)
            cmd.allowed_contexts = app_commands.AppCommandContext(
                guild=True, dm_channel=True, private_channel=True
            )

    try:
        menus = getattr(tree, "_context_menus", {}) or {}
        for menu in menus.values():
            if getattr(menu, "name", None) == "Steal emojis":
                menu.allowed_installs = app_commands.AppInstallationType(guild=True, user=True)
                menu.allowed_contexts = app_commands.AppCommandContext(
                    guild=True, dm_channel=True, private_channel=True
                )
    except Exception as e:
        print(f"Context menu flag update skipped: {e}")

    # Always publish globals first (includes /emojisteal)
    local_names = {c.name for c in tree.get_commands()}
    if force_print:
        print(f"Local tree has emojisteal: {'emojisteal' in local_names} ({len(local_names)} cmds)")

    synced = await tree.sync()
    if force_print:
        names = {c.name for c in synced}
        print(f"Synced {len(synced)} global slash/app commands.")
        print(f"  emojisteal registered: {'emojisteal' in names}")
        print(f"  User App install link: {user_app_install_url()}")

    # Wipe guild-scoped copies so Discord never routes a ghost /emojisteal
    # to a process that doesn't have the handler.
    if clear_guild_dupes:
        for guild in list(bot.guilds):
            try:
                tree.clear_commands(guild=guild)
                await tree.sync(guild=guild)
                if force_print:
                    print(f"Cleared guild commands for {guild.name} ({guild.id})")
            except Exception as ge:
                print(f"Guild command clear failed for {guild.id}: {ge}")
    elif push_to_guilds:
        for guild in list(bot.guilds):
            try:
                tree.copy_global_to(guild=guild)
                g_synced = await tree.sync(guild=guild)
                if force_print:
                    print(f"Pushed {len(g_synced)} commands to {guild.name} ({guild.id})")
            except Exception as ge:
                print(f"Guild slash push failed for {guild.id}: {ge}")

    return synced


async def sync_guild_commands(guild: discord.Guild, force_print: bool = False):
    """Push current slash commands to one guild (instant visibility)."""
    try:
        tree.copy_global_to(guild=guild)
        synced = await tree.sync(guild=guild)
        if force_print:
            print(f"Pushed {len(synced)} commands to {guild.name} ({guild.id})")
        return synced
    except Exception as e:
        print(f"Guild slash push failed for {getattr(guild, 'id', guild)}: {e}")
        return []



CONFIG_FILE = "beacon_config.json"
WARNS_FILE = "beacon_warns.json"
BACKUP_DIR = "backups"
DM_SENT_FILE = "beacon_owner_dms.json"
STICKIES_FILE = os.path.join(BASE_DIR, "beacon_stickies.json")
REMINDERS_FILE = os.path.join(BASE_DIR, "beacon_reminders.json")
LEVELS_FILE = os.path.join(BASE_DIR, "beacon_levels.json")
ECONOMY_FILE = os.path.join(BASE_DIR, "beacon_economy.json")
AUTORESPONDERS_FILE = os.path.join(BASE_DIR, "beacon_autoresponders.json")
INVITES_FILE = os.path.join(BASE_DIR, "beacon_invites.json")
TEMPROLES_FILE = os.path.join(BASE_DIR, "beacon_temproles.json")

# Free feature tuning
XP_COOLDOWN_SECONDS = 60
XP_MIN_GAIN = 15
XP_MAX_GAIN = 25
# Premium invite fake filter: accounts younger than this count as fake invites
FAKE_INVITE_ACCOUNT_AGE_DAYS = 7
DAILY_COIN_REWARD = 100
DAILY_COOLDOWN_SECONDS = 86400

custom_db = sqlite3.connect("custom_commands.db")
custom_cursor = custom_db.cursor()
filter_cursor = custom_db.cursor()


custom_cursor.execute("""
CREATE TABLE IF NOT EXISTS custom_commands(
    guild_id INTEGER,
    command TEXT,
    response TEXT,
    PRIMARY KEY(guild_id, command)
)
""")

filter_cursor = custom_db.cursor()

filter_cursor.execute("""
CREATE TABLE IF NOT EXISTS banned_words(
    word TEXT PRIMARY KEY
)
""")

custom_db.commit()


filter_cursor.execute("""
CREATE TABLE IF NOT EXISTS banned_words(
    word TEXT PRIMARY KEY
)
""")

custom_db.commit()

try:
    with open("banned_words.txt", "r", encoding="utf8") as f:
        for line in f:
            word = line.strip().lower()

            if word:
                filter_cursor.execute(
                    "INSERT OR IGNORE INTO banned_words VALUES(?)",
                    (word,)
                )

    custom_db.commit()

except FileNotFoundError:
    pass


custom_db.commit()

os.makedirs(BACKUP_DIR, exist_ok=True)


antinuke_cache = {}
mention_raid_cache = {}
raid_punish_cooldown = {}
restore_cooldown = {}
restoring_guilds = set()
dashboard_started = False
dashboard_sessions = {}
joined_guild_cache = set()


# ============================================================
# JSON / CONFIG
# ============================================================

def load_json(file, default):
    if not os.path.exists(file):
        with open(file, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=4)
        return default

    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default


def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


config = load_json(CONFIG_FILE, {})
warns = load_json(WARNS_FILE, {})
owner_dm_sent = load_json(DM_SENT_FILE, {})
stickies = load_json(STICKIES_FILE, {})
reminders = load_json(REMINDERS_FILE, [])
levels = load_json(LEVELS_FILE, {})
economy = load_json(ECONOMY_FILE, {})
autoresponders = load_json(AUTORESPONDERS_FILE, {})
invite_stats = load_json(INVITES_FILE, {})
temproles = load_json(TEMPROLES_FILE, [])

# Runtime caches (not persisted)
xp_cooldowns = {}
invite_cache = {}  # guild_id -> {code: uses}
sticky_locks = set()


def save_config():
    save_json(CONFIG_FILE, config)


def save_warns():
    save_json(WARNS_FILE, warns)


def save_stickies():
    save_json(STICKIES_FILE, stickies)


def save_reminders():
    save_json(REMINDERS_FILE, reminders)


def save_levels():
    save_json(LEVELS_FILE, levels)


def save_economy():
    save_json(ECONOMY_FILE, economy)


def save_autoresponders():
    save_json(AUTORESPONDERS_FILE, autoresponders)


def save_invite_stats():
    save_json(INVITES_FILE, invite_stats)


def save_temproles():
    save_json(TEMPROLES_FILE, temproles)


DURATION_RE = re.compile(
    r"(\d+)\s*(w|weeks?|d|days?|h|hrs?|hours?|m|mins?|minutes?|s|secs?|seconds?)",
    re.IGNORECASE,
)


def parse_duration(text):
    """Parse '2h', '7d', '1d12h', '30m' -> seconds. Returns None if invalid."""
    if not text:
        return None
    total = 0
    matched = False
    for amount, unit in DURATION_RE.findall(str(text)):
        matched = True
        n = int(amount)
        u = unit.lower()
        if u.startswith("w"):
            total += n * 604800
        elif u.startswith("d"):
            total += n * 86400
        elif u.startswith("h"):
            total += n * 3600
        elif u.startswith("m"):
            total += n * 60
        elif u.startswith("s"):
            total += n
    if not matched or total <= 0:
        return None
    return total


def format_duration(seconds):
    seconds = int(seconds)
    parts = []
    for label, size in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if seconds >= size:
            n, seconds = divmod(seconds, size)
            parts.append(f"{n}{label}")
    return " ".join(parts) or "0s"


def level_from_xp(xp):
    level = 0
    remaining = max(0, int(xp))
    while remaining >= xp_needed_for_level(level + 1):
        remaining -= xp_needed_for_level(level + 1)
        level += 1
    return level


def xp_needed_for_level(level):
    # Classic curve: 5n^2 + 50n + 100
    n = max(1, int(level))
    return 5 * n * n + 50 * n + 100


def get_user_xp(guild_id, user_id):
    g = levels.setdefault(str(guild_id), {})
    u = g.setdefault(str(user_id), {"xp": 0, "level": 0})
    return u


def get_economy_guild(guild_id):
    g = economy.setdefault(
        str(guild_id),
        {"users": {}, "shop": [], "daily": {}},
    )
    g.setdefault("users", {})
    g.setdefault("shop", [])
    g.setdefault("daily", {})
    return g


def get_balance(guild_id, user_id):
    g = get_economy_guild(guild_id)
    return int(g["users"].setdefault(str(user_id), 0))


def set_balance(guild_id, user_id, amount):
    g = get_economy_guild(guild_id)
    g["users"][str(user_id)] = max(0, int(amount))
    save_economy()


def add_coins(guild_id, user_id, amount):
    bal = get_balance(guild_id, user_id) + int(amount)
    set_balance(guild_id, user_id, bal)
    return bal


def get_invite_guild(guild_id):
    g = invite_stats.setdefault(
        str(guild_id),
        {"totals": {}, "fake": {}, "joins": {}},
    )
    g.setdefault("totals", {})
    g.setdefault("fake", {})
    g.setdefault("joins", {})
    return g


async def cache_guild_invites(guild):
    try:
        invites = await guild.invites()
        invite_cache[guild.id] = {inv.code: inv.uses or 0 for inv in invites}
    except Exception:
        invite_cache[guild.id] = {}


async def feature_background_loop():
    """Handles due reminders and expired temp roles."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            now = int(time.time())

            # Reminders
            changed = False
            still = []
            for item in list(reminders):
                if int(item.get("due_at", 0)) <= now:
                    channel = bot.get_channel(int(item.get("channel_id", 0)))
                    user_id = int(item.get("user_id", 0))
                    text = item.get("text", "Reminder!")
                    if channel is not None:
                        try:
                            await channel.send(f"⏰ <@{user_id}> reminder: {text}")
                        except Exception:
                            pass
                    changed = True
                else:
                    still.append(item)
            if changed:
                reminders.clear()
                reminders.extend(still)
                save_reminders()

            # Temp roles
            tchanged = False
            keep = []
            for item in list(temproles):
                if int(item.get("expires_at", 0)) <= now:
                    guild = bot.get_guild(int(item.get("guild_id", 0)))
                    if guild:
                        member = guild.get_member(int(item.get("user_id", 0)))
                        role = guild.get_role(int(item.get("role_id", 0)))
                        if member and role and role in member.roles:
                            try:
                                await member.remove_roles(role, reason="Temp role expired")
                            except Exception:
                                pass
                    tchanged = True
                else:
                    keep.append(item)
            if tchanged:
                temproles.clear()
                temproles.extend(keep)
                save_temproles()
        except Exception as e:
            print("feature_background_loop error:", e)

        await asyncio.sleep(15)


async def restick_message(channel):
    """Keep sticky message at the bottom of a channel."""
    key = str(channel.id)
    data = stickies.get(key)
    if not data:
        return
    if channel.id in sticky_locks:
        return
    sticky_locks.add(channel.id)
    try:
        old_id = data.get("message_id")
        if old_id:
            try:
                old = await channel.fetch_message(int(old_id))
                await old.delete()
            except Exception:
                pass
        sent = await channel.send(data.get("content", "📌 Sticky"))
        data["message_id"] = sent.id
        stickies[key] = data
        save_stickies()
    except Exception as e:
        print("sticky failed:", e)
    finally:
        sticky_locks.discard(channel.id)


async def maybe_award_xp(message):
    """Basic free XP — no role rewards."""
    if not message.guild or message.author.bot:
        return
    if not message.content or message.content.startswith(PREFIX):
        return

    key = f"{message.guild.id}:{message.author.id}"
    now = time.time()
    if now - xp_cooldowns.get(key, 0) < XP_COOLDOWN_SECONDS:
        return
    xp_cooldowns[key] = now

    gain = random.randint(XP_MIN_GAIN, XP_MAX_GAIN)
    data = get_user_xp(message.guild.id, message.author.id)
    old_level = int(data.get("level", 0))
    data["xp"] = int(data.get("xp", 0)) + gain
    new_level = level_from_xp(data["xp"])
    data["level"] = new_level
    save_levels()

    if new_level > old_level:
        try:
            await message.channel.send(
                f"🎉 {message.author.mention} leveled up to **{new_level}**!",
                delete_after=8,
            )
        except Exception:
            pass


async def try_autorespond(message):
    """Premium keyword / regex auto-responder (rules only exist if premium added them)."""
    if not message.guild or message.author.bot:
        return False

    rules = autoresponders.get(str(message.guild.id), [])
    content = message.content or ""
    for rule in rules:
        trigger = rule.get("trigger", "")
        response = rule.get("response", "")
        if not trigger or not response:
            continue
        try:
            if rule.get("is_regex"):
                if re.search(trigger, content, re.IGNORECASE):
                    await message.channel.send(response)
                    return True
            else:
                if trigger.lower() in content.lower():
                    await message.channel.send(response)
                    return True
        except re.error:
            continue
    return False


class PollView(discord.ui.View):
    def __init__(self, question, options, timeout=3600):
        super().__init__(timeout=timeout)
        self.question = question
        self.options = options
        self.votes = {i: set() for i in range(len(options))}

        for i, label in enumerate(options):
            button = discord.ui.Button(
                label=f"{i + 1}. {label[:70]}",
                style=discord.ButtonStyle.primary,
                custom_id=f"poll:{i}",
            )

            async def callback(interaction, idx=i):
                # one vote per user
                for s in self.votes.values():
                    s.discard(interaction.user.id)
                self.votes[idx].add(interaction.user.id)
                await interaction.response.edit_message(embed=self.make_embed(), view=self)

            button.callback = callback
            self.add_item(button)

    def make_embed(self):
        lines = []
        total = sum(len(v) for v in self.votes.values()) or 1
        for i, label in enumerate(self.options):
            count = len(self.votes[i])
            bar = "█" * min(20, int((count / total) * 20))
            lines.append(f"**{i + 1}. {label}** — {count} vote(s)\n{bar or '·'}")
        embed = discord.Embed(
            title="📊 Poll",
            description=f"**{self.question}**\n\n" + "\n\n".join(lines),
            color=0x5865F2,
        )
        embed.set_footer(text=f"Total votes: {sum(len(v) for v in self.votes.values())}")
        return embed


# ============================================================
# WELCOME / LOG HELPERS
# ============================================================

def format_welcome_message(template, member):
    """Replace placeholders in a welcome message template."""
    return (
        template
        .replace("{mention}", member.mention)
        .replace("{user}", str(member))
        .replace("{username}", member.name)
        .replace("{server}", member.guild.name)
        .replace("{count}", str(member.guild.member_count))
        .replace("{id}", str(member.id))
    )


async def send_welcome(member):
    cfg = get_guild(member.guild.id)

    if not cfg.get("welcome_enabled"):
        return

    channel_id = cfg.get("welcome_channel")

    if channel_id is None:
        return

    channel = member.guild.get_channel(int(channel_id))

    if channel is None:
        return

    message = format_welcome_message(cfg.get("welcome_message", "Welcome {mention}!"), member)

    try:
        if cfg.get("welcome_embed", True):
            embed = discord.Embed(
                description=message,
                color=cfg.get("welcome_embed_color", 0x5865F2)
            )
            embed.set_author(name=str(member), icon_url=member.display_avatar.url)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Member #{member.guild.member_count}")
            await channel.send(embed=embed)
        else:
            await channel.send(message)
    except Exception as e:
        print(f"Welcome message failed: {e}")


async def send_log(guild, event_key, embed):
    cfg = get_guild(guild.id)

    if not cfg.get("log_enabled"):
        return

    log_events = cfg.get("log_events", {})

    if not log_events.get(event_key, True):
        return

    channel_id = cfg.get("log_channel")

    if channel_id is None:
        return

    channel = guild.get_channel(int(channel_id))

    if channel is None:
        return

    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"Log send failed: {e}")


def log_embed(title, description, color=0x5865F2):
    embed = discord.Embed(title=title, description=description, color=color)
    embed.timestamp = discord.utils.utcnow()
    return embed


def save_owner_dms():
    save_json(DM_SENT_FILE, owner_dm_sent)


def get_guild(guild_id):
    gid = str(guild_id)

    defaults = {
        "antinuke": True,
        "punishment": "ban",
        "whitelist": [],
        "channel_create_limit": 5,
        "channel_create_seconds": 10,
        "restore_cooldown_seconds": 90,
        "wipe_before_restore": True,
        "rebackup_after_restore": True,
        # Welcome system
        "welcome_enabled": False,
        "welcome_channel": None,
        "welcome_message": "Welcome to **{server}**, {mention}! You are member #{count}.",
        "welcome_embed": True,
        "welcome_embed_color": 0x5865F2,
        # Log system
        "log_enabled": False,
        "log_channel": None,
        "log_events": {
            "member_join": True,
            "member_leave": True,
            "member_ban": True,
            "member_unban": True,
            "message_delete": True,
            "message_edit": True,
            "channel_create": True,
            "channel_delete": True,
            "role_create": True,
            "role_delete": True,
            "member_update": True,
            "voice_update": True
        },
    }

    if gid not in config:
        config[gid] = defaults.copy()
    else:
        for key, value in defaults.items():
            if key not in config[gid]:
                config[gid][key] = value

    save_config()
    return config[gid]


def is_whitelisted(guild, user):
    cfg = get_guild(guild.id)
    return user.id == guild.owner_id or user.id in cfg["whitelist"]


# ============================================================
# BACKUPS
# ============================================================

def backup_path(guild_id):
    # Public bot safe: every guild only has one structure backup, named by that guild ID.
    return os.path.join(BACKUP_DIR, f"{guild_id}.json")


DISCORD_SAFE_FILE_LIMIT = 7_500_000


def clean_filename(value):
    value = str(value)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)
    return safe[:80] or "backup"


def public_backup_filename(guild):
    return f"{clean_filename(guild.name)}_{guild.id}_backup.json"


def serialize_overwrites(channel):
    data = []

    for target, overwrite in channel.overwrites.items():
        if isinstance(target, discord.Role):
            target_type = "role"
        elif isinstance(target, discord.Member):
            target_type = "member"
        else:
            continue

        allow, deny = overwrite.pair()

        data.append({
            "target_type": target_type,
            "target_id": target.id,
            "target_name": getattr(target, "name", None),
            "allow": allow.value,
            "deny": deny.value
        })

    return data


async def create_backup(guild):
    roles = []

    for role in guild.roles:
        if role.is_default() or role.managed:
            continue

        roles.append({
            "id": role.id,
            "name": role.name,
            "permissions": role.permissions.value,
            "color": role.color.value,
            "hoist": role.hoist,
            "mentionable": role.mentionable,
            "position": role.position
        })

    channels = []

    for channel in guild.channels:
        item = {
            "id": channel.id,
            "name": channel.name,
            "type": str(channel.type),
            "position": channel.position,
            "category_id": channel.category_id,
            "overwrites": serialize_overwrites(channel)
        }

        if isinstance(channel, discord.TextChannel):
            item["topic"] = channel.topic
            item["slowmode_delay"] = channel.slowmode_delay
            item["nsfw"] = channel.nsfw

        if isinstance(channel, discord.VoiceChannel):
            item["bitrate"] = channel.bitrate
            item["user_limit"] = channel.user_limit

        channels.append(item)

    icon_b64 = None

    try:
        if guild.icon:
            raw_icon = await guild.icon.read()
            icon_b64 = base64.b64encode(raw_icon).decode("utf-8")
    except Exception as e:
        print("Icon backup failed:", e)

    # Emoji and soundboard backups are intentionally disabled.
    # This keeps /backup faster and avoids Discord emoji/soundboard rate limits.

    data = {
        "guild_id": guild.id,
        "guild_name": guild.name,
        "guild_icon_b64": icon_b64,
        "created_at": int(time.time()),
        "roles": roles,
        "channels": channels
    }

    with open(backup_path(guild.id), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    return data


async def wipe_server_structure(guild):
    """Deletes non-managed roles and all channels before restoring.
    This is intentionally slow to avoid hard rate limits.
    """
    restoring_guilds.add(guild.id)

    deleted_channels = 0
    deleted_roles = 0

    try:
        # Delete channels first.
        for channel in list(guild.channels):
            try:
                await channel.delete(reason="Beacon wipe before restore")
                deleted_channels += 1
                await asyncio.sleep(3)
            except Exception as e:
                print("Channel wipe failed:", e)

        # Delete roles below Beacon.
        roles = [
            role for role in guild.roles
            if not role.is_default()
            and not role.managed
            and role < guild.me.top_role
        ]

        # Delete from highest to lowest.
        roles.sort(key=lambda r: r.position, reverse=True)

        for role in roles:
            try:
                await role.delete(reason="Beacon wipe before restore")
                deleted_roles += 1
                await asyncio.sleep(3)
            except Exception as e:
                print("Role wipe failed:", e)

    finally:
        restoring_guilds.discard(guild.id)

    return deleted_channels, deleted_roles


async def restore_backup(guild, wipe_first=False):
    path = backup_path(guild.id)

    if not os.path.exists(path):
        return False, "No backup found."

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    restoring_guilds.add(guild.id)

    try:
        if wipe_first:
            await wipe_server_structure(guild)
            restoring_guilds.add(guild.id)

        # Restore server name + icon.
        try:
            edit_kwargs = {}

            if data.get("guild_name") and guild.name != data.get("guild_name"):
                edit_kwargs["name"] = data.get("guild_name")

            if data.get("guild_icon_b64"):
                edit_kwargs["icon"] = base64.b64decode(data["guild_icon_b64"])

            if edit_kwargs:
                await guild.edit(**edit_kwargs, reason="Beacon backup restore")
                await asyncio.sleep(4)
        except Exception as e:
            print("Guild name/icon restore failed:", e)

        # Restore roles.
        existing_roles = {role.name: role for role in guild.roles}
        role_map = {}

        sorted_roles = sorted(data.get("roles", []), key=lambda r: r.get("position", 0))

        for role_data in sorted_roles:
            role = existing_roles.get(role_data["name"])

            if role is None:
                try:
                    role = await guild.create_role(
                        name=role_data["name"],
                        permissions=discord.Permissions(role_data["permissions"]),
                        color=discord.Color(role_data["color"]),
                        hoist=role_data["hoist"],
                        mentionable=role_data["mentionable"],
                        reason="Beacon backup restore"
                    )
                    existing_roles[role.name] = role
                    await asyncio.sleep(4)
                except Exception as e:
                    print("Role restore failed:", e)
                    continue
            else:
                try:
                    await role.edit(
                        permissions=discord.Permissions(role_data["permissions"]),
                        color=discord.Color(role_data["color"]),
                        hoist=role_data["hoist"],
                        mentionable=role_data["mentionable"],
                        reason="Beacon backup restore"
                    )
                    await asyncio.sleep(2)
                except Exception as e:
                    print("Role edit failed:", e)

            role_map[role_data["id"]] = role

        # Restore categories.
        existing_channels_by_name_type = {(channel.name, str(channel.type)): channel for channel in guild.channels}
        category_map = {}

        categories = [c for c in data.get("channels", []) if c["type"] == "category"]

        for channel_data in sorted(categories, key=lambda c: c.get("position", 0)):
            channel = existing_channels_by_name_type.get((channel_data["name"], "category"))

            if channel is None:
                try:
                    channel = await guild.create_category(
                        name=channel_data["name"],
                        position=channel_data.get("position", 0),
                        reason="Beacon backup restore"
                    )
                    await asyncio.sleep(4)
                except Exception as e:
                    print("Category restore failed:", e)
                    continue
            else:
                try:
                    await channel.edit(
                        name=channel_data["name"],
                        position=channel_data.get("position", channel.position),
                        reason="Beacon backup restore"
                    )
                    await asyncio.sleep(2)
                except Exception as e:
                    print("Category edit failed:", e)

            category_map[channel_data["id"]] = channel

        # Restore normal channels.
        normal_channels = [c for c in data.get("channels", []) if c["type"] != "category"]

        for channel_data in sorted(normal_channels, key=lambda c: c.get("position", 0)):
            channel = existing_channels_by_name_type.get((channel_data["name"], channel_data["type"]))
            category = category_map.get(channel_data.get("category_id"))

            if channel is None:
                try:
                    if channel_data["type"] == "text":
                        channel = await guild.create_text_channel(
                            name=channel_data["name"],
                            topic=channel_data.get("topic"),
                            slowmode_delay=channel_data.get("slowmode_delay", 0),
                            nsfw=channel_data.get("nsfw", False),
                            category=category,
                            position=channel_data.get("position", 0),
                            reason="Beacon backup restore"
                        )

                    elif channel_data["type"] == "voice":
                        channel = await guild.create_voice_channel(
                            name=channel_data["name"],
                            bitrate=min(channel_data.get("bitrate", 64000), 96000),
                            user_limit=channel_data.get("user_limit", 0),
                            category=category,
                            position=channel_data.get("position", 0),
                            reason="Beacon backup restore"
                        )

                    await asyncio.sleep(4)

                except Exception as e:
                    print("Channel restore failed:", e)
                    continue
            else:
                try:
                    edit_kwargs = {
                        "name": channel_data["name"],
                        "position": channel_data.get("position", channel.position)
                    }

                    if category is not None:
                        edit_kwargs["category"] = category

                    if isinstance(channel, discord.TextChannel):
                        edit_kwargs["topic"] = channel_data.get("topic")
                        edit_kwargs["slowmode_delay"] = channel_data.get("slowmode_delay", 0)
                        edit_kwargs["nsfw"] = channel_data.get("nsfw", False)

                    if isinstance(channel, discord.VoiceChannel):
                        edit_kwargs["bitrate"] = min(channel_data.get("bitrate", 64000), 96000)
                        edit_kwargs["user_limit"] = channel_data.get("user_limit", 0)

                    await channel.edit(**edit_kwargs, reason="Beacon backup restore")
                    await asyncio.sleep(3)
                except Exception as e:
                    print("Channel edit failed:", e)

            # Restore overwrites.
            try:
                overwrites = {}

                for ow in channel_data.get("overwrites", []):
                    target = None

                    if ow["target_type"] == "role":
                        target = (
                            role_map.get(ow["target_id"])
                            or discord.utils.get(guild.roles, id=ow["target_id"])
                            or discord.utils.get(guild.roles, name=ow.get("target_name"))
                        )

                    elif ow["target_type"] == "member":
                        target = guild.get_member(ow["target_id"])

                    if target is None:
                        continue

                    allow = discord.Permissions(ow["allow"])
                    deny = discord.Permissions(ow["deny"])
                    overwrites[target] = discord.PermissionOverwrite.from_pair(allow, deny)

                if overwrites:
                    await channel.edit(overwrites=overwrites, reason="Beacon backup restore")
                    await asyncio.sleep(3)

            except Exception as e:
                print("Overwrite restore failed:", e)

        # Cool down after restoring channels/roles.
        # Discord rate-limits hard after lots of channel creates/edits.
        await asyncio.sleep(60)

        # Emoji and soundboard restore are intentionally disabled.
        # Old backup files may contain them, but Beacon will ignore those fields.

    finally:
        restoring_guilds.discard(guild.id)

    return True, "Wipe + restore finished." if wipe_first else "Restore finished."


# ============================================================
# ROLES
# ============================================================

async def setup_jail(guild):
    role = discord.utils.get(guild.roles, name="Jailed")

    if role is None:
        role = await guild.create_role(name="Jailed", reason="Beacon jail setup")

    for channel in guild.channels:
        try:
            await channel.set_permissions(
                role,
                view_channel=False,
                send_messages=False,
                connect=False,
                speak=False
            )
            await asyncio.sleep(0.2)
        except:
            pass

    return role


async def setup_mute(guild):
    role = discord.utils.get(guild.roles, name="Muted")

    if role is None:
        role = await guild.create_role(name="Muted", reason="Beacon mute setup")

    for channel in guild.channels:
        try:
            await channel.set_permissions(
                role,
                send_messages=False,
                speak=False
            )
            await asyncio.sleep(0.2)
        except:
            pass

    return role


# ============================================================
# PUNISH / ANTINUKE
# ============================================================

async def punish_member(guild, user, reason):
    cfg = get_guild(guild.id)

    if user is None:
        return

    if bot.user and user.id == bot.user.id:
        return

    if user.id == guild.owner_id:
        return

    if user.id in cfg["whitelist"]:
        return

    member = guild.get_member(user.id)

    if member is None:
        return

    punishment = cfg["punishment"]

    try:
        if punishment == "ban":
            await member.ban(reason=reason)

        elif punishment == "kick":
            await member.kick(reason=reason)

        elif punishment == "jail":
            jail_role = discord.utils.get(guild.roles, name="Jailed")

            if jail_role is None:
                jail_role = await setup_jail(guild)

            removable_roles = [
                role for role in member.roles
                if not role.is_default()
                and role < guild.me.top_role
            ]

            for role in removable_roles:
                try:
                    await member.remove_roles(role, reason=reason)
                except:
                    pass

            await member.add_roles(jail_role, reason=reason)

    except Exception as e:
        print(f"Punishment failed: {e}")


async def antinuke_action(guild, user, action):
    cfg = get_guild(guild.id)

    if guild.id in restoring_guilds:
        return

    if not cfg["antinuke"]:
        return

    if user is None:
        return

    if bot.user and user.id == bot.user.id:
        return

    if is_whitelisted(guild, user):
        return

    key = f"{guild.id}-{user.id}-{action}"
    now = time.time()

    if key not in antinuke_cache:
        antinuke_cache[key] = []

    antinuke_cache[key] = [
        t for t in antinuke_cache[key]
        if now - t <= cfg["channel_create_seconds"]
    ]

    antinuke_cache[key].append(now)

    if len(antinuke_cache[key]) >= cfg["channel_create_limit"]:
        restore_key = str(guild.id)
        last_restore = restore_cooldown.get(restore_key, 0)

        if now - last_restore < cfg["restore_cooldown_seconds"]:
            return

        restore_cooldown[restore_key] = now

        await punish_member(
            guild,
            user,
            "Beacon antinuke triggered: channel create spam"
        )

        if cfg.get("wipe_before_restore", True):
            ok, msg = await restore_backup(guild, wipe_first=True)
        else:
            ok, msg = await restore_backup(guild, wipe_first=False)

        print("Auto restore:", ok, msg)

        if cfg.get("rebackup_after_restore", True):
            await create_backup(guild)
            print("Re-backup saved.")


async def get_audit_user(guild, action):
    try:
        async for entry in guild.audit_logs(limit=1, action=action):
            return entry.user
    except:
        return None

    return None



# ============================================================
# WEB DASHBOARD - DISCORD OAUTH LOGIN
# ============================================================

ADMINISTRATOR_PERMISSION = 0x8
MANAGE_GUILD_PERMISSION = 0x20


def dashboard_json(handler, data, code=200):
    raw = json.dumps(data).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def dashboard_redirect(handler, location):
    handler.send_response(302)
    handler.send_header("Location", location)
    handler.end_headers()


def get_cookie_session(handler):
    cookie_header = handler.headers.get("Cookie", "")
    cookie = SimpleCookie()
    cookie.load(cookie_header)

    if "beacon_session" not in cookie:
        return None

    token = cookie["beacon_session"].value
    session = dashboard_sessions.get(token)

    if not session:
        return None

    if time.time() > session.get("expires", 0):
        dashboard_sessions.pop(token, None)
        return None

    return session


def require_session(handler):
    session = get_cookie_session(handler)

    if not session:
        dashboard_json(handler, {"ok": False, "error": "not logged in"}, 401)
        return None

    return session


def discord_api_get(path, access_token):
    req = urllib.request.Request(
        DISCORD_API + path,
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "BeaconDashboard"
        }
    )

    with urllib.request.urlopen(req, timeout=15) as res:
        return json.loads(res.read().decode("utf-8"))


def discord_exchange_code(code):
    body = urllib.parse.urlencode({
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI
    }).encode("utf-8")

    req = urllib.request.Request(
        DISCORD_API + "/oauth2/token",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "BeaconDashboard"
        }
    )

    with urllib.request.urlopen(req, timeout=15) as res:
        return json.loads(res.read().decode("utf-8"))


def user_admin_guild_ids(session):
    ids = set()

    for guild in session.get("guilds", []):
        try:
            permissions = int(guild.get("permissions", 0))
        except:
            permissions = 0

        is_owner = guild.get("owner", False)

        if is_owner or (permissions & ADMINISTRATOR_PERMISSION) or (permissions & MANAGE_GUILD_PERMISSION):
            ids.add(int(guild["id"]))

    return ids


def can_manage_guild(session, guild_id):
    guild = bot.get_guild(int(guild_id))

    if guild is None:
        return False

    user_id = int(session["user"]["id"])

    if guild.owner_id == user_id:
        return True

    return int(guild_id) in user_admin_guild_ids(session)


class BeaconDashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/":
            if not get_cookie_session(self):
                html = """
<!DOCTYPE html>
<html>
<head>
<title>Beacon Dashboard Login</title>
<style>
body{margin:0;background:#070b12;color:white;font-family:Arial;display:flex;min-height:100vh;align-items:center;justify-content:center}
.box{background:#0b1320;border:1px solid #1e3558;border-radius:20px;padding:30px;max-width:430px;box-shadow:0 10px 30px #000}
h1{color:#59a7ff;margin-top:0}
a{display:inline-block;background:#5865F2;color:white;text-decoration:none;padding:13px 18px;border-radius:12px;font-weight:bold}
p{color:#9fb7d6}
</style>
</head>
<body>
<div class="box">
<h1>Beacon Dashboard</h1>
<p>Login with Discord. You will only see servers where you are Administrator and Beacon is installed.</p>
<a href="/login">Login with Discord</a>
</div>
</body>
</html>
"""
                raw = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return

            try:
                html = Path(DASHBOARD_HTML_FILE).read_text(encoding="utf-8")
            except Exception as e:
                html = f"<h1>{e}</h1>"

            raw = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        if parsed.path == "/login":
            params = {
                "client_id": DISCORD_CLIENT_ID,
                "redirect_uri": DISCORD_REDIRECT_URI,
                "response_type": "code",
                "scope": "identify guilds",
                "prompt": "none"
            }

            dashboard_redirect(
                self,
                DISCORD_API + "/oauth2/authorize?" + urlencode(params)
            )
            return

        if parsed.path == "/callback":
            qs = parse_qs(parsed.query)
            code = qs.get("code", [None])[0]

            if not code:
                raw = b"Missing Discord OAuth code."
                self.send_response(400)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return

            try:
                token_data = discord_exchange_code(code)
                access_token = token_data["access_token"]

                user = discord_api_get("/users/@me", access_token)
                guilds = discord_api_get("/users/@me/guilds", access_token)

                session_token = secrets.token_urlsafe(32)
                dashboard_sessions[session_token] = {
                    "user": user,
                    "guilds": guilds,
                    "access_token": access_token,
                    "expires": time.time() + 60 * 60 * 8
                }

                self.send_response(302)
                self.send_header("Location", "/")
                self.send_header(
                    "Set-Cookie",
                    f"beacon_session={session_token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=28800"
                )
                self.end_headers()
                return

            except Exception as e:
                raw = f"OAuth login failed: {e}".encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return

        if parsed.path == "/logout":
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", "beacon_session=deleted; Path=/; Max-Age=0")
            self.end_headers()
            return

        # Public health check for UptimeRobot / external monitors (no login).
        # If this stops responding, the Pi likely lost power or the bot died.
        if parsed.path in {"/health", "/api/health"}:
            ready = bool(bot.user) and bot.is_ready()
            dashboard_json(
                self,
                {
                    "ok": ready,
                    "status": "online" if ready else "starting",
                    "bot": str(bot.user) if bot.user else None,
                },
                200 if ready else 503,
            )
            return

        if parsed.path == "/api/status":
            session = require_session(self)

            if not session:
                return

            admin_ids = user_admin_guild_ids(session)
            guilds = []

            for guild in bot.guilds:
                if guild.id not in admin_ids:
                    continue

                cfg = get_guild(guild.id)
                guilds.append({
                    "id": str(guild.id),
                    "name": guild.name,
                    "member_count": guild.member_count,
                    "antinuke": cfg.get("antinuke", False),
                    "punishment": cfg.get("punishment", "ban"),
                    "backup_exists": os.path.exists(backup_path(guild.id)),
                    "channels": len(guild.channels),
                    "roles": len(guild.roles)
                })

            dashboard_json(self, {
                "ok": True,
                "bot": str(bot.user),
                "user": session.get("user"),
                "guilds": guilds
            })
            return

        dashboard_json(self, {"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        session = require_session(self)

        if not session:
            return

        guild_id = qs.get("guild_id", [""])[0]

        try:
            guild_id_int = int(guild_id)
        except:
            dashboard_json(self, {"ok": False, "error": "bad guild id"}, 400)
            return

        if not can_manage_guild(session, guild_id_int):
            dashboard_json(self, {"ok": False, "error": "you are not admin in this server"}, 403)
            return

        guild = bot.get_guild(guild_id_int)

        if guild is None:
            dashboard_json(self, {"ok": False, "error": "Beacon is not in that server"}, 404)
            return

        cfg = get_guild(guild.id)

        if parsed.path == "/api/antinuke/on":
            cfg["antinuke"] = True
            save_config()
            dashboard_json(self, {"ok": True, "message": "Antinuke enabled"})
            return

        if parsed.path == "/api/antinuke/off":
            cfg["antinuke"] = False
            save_config()
            dashboard_json(self, {"ok": True, "message": "Antinuke disabled"})
            return

        if parsed.path == "/api/backup":
            async def dashboard_backup_job():
                await create_backup(guild)

            asyncio.run_coroutine_threadsafe(dashboard_backup_job(), bot.loop)
            dashboard_json(self, {"ok": True, "message": "Structure backup started"})
            return

        if parsed.path == "/api/restore":
            async def dashboard_restore_job():
                await restore_backup(guild, wipe_first=False)

            asyncio.run_coroutine_threadsafe(dashboard_restore_job(), bot.loop)
            dashboard_json(self, {"ok": True, "message": "Structure restore started"})
            return

        if parsed.path == "/api/wiperestore":
            async def dashboard_wiperestore_job():
                await restore_backup(guild, wipe_first=True)

            asyncio.run_coroutine_threadsafe(dashboard_wiperestore_job(), bot.loop)
            dashboard_json(self, {"ok": True, "message": "Wipe + structure restore started"})
            return

        dashboard_json(self, {"ok": False, "error": "not found"}, 404)


def start_dashboard():
    global dashboard_started

    if dashboard_started:
        return

    dashboard_started = True

    def run():
        server = ThreadingHTTPServer(("0.0.0.0", DASHBOARD_PORT), BeaconDashboardHandler)
        print(f"Beacon dashboard running on http://0.0.0.0:{DASHBOARD_PORT}")
        server.serve_forever()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()


# ============================================================
# EVENTS
# ============================================================

_power_alert_sent = False


async def announce_power_loss(reason: str = "shutdown"):
    """Post POWER_ALERT_MESSAGE to POWER_ALERT_GUILD_ID.

    Works for graceful stops (Ctrl+C, systemctl stop, reboot).
    Hard power cuts need an EXTERNAL monitor hitting /health (see bot start tip).
    """
    global _power_alert_sent
    if _power_alert_sent:
        return
    _power_alert_sent = True

    webhook = (POWER_ALERT_WEBHOOK_URL or "").strip()
    if webhook:
        def _post_webhook():
            data = json.dumps({"content": POWER_ALERT_MESSAGE}).encode("utf-8")
            req = urllib.request.Request(
                webhook,
                data=data,
                headers={"Content-Type": "application/json", "User-Agent": "BeaconBot"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as res:
                res.read()

        try:
            await asyncio.to_thread(_post_webhook)
            print(f"Power alert sent via webhook ({reason})")
            return
        except Exception as e:
            print("Power alert webhook failed:", e)

    guild = bot.get_guild(POWER_ALERT_GUILD_ID)
    if guild is None:
        try:
            guild = await bot.fetch_guild(POWER_ALERT_GUILD_ID)
        except Exception as e:
            print("Power alert: guild not found:", e)
            return

    channel = guild.system_channel
    if channel is None or not channel.permissions_for(guild.me).send_messages:
        channel = None
        for c in guild.text_channels:
            perms = c.permissions_for(guild.me)
            if perms.view_channel and perms.send_messages:
                channel = c
                break
    if channel is None:
        print("Power alert: no sendable channel")
        return

    try:
        await channel.send(POWER_ALERT_MESSAGE)
        print(f"Power alert sent to #{channel.name} ({reason})")
    except Exception as e:
        print("Power alert send failed:", e)


def _handle_stop_signal(signum, frame):
    print(f"Caught signal {signum} — sending power-loss alert, then shutting down")

    async def _shutdown():
        try:
            await announce_power_loss(reason=f"signal {signum}")
        finally:
            await bot.close()

    try:
        loop = bot.loop
        if loop.is_running():
            loop.call_soon_threadsafe(lambda: asyncio.create_task(_shutdown()))
        else:
            pass
    except Exception as e:
        print("Shutdown schedule failed:", e)


async def _safe_set_presence():
    """Best-effort presence; never raise on flaky Termux / phone Wi-Fi sockets."""
    try:
        if bot.is_closed() or bot.ws is None:
            return
        await bot.change_presence(activity=discord.Game(name="*help"))
    except (ConnectionClosed, OSError, asyncio.TimeoutError) as e:
        print(f"Presence update skipped: {type(e).__name__}: {e}")
    except Exception as e:
        # aiohttp / gateway write can fail mid-reconnect with assorted errors.
        print(f"Presence update skipped: {type(e).__name__}: {e}")


@bot.event
async def on_ready():
    # on_ready also fires after session invalidation / full reconnect
    # (very common on Termux / mobile Wi-Fi). Keep this handler crash-proof.
    first_ready = not getattr(bot, "_beacon_ready_once", False)
    print(f"Beacon online as {bot.user}" + ("" if first_ready else " (reconnect)"))

    if first_ready:
        # Set status once. Re-setting on every reconnect races a closing websocket
        # and was spamming tracebacks that looked like the bot "stopped".
        await _safe_set_presence()
        bot._beacon_ready_once = True
    else:
        return

    start_dashboard()

    try:
        # Global sync only on boot. Pushing to every guild blocks for a long time
        # and can rate-limit / look like random restarts under pm2.
        # Owner can still run: *resync push
        await sync_slash_commands(force_print=True, clear_guild_dupes=False, push_to_guilds=False)
    except Exception as e:
        print(f"Slash sync failed: {e}")

    for guild in bot.guilds:
        get_guild(guild.id)
        await cache_guild_invites(guild)

    if not getattr(bot, "_feature_loop_started", False):
        bot._feature_loop_started = True
        bot.loop.create_task(feature_background_loop())

    if not getattr(bot, "_stop_signals_hooked", False):
        bot._stop_signals_hooked = True
        signal.signal(signal.SIGTERM, _handle_stop_signal)
        signal.signal(signal.SIGINT, _handle_stop_signal)
        print(
            "Power-loss alert armed for guild "
            f"{POWER_ALERT_GUILD_ID}. Hard power cuts: point UptimeRobot at /health."
        )


@bot.event
async def on_guild_join(guild):
    # Prevent Discord duplicate guild join dispatches causing double messages.
    if guild.id in joined_guild_cache:
        return

    joined_guild_cache.add(guild.id)

    get_guild(guild.id)
    await sync_guild_commands(guild, force_print=True)

    # DM the server owner once only.
    try:
        guild_key = str(guild.id)

        if not owner_dm_sent.get(guild_key):
            owner = guild.owner

            if owner is None:
                owner = await bot.fetch_user(guild.owner_id)

            await asyncio.sleep(4)

            await owner.send(
                "Thank you for adding **Beacon**.\n\n"
                "Prefix: `*help`\n"
                "Our Discord: https://discord.gg/863BgjpMev\n\n"
                "Important: move my role as high as possible so I can protect your server properly."
            )

            owner_dm_sent[guild_key] = {
                "owner_id": guild.owner_id,
                "sent_at": int(time.time())
            }
            save_owner_dms()

    except discord.Forbidden:
        print("Could not DM server owner: DMs are closed.")
    except discord.HTTPException as e:
        print("Failed to DM server owner:", e)
    except Exception as e:
        print("Failed to DM server owner:", e)

    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send(
                "✅ Beacon active.\n"
                "⚠️ Move my role as high as possible, or I cannot punish admin bots above me.\n"
                "Use `/backup`, then `/antinuke_on`."
            )
            break


@bot.event
async def on_guild_channel_create(channel):
    user = await get_audit_user(channel.guild, discord.AuditLogAction.channel_create)

    if user is None:
        return

    # Log event
    embed = log_embed(
        "📁 Channel Created",
        f"**Channel:** {channel.mention} (`{channel.name}`)\n**Type:** {str(channel.type)}\n**By:** {user.mention if user else 'Unknown'}",
        color=0x57F287
    )
    await send_log(channel.guild, "channel_create", embed)

    # ONLY antinuke trigger: channel create 5 in 10s.
    await antinuke_action(channel.guild, user, "channel_create")


@bot.event
async def on_guild_channel_delete(channel):
    user = await get_audit_user(channel.guild, discord.AuditLogAction.channel_delete)
    embed = log_embed(
        "🗑️ Channel Deleted",
        f"**Channel:** `#{channel.name}`\n**Type:** {str(channel.type)}\n**By:** {user.mention if user else 'Unknown'}",
        color=0xED4245
    )
    await send_log(channel.guild, "channel_delete", embed)


@bot.event
async def on_member_join(member):
    await send_welcome(member)

    # Premium invite tracker + fake-invite filter
    try:
        if is_premium(member.guild.owner_id):
            used_code = None
            inviter_id = None
            before = invite_cache.get(member.guild.id, {})
            after_map = {}
            try:
                after_invites = await member.guild.invites()
                after_map = {inv.code: inv.uses or 0 for inv in after_invites}
                for code, uses in after_map.items():
                    if uses > before.get(code, 0):
                        used_code = code
                        for inv in after_invites:
                            if inv.code == code and inv.inviter:
                                inviter_id = inv.inviter.id
                        break
            except Exception:
                pass
            invite_cache[member.guild.id] = after_map or before

            account_age_days = (discord.utils.utcnow() - member.created_at).days
            is_fake = account_age_days < FAKE_INVITE_ACCOUNT_AGE_DAYS

            if inviter_id:
                gstat = get_invite_guild(member.guild.id)
                key = str(inviter_id)
                gstat["totals"][key] = int(gstat["totals"].get(key, 0)) + 1
                if is_fake:
                    gstat["fake"][key] = int(gstat["fake"].get(key, 0)) + 1
                gstat["joins"][str(member.id)] = {
                    "inviter_id": inviter_id,
                    "code": used_code,
                    "fake": is_fake,
                    "joined_at": int(time.time()),
                }
                save_invite_stats()
    except Exception as e:
        print("invite track failed:", e)

    embed = log_embed(
        "✅ Member Joined",
        f"**User:** {member.mention} (`{member}`)\n**ID:** {member.id}\n**Account created:** {discord.utils.format_dt(member.created_at, 'R')}",
        color=0x57F287
    )
    await send_log(member.guild, "member_join", embed)


@bot.event
async def on_member_remove(member):
    embed = log_embed(
        "👋 Member Left",
        f"**User:** `{member}` (`{member.id}`)\n**Roles:** {', '.join(r.mention for r in member.roles[1:]) or 'None'}",
        color=0xFEE75C
    )
    await send_log(member.guild, "member_leave", embed)


@bot.event
async def on_member_ban(guild, user):
    moderator = await get_audit_user(guild, discord.AuditLogAction.ban)
    embed = log_embed(
        "🔨 Member Banned",
        f"**User:** `{user}` (`{user.id}`)\n**By:** {moderator.mention if moderator else 'Unknown'}",
        color=0xED4245
    )
    await send_log(guild, "member_ban", embed)


@bot.event
async def on_member_unban(guild, user):
    moderator = await get_audit_user(guild, discord.AuditLogAction.unban)
    embed = log_embed(
        "✅ Member Unbanned",
        f"**User:** `{user}` (`{user.id}`)\n**By:** {moderator.mention if moderator else 'Unknown'}",
        color=0x57F287
    )
    await send_log(guild, "member_unban", embed)


@bot.event
async def on_message_delete(message):
    if not message.guild:
        return


    if message.author.bot:
        return

    content = message.content or "*[no text content]*"
    embed = log_embed(
        "🗑️ Message Deleted",
        f"**Author:** {message.author.mention} (`{message.author}`)\n**Channel:** {message.channel.mention}\n**Content:**\n{content[:1000]}",
        color=0xED4245
    )
    await send_log(message.guild, "message_delete", embed)


@bot.event
async def on_message_edit(before, after):
    if not before.guild:
        return

    if before.content == after.content:
        return


    if before.author.bot:
        return

    embed = log_embed(
        "✏️ Message Edited",
        f"**Author:** {before.author.mention} (`{before.author}`)\n**Channel:** {before.channel.mention}\n**Before:**\n{before.content[:500]}\n**After:**\n{after.content[:500]}\n[Jump to message]({after.jump_url})",
        color=0xFEE75C
    )
    await send_log(before.guild, "message_edit", embed)


@bot.event
async def on_guild_role_create(role):
    user = await get_audit_user(role.guild, discord.AuditLogAction.role_create)
    embed = log_embed(
        "🎭 Role Created",
        f"**Role:** {role.mention} (`{role.name}`)\n**By:** {user.mention if user else 'Unknown'}",
        color=0x57F287
    )
    await send_log(role.guild, "role_create", embed)


@bot.event
async def on_guild_role_delete(role):
    user = await get_audit_user(role.guild, discord.AuditLogAction.role_delete)
    embed = log_embed(
        "🗑️ Role Deleted",
        f"**Role:** `{role.name}`\n**By:** {user.mention if user else 'Unknown'}",
        color=0xED4245
    )
    await send_log(role.guild, "role_delete", embed)


@bot.event
async def on_member_update(before, after):
    if before.roles != after.roles:
        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        parts = []
        if added:
            parts.append(f"**Roles added:** {', '.join(r.mention for r in added)}")
        if removed:
            parts.append(f"**Roles removed:** {', '.join(r.mention for r in removed)}")
        if parts:
            embed = log_embed(
                "👤 Member Updated",
                f"**Member:** {after.mention} (`{after}`)\n" + "\n".join(parts),
                color=0x5865F2
            )
            await send_log(after.guild, "member_update", embed)

    if before.nick != after.nick:
        embed = log_embed(
            "✏️ Nickname Changed",
            f"**Member:** {after.mention} (`{after}`)\n**Before:** {before.nick or 'None'}\n**After:** {after.nick or 'None'}",
            color=0x5865F2
        )
        await send_log(after.guild, "member_update", embed)


@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel == after.channel:
        return

    if after.channel and not before.channel:
        desc = f"**{member}** joined **{after.channel.name}**"
        color = 0x57F287
    elif before.channel and not after.channel:
        desc = f"**{member}** left **{before.channel.name}**"
        color = 0xED4245
    else:
        desc = f"**{member}** moved from **{before.channel.name}** → **{after.channel.name}**"
        color = 0xFEE75C

    embed = log_embed("🔊 Voice Update", desc, color=color)
    await send_log(member.guild, "voice_update", embed)


@bot.event
async def on_message(message):
    if not message.guild:
        await bot.process_commands(message)
        return


    if message.author.bot:
        return

    cfg = get_guild(message.guild.id)

    if cfg.get("profanity_filter", False):

        words = message.content.lower().split()

        for word in words:

            filter_cursor.execute(
                "SELECT 1 FROM banned_words WHERE word=?",
                (word,)
            )

            if filter_cursor.fetchone():

                try:
                    await message.delete()
                except:
                    pass

                await message.channel.send(
                    f"{message.author.mention}, please avoid profanity.",
                    delete_after=5
                )
                return

    # Premium auto-responder (keyword / regex)
    if await try_autorespond(message):
        # still allow XP / sticky / commands after a response? skip custom cmd steal
        pass

    # Free XP
    await maybe_award_xp(message)

    if message.content.startswith("*"):

        cmd = message.content[1:].split()[0].lower()

        custom_cursor.execute(
            """
            SELECT response
            FROM custom_commands
            WHERE guild_id=? AND command=?
            """,
            (
                message.guild.id,
                cmd
            )
        )

        row = custom_cursor.fetchone()

        if row:
            await message.channel.send(row[0])
            # restick after custom command reply
            if str(message.channel.id) in stickies:
                await restick_message(message.channel)
            return

    await bot.process_commands(message)

    # Free sticky — keep pinned reply at bottom
    if str(message.channel.id) in stickies:
        await restick_message(message.channel)


# ============================================================
# HELP UI
# ============================================================

class HelpDropdown(discord.ui.Select):
    def __init__(self):
        options = [
    discord.SelectOption(label="Moderation", emoji="🛡️"),
    discord.SelectOption(label="Antinuke", emoji="🚨"),
    discord.SelectOption(label="Channel Management", emoji="🔒"),
    discord.SelectOption(label="Utility", emoji="⚙️"),
    discord.SelectOption(label="Free Features", emoji="✨"),
    discord.SelectOption(label="Premium Features", emoji="💎"),
    discord.SelectOption(label="Backups", emoji="💾"),
    discord.SelectOption(label="Welcome", emoji="👋"),
    discord.SelectOption(label="Logs", emoji="📋"),
    discord.SelectOption(label="Custom Commands", emoji="🧩")
]

        super().__init__(
            placeholder="Choose a section...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]

        embed = discord.Embed(
            title=f"Beacon Help - {choice}",
            color=0x5865F2
        )

        if choice == "Moderation":
            embed.description = """
`/ban` or `*ban` - Ban a user.
`/kick` or `*kick` - Kick a user.
`/mute` or `*mute` - Mute a user.
`/unmute` or `*unmute` - Unmute a user.
`/jail` or `*jail` - Jail a user.
`/unjail` or `*unjail` - Unjail a user.
`/warn` or `*warn` - Warn a user.
`/warnings` or `*warnings` - View warnings.
`/clearwarnings` or `*clearwarnings` - Clear warnings.
`/purge` or `*purge` - Delete messages.
"""

        elif choice == "Antinuke":
            embed.description = """
`/antinuke` or `*antinuke` - View status.
`/antinuke_on` or `*antinuke_on` - Enable antinuke and create backup.
`/antinuke_off` or `*antinuke_off` - Disable antinuke.
`/anpunishment` or `*anpunishment` - Set punishment: ban, kick, jail.
`/anwhitelist` or `*anwhitelist` - Whitelist a user.
`/anunwhitelist` or `*anunwhitelist` - Remove whitelist.

Only trigger:
- Channel create: 5 in 10s

On trigger:
- punish nuker
- slowly wipe channels/roles it can delete
- restore from backup
- restore name/icon slowly
- re-backup
"""

        elif choice == "Channel Management":
            embed.description = """
`/lock` or `*lock` - Lock current channel.
`/unlock` or `*unlock` - Unlock current channel.
`/hide` or `*hide` - Hide current channel.
`/show` or `*show` - Show current channel.
`/lockdown` or `*lockdown` - Lock all text channels.
`/unlockdown` or `*unlockdown` - Unlock all text channels.
"""

        elif choice == "Utility":
            embed.description = """
`/help` or `*help` - Show help menu.
`/ping` or `*ping` - Bot latency.
`/serverinfo` or `*serverinfo` - Server info.
`/userinfo` or `*userinfo` - User info.
`/membercount` or `*membercount` - Member count.
`/dirt` or `*dirt` - DIRT.
`/generate` or `*generate <prompt>` - Cartoon AI image (moderated). Example: astronaut cat.
`/emojisteal` — **paste** a custom emoji (User App works in any server). Or type a name if Beacon is in that server. Right-click message → Apps → Steal emojis.

"""


        elif choice == "Free Features":
            embed.description = """
`/sticky` or `*sticky <text>` - Keep a sticky message at the bottom of this channel.
`/unsticky` or `*unsticky` - Remove the sticky.
`/poll` or `*poll Question | Option A | Option B | ...` - Create a button poll.
`/remind` or `*remind 2h take out trash` - Set a reminder in this channel.
`/level` or `*level` / `*rank [@user]` - View XP level (basic, no role rewards).
`/leaderboard` or `*leaderboard` - Top XP in this server.

**Economy (free)**
`/balance` `/daily` `/pay` or `*balance` `*daily` `*pay @user amount`
`/shop` `/buy` or `*shop` `*buy <item>`
`/shopadd` `/shoprole` `/shopremove` — manage shop (Manage Server)
`/givemoney` or `*givemoney @user amount` — Seekara staff only
"""

        elif choice == "Premium Features":
            embed.description = """
**Requires Beacon Premium** (you or the server owner).

`/temprole` or `*temprole @user @Role 7d` - Temporary role grant (auto-removes).
`/temproles` or `*temproles` - List active temp roles in this server.

`/autorespond` or `*autorespond add <keyword> | <response>` - Keyword auto-reply.
`*autorespond regex <pattern> | <response>` / `list` / `remove <number>`

`/invites` or `*invites [@user]` - Invite tracker (real vs fake).
Fake invites = joined accounts younger than 7 days.

**Seekara staff** (bot owner assigns with `*staff add`)
`/staff` or `*staff add|remove|list` — owner only
Staff can use: `/givemoney`
Owner only: `/premium` `/broadcast`
"""

        elif choice == "Backups":
            embed.description = """
`/backup` or `*backup` - Save server backup: name, icon, roles, channels, and permissions. Does not save emojis or sounds.
`/restore` or `*restore` - Restore missing structure.
`/wiperestore` or `*wiperestore` - Fully wipe then restore.

Server backups are saved in:
`backups/<server_id>.json`

"""

        elif choice == "Welcome":
            embed.description = """
`/setwelcome` or `*setwelcome #channel` - Set the welcome channel and enable it.
`/welcomemessage` or `*welcomemessage <msg>` - Set a custom welcome message.
`/welcometoggle` or `*welcometoggle` - Enable/disable the welcome system.
`/welcomeembed` or `*welcomeembed` - Toggle embed on/off.
`/welcometest` or `*welcometest` - Send a test welcome for yourself.
`/welcomeinfo` or `*welcomeinfo` - View current settings.

**Placeholders:** `{mention}` `{user}` `{username}` `{server}` `{count}` `{id}`
"""

        elif choice == "Logs":
            embed.description = """
`/setlog` or `*setlog #channel` - Set the log channel and enable logging.
`/logtoggle` or `*logtoggle` - Enable/disable logging.
`/logevent` or `*logevent <event>` - Toggle a specific event on/off.
`/loginfo` or `*loginfo` - View current settings and event status.

**Events:** `member_join` `member_leave` `member_ban` `member_unban`
`message_delete` `message_edit` `channel_create` `channel_delete`
`role_create` `role_delete` `member_update` `voice_update`
"""

        elif choice == "Custom Commands":
            embed.description = """
**Beacon Premium Feature**

Create custom prefix commands that work only in your server.

### Admin Commands

`/addcommand` or `*addcommand <name> <response>`
Create a custom command.

`/editcommand` or `*editcommand <name> <new response>`
Edit an existing command.

`/deletecommand` or `*deletecommand <name>`
Delete a custom command.

`/listcommands` or `*listcommands`
View every custom command.

### Using Commands

`*addcommand rules Read the rules!`

Users can then type:

`*rules`

### Limits

• Maximum **10** custom commands per server.
• Custom commands are **prefix only**.
• Beacon Premium feature.
"""

        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(HelpDropdown())


async def send_help(send_func):
    embed = discord.Embed(
        title="Beacon Help",
        description="Select a category below.",
        color=0x5865F2
    )

    await send_func(embed=embed, view=HelpView())


# ============================================================
# COMMAND LOGIC
# ============================================================

async def do_ping(send):
    await send(f"Pong: `{round(bot.latency * 1000)}ms`")


async def do_serverinfo(guild, send):
    await send(
        f"""
**Server:** {guild.name}
**Members:** {guild.member_count}
**Roles:** {len(guild.roles)}
**Channels:** {len(guild.channels)}
"""
    )


async def do_userinfo(member, send):
    await send(
        f"""
**User:** {member}
**ID:** {member.id}
**Joined:** {member.joined_at}
"""
    )


async def do_membercount(guild, send):
    await send(f"Members: `{guild.member_count}`")


async def do_ban(member, reason, send):
    await member.ban(reason=reason)
    await send(f"Banned `{member}`")


async def do_kick(member, reason, send):
    await member.kick(reason=reason)
    await send(f"Kicked `{member}`")


async def do_purge(channel, amount, send):
    await channel.purge(limit=amount)
    await send(f"Deleted `{amount}` messages")


async def do_jail(guild, member, send):
    role = discord.utils.get(guild.roles, name="Jailed")

    if role is None:
        role = await setup_jail(guild)

    await member.add_roles(role)

    await send(f"Jailed `{member}`")


async def do_unjail(guild, member, send):
    role = discord.utils.get(guild.roles, name="Jailed")

    if role:
        await member.remove_roles(role)

    await send(f"Unjailed `{member}`")


async def do_mute(guild, member, send):
    role = discord.utils.get(guild.roles, name="Muted")

    if role is None:
        role = await setup_mute(guild)

    await member.add_roles(role)

    await send(f"Muted `{member}`")


async def do_unmute(guild, member, send):
    role = discord.utils.get(guild.roles, name="Muted")

    if role:
        await member.remove_roles(role)

    await send(f"Unmuted `{member}`")


async def do_warn(guild, member, reason, send):
    gid = str(guild.id)
    uid = str(member.id)

    if gid not in warns:
        warns[gid] = {}

    if uid not in warns[gid]:
        warns[gid][uid] = []

    warns[gid][uid].append({
        "reason": reason,
        "time": int(time.time())
    })

    save_warns()

    await send(f"Warned `{member}` for `{reason}`")


async def do_warnings(guild, member, send):
    gid = str(guild.id)
    uid = str(member.id)

    if gid not in warns or uid not in warns[gid] or len(warns[gid][uid]) == 0:
        await send("No warnings.")
        return

    text = ""

    for index, warning in enumerate(warns[gid][uid], start=1):
        if isinstance(warning, dict):
            reason = warning.get("reason", "No reason")
        else:
            reason = str(warning)

        text += f"`{index}.` {reason}\n"

    await send(text)


async def do_clearwarnings(guild, member, send):
    gid = str(guild.id)
    uid = str(member.id)

    if gid in warns and uid in warns[gid]:
        warns[gid][uid] = []
        save_warns()

    await send(f"Cleared warnings for `{member}`")


async def do_lock(channel, guild, send):
    await channel.set_permissions(guild.default_role, send_messages=False)
    await send("Channel locked.")


async def do_unlock(channel, guild, send):
    await channel.set_permissions(guild.default_role, send_messages=True)
    await send("Channel unlocked.")


async def do_hide(channel, guild, send):
    await channel.set_permissions(guild.default_role, view_channel=False)
    await send("Channel hidden.")


async def do_show(channel, guild, send):
    await channel.set_permissions(guild.default_role, view_channel=True)
    await send("Channel visible.")


async def do_lockdown(guild, send):
    count = 0

    for channel in guild.text_channels:
        try:
            await channel.set_permissions(guild.default_role, send_messages=False)
            count += 1
            await asyncio.sleep(4)
        except:
            pass

    await send(f"Locked `{count}` channels.")


async def do_unlockdown(guild, send):
    count = 0

    for channel in guild.text_channels:
        try:
            await channel.set_permissions(guild.default_role, send_messages=True)
            count += 1
            await asyncio.sleep(4)
        except:
            pass

    await send(f"Unlocked `{count}` channels.")


async def do_antinuke(guild, send):
    cfg = get_guild(guild.id)
    backup_exists = os.path.exists(backup_path(guild.id))

    await send(
        f"""
**Beacon Antinuke**
Enabled: `{cfg["antinuke"]}`
Punishment: `{cfg["punishment"]}`
Whitelist: `{len(cfg["whitelist"])}`
Backup exists: `{backup_exists}`
Wipe before restore: `{cfg["wipe_before_restore"]}`

Only trigger:
Channel create: `{cfg["channel_create_limit"]} in {cfg["channel_create_seconds"]}s`
"""
    )


# ============================================================
# WELCOME COMMANDS
# ============================================================

@tree.command(name="profanity", description="Enable or disable the profanity filter")
@app_commands.describe(
    state="Choose on or off"
)
@app_commands.choices(
    state=[
        app_commands.Choice(name="On", value="on"),
        app_commands.Choice(name="Off", value="off")
    ]
)
@app_commands.checks.has_permissions(administrator=True)
async def slash_profanity(
    interaction: discord.Interaction,
    state: app_commands.Choice[str]
):

    cfg = get_guild(interaction.guild.id)
    cfg["profanity_filter"] = state.value == "on"
    save_config()

    await interaction.response.send_message(
        f"✅ Profanity filter {'enabled' if state.value == 'on' else 'disabled'}.",
        ephemeral=True
    )

@tree.command(name="setwelcome", description="Set the welcome channel")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = get_guild(interaction.guild.id)
    cfg["welcome_channel"] = channel.id
    cfg["welcome_enabled"] = True
    save_config()
    await interaction.response.send_message(f"Welcome channel set to {channel.mention}. Welcomes enabled.")


@tree.command(name="welcomemessage", description="Set a custom welcome message")
@app_commands.checks.has_permissions(administrator=True)
async def slash_welcomemessage(interaction: discord.Interaction, message: str):
    cfg = get_guild(interaction.guild.id)
    cfg["welcome_message"] = message
    save_config()
    await interaction.response.send_message(
        f"Welcome message updated.\n\n**Preview:**\n{format_welcome_message(message, interaction.user)}\n\n"
        f"**Placeholders:** `{{mention}}` `{{user}}` `{{username}}` `{{server}}` `{{count}}` `{{id}}`"
    )


@tree.command(name="welcometest", description="Test the current welcome message")
@app_commands.checks.has_permissions(administrator=True)
async def slash_welcometest(interaction: discord.Interaction):
    await send_welcome(interaction.user)
    await interaction.response.send_message("Sent a test welcome message!", ephemeral=True)


@tree.command(name="welcometoggle", description="Enable or disable the welcome system")
@app_commands.checks.has_permissions(administrator=True)
async def slash_welcometoggle(interaction: discord.Interaction):
    cfg = get_guild(interaction.guild.id)
    cfg["welcome_enabled"] = not cfg.get("welcome_enabled", False)
    save_config()
    state = "enabled" if cfg["welcome_enabled"] else "disabled"
    await interaction.response.send_message(f"Welcome system {state}.")
    
@tree.command(name="addcommand", description="Create a custom command")
@app_commands.describe(
    name="Command name",
    response="Command response"
)
async def slash_addcommand(interaction: discord.Interaction, name: str, response: str):

    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message(
            "❌ You need Manage Server.",
            ephemeral=True
        )

    if not has_premium_access(interaction.guild, interaction.user):
        return await interaction.response.send_message(
            "❌ Custom commands are a Beacon Premium feature.",
            ephemeral=True
        )

    custom_cursor.execute(
        "SELECT COUNT(*) FROM custom_commands WHERE guild_id=?",
        (interaction.guild.id,)
    )

    if custom_cursor.fetchone()[0] >= 10:
        return await interaction.response.send_message(
            "❌ Maximum of 10 custom commands.",
            ephemeral=True
        )

    custom_cursor.execute(
        """
        INSERT OR REPLACE INTO custom_commands
        VALUES(?,?,?)
        """,
        (
            interaction.guild.id,
            name.lower(),
            response
        )
    )

    custom_db.commit()

    await interaction.response.send_message(
        f"✅ Created `*{name}`.",
        ephemeral=True
    )
    
@tree.command(name="deletecommand", description="Delete a custom command")
async def slash_deletecommand(interaction: discord.Interaction, name: str):

    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message(
            "❌ You need Manage Server.",
            ephemeral=True
        )

    if not has_premium_access(interaction.guild, interaction.user):
        return await interaction.response.send_message(
            "❌ Premium feature.",
            ephemeral=True
        )

    custom_cursor.execute(
        """
        DELETE FROM custom_commands
        WHERE guild_id=? AND command=?
        """,
        (
            interaction.guild.id,
            name.lower()
        )
    )

    custom_db.commit()

    await interaction.response.send_message(
        "✅ Deleted.",
        ephemeral=True
    )
    
@tree.command(name="listcommands", description="List custom commands")
async def slash_listcommands(interaction: discord.Interaction):

    custom_cursor.execute(
        """
        SELECT command
        FROM custom_commands
        WHERE guild_id=?
        ORDER BY command
        """,
        (interaction.guild.id,)
    )

    rows = custom_cursor.fetchall()

    if not rows:
        return await interaction.response.send_message(
            "No custom commands.",
            ephemeral=True
        )

    cmds = "\n".join(f"• *{r[0]}" for r in rows)

    await interaction.response.send_message(
        f"**Custom Commands**\n{cmds}",
        ephemeral=True
    )
    
@tree.command(name="editcommand", description="Edit a custom command")
@app_commands.describe(
    name="Command name",
    response="New response"
)
async def slash_editcommand(interaction: discord.Interaction, name: str, response: str):

    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message(
            "❌ You need Manage Server.",
            ephemeral=True
        )

    if not has_premium_access(interaction.guild, interaction.user):
        return await interaction.response.send_message(
            "❌ Premium feature.",
            ephemeral=True
        )

    custom_cursor.execute(
        """
        UPDATE custom_commands
        SET response=?
        WHERE guild_id=? AND command=?
        """,
        (
            response,
            interaction.guild.id,
            name.lower()
        )
    )

    custom_db.commit()

    await interaction.response.send_message(
        "✅ Updated.",
        ephemeral=True
    )


@tree.command(name="welcomeembed", description="Toggle welcome embed on/off")
@app_commands.checks.has_permissions(administrator=True)
async def slash_welcomeembed(interaction: discord.Interaction):
    cfg = get_guild(interaction.guild.id)
    cfg["welcome_embed"] = not cfg.get("welcome_embed", True)
    save_config()
    state = "enabled" if cfg["welcome_embed"] else "disabled"
    await interaction.response.send_message(f"Welcome embed {state}.")


@tree.command(name="welcomeinfo", description="View current welcome settings")
@app_commands.checks.has_permissions(administrator=True)
async def slash_welcomeinfo(interaction: discord.Interaction):
    cfg = get_guild(interaction.guild.id)
    channel_id = cfg.get("welcome_channel")
    channel = interaction.guild.get_channel(int(channel_id)) if channel_id else None
    embed = discord.Embed(title="Welcome Settings", color=0x5865F2)
    embed.add_field(name="Enabled", value=str(cfg.get("welcome_enabled", False)), inline=True)
    embed.add_field(name="Channel", value=channel.mention if channel else "Not set", inline=True)
    embed.add_field(name="Embed", value=str(cfg.get("welcome_embed", True)), inline=True)
    embed.add_field(name="Message", value=f"`{cfg.get('welcome_message', 'Not set')}`", inline=False)
    await interaction.response.send_message(embed=embed)


# BROADCAST
async def do_broadcast(author, message, send):
    if not is_bot_owner(author.id):
        return await send("❌ Only the bot owner can use this.")

    sent = 0
    failed = 0

    for guild in bot.guilds:
        channel = guild.system_channel

        if channel is None or not channel.permissions_for(guild.me).send_messages:
            channel = None
            for c in guild.text_channels:
                perms = c.permissions_for(guild.me)
                if perms.view_channel and perms.send_messages:
                    channel = c
                    break

        if channel is None:
            failed += 1
            continue

        try:
            embed = discord.Embed(
                title="📢 Beacon Announcement",
                description=message,
                color=0x5865F2,
            )
            await channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            sent += 1
        except Exception as e:
            print(f"{guild.name}: {e}")
            failed += 1

    await send(
        f"✅ Broadcast complete.\n"
        f"Sent: **{sent}** server(s)\n"
        f"Failed: **{failed}**"
    )


@tree.command(name="broadcast", description="Broadcast a message to every server.")
@app_commands.describe(message="The announcement to send")
async def slash_broadcast(interaction: discord.Interaction, message: str):
    await interaction.response.defer(ephemeral=True)
    await do_broadcast(interaction.user, message, _slash_send(interaction, ephemeral=True))


@bot.command(name="broadcast")
async def prefix_broadcast(ctx, *, message: str = None):
    if not message:
        return await ctx.send("Usage: `*broadcast <message>`")
    await do_broadcast(ctx.author, message, ctx.send)


# ============================================================
# PREMIUM (bot owner only) — writes premium_users.txt next to smmod.py
# Premium unlocks are checked against the SERVER OWNER's Discord id.
# ============================================================

@tree.command(name="premium", description="Add/remove/list premium user ids (bot owner only)")
@app_commands.describe(
    action="add, remove, or list",
    user_id="Discord user id (server owner id) or @mention — required for add/remove",
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="remove", value="remove"),
        app_commands.Choice(name="list", value="list"),
    ]
)
async def slash_premium(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    user_id: str = None,
):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("❌ Only the bot owner can use this.", ephemeral=True)
        return

    act = action.value

    if act == "list":
        ids = sorted(load_premium_ids(), key=lambda x: int(x))
        if not ids:
            await interaction.response.send_message(
                f"No premium users yet.\nFile: `{PREMIUM_FILE}`",
                ephemeral=True,
            )
            return
        lines = "\n".join(f"<@{uid}> `{uid}`" for uid in ids)
        await interaction.response.send_message(
            f"**Premium users** ({len(ids)})\n{lines}\nFile: `{PREMIUM_FILE}`",
            ephemeral=True,
        )
        return

    uid = normalize_premium_id(user_id)
    if uid is None and interaction.data:
        # also accept a pasted mention in the string
        pass
    if uid is None:
        await interaction.response.send_message(
            "Usage: `/premium add user_id:<id>` or `/premium remove user_id:<id>`\n"
            "Put the **server owner's** Discord user id (Developer Mode → Copy User ID).",
            ephemeral=True,
        )
        return

    if act == "add":
        added, uid = add_premium_user(uid)
        live = is_premium(uid)
        if added:
            await interaction.response.send_message(
                f"✅ Granted premium to <@{uid}> (`{uid}`).\n"
                f"Live check: **{'yes' if live else 'no'}**\n"
                f"Saved to `{PREMIUM_FILE}`",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"<@{uid}> (`{uid}`) was already premium.\n"
                f"Live check: **{'yes' if live else 'no'}**",
                ephemeral=True,
            )
        return

    # remove
    removed, uid = remove_premium_user(uid)
    if removed:
        await interaction.response.send_message(
            f"✅ Removed premium from <@{uid}> (`{uid}`).",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            f"<@{uid}> (`{uid}`) was not premium.",
            ephemeral=True,
        )


@bot.command(name="premium")
async def prefix_premium(ctx, action: str = None, user_id: str = None):
    if not is_bot_owner(ctx.author.id):
        return await ctx.send("❌ Only the bot owner can use this.")

    action = (action or "").strip().lower()

    if action in {"", "list", "ls"}:
        ids = sorted(load_premium_ids(), key=lambda x: int(x))
        if not ids:
            return await ctx.send(f"No premium users yet.\nFile: `{PREMIUM_FILE}`")
        lines = "\n".join(f"<@{uid}> `{uid}`" for uid in ids)
        return await ctx.send(f"**Premium users** ({len(ids)})\n{lines}")

    if action not in {"add", "remove", "rm", "del", "delete"}:
        return await ctx.send(
            "Usage: `*premium add <id|@user>` · `*premium remove <id|@user>` · `*premium list`"
        )

    uid = None
    if ctx.message.mentions:
        uid = normalize_premium_id(ctx.message.mentions[0].id)
    if uid is None:
        uid = normalize_premium_id(user_id)
    if uid is None:
        return await ctx.send(
            "Put a valid Discord user id (server owner id) or @mention."
        )

    if action == "add":
        added, uid = add_premium_user(uid)
        live = is_premium(uid)
        if added:
            return await ctx.send(
                f"✅ Granted premium to <@{uid}> (`{uid}`). Live check: **{'yes' if live else 'no'}**."
            )
        return await ctx.send(
            f"<@{uid}> (`{uid}`) was already premium. Live check: **{'yes' if live else 'no'}**."
        )

    removed, uid = remove_premium_user(uid)
    if removed:
        return await ctx.send(f"✅ Removed premium from <@{uid}> (`{uid}`).")
    return await ctx.send(f"<@{uid}> (`{uid}`) was not premium.")


# ============================================================
# SEEKARA STAFF — only bot owner assigns; staff can use owner cmds
# ============================================================

@tree.command(name="staff", description="Add/remove/list Seekara staff (bot owner only)")
@app_commands.describe(
    action="add, remove, or list",
    user_id="Discord user id or @mention — required for add/remove",
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="remove", value="remove"),
        app_commands.Choice(name="list", value="list"),
    ]
)
async def slash_staff(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    user_id: str = None,
):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message(
            "❌ Only the bot owner can manage Seekara staff.",
            ephemeral=True,
        )
        return

    act = action.value
    if act == "list":
        ids = sorted(load_staff_ids(), key=lambda x: int(x))
        if not ids:
            await interaction.response.send_message(
                f"No Seekara staff yet (you are always staff).\nFile: `{STAFF_FILE}`",
                ephemeral=True,
            )
            return
        lines = "\n".join(f"<@{uid}> `{uid}`" for uid in ids)
        await interaction.response.send_message(
            f"**Seekara staff** ({len(ids)})\n{lines}\n"
            f"+ owner <@{BOT_OWNER_ID}>\nFile: `{STAFF_FILE}`",
            ephemeral=True,
        )
        return

    uid = normalize_premium_id(user_id)
    if uid is None:
        await interaction.response.send_message(
            "Usage: `/staff add user_id:<id>` or `/staff remove user_id:<id>`",
            ephemeral=True,
        )
        return

    if act == "add":
        if uid == str(BOT_OWNER_ID):
            await interaction.response.send_message(
                "Owner is already Seekara staff.", ephemeral=True
            )
            return
        added, uid = add_staff_user(uid)
        if added:
            await interaction.response.send_message(
                f"✅ Added Seekara staff <@{uid}> (`{uid}`).\nSaved to `{STAFF_FILE}`",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"<@{uid}> (`{uid}`) is already Seekara staff.",
                ephemeral=True,
            )
        return

    if uid == str(BOT_OWNER_ID):
        await interaction.response.send_message(
            "Can't remove the bot owner from staff.", ephemeral=True
        )
        return
    removed, uid = remove_staff_user(uid)
    if removed:
        await interaction.response.send_message(
            f"✅ Removed Seekara staff <@{uid}> (`{uid}`).",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            f"<@{uid}> (`{uid}`) was not Seekara staff.",
            ephemeral=True,
        )


@bot.command(name="staff", aliases=["seekara", "seekarastaff"])
async def prefix_staff(ctx, action: str = None, user_id: str = None):
    if not is_bot_owner(ctx.author.id):
        return await ctx.send("❌ Only the bot owner can manage Seekara staff.")

    action = (action or "").strip().lower()
    if action in {"", "list", "ls"}:
        ids = sorted(load_staff_ids(), key=lambda x: int(x))
        if not ids:
            return await ctx.send(
                f"No Seekara staff yet (you are always staff).\nFile: `{STAFF_FILE}`"
            )
        lines = "\n".join(f"<@{uid}> `{uid}`" for uid in ids)
        return await ctx.send(
            f"**Seekara staff** ({len(ids)})\n{lines}\n+ owner <@{BOT_OWNER_ID}>"
        )

    if action not in {"add", "remove", "rm", "del", "delete"}:
        return await ctx.send(
            "Usage: `*staff add <id|@user>` · `*staff remove <id|@user>` · `*staff list`"
        )

    uid = None
    if ctx.message.mentions:
        uid = normalize_premium_id(ctx.message.mentions[0].id)
    if uid is None:
        uid = normalize_premium_id(user_id)
    if uid is None:
        return await ctx.send("Put a valid Discord user id or @mention.")

    if action == "add":
        if uid == str(BOT_OWNER_ID):
            return await ctx.send("Owner is already Seekara staff.")
        added, uid = add_staff_user(uid)
        if added:
            return await ctx.send(f"✅ Added Seekara staff <@{uid}> (`{uid}`).")
        return await ctx.send(f"<@{uid}> (`{uid}`) is already Seekara staff.")

    if uid == str(BOT_OWNER_ID):
        return await ctx.send("Can't remove the bot owner from staff.")
    removed, uid = remove_staff_user(uid)
    if removed:
        return await ctx.send(f"✅ Removed Seekara staff <@{uid}> (`{uid}`).")
    return await ctx.send(f"<@{uid}> (`{uid}`) was not Seekara staff.")


# ============================================================
# LOG COMMANDS
# ============================================================

@tree.command(name="setlog", description="Set the log channel")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setlog(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = get_guild(interaction.guild.id)
    cfg["log_channel"] = channel.id
    cfg["log_enabled"] = True
    save_config()
    await interaction.response.send_message(f"Log channel set to {channel.mention}. Logging enabled.")


@tree.command(name="logtoggle", description="Enable or disable the log system")
@app_commands.checks.has_permissions(administrator=True)
async def slash_logtoggle(interaction: discord.Interaction):
    cfg = get_guild(interaction.guild.id)
    cfg["log_enabled"] = not cfg.get("log_enabled", False)
    save_config()
    state = "enabled" if cfg["log_enabled"] else "disabled"
    await interaction.response.send_message(f"Logging {state}.")


@tree.command(name="logevent", description="Toggle a specific log event on/off")
@app_commands.checks.has_permissions(administrator=True)
async def slash_logevent(
    interaction: discord.Interaction,
    event: str
):
    valid_events = [
        "member_join", "member_leave", "member_ban", "member_unban",
        "message_delete", "message_edit", "channel_create", "channel_delete",
        "role_create", "role_delete", "member_update", "voice_update"
    ]

    if event not in valid_events:
        await interaction.response.send_message(
            f"Invalid event. Valid events:\n`{'`, `'.join(valid_events)}`"
        )
        return

    cfg = get_guild(interaction.guild.id)
    log_events = cfg.get("log_events", {})
    log_events[event] = not log_events.get(event, True)
    cfg["log_events"] = log_events
    save_config()
    state = "enabled" if log_events[event] else "disabled"
    await interaction.response.send_message(f"Log event `{event}` {state}.")


@tree.command(name="loginfo", description="View current log settings")
@app_commands.checks.has_permissions(administrator=True)
async def slash_loginfo(interaction: discord.Interaction):
    cfg = get_guild(interaction.guild.id)
    channel_id = cfg.get("log_channel")
    channel = interaction.guild.get_channel(int(channel_id)) if channel_id else None
    log_events = cfg.get("log_events", {})

    embed = discord.Embed(title="Log Settings", color=0x5865F2)
    embed.add_field(name="Enabled", value=str(cfg.get("log_enabled", False)), inline=True)
    embed.add_field(name="Channel", value=channel.mention if channel else "Not set", inline=True)

    event_lines = "\n".join(
        f"{'✅' if log_events.get(e, True) else '❌'} `{e}`"
        for e in [
            "member_join", "member_leave", "member_ban", "member_unban",
            "message_delete", "message_edit", "channel_create", "channel_delete",
            "role_create", "role_delete", "member_update", "voice_update"
        ]
    )
    embed.add_field(name="Events", value=event_lines, inline=False)
    await interaction.response.send_message(embed=embed)


# ============================================================
# SLASH COMMANDS
# ============================================================


@tree.command(name="help", description="Show help")
async def slash_help(interaction: discord.Interaction):
    await send_help(interaction.response.send_message)


@tree.command(name="ping", description="Bot latency")
async def slash_ping(interaction: discord.Interaction):
    await do_ping(interaction.response.send_message)


@tree.command(name="serverinfo", description="Server info")
async def slash_serverinfo(interaction: discord.Interaction):
    await do_serverinfo(interaction.guild, interaction.response.send_message)


@tree.command(name="userinfo", description="User info")
async def slash_userinfo(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    await do_userinfo(member, interaction.response.send_message)


@tree.command(name="membercount", description="Member count")
async def slash_membercount(interaction: discord.Interaction):
    await do_membercount(interaction.guild, interaction.response.send_message)


@tree.command(name="ban", description="Ban a user")
@app_commands.checks.has_permissions(ban_members=True)
async def slash_ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
    await do_ban(member, reason, interaction.response.send_message)


@tree.command(name="kick", description="Kick a user")
@app_commands.checks.has_permissions(kick_members=True)
async def slash_kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
    await do_kick(member, reason, interaction.response.send_message)


@tree.command(name="purge", description="Delete messages")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_purge(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)
    await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"Deleted `{amount}` messages.", ephemeral=True)


@tree.command(name="jail", description="Jail member")
@app_commands.checks.has_permissions(manage_roles=True)
async def slash_jail(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer()
    await do_jail(interaction.guild, member, interaction.followup.send)


@tree.command(name="unjail", description="Unjail member")
@app_commands.checks.has_permissions(manage_roles=True)
async def slash_unjail(interaction: discord.Interaction, member: discord.Member):
    await do_unjail(interaction.guild, member, interaction.response.send_message)


@tree.command(name="mute", description="Mute member")
@app_commands.checks.has_permissions(manage_roles=True)
async def slash_mute(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer()
    await do_mute(interaction.guild, member, interaction.followup.send)


@tree.command(name="unmute", description="Unmute member")
@app_commands.checks.has_permissions(manage_roles=True)
async def slash_unmute(interaction: discord.Interaction, member: discord.Member):
    await do_unmute(interaction.guild, member, interaction.response.send_message)


@tree.command(name="warn", description="Warn member")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
    await do_warn(interaction.guild, member, reason, interaction.response.send_message)


@tree.command(name="warnings", description="View warnings")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_warnings(interaction: discord.Interaction, member: discord.Member):
    await do_warnings(interaction.guild, member, interaction.response.send_message)


@tree.command(name="clearwarnings", description="Clear warnings")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_clearwarnings(interaction: discord.Interaction, member: discord.Member):
    await do_clearwarnings(interaction.guild, member, interaction.response.send_message)


@tree.command(name="lock", description="Lock channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def slash_lock(interaction: discord.Interaction):
    await do_lock(interaction.channel, interaction.guild, interaction.response.send_message)


@tree.command(name="unlock", description="Unlock channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def slash_unlock(interaction: discord.Interaction):
    await do_unlock(interaction.channel, interaction.guild, interaction.response.send_message)


@tree.command(name="hide", description="Hide channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def slash_hide(interaction: discord.Interaction):
    await do_hide(interaction.channel, interaction.guild, interaction.response.send_message)


@tree.command(name="show", description="Show channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def slash_show(interaction: discord.Interaction):
    await do_show(interaction.channel, interaction.guild, interaction.response.send_message)


@tree.command(name="lockdown", description="Lock all text channels")
@app_commands.checks.has_permissions(administrator=True)
async def slash_lockdown(interaction: discord.Interaction):
    await interaction.response.defer()
    await do_lockdown(interaction.guild, interaction.followup.send)


@tree.command(name="unlockdown", description="Unlock all text channels")
@app_commands.checks.has_permissions(administrator=True)
async def slash_unlockdown(interaction: discord.Interaction):
    await interaction.response.defer()
    await do_unlockdown(interaction.guild, interaction.followup.send)


@tree.command(name="antinuke", description="View antinuke")
@app_commands.checks.has_permissions(administrator=True)
async def slash_antinuke(interaction: discord.Interaction):
    await do_antinuke(interaction.guild, interaction.response.send_message)


@tree.command(name="antinuke_on", description="Enable antinuke and create backup")
@app_commands.checks.has_permissions(administrator=True)
async def slash_antinuke_on(interaction: discord.Interaction):
    await interaction.response.defer()

    cfg = get_guild(interaction.guild.id)
    cfg["antinuke"] = True
    save_config()

    await create_backup(interaction.guild)

    await interaction.followup.send("Antinuke enabled and server backup saved.")


@tree.command(name="antinuke_off", description="Disable antinuke")
@app_commands.checks.has_permissions(administrator=True)
async def slash_antinuke_off(interaction: discord.Interaction):
    cfg = get_guild(interaction.guild.id)
    cfg["antinuke"] = False
    save_config()
    await interaction.response.send_message("Antinuke disabled.")


@tree.command(name="anpunishment", description="Set punishment")
@app_commands.checks.has_permissions(administrator=True)
async def slash_anpunishment(interaction: discord.Interaction, punishment: str):
    punishment = punishment.lower()

    if punishment not in ["ban", "kick", "jail"]:
        await interaction.response.send_message("Use: ban, kick, or jail")
        return

    cfg = get_guild(interaction.guild.id)
    cfg["punishment"] = punishment
    save_config()

    await interaction.response.send_message(f"Punishment set to `{punishment}`")


@tree.command(name="anwhitelist", description="Whitelist user")
@app_commands.checks.has_permissions(administrator=True)
async def slash_anwhitelist(interaction: discord.Interaction, member: discord.Member):
    cfg = get_guild(interaction.guild.id)

    if member.id not in cfg["whitelist"]:
        cfg["whitelist"].append(member.id)

    save_config()

    await interaction.response.send_message(f"Whitelisted `{member}`")


@tree.command(name="anunwhitelist", description="Remove whitelist")
@app_commands.checks.has_permissions(administrator=True)
async def slash_anunwhitelist(interaction: discord.Interaction, member: discord.Member):
    cfg = get_guild(interaction.guild.id)

    if member.id in cfg["whitelist"]:
        cfg["whitelist"].remove(member.id)

    save_config()

    await interaction.response.send_message(f"Removed `{member}` from whitelist")


@tree.command(name="backup", description="Create this server's structure backup")
@app_commands.checks.has_permissions(administrator=True)
async def slash_backup(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    await create_backup(interaction.guild)

    path = backup_path(interaction.guild.id)
    message = (
        "Structure backup saved for **this server only**: server name, icon, roles, channels, permissions.\n"
        "Messages are not backed up. Emojis and soundboard sounds were skipped."
    )

    files = []
    if os.path.exists(path) and os.path.getsize(path) <= DISCORD_SAFE_FILE_LIMIT:
        files.append(discord.File(path, filename=public_backup_filename(interaction.guild)))

    if files:
        await interaction.followup.send(message, files=files, ephemeral=True)
    else:
        await interaction.followup.send(
            message + "\nFile is saved server-side but is too big to upload to Discord.",
            ephemeral=True
        )



@tree.command(name="getbackup", description="Download this server's latest backup")
@app_commands.checks.has_permissions(administrator=True)
async def slash_getbackup(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    path = backup_path(interaction.guild.id)

    if not os.path.exists(path):
        await interaction.followup.send("No backup found for this server. Run `/backup` first.", ephemeral=True)
        return

    if os.path.getsize(path) > DISCORD_SAFE_FILE_LIMIT:
        await interaction.followup.send("Backup exists for this server, but it is too big to upload to Discord.", ephemeral=True)
        return

    await interaction.followup.send(
        "Here is the backup for **this server only**.",
        file=discord.File(path, filename=public_backup_filename(interaction.guild)),
        ephemeral=True
    )


@tree.command(name="restore", description="Restore this server from its structure backup")
@app_commands.checks.has_permissions(administrator=True)
async def slash_restore(interaction: discord.Interaction):
    await interaction.response.defer()
    ok, msg = await restore_backup(interaction.guild, wipe_first=False)
    await interaction.followup.send(msg)



@tree.command(name="wiperestore", description="Wipe structure, then restore from backup")
@app_commands.checks.has_permissions(administrator=True)
async def slash_wiperestore(interaction: discord.Interaction):
    await interaction.response.defer()
    ok, msg = await restore_backup(interaction.guild, wipe_first=True)
    await interaction.followup.send(msg)



# ============================================================
# PREFIX COMMANDS
# ============================================================

@bot.command(name="profanity")
@commands.has_permissions(administrator=True)
async def profanity(ctx, state: str):

    state = state.lower()

    if state not in ("on", "off"):
        return await ctx.send("Usage: `*profanity on` or `*profanity off`")

    cfg = get_guild(ctx.guild.id)
    cfg["profanity_filter"] = state == "on"
    save_config()

    await ctx.send(
        f"✅ Profanity filter {'enabled' if state == 'on' else 'disabled'}."
    )


@bot.command(name="help")
async def prefix_help(ctx):
    await send_help(ctx.send)


@bot.command(name="ping")
async def prefix_ping(ctx):
    await do_ping(ctx.send)


@bot.command(name="serverinfo")
async def prefix_serverinfo(ctx):
    await do_serverinfo(ctx.guild, ctx.send)


@bot.command(name="userinfo")
async def prefix_userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    await do_userinfo(member, ctx.send)


@bot.command(name="membercount")
async def prefix_membercount(ctx):
    await do_membercount(ctx.guild, ctx.send)


@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def prefix_ban(ctx, member: discord.Member, *, reason="No reason"):
    await do_ban(member, reason, ctx.send)


@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def prefix_kick(ctx, member: discord.Member, *, reason="No reason"):
    await do_kick(member, reason, ctx.send)


@bot.command(name="purge")
@commands.has_permissions(manage_messages=True)
async def prefix_purge(ctx, amount: int):
    try:
        await ctx.message.delete()
    except:
        pass
    await do_purge(ctx.channel, amount, ctx.send)


@bot.command(name="jail")
@commands.has_permissions(manage_roles=True)
async def prefix_jail(ctx, member: discord.Member):
    await do_jail(ctx.guild, member, ctx.send)


@bot.command(name="unjail")
@commands.has_permissions(manage_roles=True)
async def prefix_unjail(ctx, member: discord.Member):
    await do_unjail(ctx.guild, member, ctx.send)


@bot.command(name="mute")
@commands.has_permissions(manage_roles=True)
async def prefix_mute(ctx, member: discord.Member):
    await do_mute(ctx.guild, member, ctx.send)


@bot.command(name="unmute")
@commands.has_permissions(manage_roles=True)
async def prefix_unmute(ctx, member: discord.Member):
    await do_unmute(ctx.guild, member, ctx.send)


@bot.command(name="warn")
@commands.has_permissions(manage_messages=True)
async def prefix_warn(ctx, member: discord.Member, *, reason="No reason"):
    await do_warn(ctx.guild, member, reason, ctx.send)


@bot.command(name="warnings")
@commands.has_permissions(manage_messages=True)
async def prefix_warnings(ctx, member: discord.Member):
    await do_warnings(ctx.guild, member, ctx.send)


@bot.command(name="clearwarnings")
@commands.has_permissions(manage_messages=True)
async def prefix_clearwarnings(ctx, member: discord.Member):
    await do_clearwarnings(ctx.guild, member, ctx.send)


@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def prefix_lock(ctx):
    await do_lock(ctx.channel, ctx.guild, ctx.send)


@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def prefix_unlock(ctx):
    await do_unlock(ctx.channel, ctx.guild, ctx.send)


@bot.command(name="hide")
@commands.has_permissions(manage_channels=True)
async def prefix_hide(ctx):
    await do_hide(ctx.channel, ctx.guild, ctx.send)


@bot.command(name="show")
@commands.has_permissions(manage_channels=True)
async def prefix_show(ctx):
    await do_show(ctx.channel, ctx.guild, ctx.send)


@bot.command(name="lockdown")
@commands.has_permissions(administrator=True)
async def prefix_lockdown(ctx):
    await do_lockdown(ctx.guild, ctx.send)


@bot.command(name="unlockdown")
@commands.has_permissions(administrator=True)
async def prefix_unlockdown(ctx):
    await do_unlockdown(ctx.guild, ctx.send)


@bot.command(name="antinuke")
@commands.has_permissions(administrator=True)
async def prefix_antinuke(ctx):
    await do_antinuke(ctx.guild, ctx.send)


@bot.command(name="antinuke_on")
@commands.has_permissions(administrator=True)
async def prefix_antinuke_on(ctx):
    cfg = get_guild(ctx.guild.id)
    cfg["antinuke"] = True
    save_config()

    await create_backup(ctx.guild)

    await ctx.send("Antinuke enabled and server backup saved.")


@bot.command(name="antinuke_off")
@commands.has_permissions(administrator=True)
async def prefix_antinuke_off(ctx):
    cfg = get_guild(ctx.guild.id)
    cfg["antinuke"] = False
    save_config()
    await ctx.send("Antinuke disabled.")


@bot.command(name="anpunishment")
@commands.has_permissions(administrator=True)
async def prefix_anpunishment(ctx, punishment: str):
    punishment = punishment.lower()

    if punishment not in ["ban", "kick", "jail"]:
        await ctx.send("Use: ban, kick, or jail")
        return

    cfg = get_guild(ctx.guild.id)
    cfg["punishment"] = punishment
    save_config()

    await ctx.send(f"Punishment set to `{punishment}`")


@bot.command(name="anwhitelist")
@commands.has_permissions(administrator=True)
async def prefix_anwhitelist(ctx, member: discord.Member):
    cfg = get_guild(ctx.guild.id)

    if member.id not in cfg["whitelist"]:
        cfg["whitelist"].append(member.id)

    save_config()

    await ctx.send(f"Whitelisted `{member}`")


@bot.command(name="anunwhitelist")
@commands.has_permissions(administrator=True)
async def prefix_anunwhitelist(ctx, member: discord.Member):
    cfg = get_guild(ctx.guild.id)

    if member.id in cfg["whitelist"]:
        cfg["whitelist"].remove(member.id)

    save_config()

    await ctx.send(f"Removed `{member}` from whitelist")


@bot.command(name="backup")
@commands.has_permissions(administrator=True)
async def prefix_backup(ctx):
    await ctx.send("Backing up server structure now.")

    await create_backup(ctx.guild)

    path = backup_path(ctx.guild.id)
    message = (
        "Structure backup saved for **this server only**: server name, icon, roles, channels, permissions.\n"
        "Messages are not backed up. Emojis and soundboard sounds were skipped."
    )

    files = []
    if os.path.exists(path) and os.path.getsize(path) <= DISCORD_SAFE_FILE_LIMIT:
        files.append(discord.File(path, filename=public_backup_filename(ctx.guild)))

    if files:
        await ctx.send(message, files=files)
    else:
        await ctx.send(message + "\nFile is saved server-side but is too big to upload to Discord.")



@bot.command(name="getbackup")
@commands.has_permissions(administrator=True)
async def prefix_getbackup(ctx):
    path = backup_path(ctx.guild.id)

    if not os.path.exists(path):
        await ctx.send("No backup found for this server. Run `*backup` first.")
        return

    if os.path.getsize(path) > DISCORD_SAFE_FILE_LIMIT:
        await ctx.send("Backup exists for this server, but it is too big to upload to Discord.")
        return

    await ctx.send(
        "Here is the backup for **this server only**.",
        file=discord.File(path, filename=public_backup_filename(ctx.guild))
    )


@bot.command(name="restore")
@commands.has_permissions(administrator=True)
async def prefix_restore(ctx):
    await ctx.send("Restoring server structure from backup.")
    ok, msg = await restore_backup(ctx.guild, wipe_first=False)
    await ctx.send(msg)



@bot.command(name="wiperestore")
@commands.has_permissions(administrator=True)
async def prefix_wiperestore(ctx):
    await ctx.send("Wiping then restoring server structure from backup.")
    ok, msg = await restore_backup(ctx.guild, wipe_first=True)
    await ctx.send(msg)



@bot.command(name="setwelcome")
@commands.has_permissions(administrator=True)
async def prefix_setwelcome(ctx, channel: discord.TextChannel):
    cfg = get_guild(ctx.guild.id)
    cfg["welcome_channel"] = channel.id
    cfg["welcome_enabled"] = True
    save_config()
    await ctx.send(f"Welcome channel set to {channel.mention}. Welcomes enabled.")


@bot.command(name="welcomemessage")
@commands.has_permissions(administrator=True)
async def prefix_welcomemessage(ctx, *, message: str):
    cfg = get_guild(ctx.guild.id)
    cfg["welcome_message"] = message
    save_config()
    await ctx.send(
        f"Welcome message updated.\n**Preview:** {format_welcome_message(message, ctx.author)}\n"
        f"**Placeholders:** `{{mention}}` `{{user}}` `{{username}}` `{{server}}` `{{count}}` `{{id}}`"
    )


@bot.command(name="welcometest")
@commands.has_permissions(administrator=True)
async def prefix_welcometest(ctx):
    await send_welcome(ctx.author)
    await ctx.send("Sent a test welcome message!")


@bot.command(name="welcometoggle")
@commands.has_permissions(administrator=True)
async def prefix_welcometoggle(ctx):
    cfg = get_guild(ctx.guild.id)
    cfg["welcome_enabled"] = not cfg.get("welcome_enabled", False)
    save_config()
    state = "enabled" if cfg["welcome_enabled"] else "disabled"
    await ctx.send(f"Welcome system {state}.")


@bot.command(name="welcomeembed")
@commands.has_permissions(administrator=True)
async def prefix_welcomeembed(ctx):
    cfg = get_guild(ctx.guild.id)
    cfg["welcome_embed"] = not cfg.get("welcome_embed", True)
    save_config()
    state = "enabled" if cfg["welcome_embed"] else "disabled"
    await ctx.send(f"Welcome embed {state}.")


@bot.command(name="welcomeinfo")
@commands.has_permissions(administrator=True)
async def prefix_welcomeinfo(ctx):
    cfg = get_guild(ctx.guild.id)
    channel_id = cfg.get("welcome_channel")
    channel = ctx.guild.get_channel(int(channel_id)) if channel_id else None
    await ctx.send(
        f"**Welcome Settings**\n"
        f"Enabled: `{cfg.get('welcome_enabled', False)}`\n"
        f"Channel: {channel.mention if channel else 'Not set'}\n"
        f"Embed: `{cfg.get('welcome_embed', True)}`\n"
        f"Message: `{cfg.get('welcome_message', 'Not set')}`"
    )


@bot.command(name="setlog")
@commands.has_permissions(administrator=True)
async def prefix_setlog(ctx, channel: discord.TextChannel):
    cfg = get_guild(ctx.guild.id)
    cfg["log_channel"] = channel.id
    cfg["log_enabled"] = True
    save_config()
    await ctx.send(f"Log channel set to {channel.mention}. Logging enabled.")


@bot.command(name="logtoggle")
@commands.has_permissions(administrator=True)
async def prefix_logtoggle(ctx):
    cfg = get_guild(ctx.guild.id)
    cfg["log_enabled"] = not cfg.get("log_enabled", False)
    save_config()
    state = "enabled" if cfg["log_enabled"] else "disabled"
    await ctx.send(f"Logging {state}.")


@bot.command(name="logevent")
@commands.has_permissions(administrator=True)
async def prefix_logevent(ctx, event: str):
    valid_events = [
        "member_join", "member_leave", "member_ban", "member_unban",
        "message_delete", "message_edit", "channel_create", "channel_delete",
        "role_create", "role_delete", "member_update", "voice_update"
    ]

    if event not in valid_events:
        await ctx.send(f"Invalid event. Valid: `{'`, `'.join(valid_events)}`")
        return

    cfg = get_guild(ctx.guild.id)
    log_events = cfg.get("log_events", {})
    log_events[event] = not log_events.get(event, True)
    cfg["log_events"] = log_events
    save_config()
    state = "enabled" if log_events[event] else "disabled"
    await ctx.send(f"Log event `{event}` {state}.")


@bot.command(name="loginfo")
@commands.has_permissions(administrator=True)
async def prefix_loginfo(ctx):
    cfg = get_guild(ctx.guild.id)
    channel_id = cfg.get("log_channel")
    channel = ctx.guild.get_channel(int(channel_id)) if channel_id else None
    log_events = cfg.get("log_events", {})
    event_lines = "\n".join(
        f"{'✅' if log_events.get(e, True) else '❌'} {e}"
        for e in [
            "member_join", "member_leave", "member_ban", "member_unban",
            "message_delete", "message_edit", "channel_create", "channel_delete",
            "role_create", "role_delete", "member_update", "voice_update"
            

        ]
    )
    await ctx.send(
        f"**Log Settings**\n"
        f"Enabled: `{cfg.get('log_enabled', False)}`\n"
        f"Channel: {channel.mention if channel else 'Not set'}\n\n"
        f"**Events:**\n{event_lines}"
    )

@bot.command()
@commands.has_permissions(manage_guild=True)
async def addcommand(ctx, name, *, response):

    if not has_premium_access(ctx.guild, ctx.author):
        return await ctx.send(
            "❌ Custom commands are a Beacon Premium feature."
        )

    custom_cursor.execute(
        "SELECT COUNT(*) FROM custom_commands WHERE guild_id=?",
        (ctx.guild.id,)
    )

    count = custom_cursor.fetchone()[0]

    if count >= 10:
        return await ctx.send(
            "❌ This server already has the maximum of 10 custom commands."
        )

    custom_cursor.execute(
        """
        INSERT OR REPLACE INTO custom_commands
        (guild_id, command, response)
        VALUES (?, ?, ?)
        """,
        (
            ctx.guild.id,
            name.lower(),
            response
        )
    )

    custom_db.commit()

    await ctx.send(f"✅ Custom command `*{name}` created successfully!")


@bot.command()
@commands.has_permissions(manage_guild=True)
async def deletecommand(ctx, name):

    if not has_premium_access(ctx.guild, ctx.author):
        return await ctx.send("❌ Custom commands are a Beacon Premium feature.")

    custom_cursor.execute(
        """
        DELETE FROM custom_commands
        WHERE guild_id=? AND command=?
        """,
        (
            ctx.guild.id,
            name.lower()
        )
    )

    custom_db.commit()

    await ctx.send(f"✅ Deleted `*{name}`.")
    
@bot.command()
async def listcommands(ctx):

    custom_cursor.execute(
        """
        SELECT command
        FROM custom_commands
        WHERE guild_id=?
        ORDER BY command
        """,
        (ctx.guild.id,)
    )

    rows = custom_cursor.fetchall()

    if not rows:
        return await ctx.send("No custom commands.")

    commands_list = "\n".join(f"• *{r[0]}" for r in rows)

    await ctx.send(
        f"**Custom Commands**\n{commands_list}"
    )
    
@bot.command()
@commands.has_permissions(manage_guild=True)
async def editcommand(ctx, name, *, response):

    if not has_premium_access(ctx.guild, ctx.author):
        return await ctx.send("❌ Custom commands are a Beacon Premium feature.")

    custom_cursor.execute(
        """
        UPDATE custom_commands
        SET response=?
        WHERE guild_id=? AND command=?
        """,
        (
            response,
            ctx.guild.id,
            name.lower()
        )
    )

    custom_db.commit()

    await ctx.send(f"✅ Updated `*{name}`.")
    
    

# ============================================================
# FREE FEATURES — sticky, poll, remind, levels  (* and /)
# ============================================================

async def do_sticky(guild, channel, author, text, send, delete_invoke=None):
    if not text:
        return await send("Usage: `*sticky <message text>` or `/sticky text:`")
    stickies[str(channel.id)] = {
        "guild_id": guild.id,
        "content": f"📌 **Sticky**\n{text}",
        "message_id": None,
    }
    save_stickies()
    if delete_invoke:
        try:
            await delete_invoke()
        except Exception:
            pass
    await restick_message(channel)
    await send("✅ Sticky set for this channel.")


async def do_unsticky(channel, send):
    key = str(channel.id)
    data = stickies.pop(key, None)
    save_stickies()
    if data and data.get("message_id"):
        try:
            msg = await channel.fetch_message(int(data["message_id"]))
            await msg.delete()
        except Exception:
            pass
    await send("✅ Sticky removed." if data else "No sticky in this channel.")


async def do_poll(raw, send):
    if not raw or "|" not in raw:
        return await send(
            "Usage: `*poll Question | Option A | Option B` or `/poll`\n"
            "Need a question and at least 2 options separated by `|`."
        )
    parts = [p.strip() for p in raw.split("|") if p.strip()]
    if len(parts) < 3:
        return await send("Need a question and at least 2 options.")
    if len(parts) > 6:
        return await send("Max 5 options (plus the question).")
    question, options = parts[0], parts[1:]
    view = PollView(question, options)
    await send(embed=view.make_embed(), view=view)


async def do_remind(user, channel, guild, duration, text, send):
    seconds = parse_duration(duration or "")
    if seconds is None or not text:
        return await send("Usage: `*remind 2h take out trash` or `/remind duration:2h text:...`")
    if seconds > 60 * 60 * 24 * 30:
        return await send("Max reminder length is 30 days.")
    due = int(time.time()) + seconds
    reminders.append(
        {
            "user_id": user.id,
            "channel_id": channel.id,
            "guild_id": guild.id if guild else 0,
            "text": text,
            "due_at": due,
        }
    )
    save_reminders()
    await send(
        f"⏰ Okay {user.mention}, I’ll remind you in **{format_duration(seconds)}**: {text}"
    )


async def do_level(guild, member, send):
    data = get_user_xp(guild.id, member.id)
    xp = int(data.get("xp", 0))
    level = int(data.get("level", level_from_xp(xp)))
    spent = 0
    for lv in range(1, level + 1):
        spent += xp_needed_for_level(lv)
    into = max(0, xp - spent)
    need = xp_needed_for_level(level + 1)
    embed = discord.Embed(
        title=f"Level — {member.display_name}",
        description=f"**Level {level}** · `{xp}` XP\nProgress to next: `{into}/{need}`",
        color=0x5865F2,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    await send(embed=embed)


async def do_leaderboard(guild, send):
    g = levels.get(str(guild.id), {})
    ranked = sorted(
        ((uid, int(v.get("xp", 0)), int(v.get("level", 0))) for uid, v in g.items()),
        key=lambda t: t[1],
        reverse=True,
    )[:10]
    if not ranked:
        return await send("No XP yet — chat to start leveling!")
    lines = [
        f"**{i}.** <@{uid}> — Level **{level}** (`{xp}` XP)"
        for i, (uid, xp, level) in enumerate(ranked, 1)
    ]
    embed = discord.Embed(
        title=f"XP Leaderboard — {guild.name}",
        description="\n".join(lines),
        color=0x5865F2,
    )
    await send(embed=embed)


@bot.command(name="sticky")
@commands.has_permissions(manage_messages=True)
async def sticky_cmd(ctx, *, text: str = None):
    await do_sticky(
        ctx.guild, ctx.channel, ctx.author, text, ctx.send,
        delete_invoke=ctx.message.delete,
    )


@tree.command(name="sticky", description="Keep a sticky message at the bottom of this channel")
@app_commands.describe(text="Sticky message content")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_sticky(interaction: discord.Interaction, text: str):
    await interaction.response.defer(ephemeral=True)
    async def send(content=None, **kwargs):
        if content is not None:
            await interaction.followup.send(content, ephemeral=True, **{k: v for k, v in kwargs.items() if k not in ('embed', 'view')})
        elif 'embed' in kwargs or 'view' in kwargs:
            await interaction.followup.send(ephemeral=True, **kwargs)
    await do_sticky(interaction.guild, interaction.channel, interaction.user, text, send)


@bot.command(name="unsticky")
@commands.has_permissions(manage_messages=True)
async def unsticky_cmd(ctx):
    await do_unsticky(ctx.channel, ctx.send)


@tree.command(name="unsticky", description="Remove the sticky message from this channel")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_unsticky(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    async def send(content=None, **kwargs):
        await interaction.followup.send(content or "", ephemeral=True, **kwargs)
    await do_unsticky(interaction.channel, send)


@bot.command(name="poll")
async def poll_cmd(ctx, *, raw: str = None):
    await do_poll(raw, ctx.send)


@tree.command(name="poll", description="Create a button poll")
@app_commands.describe(
    question="Poll question",
    option1="First option",
    option2="Second option",
    option3="Third option (optional)",
    option4="Fourth option (optional)",
    option5="Fifth option (optional)",
)
async def slash_poll(
    interaction: discord.Interaction,
    question: str,
    option1: str,
    option2: str,
    option3: str = None,
    option4: str = None,
    option5: str = None,
):
    opts = [option1, option2, option3, option4, option5]
    raw = " | ".join([question] + [o for o in opts if o])
    await interaction.response.defer()
    async def send(content=None, **kwargs):
        if content is not None and 'embed' not in kwargs:
            await interaction.followup.send(content)
        else:
            await interaction.followup.send(content, **kwargs) if content else await interaction.followup.send(**kwargs)
    await do_poll(raw, send)


@bot.command(name="remind", aliases=["reminder"])
async def remind_cmd(ctx, duration: str = None, *, text: str = None):
    await do_remind(ctx.author, ctx.channel, ctx.guild, duration, text, ctx.send)


@tree.command(name="remind", description="Set a reminder in this channel")
@app_commands.describe(duration="e.g. 2h, 30m, 1d", text="What to remind you about")
async def slash_remind(interaction: discord.Interaction, duration: str, text: str):
    await interaction.response.defer(ephemeral=True)
    async def send(content=None, **kwargs):
        await interaction.followup.send(content or "", ephemeral=True, **kwargs)
    await do_remind(interaction.user, interaction.channel, interaction.guild, duration, text, send)


@bot.command(name="level", aliases=["rank", "xp"])
async def level_cmd(ctx, member: discord.Member = None):
    await do_level(ctx.guild, member or ctx.author, ctx.send)


@tree.command(name="level", description="View XP level (basic, no role rewards)")
@app_commands.describe(member="Member to check (optional)")
async def slash_level(interaction: discord.Interaction, member: discord.Member = None):
    await interaction.response.defer()
    async def send(content=None, **kwargs):
        await interaction.followup.send(content, **kwargs) if content else await interaction.followup.send(**kwargs)
    await do_level(interaction.guild, member or interaction.user, send)


@bot.command(name="leaderboard", aliases=["lb", "levels"])
async def leaderboard_cmd(ctx):
    await do_leaderboard(ctx.guild, ctx.send)


@tree.command(name="leaderboard", description="Top XP in this server")
async def slash_leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    async def send(content=None, **kwargs):
        await interaction.followup.send(content, **kwargs) if content else await interaction.followup.send(**kwargs)
    await do_leaderboard(interaction.guild, send)


# ============================================================
# PREMIUM FEATURES — temprole, economy, autorespond, invites (* and /)
# ============================================================

async def do_temprole(guild, author, member, role, duration, send):
    if not has_premium_access(guild, author):
        return await send("❌ Temp roles are a Beacon Premium feature.")
    if member is None or role is None or duration is None:
        return await send("Usage: `*temprole @user @Role 7d` or `/temprole`")
    seconds = parse_duration(duration)
    if seconds is None:
        return await send("Invalid duration. Example: `7d`, `12h`, `30m`")
    if seconds > 60 * 60 * 24 * 90:
        return await send("Max temp role length is 90 days.")
    me = guild.me
    if role >= me.top_role or (
        hasattr(author, "top_role")
        and role >= author.top_role
        and author.id != guild.owner_id
    ):
        return await send("I can’t manage that role (role hierarchy).")
    try:
        await member.add_roles(role, reason=f"Temp role by {author}")
    except Exception as e:
        return await send(f"Failed to add role: `{e}`")
    expires = int(time.time()) + seconds
    temproles.append(
        {
            "guild_id": guild.id,
            "user_id": member.id,
            "role_id": role.id,
            "expires_at": expires,
            "by": author.id,
        }
    )
    save_temproles()
    await send(
        f"✅ Gave {member.mention} {role.mention} for **{format_duration(seconds)}** "
        f"(until <t:{expires}:R>)."
    )


async def do_temproles_list(guild, author, send):
    if not has_premium_access(guild, author):
        return await send("❌ Temp roles are a Beacon Premium feature.")
    rows = [t for t in temproles if int(t.get("guild_id", 0)) == guild.id]
    if not rows:
        return await send("No active temp roles.")
    lines = [
        f"<@{t['user_id']}> → <@&{t['role_id']}> · expires <t:{int(t['expires_at'])}:R>"
        for t in rows[:20]
    ]
    await send("**Active temp roles**\n" + "\n".join(lines))


async def do_balance(guild, author, member, send):
    member = member or author
    bal = get_balance(guild.id, member.id)
    await send(f"💰 {member.mention} has **{bal}** coins.")


async def do_daily(guild, author, send):
    g = get_economy_guild(guild.id)
    last = int(g["daily"].get(str(author.id), 0))
    now = int(time.time())
    if now - last < DAILY_COOLDOWN_SECONDS:
        left = DAILY_COOLDOWN_SECONDS - (now - last)
        return await send(f"Daily already claimed. Try again in **{format_duration(left)}**.")
    g["daily"][str(author.id)] = now
    bal = add_coins(guild.id, author.id, DAILY_COIN_REWARD)
    await send(f"✅ Daily +**{DAILY_COIN_REWARD}** coins. Balance: **{bal}**.")


async def do_pay(guild, author, member, amount, send):
    if member is None or amount is None or amount <= 0:
        return await send("Usage: `*pay @user 50` or `/pay`")
    if member.id == author.id:
        return await send("You can’t pay yourself.")
    bal = get_balance(guild.id, author.id)
    if bal < amount:
        return await send("Not enough coins.")
    set_balance(guild.id, author.id, bal - amount)
    add_coins(guild.id, member.id, amount)
    await send(f"✅ Paid **{amount}** coins to {member.mention}.")


async def do_givemoney(guild, author, member, amount, send):
    """Seekara staff: spawn coins for someone (does not take from your balance)."""
    if not is_seekara_staff(author.id):
        return await send("❌ Seekara staff only.")
    if guild is None:
        return await send("Use this in a server.")
    if member is None or amount is None or amount <= 0:
        return await send("Usage: `*givemoney @user 1000` or `/givemoney`")
    bal = add_coins(guild.id, member.id, int(amount))
    await send(f"✅ Gave **{amount}** coins to {member.mention}. Their balance is now **{bal}**.")


async def do_shop(guild, author, send):
    g = get_economy_guild(guild.id)
    if not g["shop"]:
        return await send("Shop is empty. Admins: `/shopadd` or `*shopadd 100 Cool Item`")
    lines = []
    for i, item in enumerate(g["shop"], 1):
        extra = f" → role <@&{item['role_id']}>" if item.get("role_id") else ""
        lines.append(f"**{i}. {item['name']}** — `{item['price']}` coins{extra}")
    embed = discord.Embed(title="🛒 Shop", description="\n".join(lines), color=0xFEE75C)
    embed.set_footer(text="Buy with /buy or *buy <item name>")
    await send(embed=embed)


async def do_shopadd(guild, author, price, name, send):
    if price is None or price < 0 or not name:
        return await send("Usage: `*shopadd 100 Cool Item` or `/shopadd`")
    g = get_economy_guild(guild.id)
    g["shop"].append({"name": name, "price": int(price), "role_id": None})
    save_economy()
    await send(f"✅ Added shop item **{name}** for `{price}` coins.")


async def do_shoprole(guild, author, price, role, send):
    if price is None or role is None:
        return await send("Usage: `*shoprole 500 @VIP` or `/shoprole`")
    g = get_economy_guild(guild.id)
    g["shop"].append({"name": role.name, "price": int(price), "role_id": role.id})
    save_economy()
    await send(f"✅ Added role item {role.mention} for `{price}` coins.")


async def do_shopremove(guild, author, name, send):
    if not name:
        return await send("Usage: `*shopremove <item name>` or `/shopremove`")
    g = get_economy_guild(guild.id)
    before = len(g["shop"])
    g["shop"] = [i for i in g["shop"] if i.get("name", "").lower() != name.lower()]
    save_economy()
    if len(g["shop"]) == before:
        return await send("Item not found.")
    await send(f"✅ Removed **{name}** from the shop.")


async def do_buy(guild, author, name, send):
    if not name:
        return await send("Usage: `*buy <item name>` or `/buy`")
    g = get_economy_guild(guild.id)
    item = next((i for i in g["shop"] if i.get("name", "").lower() == name.lower()), None)
    if not item:
        return await send("Item not found. Use `/shop` or `*shop`.")
    bal = get_balance(guild.id, author.id)
    price = int(item["price"])
    if bal < price:
        return await send(f"Need `{price}` coins — you have `{bal}`.")
    set_balance(guild.id, author.id, bal - price)
    if item.get("role_id"):
        role = guild.get_role(int(item["role_id"]))
        if role:
            try:
                await author.add_roles(role, reason="Shop purchase")
            except Exception as e:
                add_coins(guild.id, author.id, price)
                return await send(f"Could not give role, refunded. `{e}`")
    await send(f"✅ Purchased **{item['name']}** for `{price}` coins.")


async def do_autorespond(guild, author, action, rest, send):
    if not has_premium_access(guild, author):
        return await send("❌ Auto-responder is a Beacon Premium feature.")
    action = (action or "").lower()
    gid = str(guild.id)
    rules = autoresponders.setdefault(gid, [])

    if action in {"list", "ls"}:
        if not rules:
            return await send("No auto-responders set.")
        lines = []
        for i, r in enumerate(rules, 1):
            kind = "regex" if r.get("is_regex") else "keyword"
            lines.append(f"**{i}.** ({kind}) `{r.get('trigger')}` → {r.get('response')[:80]}")
        return await send("\n".join(lines))

    if action == "remove":
        try:
            idx = int((rest or "0").strip()) - 1
            removed = rules.pop(idx)
            save_autoresponders()
            return await send(f"✅ Removed `{removed.get('trigger')}`.")
        except Exception:
            return await send("Usage: `/autorespond action:remove trigger_or_data:<number>`")

    if action in {"add", "regex"}:
        if not rest or "|" not in rest:
            return await send(
                "Usage: `/autorespond action:add trigger_or_data:keyword | response`"
            )
        trigger, response = [p.strip() for p in rest.split("|", 1)]
        if action == "regex":
            try:
                re.compile(trigger)
            except re.error as e:
                return await send(f"Invalid regex: `{e}`")
        rules.append(
            {
                "trigger": trigger,
                "response": response,
                "is_regex": action == "regex",
            }
        )
        save_autoresponders()
        return await send(f"✅ Auto-responder saved for `{trigger}`.")

    await send(
        "Usage: `/autorespond` or `*autorespond add|regex|list|remove ...`"
    )


async def do_invites(guild, author, member, send):
    if not has_premium_access(guild, author):
        return await send("❌ Invite tracker is a Beacon Premium feature.")
    member = member or author
    g = get_invite_guild(guild.id)
    total = int(g["totals"].get(str(member.id), 0))
    fake = int(g["fake"].get(str(member.id), 0))
    real = max(0, total - fake)
    embed = discord.Embed(
        title=f"Invites — {member.display_name}",
        description=(
            f"**Total:** {total}\n"
            f"**Real:** {real}\n"
            f"**Fake:** {fake}\n\n"
            f"Fake = invited account younger than **{FAKE_INVITE_ACCOUNT_AGE_DAYS}** days."
        ),
        color=0x57F287,
    )
    await send(embed=embed)


def _slash_send(interaction, ephemeral=False):
    async def send(content=None, **kwargs):
        kwargs = dict(kwargs)
        # followup after defer
        if content is None:
            await interaction.followup.send(ephemeral=ephemeral, **kwargs)
        else:
            await interaction.followup.send(content, ephemeral=ephemeral, **kwargs)
    return send


@bot.command(name="temprole")
@commands.has_permissions(manage_roles=True)
async def temprole_cmd(ctx, member: discord.Member = None, role: discord.Role = None, duration: str = None):
    await do_temprole(ctx.guild, ctx.author, member, role, duration, ctx.send)


@tree.command(name="temprole", description="Give a temporary role (Premium)")
@app_commands.describe(member="Member", role="Role to grant", duration="e.g. 7d, 12h")
@app_commands.checks.has_permissions(manage_roles=True)
async def slash_temprole(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role,
    duration: str,
):
    await interaction.response.defer()
    await do_temprole(interaction.guild, interaction.user, member, role, duration, _slash_send(interaction))


@bot.command(name="temproles")
@commands.has_permissions(manage_roles=True)
async def temproles_cmd(ctx):
    await do_temproles_list(ctx.guild, ctx.author, ctx.send)


@tree.command(name="temproles", description="List active temp roles (Premium)")
@app_commands.checks.has_permissions(manage_roles=True)
async def slash_temproles(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await do_temproles_list(interaction.guild, interaction.user, _slash_send(interaction, ephemeral=True))


@bot.command(name="balance", aliases=["bal", "coins"])
async def balance_cmd(ctx, member: discord.Member = None):
    await do_balance(ctx.guild, ctx.author, member, ctx.send)


@tree.command(name="balance", description="Check coin balance")
@app_commands.describe(member="Member (optional)")
async def slash_balance(interaction: discord.Interaction, member: discord.Member = None):
    await interaction.response.defer()
    await do_balance(interaction.guild, interaction.user, member, _slash_send(interaction))


@bot.command(name="daily")
async def daily_cmd(ctx):
    await do_daily(ctx.guild, ctx.author, ctx.send)


@tree.command(name="daily", description="Claim daily coins")
async def slash_daily(interaction: discord.Interaction):
    await interaction.response.defer()
    await do_daily(interaction.guild, interaction.user, _slash_send(interaction))


@bot.command(name="pay", aliases=["givecoins"])
async def pay_cmd(ctx, member: discord.Member = None, amount: int = None):
    await do_pay(ctx.guild, ctx.author, member, amount, ctx.send)


@tree.command(name="pay", description="Pay coins to a member")
@app_commands.describe(member="Member to pay", amount="Amount of coins")
async def slash_pay(interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 1, 1_000_000]):
    await interaction.response.defer()
    await do_pay(interaction.guild, interaction.user, member, amount, _slash_send(interaction))


@bot.command(name="givemoney", aliases=["givebucks", "addmoney", "ecoadd"])
async def givemoney_cmd(ctx, member: discord.Member = None, amount: int = None):
    await do_givemoney(ctx.guild, ctx.author, member, amount, ctx.send)


@tree.command(name="givemoney", description="Seekara staff: give coins to a member")
@app_commands.describe(member="Member to fund", amount="Coins to add")
async def slash_givemoney(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: app_commands.Range[int, 1, 1_000_000_000],
):
    await interaction.response.defer(ephemeral=True)
    await do_givemoney(
        interaction.guild,
        interaction.user,
        member,
        amount,
        _slash_send(interaction, ephemeral=True),
    )


@bot.command(name="shop")
async def shop_cmd(ctx):
    await do_shop(ctx.guild, ctx.author, ctx.send)


@tree.command(name="shop", description="View the economy shop")
async def slash_shop(interaction: discord.Interaction):
    await interaction.response.defer()
    await do_shop(interaction.guild, interaction.user, _slash_send(interaction))


@bot.command(name="shopadd")
@commands.has_permissions(manage_guild=True)
async def shopadd_cmd(ctx, price: int = None, *, name: str = None):
    await do_shopadd(ctx.guild, ctx.author, price, name, ctx.send)


@tree.command(name="shopadd", description="Add a shop item")
@app_commands.describe(price="Price in coins", name="Item name")
@app_commands.checks.has_permissions(manage_guild=True)
async def slash_shopadd(interaction: discord.Interaction, price: app_commands.Range[int, 0, 1_000_000], name: str):
    await interaction.response.defer()
    await do_shopadd(interaction.guild, interaction.user, price, name, _slash_send(interaction))


@bot.command(name="shoprole")
@commands.has_permissions(manage_guild=True)
async def shoprole_cmd(ctx, price: int = None, role: discord.Role = None):
    await do_shoprole(ctx.guild, ctx.author, price, role, ctx.send)


@tree.command(name="shoprole", description="Add a role to the shop")
@app_commands.describe(price="Price in coins", role="Role to sell")
@app_commands.checks.has_permissions(manage_guild=True)
async def slash_shoprole(interaction: discord.Interaction, price: app_commands.Range[int, 0, 1_000_000], role: discord.Role):
    await interaction.response.defer()
    await do_shoprole(interaction.guild, interaction.user, price, role, _slash_send(interaction))


@bot.command(name="shopremove")
@commands.has_permissions(manage_guild=True)
async def shopremove_cmd(ctx, *, name: str = None):
    await do_shopremove(ctx.guild, ctx.author, name, ctx.send)


@tree.command(name="shopremove", description="Remove a shop item")
@app_commands.describe(name="Item name")
@app_commands.checks.has_permissions(manage_guild=True)
async def slash_shopremove(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    await do_shopremove(interaction.guild, interaction.user, name, _slash_send(interaction))


@bot.command(name="buy")
async def buy_cmd(ctx, *, name: str = None):
    await do_buy(ctx.guild, ctx.author, name, ctx.send)


@tree.command(name="buy", description="Buy a shop item")
@app_commands.describe(name="Item name")
async def slash_buy(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    await do_buy(interaction.guild, interaction.user, name, _slash_send(interaction))


@bot.command(name="autorespond", aliases=["ar"])
@commands.has_permissions(manage_guild=True)
async def autorespond_cmd(ctx, action: str = None, *, rest: str = None):
    await do_autorespond(ctx.guild, ctx.author, action, rest, ctx.send)


@tree.command(name="autorespond", description="Manage keyword/regex auto-replies (Premium)")
@app_commands.describe(
    action="add, regex, list, or remove",
    trigger_or_data="For add/regex: `trigger | response`. For remove: number.",
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="regex", value="regex"),
        app_commands.Choice(name="list", value="list"),
        app_commands.Choice(name="remove", value="remove"),
    ]
)
@app_commands.checks.has_permissions(manage_guild=True)
async def slash_autorespond(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    trigger_or_data: str = None,
):
    await interaction.response.defer(ephemeral=True)
    await do_autorespond(
        interaction.guild,
        interaction.user,
        action.value,
        trigger_or_data,
        _slash_send(interaction, ephemeral=True),
    )


@bot.command(name="invites", aliases=["inv"])
async def invites_cmd(ctx, member: discord.Member = None):
    await do_invites(ctx.guild, ctx.author, member, ctx.send)


@tree.command(name="invites", description="Invite tracker with fake filter (Premium)")
@app_commands.describe(member="Member (optional)")
async def slash_invites(interaction: discord.Interaction, member: discord.Member = None):
    await interaction.response.defer()
    await do_invites(interaction.guild, interaction.user, member, _slash_send(interaction))


@bot.event
async def on_invite_create(invite):
    if invite.guild:
        await cache_guild_invites(invite.guild)


@bot.event
async def on_invite_delete(invite):
    if invite.guild:
        await cache_guild_invites(invite.guild)


# ============================================================
# FUN — dirt
# ============================================================

DIRT_EMOJI = "<:Dirt:1533881321825505491>"
DIRT_MESSAGE = f"DIRT {DIRT_EMOJI}"


@bot.command(name="dirt")
async def dirt_cmd(ctx):
    await ctx.send(DIRT_MESSAGE)


@tree.command(name="dirt", description="DIRT")
async def slash_dirt(interaction: discord.Interaction):
    await interaction.response.send_message(DIRT_MESSAGE)


# ============================================================
# IMAGE GENERATION (local cartoon AI + prompt moderation)
# Ubuntu: pip install torch diffusers transformers accelerate safetensors pillow
# ============================================================

_GENERATE_BLOCKED = [
    "nsfw", "nude", "naked", "porn", "sex", "sexual", "hentai", "xxx", "onlyfans",
    "gore", "guro", "bloodbath", "dismember", "decapitat", "torture",
    "rape", "molest", "child porn", "underage", "loli", "shota",
    "bestiality", "zoophil", "scat",
    "suicide", "kill myself", "school shooting",
]

_CARTOON_POS = (
    "modern disney pixar cartoon style, cute colorful 3d animation still, "
    "clean character design, friendly face, big expressive eyes with pupils, "
    "correct anatomy, wholesome family friendly, vibrant colors, high quality"
)
_CARTOON_NEG = (
    "photo, photorealistic, realistic photo, horror, creepy, uncanny, gore, nsfw, "
    "nude, deformed, mutated, extra limbs, missing limbs, bad anatomy, blurry, "
    "low quality, text, watermark, collage, grid, multiple panels"
)

_sd_pipe = None
_sd_lock = threading.Lock()


def moderate_generate_prompt(prompt: str):
    text = " ".join((prompt or "").strip().split())
    if not text:
        return False, "empty prompt"
    lowered = text.lower()
    for bad in _GENERATE_BLOCKED:
        if bad in lowered:
            return False, f"blocked topic (`{bad}`)"
    if len(text) > 300:
        text = text[:300].rstrip()
    return True, text


def stylize_generate_prompt(prompt: str) -> str:
    return f"{prompt.strip()}, {_CARTOON_POS}"


def _get_sd_pipeline():
    """Lazy-load local SD-Turbo once (CPU ok on Ubuntu)."""
    global _sd_pipe
    if _sd_pipe is not None:
        return _sd_pipe
    with _sd_lock:
        if _sd_pipe is not None:
            return _sd_pipe
        try:
            import sys
            import torch
            from diffusers import AutoPipelineForText2Image
        except Exception as e:
            import sys
            raise RuntimeError(
                "Image packages not found in the Python that runs Beacon.\n"
                f"Bot python: `{sys.executable}`\n"
                f"Import error: `{type(e).__name__}: {e}`\n"
                "Install into THAT python with:\n"
                f"`{sys.executable} -m pip install torch diffusers transformers "
                "accelerate safetensors pillow --break-system-packages`"
            ) from e

        print("Loading local cartoon image model (first time can take a minute)...")
        try:
            pipe = AutoPipelineForText2Image.from_pretrained(
                "stabilityai/sd-turbo",
                torch_dtype=torch.float32,
            )
        except Exception as e:
            raise RuntimeError(
                f"Image packages imported, but model failed to load: `{type(e).__name__}: {e}`"
            ) from e
        pipe = pipe.to("cpu")
        pipe.set_progress_bar_config(disable=True)
        _sd_pipe = pipe
        print("Cartoon image model ready.")
        return _sd_pipe


def generate_ai_image(prompt: str, width: int = 512, height: int = 512):
    """
    Generate a cartoon-style image locally with SD-Turbo.
    Returns (png_bytes, 'png').
    """
    ok, cleaned = moderate_generate_prompt(prompt)
    if not ok:
        raise ValueError(cleaned)

    styled = stylize_generate_prompt(cleaned)
    pipe = _get_sd_pipeline()

    # SD-Turbo: few steps, guidance_scale 0
    image = pipe(
        prompt=styled,
        negative_prompt=_CARTOON_NEG,
        num_inference_steps=6,
        guidance_scale=0.0,
        width=width,
        height=height,
        generator=__import__("torch").Generator("cpu").manual_seed(secrets.randbelow(2**31 - 1)),
    ).images[0]

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue(), "png"


async def do_generate(prompt: str, send):
    prompt = (prompt or "").strip()
    if not prompt:
        await send(
            "Usage: `*generate <prompt>` or `/generate prompt:`\n"
            "Example: `*generate astronaut cat`\n"
            "Always cartoon / Pixar style. Family-friendly only."
        )
        return

    ok, cleaned = moderate_generate_prompt(prompt)
    if not ok:
        await send(
            "That prompt was blocked by moderation.\n"
            "No NSFW, gore, or illegal stuff."
        )
        return

    await send(f"Generating cartoon image for: **{cleaned}** … (first run may be slow)")

    try:
        image_bytes, ext = await asyncio.to_thread(generate_ai_image, cleaned, 512, 512)
    except ValueError as e:
        await send(f"Blocked by moderation: `{e}`")
        return
    except Exception as e:
        await send(f"Image generation failed: `{e}`")
        return

    filename = f"beacon_generate.{ext}"
    file = discord.File(io.BytesIO(image_bytes), filename=filename)
    embed = discord.Embed(
        title="Beacon Image Generator",
        description=f"**Prompt:** {cleaned}\n**Style:** cartoon / Pixar-like",
        color=0x5865F2,
    )
    embed.set_image(url=f"attachment://{filename}")
    embed.set_footer(text="Local cartoon AI • moderated")
    await send(embed=embed, file=file)


@bot.command(name="generate", aliases=["imagine", "img", "draw"])
async def prefix_generate(ctx, *, prompt: str = None):
    await do_generate(prompt, ctx.send)


@tree.command(name="generate", description="Generate a cartoon AI image from a text prompt")
@app_commands.describe(prompt="What to generate, e.g. astronaut cat in space")
async def slash_generate(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    await do_generate(prompt, interaction.followup.send)


# ============================================================
# EMOJI STEAL (PNG download)
# User App: paste a custom emoji into the option (works in ANY server).
# CDN download only needs the emoji id — Beacon does not need to be in that server.
# Typing :name: also works when Beacon can see that server's emoji list.
# ============================================================

CUSTOM_EMOJI_RE = re.compile(r"<(a?):([A-Za-z0-9_]+):(\d+)>")
EMOJI_NAME_RE = re.compile(r"^:?([A-Za-z0-9_]+):?$")


def iter_search_guilds(prefer: discord.Guild | None = None):
    if prefer is not None:
        yield prefer
    for g in bot.guilds:
        if prefer is None or g.id != prefer.id:
            yield g


def find_emoji_by_name_in_lists(name: str, emoji_lists):
    needle = (name or "").strip().strip(":").lower()
    if not needle:
        return None
    exact, partial = [], []
    for emojis in emoji_lists:
        for e in emojis:
            n = (getattr(e, "name", None) or "").lower()
            if n == needle:
                exact.append(e)
            elif needle in n:
                partial.append(e)
    if exact:
        return exact[0]
    if partial:
        partial.sort(key=lambda e: len(getattr(e, "name", "") or ""))
        return partial[0]
    return None


def find_emoji_by_name(name: str, prefer: discord.Guild | None = None):
    """Search Beacon-joined guilds by name."""
    lists = [g.emojis for g in iter_search_guilds(prefer)]
    return find_emoji_by_name_in_lists(name, lists)


def partial_from_api_emoji(data: dict):
    return discord.PartialEmoji(
        name=data.get("name") or "emoji",
        id=int(data["id"]),
        animated=bool(data.get("animated")),
    )


async def fetch_emojis_for_guild_id(guild_id: int | None):
    """Best-effort emoji list for a guild. Works if Beacon is in it; else []."""
    if not guild_id:
        return []
    g = bot.get_guild(int(guild_id))
    if g is not None:
        if g.emojis:
            return list(g.emojis)
        try:
            return list(await g.fetch_emojis())
        except Exception:
            return list(g.emojis)
    # Not in guild — Discord will usually 403; try anyway.
    try:
        raw = await bot.http.get_all_custom_emojis(int(guild_id))
        return [partial_from_api_emoji(e) for e in raw]
    except Exception:
        return []


def parse_emoji_with_id(text: str):
    """Parse any form that includes a snowflake — works for User Apps anywhere."""
    text = (text or "").strip()
    if not text:
        return None

    m = CUSTOM_EMOJI_RE.fullmatch(text) or CUSTOM_EMOJI_RE.search(text)
    if m:
        return discord.PartialEmoji(
            name=m.group(2),
            id=int(m.group(3)),
            animated=bool(m.group(1)),
        )

    try:
        pe = discord.PartialEmoji.from_str(text)
        if pe and pe.id:
            return pe
    except Exception:
        pass

    bare = re.fullmatch(r"(a?):([A-Za-z0-9_]+):(\d{13,20})", text)
    if bare:
        return discord.PartialEmoji(
            name=bare.group(2),
            id=int(bare.group(3)),
            animated=bool(bare.group(1)),
        )

    if text.isdigit() and len(text) >= 13:
        return discord.PartialEmoji(name="emoji", id=int(text), animated=False)
    return None


async def resolve_custom_emoji(raw, guild: discord.Guild | None = None, guild_id: int | None = None):
    """Resolve pasted <:name:id> (any server) or :name: when we can list that guild."""
    if raw is None:
        return None

    if isinstance(raw, (discord.Emoji, discord.PartialEmoji)):
        return raw if getattr(raw, "id", None) else None

    text = str(raw).strip()
    if not text:
        return None

    # 1) Anything with an id → CDN steal works with zero guild access (User App)
    with_id = parse_emoji_with_id(text)
    if with_id is not None:
        return with_id

    # 2) :name: / name — need an emoji list for this server (or Beacon's servers)
    nm = EMOJI_NAME_RE.fullmatch(text)
    name = nm.group(1) if nm else re.sub(r"[^A-Za-z0-9_]", "", text)
    if not name:
        return None

    gid = guild_id or (guild.id if guild is not None else None)
    local_lists = []
    fetched = await fetch_emojis_for_guild_id(gid)
    if fetched:
        local_lists.append(fetched)
    if guild is not None and guild.emojis and guild.emojis not in local_lists:
        local_lists.append(list(guild.emojis))

    found = find_emoji_by_name_in_lists(name, local_lists)
    if found is not None:
        return found

    # Fallback: any server Beacon is already in
    return find_emoji_by_name(name, guild)


def find_custom_emojis(text: str):
    """All custom emojis in a string (deduped by id)."""
    seen = set()
    out = []
    for animated, name, eid in CUSTOM_EMOJI_RE.findall(text or ""):
        eid = int(eid)
        if eid in seen:
            continue
        seen.add(eid)
        out.append(discord.PartialEmoji(name=name, id=eid, animated=bool(animated)))
    return out


def find_custom_emojis_in_message(message: discord.Message):
    """Custom emojis in content, embeds, and reactions (CDN-stealable anywhere)."""
    chunks = [message.content or ""]
    for emb in message.embeds:
        if emb.title:
            chunks.append(emb.title)
        if emb.description:
            chunks.append(emb.description)
        if emb.footer and emb.footer.text:
            chunks.append(emb.footer.text)
        if emb.author and emb.author.name:
            chunks.append(emb.author.name)
        for field in emb.fields:
            chunks.append(field.name or "")
            chunks.append(field.value or "")
    found = find_custom_emojis("\n".join(chunks))
    seen = {int(e.id) for e in found}
    for reaction in message.reactions:
        emoji = reaction.emoji
        if isinstance(emoji, (discord.Emoji, discord.PartialEmoji)) and getattr(emoji, "id", None):
            eid = int(emoji.id)
            if eid not in seen:
                seen.add(eid)
                found.append(emoji)
    return found


def fetch_emoji_bytes(emoji_id: int, animated: bool = False) -> tuple[bytes, str]:
    """Download emoji from Discord CDN. Animated → GIF, otherwise PNG."""
    ext = "gif" if animated else "png"
    url = f"https://cdn.discordapp.com/emojis/{int(emoji_id)}.{ext}?size=256&quality=lossless"
    req = urllib.request.Request(url, headers={"User-Agent": "BeaconBot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            data = res.read()
    except Exception:
        # Fallback: some animated ids still serve png only
        if animated:
            return fetch_emoji_bytes(emoji_id, animated=False)
        raise
    if not data:
        raise RuntimeError("empty emoji download")
    return data, ext


async def send_stolen_emoji(emoji, send):
    if emoji is None or not getattr(emoji, "id", None):
        return await send("Need a **custom** emoji (not a default Unicode one).")
    animated = bool(getattr(emoji, "animated", False))
    try:
        data, ext = await asyncio.to_thread(fetch_emoji_bytes, int(emoji.id), animated)
    except Exception as e:
        return await send(f"Could not download that emoji: `{e}`")

    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(emoji.name or "emoji")).strip("_") or "emoji"
    filename = f"{safe_name}_{emoji.id}.{ext}"
    file = discord.File(io.BytesIO(data), filename=filename)

    kind = "GIF" if ext == "gif" else "PNG"
    embed = discord.Embed(
        title="Emoji steal",
        description=f"**:{emoji.name}:** → {kind} download",
        color=0x5865F2,
    )
    if ext == "gif":
        embed.set_footer(text="Animated emoji exported as GIF")
    embed.set_image(url=f"attachment://{filename}")
    await send(embed=embed, file=file)


async def do_emojisteal(raw_emoji, guild: discord.Guild | None, send, guild_id: int | None = None):
    emoji = await resolve_custom_emoji(raw_emoji, guild, guild_id=guild_id)
    if emoji is None or not getattr(emoji, "id", None):
        return await send(
            "Couldn't read that.\n"
            "**User App (any server):** paste the custom emoji into `emoji:` "
            "(open the emoji picker and tap it — Discord fills `<:name:id>`).\n"
            "Or right-click a message → **Apps → Steal emojis**.\n"
            "Typing just `:name:` only works if Beacon is in that server."
        )
    await send_stolen_emoji(emoji, send)


@bot.command(name="emojisteal", aliases=["stealemoji", "steal"])
async def prefix_emojisteal(ctx, *, emoji: str = None):
    """Download a custom emoji as PNG. Paste <:name:id> or type the name."""
    if not emoji:
        return await ctx.send(
            "Usage: `*emojisteal` then **paste** a custom emoji, or type `name`.\n"
            "Paste works in any server. Name lookup needs Beacon in that server."
        )
    await do_emojisteal(emoji, ctx.guild, ctx.send, guild_id=ctx.guild.id if ctx.guild else None)


@tree.command(
    name="emojisteal",
    description="Steal a custom emoji as PNG — paste it (works in any server as User App)",
)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(
    emoji="PASTE a custom emoji here (emoji picker → tap). Or type a name if Beacon is in the server."
)
async def slash_emojisteal(interaction: discord.Interaction, emoji: str):
    await interaction.response.defer(ephemeral=True)
    await do_emojisteal(
        emoji,
        interaction.guild,
        interaction.followup.send,
        guild_id=interaction.guild_id,
    )


@slash_emojisteal.autocomplete("emoji")
async def emojisteal_autocomplete(interaction: discord.Interaction, current: str):
    cur = (current or "").lower().strip().strip(":")
    m = CUSTOM_EMOJI_RE.search(current or "")
    if m:
        return [app_commands.Choice(name=f":{m.group(2)}:", value=m.group(3))]

    # Prefer THIS server's emojis (where you ran the app command)
    emojis = await fetch_emojis_for_guild_id(interaction.guild_id)
    # If we can't see this server, fall back to Beacon-joined servers
    if not emojis:
        emojis = []
        seen = set()
        for g in bot.guilds:
            for e in g.emojis:
                if e.id in seen:
                    continue
                seen.add(e.id)
                emojis.append(e)

    choices = []
    seen_ids = set()
    for e in emojis:
        eid = int(e.id)
        if eid in seen_ids:
            continue
        name = (getattr(e, "name", None) or "").lower()
        if cur and cur not in name and cur not in str(eid):
            continue
        seen_ids.add(eid)
        label = f":{getattr(e, 'name', 'emoji')}:"
        if getattr(e, "animated", False):
            label += " (a)"
        choices.append(app_commands.Choice(name=label[:100], value=str(eid)))
        if len(choices) >= 25:
            break
    return choices


@bot.command(name="resync")
async def prefix_resync(ctx, mode: str = "clear"):
    """Owner: `*resync` clears guild ghosts + publishes globals. `*resync push` for instant guild copy."""
    if not is_bot_owner(ctx.author.id):
        return await ctx.send("❌ Only the bot owner can use this.")
    mode_l = (mode or "").lower().strip()
    push = mode_l in ("push", "guilds", "instant")
    clear = not push
    await ctx.send(
        "Syncing globals"
        + (" and pushing to servers…" if push else " and clearing guild copies…")
    )
    try:
        synced = await sync_slash_commands(
            force_print=True,
            clear_guild_dupes=clear,
            push_to_guilds=push,
        )
    except Exception as e:
        return await ctx.send(f"Sync failed: `{e}`")
    names = sorted(c.name for c in synced)
    has = "emojisteal" in names
    await ctx.send(
        f"Synced **{len(synced)}** global commands. "
        f"`/emojisteal` registered: **{'yes' if has else 'NO'}**.\n"
        f"**User App (other servers):** {user_app_install_url()}\n"
        f"Also works as `*emojisteal name`"
    )


@tree.context_menu(name="Steal emojis")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def context_steal_emojis(interaction: discord.Interaction, message: discord.Message):
    """Right-click a MESSAGE → Apps → Steal emojis (works in any server as User App)."""
    await interaction.response.defer(ephemeral=True)
    found = find_custom_emojis_in_message(message)

    if not found:
        return await interaction.followup.send(
            "No custom emojis in that **message**.\n"
            "Right-click the **message** (not the emoji picker) → Apps → Steal emojis.\n"
            "Or `/emojisteal` and **paste** the emoji into `emoji:`.",
            ephemeral=True,
        )

    files = []
    lines = []
    for emoji in found[:10]:
        animated = bool(getattr(emoji, "animated", False))
        try:
            data, ext = await asyncio.to_thread(
                fetch_emoji_bytes, int(emoji.id), animated
            )
        except Exception as e:
            lines.append(f":{getattr(emoji, 'name', 'emoji')}: failed (`{e}`)")
            continue
        safe_name = re.sub(
            r"[^A-Za-z0-9_-]+",
            "_",
            str(getattr(emoji, "name", None) or "emoji"),
        ).strip("_") or "emoji"
        filename = f"{safe_name}_{emoji.id}.{ext}"
        files.append(discord.File(io.BytesIO(data), filename=filename))
        kind = "GIF" if ext == "gif" else "PNG"
        lines.append(f"**:{getattr(emoji, 'name', 'emoji')}:** → `{filename}` ({kind})")

    if not files:
        return await interaction.followup.send("Could not download those emojis.", ephemeral=True)

    embed = discord.Embed(
        title=f"Stolen {len(files)} emoji(s)",
        description="\n".join(lines),
        color=0x5865F2,
    )
    await interaction.followup.send(embed=embed, files=files, ephemeral=True)


# ============================================================
# ERRORS / START
# ============================================================


@bot.event
async def on_command_error(ctx, error):
    await ctx.send(f"Error: `{error}`")


@tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    try:
        if isinstance(error, app_commands.CommandNotFound):
            msg = (
                f"`{error.name}` is registered on Discord but this Beacon process "
                f"doesn't have the handler (old `smmod.py` on the VPS).\n"
                f"Replace VPS `smmod.py` with the latest ready file and "
                f"`pm2 restart beacon`."
            )
        else:
            msg = f"Error: `{error}`"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass


# Termux / phone Wi-Fi: discord.py reconnects on its own; gateway WARNING spam is normal.
logging.getLogger("discord.gateway").setLevel(logging.ERROR)
logging.getLogger("discord.client").setLevel(logging.WARNING)

bot.run(TOKEN or os.environ.get("DISCORD_TOKEN", ""))
