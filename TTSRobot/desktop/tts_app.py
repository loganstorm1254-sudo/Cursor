"""
TTS Robot for Windows — control panel for the Discord robot voice engine.

Stdlib HTTP UI + bot_tts.py. Double-click TTSRobot.exe to open this in your browser.
Paste your Discord bot token, hit Start, then use !tts in Discord voice channels.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import shutil
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("TTS_ROBOT_ROOT") or os.path.dirname(HERE)
for candidate in (HERE, ROOT, os.path.join(HERE, "..", ".."), os.path.dirname(HERE)):
    if os.path.exists(os.path.join(candidate, "bot_tts.py")):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
        break

FFMPEG_DIR = Path(ROOT) / "ffmpeg"
FFMPEG_EXE = FFMPEG_DIR / "ffmpeg.exe"
FFMPEG_GZ = FFMPEG_DIR / "ffmpeg-win64.gz"
FFMPEG_URL = (
    "https://github.com/eugeneware/ffmpeg-static/releases/download/"
    "b6.0/ffmpeg-win32-x64.gz"
)

# Prefer bundled ffmpeg next to the pack root
if FFMPEG_DIR.is_dir():
    os.environ["PATH"] = str(FFMPEG_DIR) + os.pathsep + os.environ.get("PATH", "")

import bot_tts  # noqa: E402

CONFIG_PATH = Path(ROOT) / "tts_robot_config.json"
PREVIEW_DIR = Path(ROOT) / "preview_cache"

STATE = {
    "running": False,
    "starting": False,
    "bot_user": None,
    "bot_id": None,
    "invite": None,
    "error": None,
    "token_saved": False,
    "preset": bot_tts.DEFAULT_PRESET,
    "speaker": "guy",
    "rate": bot_tts.DEFAULT_RATE,
    "logs": deque(maxlen=250),
    "started_at": None,
}

_bot_thread: threading.Thread | None = None
_log_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with _log_lock:
        STATE["logs"].append(line)
    print(line, flush=True)


def ensure_ffmpeg() -> str:
    """Return path to ffmpeg.exe, extracting or downloading if needed."""
    if FFMPEG_EXE.exists() and FFMPEG_EXE.stat().st_size > 1_000_000:
        os.environ["PATH"] = str(FFMPEG_DIR) + os.pathsep + os.environ.get("PATH", "")
        return str(FFMPEG_EXE)
    which = shutil.which("ffmpeg")
    if which:
        return which

    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
    gz_path = FFMPEG_GZ
    if not gz_path.exists() or gz_path.stat().st_size < 1_000_000:
        log("Downloading ffmpeg for Windows (one-time, ~28 MB)…")
        urllib.request.urlretrieve(FFMPEG_URL, gz_path)  # noqa: S310
    log("Extracting ffmpeg.exe…")
    with gzip.open(gz_path, "rb") as src, open(FFMPEG_EXE, "wb") as dst:
        shutil.copyfileobj(src, dst)
    if not FFMPEG_EXE.exists() or FFMPEG_EXE.stat().st_size < 1_000_000:
        raise RuntimeError("Failed to prepare ffmpeg.exe")
    os.environ["PATH"] = str(FFMPEG_DIR) + os.pathsep + os.environ.get("PATH", "")
    log(f"ffmpeg ready ({FFMPEG_EXE.stat().st_size // (1024*1024)} MB)")
    return str(FFMPEG_EXE)


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception as exc:
        log(f"Could not save config: {exc}")


def apply_settings(preset: str | None = None, speaker: str | None = None, rate: float | None = None) -> None:
    if preset:
        STATE["preset"] = preset
    if speaker:
        STATE["speaker"] = speaker
    if rate is not None:
        STATE["rate"] = float(rate)
    voice = bot_tts.SPEAKERS.get(STATE["speaker"], STATE["speaker"])
    bot_tts.set_engine_defaults(preset=STATE["preset"], speaker=voice, rate=STATE["rate"])
    cfg = load_config()
    cfg["preset"] = STATE["preset"]
    cfg["speaker"] = STATE["speaker"]
    cfg["rate"] = STATE["rate"]
    save_config(cfg)


def persist_token(token: str) -> None:
    cfg = load_config()
    cfg["token"] = token
    cfg["preset"] = STATE["preset"]
    cfg["speaker"] = STATE["speaker"]
    cfg["rate"] = STATE["rate"]
    save_config(cfg)
    STATE["token_saved"] = True


def clear_token() -> None:
    cfg = load_config()
    cfg.pop("token", None)
    save_config(cfg)
    STATE["token_saved"] = False


def _on_ready_hook() -> None:
    user = bot_tts.bot.user
    if user:
        STATE["bot_user"] = str(user)
        STATE["bot_id"] = user.id
        STATE["invite"] = bot_tts.invite_url(user.id)
        STATE["running"] = True
        STATE["starting"] = False
        STATE["error"] = None
        STATE["started_at"] = time.time()
        log(f"Online as {user} — invite link ready in the control panel.")


# Patch on_ready to also update Windows UI state
_orig_on_ready = bot_tts.on_ready


@bot_tts.bot.event
async def on_ready():
    await _orig_on_ready()
    _on_ready_hook()


def start_bot(token: str) -> dict:
    global _bot_thread
    token = (token or "").strip() or str(load_config().get("token") or "")
    if not token:
        return {"ok": False, "error": "Paste your Discord bot token first."}
    if STATE["running"] or STATE["starting"]:
        return {"ok": False, "error": "Bot is already running."}
    if _bot_thread and _bot_thread.is_alive():
        return {"ok": False, "error": "Bot thread still shutting down — wait a second."}
    if getattr(bot_tts.bot, "is_closed", lambda: False)():
        return {
            "ok": False,
            "error": "Bot was stopped. Close this window and double-click TTSRobot.exe again to restart.",
        }

    try:
        ensure_ffmpeg()
        bot_tts.require_ffmpeg()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    apply_settings()
    persist_token(token)
    STATE["starting"] = True
    STATE["error"] = None
    STATE["bot_user"] = None
    STATE["invite"] = None
    log("Starting Discord bot…")

    def runner() -> None:
        try:
            bot_tts.bot.run(token, reconnect=True)
        except Exception as exc:
            STATE["error"] = f"{type(exc).__name__}: {exc}"
            log(f"Bot stopped with error: {STATE['error']}")
            traceback.print_exc()
        finally:
            STATE["running"] = False
            STATE["starting"] = False
            STATE["bot_user"] = None
            log("Bot offline.")

    _bot_thread = threading.Thread(target=runner, name="discord-tts-bot", daemon=True)
    _bot_thread.start()
    return {"ok": True, "message": "Starting… watch the log panel."}


def stop_bot() -> dict:
    if not STATE["running"] and not STATE["starting"]:
        return {"ok": False, "error": "Bot is not running."}
    log("Stopping bot…")
    try:
        loop = getattr(bot_tts.bot, "loop", None)
        if loop and loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(bot_tts.bot.close(), loop)
            fut.result(timeout=15)
        else:
            # force-ish: close may no-op if not started yet
            pass
    except Exception as exc:
        log(f"Stop note: {exc}")
    STATE["running"] = False
    STATE["starting"] = False
    return {"ok": True, "message": "Stop requested."}


async def _preview_async(text: str, preset: str, speaker: str, rate: float) -> Path:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    voice = bot_tts.SPEAKERS.get(speaker, speaker)
    clean = bot_tts.sanitize_text(text) or "Hello. I am a robot voice engine."
    path = await bot_tts.make_speech_file(clean, voice, rate, preset)
    dest = PREVIEW_DIR / f"preview_{preset}.wav"
    dest.write_bytes(path.read_bytes())
    path.unlink(missing_ok=True)
    return dest


def make_preview(text: str, preset: str, speaker: str, rate: float) -> dict:
    try:
        ensure_ffmpeg()
        bot_tts.require_ffmpeg()
        dest = asyncio.run(_preview_async(text, preset, speaker, rate))
        log(f"Preview ready: {dest.name}")
        return {"ok": True, "url": f"/preview/{dest.name}"}
    except Exception as exc:
        traceback.print_exc()
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def public_status() -> dict:
    with _log_lock:
        logs = list(STATE["logs"])[-80:]
    return {
        "running": STATE["running"],
        "starting": STATE["starting"],
        "bot_user": STATE["bot_user"],
        "bot_id": STATE["bot_id"],
        "invite": STATE["invite"],
        "error": STATE["error"],
        "token_saved": STATE["token_saved"] or bool(load_config().get("token")),
        "preset": STATE["preset"],
        "speaker": STATE["speaker"],
        "rate": STATE["rate"],
        "presets": {k: v["label"] for k, v in bot_tts.PRESETS.items()},
        "speakers": bot_tts.SPEAKERS,
        "ffmpeg": bool(shutil.which("ffmpeg") or FFMPEG_EXE.exists() or FFMPEG_GZ.exists()),
        "logs": logs,
    }


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>TTS Robot</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet"/>
<style>
  :root {
    --bg0: #0a1214;
    --bg1: #102024;
    --bg2: #163038;
    --line: #2a4a52;
    --text: #e4f4f2;
    --muted: #7fa3a8;
    --accent: #2ee6c2;
    --accent2: #149e86;
    --warn: #e6b84d;
    --danger: #ef6b6b;
    --ok: #3dce8e;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    color: var(--text);
    background:
      radial-gradient(900px 500px at 0% 0%, rgba(46,230,194,0.14), transparent 55%),
      radial-gradient(800px 480px at 100% 10%, rgba(20,120,140,0.22), transparent 50%),
      linear-gradient(165deg, #0c181c 0%, #0a1214 45%, #0e1a1c 100%);
    background-attachment: fixed;
  }
  .wrap { max-width: 920px; margin: 0 auto; padding: 28px 20px 40px; }
  header { margin-bottom: 22px; animation: rise 0.7s ease-out both; }
  .brand {
    font-family: Orbitron, sans-serif;
    font-size: clamp(2rem, 5vw, 2.8rem);
    font-weight: 700;
    letter-spacing: 0.04em;
    line-height: 1.1;
    margin: 0;
  }
  .brand em {
    font-style: normal;
    color: var(--accent);
    text-shadow: 0 0 24px rgba(46,230,194,0.35);
  }
  .tag {
    margin: 10px 0 0;
    color: var(--muted);
    font-size: 1.05rem;
    max-width: 36rem;
  }
  .panel {
    background: linear-gradient(180deg, rgba(16,32,36,0.92), rgba(10,18,20,0.95));
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 22px;
    margin-bottom: 16px;
    animation: rise 0.75s ease-out both;
  }
  .panel:nth-child(3) { animation-delay: 0.08s; }
  .panel:nth-child(4) { animation-delay: 0.16s; }
  .panel:nth-child(5) { animation-delay: 0.24s; }
  h2 {
    font-family: Orbitron, sans-serif;
    font-size: 0.85rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--accent);
    margin: 0 0 14px;
  }
  label { display: block; color: var(--muted); font-size: 0.9rem; margin-bottom: 6px; }
  input[type=password], input[type=text], select, textarea {
    width: 100%;
    background: var(--bg0);
    border: 1px solid var(--line);
    color: var(--text);
    border-radius: 3px;
    padding: 11px 12px;
    font: inherit;
    outline: none;
  }
  input:focus, select:focus, textarea:focus { border-color: var(--accent); }
  .row { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; align-items: center; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
  @media (max-width: 700px) { .grid { grid-template-columns: 1fr; } }
  button {
    font-family: Orbitron, sans-serif;
    font-size: 0.78rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    border: 0;
    border-radius: 3px;
    padding: 12px 16px;
    cursor: pointer;
    color: #041412;
    background: linear-gradient(180deg, var(--accent), var(--accent2));
    transition: transform 0.15s ease, filter 0.15s ease;
  }
  button:hover { filter: brightness(1.08); transform: translateY(-1px); }
  button:disabled { opacity: 0.45; cursor: wait; transform: none; }
  button.ghost {
    color: var(--text);
    background: transparent;
    border: 1px solid var(--line);
  }
  button.danger {
    color: #2a0c0c;
    background: linear-gradient(180deg, #f08a8a, #c44d4d);
  }
  .status {
    display: inline-flex; align-items: center; gap: 8px;
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.9rem;
    color: var(--muted);
  }
  .dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--muted);
    box-shadow: 0 0 0 0 rgba(46,230,194,0.4);
  }
  .dot.on {
    background: var(--ok);
    animation: pulse 1.6s ease-out infinite;
  }
  .dot.boot { background: var(--warn); }
  .dot.err { background: var(--danger); }
  #log {
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.82rem;
    background: #060c0e;
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 12px;
    height: 220px;
    overflow: auto;
    white-space: pre-wrap;
    color: #b7d4d0;
  }
  .hint { color: var(--muted); font-size: 0.9rem; line-height: 1.45; margin: 10px 0 0; }
  a { color: var(--accent); }
  #err { color: var(--danger); min-height: 1.2em; margin-top: 8px; font-size: 0.92rem; }
  audio { width: 100%; margin-top: 12px; }
  @keyframes rise {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: none; }
  }
  @keyframes pulse {
    0% { box-shadow: 0 0 0 0 rgba(61,206,142,0.55); }
    70% { box-shadow: 0 0 0 10px rgba(61,206,142,0); }
    100% { box-shadow: 0 0 0 0 rgba(61,206,142,0); }
  }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1 class="brand">TTS <em>Robot</em></h1>
    <p class="tag">Discord robot voice engine for Windows — paste a bot token, start, then <code>!tts</code> in a voice channel.</p>
  </header>

  <section class="panel">
    <h2>Engine</h2>
    <div class="row" style="justify-content:space-between">
      <div class="status"><span class="dot" id="dot"></span><span id="statusText">offline</span></div>
      <div class="status" id="ffmpegLine">ffmpeg: …</div>
    </div>
    <label for="token" style="margin-top:16px">Discord bot token</label>
    <input id="token" type="password" placeholder="Paste token from Discord Developer Portal" autocomplete="off"/>
    <div class="row">
      <button id="startBtn" onclick="startBot()">Start bot</button>
      <button class="danger" id="stopBtn" onclick="stopBot()" disabled>Stop</button>
      <button class="ghost" onclick="forgetToken()">Forget token</button>
    </div>
    <div id="err"></div>
    <p class="hint">
      Enable <b>Message Content Intent</b> on the bot. Invite with Connect + Speak.
      <span id="inviteWrap" style="display:none"> · <a id="invite" href="#" target="_blank" rel="noopener">Invite this bot</a></span>
    </p>
  </section>

  <section class="panel">
    <h2>Voice</h2>
    <div class="grid">
      <div>
        <label for="preset">Preset</label>
        <select id="preset"></select>
      </div>
      <div>
        <label for="speaker">Speaker</label>
        <select id="speaker"></select>
      </div>
      <div>
        <label for="rate">Speed</label>
        <input id="rate" type="text" value="1.0"/>
      </div>
    </div>
    <div class="row">
      <button class="ghost" onclick="saveVoice()">Save voice settings</button>
    </div>
    <label for="previewText" style="margin-top:16px">Preview (no Discord needed)</label>
    <input id="previewText" type="text" value="Hello. I am a robot voice engine for Discord."/>
    <div class="row">
      <button class="ghost" onclick="preview()">Generate preview</button>
    </div>
    <audio id="player" controls></audio>
  </section>

  <section class="panel">
    <h2>Log</h2>
    <div id="log"></div>
    <p class="hint">In Discord: join a VC → <code>!tts hello crew</code> · <code>!voice dalek</code> · <code>!auto on</code> · <code>!ttshelp</code></p>
  </section>
</div>
<script>
let busy = false;
function $(id){ return document.getElementById(id); }
function setErr(m){ $('err').textContent = m || ''; }

async function api(path, body){
  const r = await fetch(path, {
    method: body ? 'POST' : 'GET',
    headers: body ? {'Content-Type':'application/json'} : undefined,
    body: body ? JSON.stringify(body) : undefined
  });
  return r.json();
}

function fillSelects(st){
  const p = $('preset');
  const s = $('speaker');
  if (!p.options.length){
    for (const [k,label] of Object.entries(st.presets||{})){
      const o = document.createElement('option'); o.value=k; o.textContent=k+' — '+label; p.appendChild(o);
    }
    for (const [k,v] of Object.entries(st.speakers||{})){
      const o = document.createElement('option'); o.value=k; o.textContent=k+' → '+v; s.appendChild(o);
    }
  }
  p.value = st.preset; s.value = st.speaker; $('rate').value = st.rate;
}

function paint(st){
  fillSelects(st);
  const dot = $('dot');
  dot.className = 'dot';
  let text = 'offline';
  if (st.starting){ dot.classList.add('boot'); text = 'starting…'; }
  else if (st.running){ dot.classList.add('on'); text = 'online as ' + (st.bot_user||'bot'); }
  else if (st.error){ dot.classList.add('err'); text = 'error'; }
  $('statusText').textContent = text;
  $('ffmpegLine').textContent = st.ffmpeg ? 'ffmpeg: ready' : 'ffmpeg: MISSING';
  $('startBtn').disabled = st.running || st.starting || busy;
  $('stopBtn').disabled = !(st.running || st.starting) || busy;
  if (st.invite){
    $('inviteWrap').style.display = '';
    $('invite').href = st.invite;
  }
  if (st.error) setErr(st.error);
  $('log').textContent = (st.logs||[]).join('\n');
  $('log').scrollTop = $('log').scrollHeight;
}

async function refresh(){
  try { paint(await api('/api/status')); }
  catch(e){ setErr(e.message); }
}

async function startBot(){
  setErr(''); busy = true;
  try {
    const j = await api('/api/start', {token: $('token').value.trim()});
    if (!j.ok) setErr(j.error||'Start failed');
  } finally { busy=false; refresh(); }
}
async function stopBot(){
  setErr(''); busy=true;
  try {
    const j = await api('/api/stop', {});
    if (!j.ok) setErr(j.error||'Stop failed');
  } finally { busy=false; refresh(); }
}
async function forgetToken(){
  await api('/api/forget', {});
  $('token').value = '';
  setErr('Saved token cleared.');
  refresh();
}
async function saveVoice(){
  setErr('');
  const j = await api('/api/settings', {
    preset: $('preset').value,
    speaker: $('speaker').value,
    rate: parseFloat($('rate').value||'1')
  });
  if (!j.ok) setErr(j.error||'Save failed');
  refresh();
}
async function preview(){
  setErr(''); busy=true;
  try {
    const j = await api('/api/preview', {
      text: $('previewText').value,
      preset: $('preset').value,
      speaker: $('speaker').value,
      rate: parseFloat($('rate').value||'1')
    });
    if (!j.ok){ setErr(j.error||'Preview failed'); return; }
    $('player').src = j.url + '?t=' + Date.now();
    $('player').play().catch(()=>{});
  } finally { busy=false; refresh(); }
}
refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # keep console quieter; important events go through log()
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _json(self, code: int, obj: dict):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self):
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            return self._html()
        if parsed.path == "/api/status":
            return self._json(200, public_status())
        if parsed.path.startswith("/preview/"):
            name = os.path.basename(parsed.path)
            path = PREVIEW_DIR / name
            if not path.exists() or not name.endswith(".wav"):
                return self.send_error(404)
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(404)

    def do_POST(self):
        data = self._read_json()
        path = urlparse(self.path).path
        try:
            if path == "/api/start":
                return self._json(200, start_bot(str(data.get("token") or "")))
            if path == "/api/stop":
                return self._json(200, stop_bot())
            if path == "/api/forget":
                clear_token()
                return self._json(200, {"ok": True})
            if path == "/api/settings":
                try:
                    apply_settings(
                        preset=str(data.get("preset") or STATE["preset"]),
                        speaker=str(data.get("speaker") or STATE["speaker"]),
                        rate=float(data.get("rate") if data.get("rate") is not None else STATE["rate"]),
                    )
                    # rewrite full config preserving token
                    cfg = load_config()
                    cfg.update({
                        "preset": STATE["preset"],
                        "speaker": STATE["speaker"],
                        "rate": STATE["rate"],
                    })
                    save_config(cfg)
                    log(f"Voice settings: {STATE['preset']} / {STATE['speaker']} @ {STATE['rate']}")
                    return self._json(200, {"ok": True})
                except Exception as exc:
                    return self._json(200, {"ok": False, "error": str(exc)})
            if path == "/api/preview":
                return self._json(
                    200,
                    make_preview(
                        str(data.get("text") or ""),
                        str(data.get("preset") or STATE["preset"]),
                        str(data.get("speaker") or STATE["speaker"]),
                        float(data.get("rate") if data.get("rate") is not None else STATE["rate"]),
                    ),
                )
        except Exception as exc:
            traceback.print_exc()
            return self._json(200, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        self.send_error(404)


def bootstrap_from_disk() -> None:
    cfg = load_config()
    if cfg.get("preset"):
        STATE["preset"] = cfg["preset"]
    if cfg.get("speaker"):
        STATE["speaker"] = cfg["speaker"]
    if cfg.get("rate") is not None:
        STATE["rate"] = float(cfg["rate"])
    STATE["token_saved"] = bool(cfg.get("token"))
    try:
        apply_settings()
    except Exception:
        pass
    try:
        if FFMPEG_EXE.exists() or FFMPEG_GZ.exists() or shutil.which("ffmpeg"):
            ensure_ffmpeg()
            log("ffmpeg ready.")
        else:
            log("ffmpeg will download on first Start / Preview.")
    except Exception as exc:
        log(f"ffmpeg setup: {exc}")


def main() -> None:
    bootstrap_from_disk()
    port = int(os.environ.get("TTS_ROBOT_PORT", "8777"))
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = httpd.server_address[1]

    url = f"http://127.0.0.1:{port}/"
    log(f"TTS Robot control panel: {url}")
    log("Leave this window open. Close it to quit.")
    if load_config().get("token"):
        log("Saved token found — click Start to use it (paste optional).")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log("Bye!")
        try:
            stop_bot()
        except Exception:
            pass


if __name__ == "__main__":
    main()
