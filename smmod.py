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
# Free: sticky, polls, reminders, basic XP
# Premium: temprole, economy shop, autoresponder, invite tracker
# TTS: /tts join|leave|say and *tts (multi-server VCs; needs gTTS + ffmpeg)
# Music: /play YouTube URL or search (needs yt-dlp + ffmpeg)
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
import json
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

try:
    from gtts import gTTS
except ImportError:
    gTTS = None

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

# Always read/write premium next to this script (not the shell's cwd).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREMIUM_FILE = os.path.join(BASE_DIR, "premium_users.txt")
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


intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)
tree = bot.tree



CONFIG_FILE = "beacon_config.json"
WARNS_FILE = "beacon_warns.json"
BACKUP_DIR = "backups"
MESSAGE_BACKUP_DIR = "message_backups"
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
os.makedirs(MESSAGE_BACKUP_DIR, exist_ok=True)

# Regular /backup now also backs up recent messages from every readable text channel.
# Regular /restore and /wiperestore replay the latest all-channel message backup after restoring structure.
DEFAULT_BACKUP_MESSAGE_LIMIT_PER_CHANNEL = 500
DEFAULT_RESTORE_MESSAGE_LIMIT_PER_CHANNEL = 100

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
        # Message backup system
        "message_backup_live_enabled": False,
        "message_backup_include_bots": False,
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
        }
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


def public_backup_filename(guild):
    return f"{clean_filename(guild.name)}_{guild.id}_backup.json"


def latest_message_backup_file_for_guild(guild_id):
    folder = message_backup_guild_dir(guild_id)

    files = [
        os.path.join(folder, name)
        for name in os.listdir(folder)
        if name.endswith(".json")
    ]

    if not files:
        return None

    return max(files, key=os.path.getmtime)


def public_message_backup_filename(guild, path):
    return f"{clean_filename(guild.name)}_{guild.id}_{os.path.basename(path)}"


def message_backup_guild_dir(guild_id):
    path = os.path.join(MESSAGE_BACKUP_DIR, str(guild_id))
    os.makedirs(path, exist_ok=True)
    return path


def clean_filename(value):
    value = str(value)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)
    return safe[:80] or "backup"


def message_to_backup_dict(message, event="message", before_content=None, after_content=None):
    return {
        "event": event,
        "message_id": message.id,
        "guild_id": message.guild.id if message.guild else None,
        "guild_name": message.guild.name if message.guild else None,
        "channel_id": message.channel.id if message.channel else None,
        "channel_name": getattr(message.channel, "name", None),
        "channel_type": str(getattr(message.channel, "type", "unknown")),
        "author_id": message.author.id if message.author else None,
        "author": str(message.author) if message.author else None,
        "author_bot": bool(getattr(message.author, "bot", False)),
        "content": message.content,
        "before_content": before_content,
        "after_content": after_content,
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "edited_at": message.edited_at.isoformat() if message.edited_at else None,
        "jump_url": getattr(message, "jump_url", None),
        "pinned": getattr(message, "pinned", False),
        "mentions": [user.id for user in getattr(message, "mentions", [])],
        "role_mentions": [role.id for role in getattr(message, "role_mentions", [])],
        "attachments": [
            {
                "id": attachment.id,
                "filename": attachment.filename,
                "url": attachment.url,
                "proxy_url": attachment.proxy_url,
                "size": attachment.size,
                "content_type": getattr(attachment, "content_type", None)
            }
            for attachment in getattr(message, "attachments", [])
        ],
        "embeds": [embed.to_dict() for embed in getattr(message, "embeds", [])]
    }


async def save_live_message_backup(message, event="created", before_content=None, after_content=None):
    """Append one message event to a per-channel JSONL file."""
    if not message.guild:
        return

    cfg = get_guild(message.guild.id)

    if not cfg.get("message_backup_live_enabled", False):
        return

    if getattr(message.author, "bot", False) and not cfg.get("message_backup_include_bots", False):
        return

    folder = message_backup_guild_dir(message.guild.id)
    path = os.path.join(folder, f"live_{message.channel.id}.jsonl")
    data = message_to_backup_dict(
        message,
        event=event,
        before_content=before_content,
        after_content=after_content
    )

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


async def backup_channel_messages(channel, limit=1000):
    """Back up recent messages from one text channel/thread into a JSON file."""
    limit = max(1, min(int(limit), 10000))
    guild = channel.guild
    folder = message_backup_guild_dir(guild.id)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{clean_filename(channel.name)}_{channel.id}.json"
    path = os.path.join(folder, filename)

    messages = []

    async for message in channel.history(limit=limit, oldest_first=True):
        messages.append(message_to_backup_dict(message, event="history"))

    data = {
        "backup_type": "channel_messages",
        "created_at": int(time.time()),
        "guild_id": guild.id,
        "guild_name": guild.name,
        "channel_id": channel.id,
        "channel_name": channel.name,
        "requested_limit": limit,
        "message_count": len(messages),
        "messages": messages
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return path, len(messages)


async def backup_all_text_messages(guild, limit_per_channel=500):
    """Back up recent messages from every readable text channel into one JSON file."""
    limit_per_channel = max(1, min(int(limit_per_channel), 5000))
    folder = message_backup_guild_dir(guild.id)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(folder, f"{timestamp}_{clean_filename(guild.name)}_all_messages.json")

    result = {
        "backup_type": "all_text_channel_messages",
        "created_at": int(time.time()),
        "guild_id": guild.id,
        "guild_name": guild.name,
        "limit_per_channel": limit_per_channel,
        "channels": [],
        "skipped_channels": []
    }

    for channel in guild.text_channels:
        try:
            perms = channel.permissions_for(guild.me)

            if not perms.view_channel or not perms.read_message_history:
                result["skipped_channels"].append({
                    "channel_id": channel.id,
                    "channel_name": channel.name,
                    "reason": "missing view_channel or read_message_history permission"
                })
                continue

            channel_messages = []

            async for message in channel.history(limit=limit_per_channel, oldest_first=True):
                channel_messages.append(message_to_backup_dict(message, event="history"))

            result["channels"].append({
                "channel_id": channel.id,
                "channel_name": channel.name,
                "message_count": len(channel_messages),
                "messages": channel_messages
            })

            await asyncio.sleep(1)

        except Exception as e:
            result["skipped_channels"].append({
                "channel_id": getattr(channel, "id", None),
                "channel_name": getattr(channel, "name", None),
                "reason": str(e)
            })

    result["total_messages"] = sum(c["message_count"] for c in result["channels"])

    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return path, result["total_messages"], len(result["channels"]), len(result["skipped_channels"])



def safe_backup_file_path(guild_id, file_name):
    """Return a safe path inside this guild's message backup folder."""
    folder = os.path.abspath(message_backup_guild_dir(guild_id))
    file_name = os.path.basename(str(file_name or ""))

    if not file_name or file_name in [".", ".."]:
        return None

    path = os.path.abspath(os.path.join(folder, file_name))

    if not path.startswith(folder + os.sep):
        return None

    if not os.path.exists(path):
        return None

    return path


def channel_name_matches(saved_name, current_name):
    """Loose channel-name match for restored channels whose Discord IDs changed."""
    if not saved_name or not current_name:
        return False

    return clean_filename(str(saved_name).lower()) == clean_filename(str(current_name).lower())


def load_messages_from_backup_file(path, channel_id=None, channel_name=None):
    """Load messages for one channel from a message backup JSON file.

    First matches by channel ID. If the server was wiped/restored, Discord gives
    recreated channels new IDs, so this also falls back to the channel name.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    backup_type = data.get("backup_type")

    if backup_type == "channel_messages":
        saved_id = data.get("channel_id")
        saved_name = data.get("channel_name")

        if channel_id is not None and saved_id is not None:
            try:
                if int(saved_id) == int(channel_id):
                    return data.get("messages", [])
            except:
                pass

        if channel_name_matches(saved_name, channel_name):
            return data.get("messages", [])

    if backup_type == "all_text_channel_messages":
        # Prefer exact channel ID first.
        if channel_id is not None:
            for channel_data in data.get("channels", []):
                try:
                    if int(channel_data.get("channel_id", 0)) == int(channel_id):
                        return channel_data.get("messages", [])
                except:
                    pass

        # Fallback for restored channels with new IDs.
        for channel_data in data.get("channels", []):
            if channel_name_matches(channel_data.get("channel_name"), channel_name):
                return channel_data.get("messages", [])

    return []


def find_latest_message_backup_for_channel(guild_id, channel_id=None, channel_name=None):
    """Find the newest normal JSON message backup containing this channel.

    Matches by channel ID first, then by channel name. The name fallback matters
    after /wiperestore because recreated channels get new Discord IDs.
    """
    folder = message_backup_guild_dir(guild_id)

    files = [
        os.path.join(folder, name)
        for name in os.listdir(folder)
        if name.endswith(".json")
    ]

    files.sort(key=lambda path: os.path.getmtime(path), reverse=True)

    for path in files:
        try:
            messages = load_messages_from_backup_file(path, channel_id=channel_id, channel_name=channel_name)
            if messages:
                return path, messages
        except Exception as e:
            print("Message backup scan failed:", path, e)

    return None, []


async def get_restore_webhook(channel):
    """Get or create a webhook used to replay messages."""
    try:
        webhooks = await channel.webhooks()

        for hook in webhooks:
            if hook.name == "Beacon Message Restore":
                return hook

        return await channel.create_webhook(
            name="Beacon Message Restore",
            reason="Beacon message backup restore"
        )
    except Exception as e:
        print("Could not get/create restore webhook:", e)
        return None


def build_restored_message_content(message_data, include_timestamps=True):
    content = message_data.get("content") or ""

    attachment_lines = []
    for attachment in message_data.get("attachments", []):
        filename = attachment.get("filename") or "attachment"
        url = attachment.get("url") or attachment.get("proxy_url")
        if url:
            attachment_lines.append(f"📎 {filename}: {url}")

    if attachment_lines:
        if content:
            content += "\n\n"
        content += "\n".join(attachment_lines)

    if include_timestamps:
        created_at = message_data.get("created_at")
        if created_at:
            if content:
                content += "\n"
            content += f"`Originally sent: {created_at}`"

    if not content.strip():
        content = "*[empty message / embed-only message]*"

    if len(content) > 1900:
        content = content[:1850] + "\n*[message was too long, trimmed during restore]*"

    return content


async def restore_messages_to_channel(channel, file_name=None, max_messages=100, include_timestamps=True):
    """Replay backed-up messages into a channel using a webhook when possible."""
    max_messages = max(1, min(int(max_messages), 1000))

    perms = channel.permissions_for(channel.guild.me)

    if not perms.view_channel or not perms.send_messages:
        return False, "I need View Channel and Send Messages permissions in that channel."

    path = None
    messages = []

    if file_name:
        path = safe_backup_file_path(channel.guild.id, file_name)
        if path is None:
            return False, "I could not find that backup file in this server's message backup folder."
        messages = load_messages_from_backup_file(path, channel_id=channel.id, channel_name=channel.name)
    else:
        path, messages = find_latest_message_backup_for_channel(channel.guild.id, channel_id=channel.id, channel_name=channel.name)

    if not path or not messages:
        return False, "No message backup found for this channel name. Run `/getmessagebackup` to check that a backup exists, or run `/messagebackup_all` before restoring/wiping."

    # If the backup is huge, restore the newest N while preserving old-to-new order.
    selected_messages = messages[-max_messages:]

    webhook = None
    if perms.manage_webhooks:
        webhook = await get_restore_webhook(channel)

    restored = 0
    failed = 0

    for message_data in selected_messages:
        try:
            content = build_restored_message_content(message_data, include_timestamps=include_timestamps)
            username = (message_data.get("author") or "Unknown user")[:80]

            if webhook:
                await webhook.send(
                    content=content,
                    username=username,
                    allowed_mentions=discord.AllowedMentions.none()
                )
            else:
                await channel.send(
                    f"**{username}:**\n{content}",
                    allowed_mentions=discord.AllowedMentions.none()
                )

            restored += 1
            await asyncio.sleep(0.8)
        except Exception as e:
            failed += 1
            print("Message restore failed:", e)
            await asyncio.sleep(2)

    mode = "webhook usernames" if webhook else "normal bot messages because Manage Webhooks is missing"
    return True, (
        f"Restored `{restored}` messages into {channel.mention} using {mode}.\n"
        f"Failed: `{failed}`\n"
        f"Source: `{os.path.basename(path)}`\n"
        "Warning: restored messages are reposts, not the original Discord messages."
    )


def find_latest_all_message_backup_for_guild(guild_id):
    """Find the newest all-channel message backup for this guild."""
    folder = message_backup_guild_dir(guild_id)

    files = [
        os.path.join(folder, name)
        for name in os.listdir(folder)
        if name.endswith(".json")
    ]

    files.sort(key=lambda path: os.path.getmtime(path), reverse=True)

    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if data.get("backup_type") == "all_text_channel_messages":
                return path, data

        except Exception as e:
            print("All-message backup scan failed:", path, e)

    return None, None


def find_text_channel_for_saved_backup(guild, channel_data):
    """Match saved message backup channel data to the current restored channel."""
    saved_id = channel_data.get("channel_id")
    saved_name = channel_data.get("channel_name")

    if saved_id is not None:
        try:
            channel = guild.get_channel(int(saved_id))
            if isinstance(channel, discord.TextChannel):
                return channel
        except:
            pass

    for channel in guild.text_channels:
        if channel_name_matches(saved_name, channel.name):
            return channel

    return None


async def restore_all_messages_for_guild(guild, max_messages_per_channel=DEFAULT_RESTORE_MESSAGE_LIMIT_PER_CHANNEL, include_timestamps=True):
    """Replay the latest all-channel message backup into matching current channels."""
    max_messages_per_channel = max(1, min(int(max_messages_per_channel), 1000))
    path, data = find_latest_all_message_backup_for_guild(guild.id)

    if not path or not data:
        return False, "No all-channel message backup found. Run `/backup` or `/messagebackup_all` first."

    restored_channels = 0
    restored_messages = 0
    skipped_channels = 0
    failed_channels = 0

    for channel_data in data.get("channels", []):
        try:
            channel = find_text_channel_for_saved_backup(guild, channel_data)

            if channel is None:
                skipped_channels += 1
                continue

            message_count = int(channel_data.get("message_count", 0))
            if message_count <= 0:
                skipped_channels += 1
                continue

            ok, msg = await restore_messages_to_channel(
                channel,
                file_name=os.path.basename(path),
                max_messages=max_messages_per_channel,
                include_timestamps=include_timestamps
            )

            if ok:
                restored_channels += 1
                restored_messages += min(message_count, max_messages_per_channel)
            else:
                failed_channels += 1
                print("Channel message restore skipped:", channel.name, msg)

            await asyncio.sleep(2)

        except Exception as e:
            failed_channels += 1
            print("Channel message restore failed:", e)
            await asyncio.sleep(3)

    return True, (
        f"Message restore finished from `{os.path.basename(path)}`. "
        f"Replayed up to `{max_messages_per_channel}` messages per channel.\n"
        f"Channels restored: `{restored_channels}` | Estimated messages reposted: `{restored_messages}` | "
        f"Skipped: `{skipped_channels}` | Failed: `{failed_channels}`\n"
        "Warning: these are reposted messages, not original Discord messages."
    )


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
                await backup_all_text_messages(guild, DEFAULT_BACKUP_MESSAGE_LIMIT_PER_CHANNEL)

            asyncio.run_coroutine_threadsafe(dashboard_backup_job(), bot.loop)
            dashboard_json(self, {"ok": True, "message": "Backup started, including recent messages"})
            return

        if parsed.path == "/api/restore":
            async def dashboard_restore_job():
                ok, _ = await restore_backup(guild, wipe_first=False)
                if ok:
                    await restore_all_messages_for_guild(guild, DEFAULT_RESTORE_MESSAGE_LIMIT_PER_CHANNEL)

            asyncio.run_coroutine_threadsafe(dashboard_restore_job(), bot.loop)
            dashboard_json(self, {"ok": True, "message": "Restore started, including message replay"})
            return

        if parsed.path == "/api/wiperestore":
            async def dashboard_wiperestore_job():
                ok, _ = await restore_backup(guild, wipe_first=True)
                if ok:
                    await restore_all_messages_for_guild(guild, DEFAULT_RESTORE_MESSAGE_LIMIT_PER_CHANNEL)

            asyncio.run_coroutine_threadsafe(dashboard_wiperestore_job(), bot.loop)
            dashboard_json(self, {"ok": True, "message": "Wipe restore started, including message replay"})
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


@bot.event
async def on_ready():
    print(f"Beacon online as {bot.user}")

    await bot.change_presence(activity=discord.Game(name="*help"))

    start_dashboard()

    try:
        if tree.get_command("tts") is None:
            tree.add_command(tts_slash)
    except Exception:
        pass

    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} slash commands.")
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

    await save_live_message_backup(message, event="deleted")

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

    await save_live_message_backup(
        after,
        event="edited",
        before_content=before.content,
        after_content=after.content
    )

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

    await save_live_message_backup(message, event="created")

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
    discord.SelectOption(label="Music", emoji="🎵"),
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
`/tts join` · `/tts_join` or `*tts join` - Join your voice channel (multi-server OK).
`/tts leave` · `/tts_leave` or `*tts leave` - Leave voice.
`/tts say` · `/tts_say` or `*tts <text>` - Speak text in the joined VC.
`/play` or `*play <url or search>` - Play YouTube (URL or name search).
`/skip` `/stop` `/pause` `/resume` `/queue` `/np` - Music controls.
"""

        elif choice == "Music":
            embed.description = """
`/play` or `*play <YouTube URL or search terms>` - Play or queue a song.
`/skip` or `*skip` - Skip current song.
`/stop` or `*stop` - Stop and clear the queue.
`/pause` `/resume` or `*pause` `*resume` - Pause / resume.
`/queue` or `*queue` - Show the queue.
`/np` or `*np` - Now playing.

Needs: `pip install yt-dlp --break-system-packages` and ffmpeg.
"""

        elif choice == "Free Features":
            embed.description = """
`/sticky` or `*sticky <text>` - Keep a sticky message at the bottom of this channel.
`/unsticky` or `*unsticky` - Remove the sticky.
`/poll` or `*poll Question | Option A | Option B | ...` - Create a button poll.
`/remind` or `*remind 2h take out trash` - Set a reminder in this channel.
`/level` or `*level` / `*rank [@user]` - View XP level (basic, no role rewards).
`/leaderboard` or `*leaderboard` - Top XP in this server.
"""

        elif choice == "Premium Features":
            embed.description = """
**Requires Beacon Premium** (you or the server owner).

`/temprole` or `*temprole @user @Role 7d` - Temporary role grant (auto-removes).
`/temproles` or `*temproles` - List active temp roles in this server.

`/balance` `/daily` `/pay` or `*balance` `*daily` `*pay @user amount` - Economy coins.
`/givemoney` or `*givemoney @user amount` - Owner only: spawn coins for someone.
`/shop` `/buy` or `*shop` `*buy <item>` - Browse / buy shop items.
`/shopadd` `/shoprole` `/shopremove` or `*shopadd` `*shoprole` `*shopremove` - Manage shop.

`/autorespond` or `*autorespond add <keyword> | <response>` - Keyword auto-reply.
`*autorespond regex <pattern> | <response>` / `list` / `remove <number>`

`/invites` or `*invites [@user]` - Invite tracker (real vs fake).
Fake invites = joined accounts younger than 7 days.
"""

        elif choice == "Backups":
            embed.description = """
`/backup` or `*backup` - Save server backup: name, icon, roles, channels, and permissions. Does not save emojis or sounds.
`/restore` or `*restore` - Restore missing structure.
`/wiperestore` or `*wiperestore` - Fully wipe then restore.
`/messagebackup` or `*messagebackup` - Back up messages from the current/selected channel.
`/messagebackup_all` or `*messagebackup_all` - Back up messages from all readable text channels.
`/messagebackup_live` or `*messagebackup_live on/off` - Toggle automatic live message backups.
`/messagebackups` or `*messagebackups` - List saved message backup files.

Server backups are saved in:
`backups/<server_id>.json`

Message backups are saved in:
`message_backups/<server_id>/`
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
@tree.command(name="broadcast", description="Broadcast a message to every server.")
@app_commands.describe(message="The announcement to send")
async def slash_broadcast(interaction: discord.Interaction, message: str):

    OWNER_ID = 1257060226029584459

    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ You can't use this command.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    sent = 0
    failed = 0

    for guild in bot.guilds:

        channel = guild.system_channel

        # Fall back to the first text channel the bot can send in
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
                color=0x5865F2
            )

            await channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none()
            )

            sent += 1

        except Exception as e:
            print(f"{guild.name}: {e}")
            failed += 1

    await interaction.followup.send(
        f"✅ Broadcast complete.\n"
        f"Sent: **{sent}** server(s)\n"
        f"Failed: **{failed}**",
        ephemeral=True
    )


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
    if interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("❌ You can't use this command.", ephemeral=True)
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
    if ctx.author.id != BOT_OWNER_ID:
        return await ctx.send("❌ You can't use this command.")

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


@tree.command(name="backup", description="Create this server's backup, including recent messages")
@app_commands.checks.has_permissions(administrator=True)
async def slash_backup(
    interaction: discord.Interaction,
    message_limit_per_channel: app_commands.Range[int, 1, 5000] = DEFAULT_BACKUP_MESSAGE_LIMIT_PER_CHANNEL
):
    await interaction.response.defer(ephemeral=True)

    await create_backup(interaction.guild)
    message_path, total_messages, channel_count, skipped_channels = await backup_all_text_messages(
        interaction.guild,
        message_limit_per_channel
    )

    path = backup_path(interaction.guild.id)
    message = (
        "Backup saved for **this server only**: server name, icon, roles, channels, permissions, "
        f"and `{total_messages}` recent messages from `{channel_count}` channels.\n"
        f"Message limit per channel: `{message_limit_per_channel}` | Skipped message channels: `{skipped_channels}`\n"
        "Emojis and soundboard sounds were skipped."
    )

    files = []
    if os.path.exists(path) and os.path.getsize(path) <= DISCORD_SAFE_FILE_LIMIT:
        files.append(discord.File(path, filename=public_backup_filename(interaction.guild)))
    if os.path.exists(message_path) and os.path.getsize(message_path) <= DISCORD_SAFE_FILE_LIMIT:
        files.append(discord.File(message_path, filename=public_message_backup_filename(interaction.guild, message_path)))

    if files:
        await interaction.followup.send(message, files=files, ephemeral=True)
    else:
        await interaction.followup.send(
            message + "\nFiles are saved server-side but are too big to upload to Discord.",
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


@tree.command(name="messagebackups", description="List this server's saved message backup files")
@app_commands.checks.has_permissions(administrator=True)
async def slash_messagebackups(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    folder = message_backup_guild_dir(interaction.guild.id)
    files = [
        os.path.join(folder, name)
        for name in os.listdir(folder)
        if name.endswith(".json")
    ]
    files.sort(key=lambda path: os.path.getmtime(path), reverse=True)

    if not files:
        await interaction.followup.send("No message backup files found for this server.", ephemeral=True)
        return

    lines = []
    for path in files[:15]:
        try:
            size_kb = os.path.getsize(path) // 1024
            lines.append(f"`{os.path.basename(path)}` - `{size_kb} KB`")
        except:
            lines.append(f"`{os.path.basename(path)}`")

    await interaction.followup.send(
        "Latest message backup files for **this server only**:\n" + "\n".join(lines),
        ephemeral=True
    )


@tree.command(name="getmessagebackup", description="Download this server's latest message backup")
@app_commands.checks.has_permissions(administrator=True)
async def slash_getmessagebackup(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    path = latest_message_backup_file_for_guild(interaction.guild.id)

    if not path:
        await interaction.followup.send("No message backup found for this server. Run `/messagebackup` or `/messagebackup_all` first.", ephemeral=True)
        return

    if os.path.getsize(path) > DISCORD_SAFE_FILE_LIMIT:
        await interaction.followup.send("Latest message backup exists for this server, but it is too big to upload to Discord.", ephemeral=True)
        return

    await interaction.followup.send(
        "Here is the latest message backup for **this server only**.",
        file=discord.File(path, filename=public_message_backup_filename(interaction.guild, path)),
        ephemeral=True
    )


@tree.command(name="messagebackup", description="Back up messages from a channel")
@app_commands.checks.has_permissions(administrator=True)
async def slash_messagebackup(
    interaction: discord.Interaction,
    channel: discord.TextChannel = None,
    limit: app_commands.Range[int, 1, 10000] = 1000
):
    await interaction.response.defer(ephemeral=True)

    target_channel = channel or interaction.channel

    if not isinstance(target_channel, (discord.TextChannel, discord.Thread)):
        await interaction.followup.send("This only works in text channels/threads.", ephemeral=True)
        return

    path, count = await backup_channel_messages(target_channel, limit)
    message = f"Message backup saved for **this server only**: `{count}` messages from {target_channel.mention}."

    if os.path.getsize(path) <= DISCORD_SAFE_FILE_LIMIT:
        await interaction.followup.send(message, file=discord.File(path, filename=public_message_backup_filename(interaction.guild, path)), ephemeral=True)
    else:
        await interaction.followup.send(message + "\nFile is too big for Discord upload, but it is saved server-side.", ephemeral=True)


@tree.command(name="messagebackup_all", description="Back up messages from every readable text channel")
@app_commands.checks.has_permissions(administrator=True)
async def slash_messagebackup_all(
    interaction: discord.Interaction,
    limit_per_channel: app_commands.Range[int, 1, 5000] = 500
):
    await interaction.response.defer(ephemeral=True)

    path, total, channel_count, skipped = await backup_all_text_messages(interaction.guild, limit_per_channel)
    message = (
        f"Message backup saved for **this server only**: `{total}` messages from `{channel_count}` channels.\n"
        f"Skipped channels: `{skipped}`"
    )

    if os.path.getsize(path) <= DISCORD_SAFE_FILE_LIMIT:
        await interaction.followup.send(message, file=discord.File(path, filename=public_message_backup_filename(interaction.guild, path)), ephemeral=True)
    else:
        await interaction.followup.send(message + "\nFile is too big for Discord upload, but it is saved server-side.", ephemeral=True)


@tree.command(name="messagebackup_live", description="Turn automatic live message backups on or off")
@app_commands.checks.has_permissions(administrator=True)
async def slash_messagebackup_live(interaction: discord.Interaction, enabled: bool):
    cfg = get_guild(interaction.guild.id)
    cfg["message_backup_live_enabled"] = enabled
    save_config()

    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(f"Live message backups {state} for **this server only**.", ephemeral=True)


@tree.command(name="messagerestore", description="Replay backed-up messages into a channel")
@app_commands.checks.has_permissions(administrator=True)
async def slash_messagerestore(
    interaction: discord.Interaction,
    channel: discord.TextChannel = None,
    file_name: str = None,
    max_messages: app_commands.Range[int, 1, 1000] = 100,
    include_timestamps: bool = True
):
    await interaction.response.defer(ephemeral=True)

    target_channel = channel or interaction.channel

    if not isinstance(target_channel, discord.TextChannel):
        await interaction.followup.send("This only works in normal text channels.", ephemeral=True)
        return

    ok, msg = await restore_messages_to_channel(
        target_channel,
        file_name=file_name,
        max_messages=max_messages,
        include_timestamps=include_timestamps
    )

    await interaction.followup.send(msg, ephemeral=True)


@tree.command(name="restore", description="Restore server and replay backed-up messages")
@app_commands.checks.has_permissions(administrator=True)
async def slash_restore(
    interaction: discord.Interaction,
    restore_messages: bool = True,
    max_messages_per_channel: app_commands.Range[int, 1, 1000] = DEFAULT_RESTORE_MESSAGE_LIMIT_PER_CHANNEL
):
    await interaction.response.defer()

    ok, msg = await restore_backup(interaction.guild, wipe_first=False)

    if restore_messages and ok:
        mok, mmsg = await restore_all_messages_for_guild(
            interaction.guild,
            max_messages_per_channel=max_messages_per_channel,
            include_timestamps=True
        )
        msg = msg + "\n\n" + mmsg

    await interaction.followup.send(msg)


@tree.command(name="wiperestore", description="Wipe server structure, restore it, then replay messages")
@app_commands.checks.has_permissions(administrator=True)
async def slash_wiperestore(
    interaction: discord.Interaction,
    restore_messages: bool = True,
    max_messages_per_channel: app_commands.Range[int, 1, 1000] = DEFAULT_RESTORE_MESSAGE_LIMIT_PER_CHANNEL
):
    await interaction.response.defer()

    ok, msg = await restore_backup(interaction.guild, wipe_first=True)

    if restore_messages and ok:
        mok, mmsg = await restore_all_messages_for_guild(
            interaction.guild,
            max_messages_per_channel=max_messages_per_channel,
            include_timestamps=True
        )
        msg = msg + "\n\n" + mmsg

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
async def prefix_backup(ctx, message_limit_per_channel: int = DEFAULT_BACKUP_MESSAGE_LIMIT_PER_CHANNEL):
    await ctx.send("Backing up server structure and messages now.")

    await create_backup(ctx.guild)
    message_path, total_messages, channel_count, skipped_channels = await backup_all_text_messages(
        ctx.guild,
        message_limit_per_channel
    )

    path = backup_path(ctx.guild.id)
    message = (
        "Backup saved for **this server only**: server name, icon, roles, channels, permissions, "
        f"and `{total_messages}` recent messages from `{channel_count}` channels.\n"
        f"Message limit per channel: `{message_limit_per_channel}` | Skipped message channels: `{skipped_channels}`\n"
        "Emojis and soundboard sounds were skipped."
    )

    files = []
    if os.path.exists(path) and os.path.getsize(path) <= DISCORD_SAFE_FILE_LIMIT:
        files.append(discord.File(path, filename=public_backup_filename(ctx.guild)))
    if os.path.exists(message_path) and os.path.getsize(message_path) <= DISCORD_SAFE_FILE_LIMIT:
        files.append(discord.File(message_path, filename=public_message_backup_filename(ctx.guild, message_path)))

    if files:
        await ctx.send(message, files=files)
    else:
        await ctx.send(message + "\nFiles are saved server-side but are too big to upload to Discord.")


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


@bot.command(name="messagebackups")
@commands.has_permissions(administrator=True)
async def prefix_messagebackups(ctx):
    folder = message_backup_guild_dir(ctx.guild.id)
    files = [
        os.path.join(folder, name)
        for name in os.listdir(folder)
        if name.endswith(".json")
    ]
    files.sort(key=lambda path: os.path.getmtime(path), reverse=True)

    if not files:
        await ctx.send("No message backup files found for this server.")
        return

    lines = []
    for path in files[:15]:
        try:
            size_kb = os.path.getsize(path) // 1024
            lines.append(f"`{os.path.basename(path)}` - `{size_kb} KB`")
        except:
            lines.append(f"`{os.path.basename(path)}`")

    await ctx.send("Latest message backup files for **this server only**:\n" + "\n".join(lines))


@bot.command(name="getmessagebackup")
@commands.has_permissions(administrator=True)
async def prefix_getmessagebackup(ctx):
    path = latest_message_backup_file_for_guild(ctx.guild.id)

    if not path:
        await ctx.send("No message backup found for this server. Run `*messagebackup` or `*messagebackup_all` first.")
        return

    if os.path.getsize(path) > DISCORD_SAFE_FILE_LIMIT:
        await ctx.send("Latest message backup exists for this server, but it is too big to upload to Discord.")
        return

    await ctx.send(
        "Here is the latest message backup for **this server only**.",
        file=discord.File(path, filename=public_message_backup_filename(ctx.guild, path))
    )


@bot.command(name="messagebackup")
@commands.has_permissions(administrator=True)
async def prefix_messagebackup(ctx, limit: int = 1000):
    path, count = await backup_channel_messages(ctx.channel, limit)
    message = f"Message backup saved for **this server only**: `{count}` messages from {ctx.channel.mention}."

    if os.path.getsize(path) <= DISCORD_SAFE_FILE_LIMIT:
        await ctx.send(message, file=discord.File(path, filename=public_message_backup_filename(ctx.guild, path)))
    else:
        await ctx.send(message + "\nFile is too big for Discord upload, but it is saved server-side.")


@bot.command(name="messagebackup_all")
@commands.has_permissions(administrator=True)
async def prefix_messagebackup_all(ctx, limit_per_channel: int = 500):
    await ctx.send("Backing up messages now. This can take a while on big servers.")
    path, total, channel_count, skipped = await backup_all_text_messages(ctx.guild, limit_per_channel)
    message = (
        f"Message backup saved for **this server only**: `{total}` messages from `{channel_count}` channels.\n"
        f"Skipped channels: `{skipped}`"
    )

    if os.path.getsize(path) <= DISCORD_SAFE_FILE_LIMIT:
        await ctx.send(message, file=discord.File(path, filename=public_message_backup_filename(ctx.guild, path)))
    else:
        await ctx.send(message + "\nFile is too big for Discord upload, but it is saved server-side.")


@bot.command(name="messagebackup_live")
@commands.has_permissions(administrator=True)
async def prefix_messagebackup_live(ctx, state: str):
    state = state.lower()

    if state not in ["on", "off", "true", "false", "enable", "disable", "enabled", "disabled"]:
        await ctx.send("Use: `*messagebackup_live on` or `*messagebackup_live off`")
        return

    enabled = state in ["on", "true", "enable", "enabled"]
    cfg = get_guild(ctx.guild.id)
    cfg["message_backup_live_enabled"] = enabled
    save_config()

    await ctx.send(f"Live message backups {'enabled' if enabled else 'disabled'} for **this server only**.")


@bot.command(name="messagerestore")
@commands.has_permissions(administrator=True)
async def prefix_messagerestore(ctx, limit: int = 100):
    await ctx.send("Restoring messages. This will repost them, not bring back the original Discord messages.")

    ok, msg = await restore_messages_to_channel(
        ctx.channel,
        file_name=None,
        max_messages=limit,
        include_timestamps=True
    )

    await ctx.send(msg)


@bot.command(name="restore")
@commands.has_permissions(administrator=True)
async def prefix_restore(ctx, max_messages_per_channel: int = DEFAULT_RESTORE_MESSAGE_LIMIT_PER_CHANNEL):
    await ctx.send("Restoring server structure. Messages will be replayed after the structure restore.")
    ok, msg = await restore_backup(ctx.guild, wipe_first=False)

    if ok:
        mok, mmsg = await restore_all_messages_for_guild(
            ctx.guild,
            max_messages_per_channel=max_messages_per_channel,
            include_timestamps=True
        )
        msg = msg + "\n\n" + mmsg

    await ctx.send(msg)


@bot.command(name="wiperestore")
@commands.has_permissions(administrator=True)
async def prefix_wiperestore(ctx, max_messages_per_channel: int = DEFAULT_RESTORE_MESSAGE_LIMIT_PER_CHANNEL):
    await ctx.send("Wiping/restoring server structure. Messages will be replayed after channels are recreated.")
    ok, msg = await restore_backup(ctx.guild, wipe_first=True)

    if ok:
        mok, mmsg = await restore_all_messages_for_guild(
            ctx.guild,
            max_messages_per_channel=max_messages_per_channel,
            include_timestamps=True
        )
        msg = msg + "\n\n" + mmsg

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
    if not has_premium_access(guild, author):
        return await send("❌ Economy is a Beacon Premium feature.")
    member = member or author
    bal = get_balance(guild.id, member.id)
    await send(f"💰 {member.mention} has **{bal}** coins.")


async def do_daily(guild, author, send):
    if not has_premium_access(guild, author):
        return await send("❌ Economy is a Beacon Premium feature.")
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
    if not has_premium_access(guild, author):
        return await send("❌ Economy is a Beacon Premium feature.")
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
    """Owner-only: spawn coins for someone (does not take from your balance)."""
    if author.id != BOT_OWNER_ID:
        return await send("❌ Only the bot owner can use this.")
    if guild is None:
        return await send("Use this in a server.")
    if member is None or amount is None or amount <= 0:
        return await send("Usage: `*givemoney @user 1000` or `/givemoney`")
    bal = add_coins(guild.id, member.id, int(amount))
    await send(f"✅ Gave **{amount}** coins to {member.mention}. Their balance is now **{bal}**.")


async def do_shop(guild, author, send):
    if not has_premium_access(guild, author):
        return await send("❌ Economy is a Beacon Premium feature.")
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
    if not has_premium_access(guild, author):
        return await send("❌ Economy is a Beacon Premium feature.")
    if price is None or price < 0 or not name:
        return await send("Usage: `*shopadd 100 Cool Item` or `/shopadd`")
    g = get_economy_guild(guild.id)
    g["shop"].append({"name": name, "price": int(price), "role_id": None})
    save_economy()
    await send(f"✅ Added shop item **{name}** for `{price}` coins.")


async def do_shoprole(guild, author, price, role, send):
    if not has_premium_access(guild, author):
        return await send("❌ Economy is a Beacon Premium feature.")
    if price is None or role is None:
        return await send("Usage: `*shoprole 500 @VIP` or `/shoprole`")
    g = get_economy_guild(guild.id)
    g["shop"].append({"name": role.name, "price": int(price), "role_id": role.id})
    save_economy()
    await send(f"✅ Added role item {role.mention} for `{price}` coins.")


async def do_shopremove(guild, author, name, send):
    if not has_premium_access(guild, author):
        return await send("❌ Economy is a Beacon Premium feature.")
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
    if not has_premium_access(guild, author):
        return await send("❌ Economy is a Beacon Premium feature.")
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


@tree.command(name="balance", description="Check coin balance (Premium)")
@app_commands.describe(member="Member (optional)")
async def slash_balance(interaction: discord.Interaction, member: discord.Member = None):
    await interaction.response.defer()
    await do_balance(interaction.guild, interaction.user, member, _slash_send(interaction))


@bot.command(name="daily")
async def daily_cmd(ctx):
    await do_daily(ctx.guild, ctx.author, ctx.send)


@tree.command(name="daily", description="Claim daily coins (Premium)")
async def slash_daily(interaction: discord.Interaction):
    await interaction.response.defer()
    await do_daily(interaction.guild, interaction.user, _slash_send(interaction))


@bot.command(name="pay", aliases=["givecoins"])
async def pay_cmd(ctx, member: discord.Member = None, amount: int = None):
    await do_pay(ctx.guild, ctx.author, member, amount, ctx.send)


@tree.command(name="pay", description="Pay coins to a member (Premium)")
@app_commands.describe(member="Member to pay", amount="Amount of coins")
async def slash_pay(interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 1, 1_000_000]):
    await interaction.response.defer()
    await do_pay(interaction.guild, interaction.user, member, amount, _slash_send(interaction))


@bot.command(name="givemoney", aliases=["givebucks", "addmoney", "ecoadd"])
async def givemoney_cmd(ctx, member: discord.Member = None, amount: int = None):
    await do_givemoney(ctx.guild, ctx.author, member, amount, ctx.send)


@tree.command(name="givemoney", description="Owner only: give coins to a member")
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


@tree.command(name="shop", description="View the economy shop (Premium)")
async def slash_shop(interaction: discord.Interaction):
    await interaction.response.defer()
    await do_shop(interaction.guild, interaction.user, _slash_send(interaction))


@bot.command(name="shopadd")
@commands.has_permissions(manage_guild=True)
async def shopadd_cmd(ctx, price: int = None, *, name: str = None):
    await do_shopadd(ctx.guild, ctx.author, price, name, ctx.send)


@tree.command(name="shopadd", description="Add a shop item (Premium)")
@app_commands.describe(price="Price in coins", name="Item name")
@app_commands.checks.has_permissions(manage_guild=True)
async def slash_shopadd(interaction: discord.Interaction, price: app_commands.Range[int, 0, 1_000_000], name: str):
    await interaction.response.defer()
    await do_shopadd(interaction.guild, interaction.user, price, name, _slash_send(interaction))


@bot.command(name="shoprole")
@commands.has_permissions(manage_guild=True)
async def shoprole_cmd(ctx, price: int = None, role: discord.Role = None):
    await do_shoprole(ctx.guild, ctx.author, price, role, ctx.send)


@tree.command(name="shoprole", description="Add a role to the shop (Premium)")
@app_commands.describe(price="Price in coins", role="Role to sell")
@app_commands.checks.has_permissions(manage_guild=True)
async def slash_shoprole(interaction: discord.Interaction, price: app_commands.Range[int, 0, 1_000_000], role: discord.Role):
    await interaction.response.defer()
    await do_shoprole(interaction.guild, interaction.user, price, role, _slash_send(interaction))


@bot.command(name="shopremove")
@commands.has_permissions(manage_guild=True)
async def shopremove_cmd(ctx, *, name: str = None):
    await do_shopremove(ctx.guild, ctx.author, name, ctx.send)


@tree.command(name="shopremove", description="Remove a shop item (Premium)")
@app_commands.describe(name="Item name")
@app_commands.checks.has_permissions(manage_guild=True)
async def slash_shopremove(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    await do_shopremove(interaction.guild, interaction.user, name, _slash_send(interaction))


@bot.command(name="buy")
async def buy_cmd(ctx, *, name: str = None):
    await do_buy(ctx.guild, ctx.author, name, ctx.send)


@tree.command(name="buy", description="Buy a shop item (Premium)")
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
# TTS — multi-guild voice (one VC per server, many servers at once)
# Needs: pip install gTTS PyNaCl   and system ffmpeg
# ============================================================

TTS_DIR = os.path.join(BASE_DIR, "tts_cache")
os.makedirs(TTS_DIR, exist_ok=True)

# guild_id -> asyncio.Queue of (text, announce_channel_or_None)
tts_queues: dict[int, asyncio.Queue] = {}
# guild_id -> worker task
tts_workers: dict[int, asyncio.Task] = {}
_tts_lock = None

def get_tts_lock():
    global _tts_lock
    if _tts_lock is None:
        _tts_lock = asyncio.Lock()
    return _tts_lock


def get_guild_voice(guild):
    if guild is None:
        return None
    return guild.voice_client


async def tts_generate_file(text: str) -> str:
    if gTTS is None:
        raise RuntimeError("gTTS is not installed. Run: pip install gTTS PyNaCl")
    text = (text or "").strip()
    if not text:
        raise ValueError("empty text")
    if len(text) > 500:
        text = text[:500]
    path = os.path.join(TTS_DIR, f"tts_{int(time.time() * 1000)}_{os.getpid()}.mp3")

    def _write():
        gTTS(text=text, lang="en").save(path)

    await asyncio.to_thread(_write)
    return path


async def tts_play_file(vc: discord.VoiceClient, path: str):
    if not vc or not vc.is_connected():
        raise RuntimeError("not connected to voice")

    done = asyncio.Event()

    def _after(error):
        try:
            bot.loop.call_soon_threadsafe(done.set)
        except Exception:
            done.set()

    # Stop anything currently playing in this VC
    if vc.is_playing():
        vc.stop()

    source = discord.FFmpegPCMAudio(
        path,
        before_options="-nostdin",
        options="-vn",
    )
    vc.play(source, after=_after)
    await done.wait()


async def tts_worker(guild_id: int):
    """Plays queued TTS lines for one guild so servers don't block each other."""
    queue = tts_queues[guild_id]
    while True:
        path = None
        try:
            text, _ = await queue.get()
            guild = bot.get_guild(guild_id)
            vc = get_guild_voice(guild) if guild else None
            if vc is None or not vc.is_connected():
                continue
            path = await tts_generate_file(text)
            await tts_play_file(vc, path)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"TTS worker {guild_id} error:", e)
        finally:
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
            try:
                queue.task_done()
            except Exception:
                pass


async def ensure_tts_worker(guild_id: int):
    async with get_tts_lock():
        if guild_id not in tts_queues:
            tts_queues[guild_id] = asyncio.Queue()
        task = tts_workers.get(guild_id)
        if task is None or task.done():
            tts_workers[guild_id] = asyncio.create_task(tts_worker(guild_id))


async def do_tts_join(guild, author, send):
    if guild is None:
        return await send("TTS only works in a server.")
    if not isinstance(author, discord.Member):
        return await send("Couldn't find your member info.")
    if author.voice is None or author.voice.channel is None:
        return await send("Join a voice channel first, then use `/tts join` or `*tts join`.")

    channel = author.voice.channel
    vc = get_guild_voice(guild)

    try:
        if vc and vc.is_connected():
            if vc.channel and vc.channel.id == channel.id:
                await ensure_tts_worker(guild.id)
                return await send(f"Already in {channel.mention}.")
            await vc.move_to(channel)
        else:
            await channel.connect()
        await ensure_tts_worker(guild.id)
        connected = len([c for c in bot.voice_clients if c.is_connected()])
        await send(
            f"✅ Joined {channel.mention}.\n"
            f"Beacon is in **{connected}** voice channel(s) right now (multi-server OK).\n"
            f"Speak with `/tts say` or `*tts <text>`."
        )
    except Exception as e:
        await send(
            f"Failed to join VC: `{e}`\n"
            f"Make sure I have Connect + Speak, and ffmpeg is installed."
        )


async def do_tts_leave(guild, send):
    if guild is None:
        return await send("TTS only works in a server.")
    vc = get_guild_voice(guild)
    if vc is None or not vc.is_connected():
        return await send("I'm not in a voice channel here.")
    try:
        await vc.disconnect()
    except Exception as e:
        return await send(f"Failed to leave: `{e}`")
    await send("👋 Left the voice channel.")


async def do_tts_say(guild, author, text, send):
    if guild is None:
        return await send("TTS only works in a server.")
    text = (text or "").strip()
    if not text:
        return await send("Usage: `*tts <text>` or `/tts say text:...`")
    if gTTS is None:
        return await send("TTS missing dependency. Run: `pip install gTTS PyNaCl` (and install ffmpeg).")

    vc = get_guild_voice(guild)
    # Auto-join author's VC if not connected
    if vc is None or not vc.is_connected():
        if isinstance(author, discord.Member) and author.voice and author.voice.channel:
            try:
                await author.voice.channel.connect()
            except Exception as e:
                return await send(f"Couldn't join your VC: `{e}`")
        else:
            return await send("I'm not in a VC. Use `/tts join` / `*tts join` first (or join a VC and try again).")

    await ensure_tts_worker(guild.id)
    await tts_queues[guild.id].put((text, None))
    await send(f"🔊 Queued TTS: {text[:120]}{'…' if len(text) > 120 else ''}")


# Prefix: *tts join | *tts leave | *tts <text>
@bot.group(name="tts", invoke_without_command=True)
async def tts_prefix(ctx, *, text: str = None):
    if text:
        await do_tts_say(ctx.guild, ctx.author, text, ctx.send)
    else:
        await ctx.send(
            "TTS commands:\n"
            "`*tts join` / `/tts join` — join your VC\n"
            "`*tts leave` / `/tts leave` — leave\n"
            "`*tts <text>` / `/tts say` — speak\n"
            "Beacon can be in multiple servers' VCs at once."
        )


@tts_prefix.command(name="join")
async def tts_prefix_join(ctx):
    await do_tts_join(ctx.guild, ctx.author, ctx.send)


@tts_prefix.command(name="leave")
async def tts_prefix_leave(ctx):
    await do_tts_leave(ctx.guild, ctx.send)


@tts_prefix.command(name="say")
async def tts_prefix_say(ctx, *, text: str = None):
    await do_tts_say(ctx.guild, ctx.author, text, ctx.send)


# Slash: /tts join | /tts leave | /tts say
tts_slash = app_commands.Group(name="tts", description="Text-to-speech in voice (multi-server)")


@tts_slash.command(name="join", description="Join your current voice channel")
async def tts_slash_join(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await do_tts_join(interaction.guild, interaction.user, _slash_send(interaction, ephemeral=True))


@tts_slash.command(name="leave", description="Leave the voice channel in this server")
async def tts_slash_leave(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await do_tts_leave(interaction.guild, _slash_send(interaction, ephemeral=True))


@tts_slash.command(name="say", description="Speak text in the joined voice channel")
@app_commands.describe(text="What Beacon should say")
async def tts_slash_say(interaction: discord.Interaction, text: str):
    await interaction.response.defer()
    await do_tts_say(interaction.guild, interaction.user, text, _slash_send(interaction))


try:
    if tree.get_command("tts") is None:
        tree.add_command(tts_slash)
except Exception as e:
    print("tree.add_command(tts_slash):", e)


# Extra top-level slash aliases (easier to find in Discord's command list)
@tree.command(name="tts_join", description="TTS: join your voice channel")
async def slash_tts_join(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await do_tts_join(interaction.guild, interaction.user, _slash_send(interaction, ephemeral=True))


@tree.command(name="tts_leave", description="TTS: leave voice channel")
async def slash_tts_leave(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await do_tts_leave(interaction.guild, _slash_send(interaction, ephemeral=True))


@tree.command(name="tts_say", description="TTS: speak text in voice")
@app_commands.describe(text="What Beacon should say")
async def slash_tts_say(interaction: discord.Interaction, text: str):
    await interaction.response.defer()
    await do_tts_say(interaction.guild, interaction.user, text, _slash_send(interaction))


# ============================================================
# MUSIC — YouTube URL or search (yt-dlp + ffmpeg)
# pip install yt-dlp --break-system-packages
# ============================================================

YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "noplaylist": True,
    "skip_download": True,
}

FFMPEG_BEFORE = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin"
FFMPEG_OPTIONS = "-vn"


class GuildMusicPlayer:
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.queue: list[dict] = []
        self.current: dict | None = None
        self.text_channel_id: int | None = None
        self.manual_stop = False

    def clear(self):
        self.queue.clear()
        self.current = None


music_players: dict[int, GuildMusicPlayer] = {}


def get_music_player(guild_id: int) -> GuildMusicPlayer:
    if guild_id not in music_players:
        music_players[guild_id] = GuildMusicPlayer(guild_id)
    return music_players[guild_id]


def _looks_like_url(text: str) -> bool:
    t = (text or "").strip().lower()
    return (
        t.startswith("http://")
        or t.startswith("https://")
        or "youtube.com/" in t
        or "youtu.be/" in t
    )


async def youtube_resolve(query: str) -> dict:
    """Resolve a YouTube URL or search query to track metadata."""
    if yt_dlp is None:
        raise RuntimeError(
            "yt-dlp is not installed. Run: pip install yt-dlp --break-system-packages"
        )

    query = (query or "").strip()
    if not query:
        raise ValueError("empty query")

    search = query if _looks_like_url(query) else f"ytsearch1:{query}"

    def _extract():
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(search, download=False)
            if info is None:
                raise RuntimeError("No results.")
            if "entries" in info:
                entries = [e for e in info["entries"] if e]
                if not entries:
                    raise RuntimeError("No YouTube results for that search.")
                info = entries[0]
            webpage = info.get("webpage_url") or info.get("original_url") or query
            if not info.get("url") and webpage:
                info2 = ydl.extract_info(webpage, download=False)
                if info2:
                    info = info2
                    webpage = info.get("webpage_url") or webpage
            if not info.get("url"):
                raise RuntimeError("Couldn't get an audio stream URL.")
            return {
                "title": info.get("title") or "Unknown",
                "webpage_url": webpage,
                "duration": info.get("duration"),
                "thumbnail": info.get("thumbnail"),
                "uploader": info.get("uploader") or info.get("channel") or "",
            }

    return await asyncio.to_thread(_extract)


async def youtube_refresh_stream(webpage_url: str) -> str:
    """YouTube stream links expire — refresh before each play."""

    def _extract():
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(webpage_url, download=False)
            if info is None:
                raise RuntimeError("Failed to refresh stream.")
            if "entries" in info:
                info = next((e for e in info["entries"] if e), None)
            if not info or not info.get("url"):
                raise RuntimeError("Failed to refresh stream URL.")
            return info["url"]

    return await asyncio.to_thread(_extract)


def format_track_duration(seconds):
    if seconds is None:
        return "?:??"
    try:
        seconds = int(seconds)
    except Exception:
        return "?:??"
    m, s = divmod(max(0, seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


async def ensure_voice_for_music(guild, author):
    if guild is None:
        raise RuntimeError("Music only works in a server.")
    if not isinstance(author, discord.Member):
        raise RuntimeError("Couldn't resolve your voice channel.")
    vc = get_guild_voice(guild)
    if vc and vc.is_connected():
        if author.voice and author.voice.channel and vc.channel.id != author.voice.channel.id:
            await vc.move_to(author.voice.channel)
        return vc
    if author.voice is None or author.voice.channel is None:
        raise RuntimeError("Join a voice channel first.")
    return await author.voice.channel.connect()


async def music_play_current(guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        return
    player = get_music_player(guild_id)
    vc = get_guild_voice(guild)
    if vc is None or not vc.is_connected():
        player.clear()
        return

    if not player.queue:
        player.current = None
        return

    player.manual_stop = False
    track = player.queue.pop(0)
    player.current = track

    try:
        stream = await youtube_refresh_stream(track["webpage_url"])
    except Exception as e:
        ch = bot.get_channel(player.text_channel_id) if player.text_channel_id else None
        if ch:
            try:
                await ch.send(f"❌ Couldn't play **{track.get('title', 'track')}**: `{e}`")
            except Exception:
                pass
        await music_play_current(guild_id)
        return

    def _after(error):
        async def _continue():
            if error:
                print(f"Music play error guild={guild_id}: {error}")
            p = get_music_player(guild_id)
            if p.manual_stop:
                p.manual_stop = False
                return
            await music_play_current(guild_id)

        try:
            asyncio.run_coroutine_threadsafe(_continue(), bot.loop)
        except Exception as exc:
            print("music after schedule failed:", exc)

    try:
        if vc.is_playing() or vc.is_paused():
            player.manual_stop = True
            vc.stop()
            await asyncio.sleep(0.15)
            player.manual_stop = False

        source = discord.FFmpegPCMAudio(
            stream,
            before_options=FFMPEG_BEFORE,
            options=FFMPEG_OPTIONS,
        )
        vc.play(source, after=_after)
    except Exception as e:
        ch = bot.get_channel(player.text_channel_id) if player.text_channel_id else None
        if ch:
            try:
                await ch.send(f"❌ FFmpeg play failed: `{e}`")
            except Exception:
                pass
        await music_play_current(guild_id)
        return

    ch = bot.get_channel(player.text_channel_id) if player.text_channel_id else None
    if ch:
        embed = discord.Embed(
            title="🎵 Now playing",
            description=f"**[{track['title']}]({track['webpage_url']})**",
            color=0xED4245,
        )
        if track.get("thumbnail"):
            embed.set_thumbnail(url=track["thumbnail"])
        embed.add_field(
            name="Duration",
            value=format_track_duration(track.get("duration")),
            inline=True,
        )
        if track.get("requester"):
            embed.add_field(
                name="Requested by",
                value=f"<@{track['requester']}>",
                inline=True,
            )
        try:
            await ch.send(embed=embed)
        except Exception:
            pass


async def do_music_play(guild, author, channel, query, send):
    if yt_dlp is None:
        return await send(
            "Music needs yt-dlp. Run: `pip install yt-dlp --break-system-packages`"
        )
    query = (query or "").strip()
    if not query:
        return await send("Usage: `*play <YouTube URL or search>` / `/play query:`")

    try:
        await ensure_voice_for_music(guild, author)
    except Exception as e:
        return await send(f"❌ {e}")

    await send(f"🔎 Looking up: `{query[:100]}`…")
    try:
        info = await youtube_resolve(query)
    except Exception as e:
        return await send(f"❌ Search/URL failed: `{e}`")

    player = get_music_player(guild.id)
    player.text_channel_id = channel.id if channel else player.text_channel_id
    track = {
        "title": info["title"],
        "webpage_url": info["webpage_url"],
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader"),
        "requester": author.id,
    }
    player.queue.append(track)

    vc = get_guild_voice(guild)
    idle = (
        vc
        and vc.is_connected()
        and not vc.is_playing()
        and not vc.is_paused()
        and player.current is None
    )
    if idle:
        await music_play_current(guild.id)
        return

    pos = len(player.queue)
    await send(
        f"✅ Queued **{track['title']}** "
        f"(`{format_track_duration(track.get('duration'))}`) — position **{pos}**"
    )


async def do_music_skip(guild, send):
    vc = get_guild_voice(guild) if guild else None
    if guild is None or not vc or not vc.is_connected():
        return await send("Nothing is playing.")
    player = get_music_player(guild.id)
    if not player.current and not vc.is_playing() and not vc.is_paused():
        return await send("Nothing is playing.")
    title = player.current.get("title") if player.current else "track"
    # after-callback advances queue
    player.manual_stop = False
    vc.stop()
    await send(f"⏭️ Skipped **{title}**.")


async def do_music_stop(guild, send):
    if guild is None:
        return await send("Not in a server.")
    player = get_music_player(guild.id)
    player.clear()
    player.manual_stop = True
    vc = get_guild_voice(guild)
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
    await send("⏹️ Stopped and cleared the queue.")


async def do_music_pause(guild, send):
    vc = get_guild_voice(guild) if guild else None
    if not vc or not vc.is_playing():
        return await send("Nothing is playing.")
    vc.pause()
    await send("⏸️ Paused.")


async def do_music_resume(guild, send):
    vc = get_guild_voice(guild) if guild else None
    if not vc or not vc.is_paused():
        return await send("Nothing is paused.")
    vc.resume()
    await send("▶️ Resumed.")


async def do_music_queue(guild, send):
    if guild is None:
        return await send("Not in a server.")
    player = get_music_player(guild.id)
    lines = []
    if player.current:
        lines.append(
            f"**Now:** [{player.current['title']}]({player.current['webpage_url']})"
        )
    if not player.queue and not player.current:
        return await send("Queue is empty. `*play <url or search>`")
    for i, t in enumerate(player.queue[:15], 1):
        lines.append(
            f"**{i}.** {t['title']} (`{format_track_duration(t.get('duration'))}`)"
        )
    if len(player.queue) > 15:
        lines.append(f"…and {len(player.queue) - 15} more")
    embed = discord.Embed(
        title="🎶 Queue", description="\n".join(lines), color=0x5865F2
    )
    await send(embed=embed)


async def do_music_np(guild, send):
    if guild is None:
        return await send("Not in a server.")
    player = get_music_player(guild.id)
    if not player.current:
        return await send("Nothing is playing.")
    t = player.current
    embed = discord.Embed(
        title="🎵 Now playing",
        description=f"**[{t['title']}]({t['webpage_url']})**",
        color=0xED4245,
    )
    if t.get("thumbnail"):
        embed.set_thumbnail(url=t["thumbnail"])
    embed.add_field(
        name="Duration",
        value=format_track_duration(t.get("duration")),
        inline=True,
    )
    if t.get("requester"):
        embed.add_field(
            name="Requested by", value=f"<@{t['requester']}>", inline=True
        )
    await send(embed=embed)


@bot.command(name="play", aliases=["p", "yt"])
async def play_cmd(ctx, *, query: str = None):
    await do_music_play(ctx.guild, ctx.author, ctx.channel, query, ctx.send)


@tree.command(name="play", description="Play a YouTube URL or search on YouTube")
@app_commands.describe(query="YouTube URL or search terms")
async def slash_play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    await do_music_play(
        interaction.guild,
        interaction.user,
        interaction.channel,
        query,
        _slash_send(interaction),
    )


@bot.command(name="skip", aliases=["next"])
async def skip_cmd(ctx):
    await do_music_skip(ctx.guild, ctx.send)


@tree.command(name="skip", description="Skip the current song")
async def slash_skip(interaction: discord.Interaction):
    await interaction.response.defer()
    await do_music_skip(interaction.guild, _slash_send(interaction))


@bot.command(name="stop")
async def stop_cmd(ctx):
    await do_music_stop(ctx.guild, ctx.send)


@tree.command(name="stop", description="Stop music and clear the queue")
async def slash_stop(interaction: discord.Interaction):
    await interaction.response.defer()
    await do_music_stop(interaction.guild, _slash_send(interaction))


@bot.command(name="pause")
async def pause_cmd(ctx):
    await do_music_pause(ctx.guild, ctx.send)


@tree.command(name="pause", description="Pause the current song")
async def slash_pause(interaction: discord.Interaction):
    await interaction.response.defer()
    await do_music_pause(interaction.guild, _slash_send(interaction))


@bot.command(name="resume", aliases=["unpause"])
async def resume_cmd(ctx):
    await do_music_resume(ctx.guild, ctx.send)


@tree.command(name="resume", description="Resume paused music")
async def slash_resume(interaction: discord.Interaction):
    await interaction.response.defer()
    await do_music_resume(interaction.guild, _slash_send(interaction))


@bot.command(name="queue", aliases=["q"])
async def queue_cmd(ctx):
    await do_music_queue(ctx.guild, ctx.send)


@tree.command(name="queue", description="Show the music queue")
async def slash_queue(interaction: discord.Interaction):
    await interaction.response.defer()
    await do_music_queue(interaction.guild, _slash_send(interaction))


@bot.command(name="np", aliases=["nowplaying", "now"])
async def np_cmd(ctx):
    await do_music_np(ctx.guild, ctx.send)


@tree.command(name="np", description="Show the song currently playing")
async def slash_np(interaction: discord.Interaction):
    await interaction.response.defer()
    await do_music_np(interaction.guild, _slash_send(interaction))


# ============================================================
# ERRORS / START
# ============================================================


@bot.event
async def on_command_error(ctx, error):
    await ctx.send(f"Error: `{error}`")


@tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(f"Error: `{error}`", ephemeral=True)
        else:
            await interaction.response.send_message(f"Error: `{error}`", ephemeral=True)
    except:
        pass


import logging
logging.getLogger("discord.voice_state").setLevel(logging.WARNING)
logging.getLogger("discord.player").setLevel(logging.WARNING)

bot.run(TOKEN or os.environ.get("DISCORD_TOKEN", ""))
