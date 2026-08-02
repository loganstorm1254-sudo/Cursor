#!/usr/bin/env python3
"""
Reel — stream MKVs and MP4s from your Movies folder over Wi‑Fi.

Phone: open in VLC (Network stream) for full audio.
Browser: optional ffmpeg remux (H.264 + AAC) when ffmpeg is installed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mkv", ".m4v", ".webm", ".mov"}
MIME = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
}

STATE: dict = {
    "movies_dir": None,
    "index": {},
    "port": 8080,
    "ffmpeg": None,
    "vlc": None,
}


def default_movies_dir() -> Path:
    env = os.environ.get("REEL_MOVIES_DIR")
    if env:
        return Path(env)
    for candidate in (
        Path(r"D:\Movies"),
        Path(r"D:\movies"),
        Path.home() / "Movies",
        Path.home() / "Videos",
        Path("/tmp/test-movies"),
    ):
        if candidate.is_dir():
            return candidate
    return Path(r"D:\Movies")


def find_ffmpeg() -> str | None:
    env = os.environ.get("REEL_FFMPEG") or os.environ.get("FFMPEG")
    if env and Path(env).is_file():
        return env
    which = shutil.which("ffmpeg")
    if which:
        return which
    for candidate in (
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
        Path.home() / "scoop" / "apps" / "ffmpeg" / "current" / "bin" / "ffmpeg.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def find_vlc() -> str | None:
    env = os.environ.get("REEL_VLC") or os.environ.get("VLC")
    if env and Path(env).is_file():
        return env
    which = shutil.which("vlc") or shutil.which("vlc.exe")
    if which:
        return which
    for candidate in (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "VideoLAN" / "VLC" / "vlc.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "VideoLAN" / "VLC" / "vlc.exe",
        Path("/usr/bin/vlc"),
        Path("/usr/bin/cvlc"),
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def lan_ips() -> list[str]:
    found: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            primary = s.getsockname()[0]
            if primary and not primary.startswith("127."):
                found.append(primary)
    except OSError:
        pass
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    # Enumerate interfaces (best effort)
    try:
        for info in socket.getaddrinfo(socket.getfqdn(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    if not found:
        found.append("127.0.0.1")
    return found


def movie_id(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode("utf-8", "replace")).hexdigest()[:16]


def pretty_title(path: Path) -> str:
    name = path.stem
    name = re.sub(r"[._]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or path.name


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def scan_movies(root: Path) -> dict:
    index = {}
    if not root.is_dir():
        return index
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if not d.startswith(".") and d.lower() not in {"@eadir", "system volume information"}
        ]
        for name in filenames:
            path = Path(dirpath) / name
            ext = path.suffix.lower()
            if ext not in VIDEO_EXTS:
                continue
            try:
                st = path.stat()
            except OSError:
                continue
            mid = movie_id(path)
            try:
                rel = str(path.relative_to(root))
            except ValueError:
                rel = path.name
            index[mid] = {
                "id": mid,
                "title": pretty_title(path),
                "path": str(path),
                "rel": rel.replace("\\", "/"),
                "folder": str(Path(rel).parent).replace("\\", "/") if Path(rel).parent != Path(".") else "",
                "size": st.st_size,
                "size_label": human_size(st.st_size),
                "ext": ext.lstrip(".").upper(),
                "mtime": int(st.st_mtime),
            }
    return dict(sorted(index.items(), key=lambda kv: kv[1]["title"].lower()))


def refresh_index() -> None:
    STATE["index"] = scan_movies(STATE["movies_dir"])


def resolve_movie(mid: str) -> dict | None:
    meta = STATE["index"].get(mid)
    if not meta:
        refresh_index()
        meta = STATE["index"].get(mid)
    if not meta:
        return None
    path = Path(meta["path"])
    if not path.is_file():
        return None
    try:
        path.resolve().relative_to(Path(STATE["movies_dir"]).resolve())
    except ValueError:
        return None
    return meta


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Reel</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Figtree:wght@400;500;600&display=swap" rel="stylesheet"/>
<style>
  :root {
    --ink: #0c0b0a;
    --panel: #161310;
    --panel2: #1e1a15;
    --line: #2f2920;
    --text: #f3ebe0;
    --muted: #a89880;
    --gold: #e0a84a;
    --gold-dim: #b07a22;
    --haze: rgba(224, 168, 74, 0.12);
    --danger: #e07060;
    --ok: #6cbc7a;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; min-height: 100%; }
  body {
    font-family: "Figtree", sans-serif;
    color: var(--text);
    background:
      radial-gradient(900px 500px at 0% 0%, #2a2114 0%, transparent 55%),
      radial-gradient(800px 480px at 100% 10%, #1a1510 0%, transparent 50%),
      linear-gradient(180deg, #100e0c 0%, var(--ink) 40%, #0a0908 100%);
    background-attachment: fixed;
  }
  .shell { position: relative; z-index: 1; max-width: 1100px; margin: 0 auto; padding: 28px 20px 80px; }
  header.hero {
    min-height: min(42vh, 340px);
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    gap: 10px;
    margin-bottom: 22px;
    animation: rise 0.7s ease-out both;
  }
  .brand {
    font-family: "Syne", sans-serif;
    font-weight: 800;
    font-size: clamp(3.4rem, 12vw, 6.5rem);
    line-height: 0.9;
    letter-spacing: -0.03em;
    margin: 0;
  }
  .brand em { font-style: normal; color: var(--gold); }
  .tagline { margin: 0; max-width: 32rem; color: var(--muted); font-size: 1.05rem; line-height: 1.45; }
  .wifi-box {
    margin-top: 8px;
    padding: 14px 16px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: linear-gradient(180deg, var(--panel2), var(--panel));
    animation: rise 0.7s ease-out 0.08s both;
  }
  .wifi-box h2 {
    margin: 0 0 8px;
    font-family: "Syne", sans-serif;
    font-size: 1rem;
    font-weight: 700;
  }
  .wifi-box ol { margin: 0; padding-left: 1.2rem; color: var(--muted); }
  .wifi-box li { margin: 4px 0; }
  .wifi-box code, .url {
    color: var(--gold);
    word-break: break-all;
    font-family: ui-monospace, Consolas, monospace;
    font-size: 0.92rem;
  }
  .meta-row {
    display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center;
    margin-top: 6px; color: var(--muted); font-size: 0.92rem;
  }
  .meta-row strong { color: var(--text); font-weight: 600; }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--gold); display: inline-block; animation: pulse 2.2s ease-in-out infinite; }
  .toolbar { display: flex; gap: 10px; flex-wrap: wrap; margin: 8px 0 22px; animation: rise 0.7s ease-out 0.1s both; }
  #q {
    flex: 1 1 220px; min-width: 0; background: var(--panel); border: 1px solid var(--line);
    color: var(--text); border-radius: 10px; padding: 12px 14px; font: inherit; outline: none;
  }
  #q:focus { border-color: var(--gold-dim); box-shadow: 0 0 0 3px var(--haze); }
  button, .btn {
    font: inherit; font-weight: 600; border: 1px solid var(--line); background: var(--panel2);
    color: var(--text); border-radius: 10px; padding: 12px 16px; cursor: pointer; text-decoration: none; display: inline-block;
  }
  button.primary, .btn.primary {
    background: linear-gradient(180deg, #f0b85a, var(--gold-dim));
    border-color: transparent; color: #1a1206;
  }
  button:hover, .btn:hover { filter: brightness(1.06); }
  .grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 14px; animation: rise 0.75s ease-out 0.18s both;
  }
  .tile {
    text-align: left; padding: 0; overflow: hidden;
    background: linear-gradient(165deg, var(--panel2), var(--panel));
    border: 1px solid var(--line); border-radius: 14px;
    transition: border-color 0.2s, transform 0.2s;
  }
  .tile:hover { border-color: #4a3d2a; transform: translateY(-2px); }
  .poster {
    height: 120px; display: flex; align-items: flex-end; padding: 14px;
    background:
      linear-gradient(180deg, transparent 20%, rgba(12,11,10,0.85) 100%),
      linear-gradient(135deg, #3a2d18 0%, #1a1510 55%, #241c12 100%);
    font-family: "Syne", sans-serif; font-weight: 700; font-size: 1.55rem;
    letter-spacing: -0.02em; line-height: 1.1;
  }
  .poster span { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .info { padding: 12px 14px 14px; }
  .info h2 { font-family: "Syne", sans-serif; font-size: 1.05rem; font-weight: 700; margin: 0 0 6px; line-height: 1.25; }
  .info p { margin: 0; color: var(--muted); font-size: 0.86rem; }
  .badge {
    display: inline-block; margin-top: 8px; font-size: 0.72rem; font-weight: 700;
    letter-spacing: 0.06em; color: var(--gold); border: 1px solid #4a3d2a;
    padding: 3px 7px; border-radius: 6px;
  }
  .empty, .error { padding: 28px 8px; color: var(--muted); text-align: center; }
  .error { color: var(--danger); }
  #player-view { display: none; }
  #player-view.show { display: block; animation: rise 0.45s ease-out both; }
  #library-view.hide { display: none; }
  .player-head {
    display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
    justify-content: space-between; margin-bottom: 16px;
  }
  .player-head h1 {
    font-family: "Syne", sans-serif; font-size: clamp(1.4rem, 4vw, 2rem);
    margin: 0; letter-spacing: -0.02em;
  }
  .actions { display: flex; flex-wrap: wrap; gap: 10px; margin: 0 0 14px; }
  video {
    width: 100%; max-height: min(70vh, 720px); background: #000;
    border-radius: 12px; border: 1px solid var(--line); outline: none;
  }
  .hint { margin-top: 12px; color: var(--muted); font-size: 0.88rem; line-height: 1.45; }
  .hint .url { display: block; margin-top: 6px; }
  .ok { color: var(--ok); }
  @keyframes rise { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes pulse { 0%, 100% { opacity: 0.45; } 50% { opacity: 1; } }
  @media (max-width: 560px) {
    .shell { padding: 18px 14px 64px; }
    header.hero { min-height: auto; margin-bottom: 14px; }
    .poster { height: 100px; }
  }
</style>
</head>
<body>
  <div class="shell">
    <div id="library-view">
      <header class="hero">
        <h1 class="brand">Re<em>el</em></h1>
        <p class="tagline">Movies from this PC over Wi‑Fi. Use <strong style="color:var(--text)">VLC</strong> on your phone for sound — browsers often drop movie audio.</p>
        <div class="meta-row">
          <span class="dot" aria-hidden="true"></span>
          <span><strong id="count">0</strong> titles</span>
          <span id="folder-label">…</span>
          <span id="engine-label"></span>
        </div>
      </header>
      <div class="wifi-box" id="wifi-box">
        <h2>Phone on same Wi‑Fi</h2>
        <ol>
          <li>Install <strong style="color:var(--text)">VLC</strong> from the app store.</li>
          <li>On this phone open one of these (same Wi‑Fi as the PC):</li>
        </ol>
        <p id="lan-urls" class="url" style="margin:10px 0 0">Loading…</p>
        <p class="hint" style="margin-top:10px">If it won’t load: on the PC re-run <code>Reel.bat</code> and allow the Windows Firewall popup / “Private network”.</p>
      </div>
      <div class="toolbar">
        <input id="q" type="search" placeholder="Search titles…" autocomplete="off"/>
        <button type="button" id="refresh" class="primary">Refresh</button>
      </div>
      <div id="grid" class="grid"></div>
      <div id="empty" class="empty" hidden>No MKVs or MP4s found in this folder.</div>
      <div id="err" class="error" hidden></div>
    </div>

    <div id="player-view">
      <div class="player-head">
        <h1 id="play-title">Playing</h1>
        <button type="button" id="back">← Library</button>
      </div>
      <div class="actions">
        <a id="vlc-link" class="btn primary" href="#">Open in VLC (audio)</a>
        <button type="button" id="copy-url">Copy VLC URL</button>
        <button type="button" id="play-browser">Play in browser</button>
        <button type="button" id="play-pc-vlc" hidden>Play on this PC (VLC)</button>
      </div>
      <video id="vid" controls playsinline preload="metadata"></video>
      <p class="hint" id="play-hint"></p>
    </div>
  </div>
<script>
const grid = document.getElementById("grid");
const empty = document.getElementById("empty");
const err = document.getElementById("err");
const countEl = document.getElementById("count");
const folderLabel = document.getElementById("folder-label");
const engineLabel = document.getElementById("engine-label");
const lanUrls = document.getElementById("lan-urls");
const q = document.getElementById("q");
const libraryView = document.getElementById("library-view");
const playerView = document.getElementById("player-view");
const vid = document.getElementById("vid");
const playTitle = document.getElementById("play-title");
const playHint = document.getElementById("play-hint");
const vlcLink = document.getElementById("vlc-link");
const playPcVlc = document.getElementById("play-pc-vlc");

let movies = [];
let info = { ffmpeg: false, vlc: false, lan_urls: [] };
let current = null;

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}

function absUrl(path) {
  return location.origin + path;
}

function vlcStreamUrl(m) {
  // Raw file URL — VLC plays AC3/DTS/etc. browsers usually can't
  return absUrl("/raw/" + encodeURIComponent(m.id) + "/" + encodeURIComponent(m.rel.split("/").pop()));
}

function render(list) {
  grid.innerHTML = "";
  empty.hidden = list.length > 0;
  for (const m of list) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tile";
    btn.innerHTML =
      `<div class="poster"><span>${esc(m.title)}</span></div>` +
      `<div class="info"><h2>${esc(m.title)}</h2>` +
      `<p>${esc(m.folder || "Movies")} · ${esc(m.size_label)}</p>` +
      `<span class="badge">${esc(m.ext)}</span></div>`;
    btn.addEventListener("click", () => openMovie(m));
    grid.appendChild(btn);
  }
}

function filter() {
  const needle = q.value.trim().toLowerCase();
  if (!needle) return render(movies);
  render(movies.filter(m =>
    m.title.toLowerCase().includes(needle) ||
    (m.folder || "").toLowerCase().includes(needle) ||
    m.rel.toLowerCase().includes(needle)
  ));
}

async function load() {
  err.hidden = true;
  try {
    const res = await fetch("/api/movies?refresh=1");
    if (!res.ok) throw new Error("Could not load library");
    const data = await res.json();
    movies = data.movies || [];
    info = data;
    countEl.textContent = String(movies.length);
    folderLabel.textContent = data.movies_dir || "";
    const bits = [];
    bits.push(data.ffmpeg ? "ffmpeg audio fix: on" : "ffmpeg: off");
    bits.push(data.vlc ? "VLC on PC: found" : "VLC on PC: not found");
    engineLabel.textContent = bits.join(" · ");
    playPcVlc.hidden = !data.vlc;
    const urls = (data.lan_urls || []).map(u => `<div class="url">${esc(u)}</div>`).join("") ||
      `<div class="url">${esc(location.origin + "/")}</div>`;
    lanUrls.innerHTML = urls;
    filter();
  } catch (e) {
    err.hidden = false;
    err.textContent = e.message || String(e);
  }
}

function openMovie(m) {
  current = m;
  playTitle.textContent = m.title;
  const raw = vlcStreamUrl(m);
  vlcLink.href = raw;
  // Android VLC intent when possible
  const isAndroid = /Android/i.test(navigator.userAgent);
  if (isAndroid) {
    vlcLink.href = "intent:" + raw.replace(/^https?:/, "") +
      "#Intent;action=android.intent.action.VIEW;scheme=http;type=video/*;package=org.videolan.vlc;end";
  }
  playHint.innerHTML =
    `Best audio: tap <strong class="ok">Open in VLC</strong>, or in VLC → Network → paste:<br>` +
    `<span class="url">${esc(raw)}</span><br><br>` +
    (info.ffmpeg
      ? "Browser play remuxes audio to AAC via ffmpeg on the PC."
      : "Browser play may have no sound without ffmpeg. Use VLC.");
  libraryView.classList.add("hide");
  playerView.classList.add("show");
  // Prefer VLC path — don't autoplay browser (often silent)
  vid.removeAttribute("src");
  vid.load();
}

function playInBrowser() {
  if (!current) return;
  const src = info.ffmpeg
    ? "/play/" + encodeURIComponent(current.id)
    : "/raw/" + encodeURIComponent(current.id);
  vid.src = src;
  vid.play().catch(() => {});
}

async function playOnPcVlc() {
  if (!current) return;
  try {
    const res = await fetch("/api/vlc/" + encodeURIComponent(current.id), { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "VLC launch failed");
    playHint.innerHTML = `<span class="ok">Opened in VLC on this PC.</span>`;
  } catch (e) {
    playHint.textContent = e.message || String(e);
  }
}

async function copyUrl() {
  if (!current) return;
  const raw = vlcStreamUrl(current);
  try {
    await navigator.clipboard.writeText(raw);
    playHint.innerHTML = `<span class="ok">Copied.</span> Paste into VLC → Open Network Stream.<br><span class="url">${esc(raw)}</span>`;
  } catch {
    playHint.innerHTML = `Copy this into VLC:<br><span class="url">${esc(raw)}</span>`;
  }
}

function closePlayer() {
  vid.pause();
  vid.removeAttribute("src");
  vid.load();
  current = null;
  playerView.classList.remove("show");
  libraryView.classList.remove("hide");
}

document.getElementById("refresh").addEventListener("click", load);
document.getElementById("back").addEventListener("click", closePlayer);
document.getElementById("play-browser").addEventListener("click", playInBrowser);
document.getElementById("copy-url").addEventListener("click", copyUrl);
playPcVlc.addEventListener("click", playOnPcVlc);
q.addEventListener("input", filter);
load();
</script>
</body>
</html>
"""


class ReelHandler(BaseHTTPRequestHandler):
    server_version = "Reel/1.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, data, "application/json; charset=utf-8")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range, Content-Type")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_HEAD(self) -> None:
        self._route(head_only=True)

    def do_GET(self) -> None:
        self._route(head_only=False)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/vlc/"):
            mid = urllib.parse.unquote(path[len("/api/vlc/") :])
            self._launch_vlc(mid)
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def _route(self, head_only: bool) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
            return

        if path == "/api/movies":
            if qs.get("refresh", ["0"])[0] in ("1", "true", "yes"):
                refresh_index()
            port = STATE["port"]
            urls = [f"http://{ip}:{port}/" for ip in lan_ips()]
            movies = [
                {
                    "id": m["id"],
                    "title": m["title"],
                    "rel": m["rel"],
                    "folder": m["folder"],
                    "size": m["size"],
                    "size_label": m["size_label"],
                    "ext": m["ext"],
                    "mtime": m["mtime"],
                }
                for m in STATE["index"].values()
            ]
            self._json(
                200,
                {
                    "movies": movies,
                    "movies_dir": str(STATE["movies_dir"]),
                    "count": len(movies),
                    "lan_urls": urls,
                    "ffmpeg": bool(STATE["ffmpeg"]),
                    "vlc": bool(STATE["vlc"]),
                },
            )
            return

        if path.startswith("/raw/"):
            rest = path[len("/raw/") :]
            mid = urllib.parse.unquote(rest.split("/", 1)[0])
            self._stream_file(mid, head_only=head_only)
            return

        if path.startswith("/stream/"):
            mid = urllib.parse.unquote(path[len("/stream/") :])
            self._stream_file(mid, head_only=head_only)
            return

        if path.startswith("/play/"):
            mid = urllib.parse.unquote(path[len("/play/") :])
            self._stream_ffmpeg(mid, head_only=head_only)
            return

        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def _launch_vlc(self, mid: str) -> None:
        meta = resolve_movie(mid)
        vlc = STATE["vlc"]
        if not meta:
            self._json(404, {"error": "Movie not found"})
            return
        if not vlc:
            self._json(400, {"error": "VLC not found on this PC. Install VLC, then restart Reel."})
            return
        path = meta["path"]
        try:
            subprocess.Popen(
                [vlc, "--fullscreen", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as e:
            self._json(500, {"error": str(e)})
            return
        self._json(200, {"ok": True, "path": path})

    def _stream_file(self, mid: str, head_only: bool) -> None:
        meta = resolve_movie(mid)
        if not meta:
            self._send(404, b"Movie not found", "text/plain; charset=utf-8")
            return

        path = Path(meta["path"])
        ext = path.suffix.lower()
        ctype = MIME.get(ext) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        size = path.stat().st_size
        range_header = self.headers.get("Range")
        # Helpful for VLC / media players
        disposition = 'inline; filename="%s"' % path.name.replace('"', "")

        if range_header:
            m = re.match(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not m:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Connection", "close")
                self.end_headers()
                return
            start_s, end_s = m.group(1), m.group(2)
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else size - 1
            if start >= size or end < start:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Connection", "close")
                self.end_headers()
                return
            end = min(end, size - 1)
            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(length))
            self.send_header("Content-Disposition", disposition)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            if head_only:
                return
            with path.open("rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    remaining -= len(chunk)
            return

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", disposition)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        if head_only:
            return
        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return

    def _stream_ffmpeg(self, mid: str, head_only: bool) -> None:
        """Remux/transcode to fragmented MP4 with AAC so browsers get audio."""
        meta = resolve_movie(mid)
        ffmpeg = STATE["ffmpeg"]
        if not meta:
            self._send(404, b"Movie not found", "text/plain; charset=utf-8")
            return
        if not ffmpeg:
            # Fall back to raw file
            self._stream_file(mid, head_only=head_only)
            return

        path = meta["path"]
        if head_only:
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            return

        # Copy video when possible; always encode audio to AAC (movie tracks are often AC3/DTS)
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            path,
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-b:a",
            "192k",
            "-movflags",
            "frag_keyframe+empty_moov+default_base_moof",
            "-f",
            "mp4",
            "pipe:1",
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1024 * 64,
            )
        except OSError as e:
            self._send(500, str(e).encode(), "text/plain; charset=utf-8")
            return

        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            assert proc.stdout is not None
            while True:
                chunk = proc.stdout.read(1024 * 256)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    proc.kill()
                    break
        finally:
            try:
                proc.kill()
            except OSError:
                pass
            try:
                proc.wait(timeout=2)
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Reel — stream local movies over Wi‑Fi (VLC-friendly)")
    parser.add_argument("--movies", "-m", type=Path, default=default_movies_dir())
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (0.0.0.0 = all Wi‑Fi adapters)")
    parser.add_argument("--port", "-p", type=int, default=8080)
    parser.add_argument("--open", action="store_true", help="Open library in this PC's browser")
    args = parser.parse_args()

    movies_dir = args.movies.expanduser()
    STATE["movies_dir"] = movies_dir
    STATE["port"] = args.port
    STATE["ffmpeg"] = find_ffmpeg()
    STATE["vlc"] = find_vlc()
    refresh_index()

    if not movies_dir.is_dir():
        print(f"Movies folder not found yet: {movies_dir}", file=sys.stderr)
        print("Create it (or pass --movies PATH). Server will still start.", file=sys.stderr)
    else:
        print(f"Scanning: {movies_dir}")
        print(f"Found {len(STATE['index'])} video(s)")

    print(f"VLC on PC:   {STATE['vlc'] or 'NOT FOUND (install for Play on this PC)'}")
    print(f"ffmpeg:      {STATE['ffmpeg'] or 'NOT FOUND (browser play may have no audio — use VLC on phone)'}")

    try:
        httpd = ThreadingHTTPServer((args.host, args.port), ReelHandler)
    except OSError as e:
        print(f"\nCould not bind {args.host}:{args.port} — {e}", file=sys.stderr)
        print("Is another Reel/app already using that port?", file=sys.stderr)
        return 1

    ips = lan_ips()
    print()
    print("================================================")
    print("  Reel is live — use your PHONE on same Wi-Fi")
    print("================================================")
    print(f"  This PC:   http://127.0.0.1:{args.port}/")
    for ip in ips:
        print(f"  PHONE:     http://{ip}:{args.port}/")
    print()
    print("  On phone: install VLC → open a movie → Open in VLC")
    print("  (or VLC → Network → paste the /raw/... URL)")
    print("  If phone can't connect: allow Windows Firewall for Python/port")
    print("================================================")
    print()

    if args.open:
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{args.port}/")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
