#!/usr/bin/env python3
"""
Reel — stream MKVs/MP4s from D:\\Movies over Wi‑Fi.

Scan the QR on the PC (or open the printed URL) on your phone.
Use VLC on the phone for full movie audio; browser play remuxes AAC when ffmpeg is available.
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
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mkv", ".m4v", ".webm", ".mov", ".avi", ".wmv", ".ts", ".m2ts"}
MIME = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".wmv": "video/x-ms-wmv",
    ".ts": "video/mp2t",
    ".m2ts": "video/mp2t",
}

STATE: dict = {
    "movies_dir": None,
    "index": {},
    "port": 8787,
    "ffmpeg": None,
    "ffprobe": None,
    "vlc": None,
    "announce": None,
    "lan_urls": [],
    "thumb_dir": None,
    "thumb_lock": threading.Lock(),
}


def default_movies_dir() -> Path:
    env = os.environ.get("REEL_MOVIES_DIR")
    if env:
        return Path(env)
    for candidate in (
        Path(r"D:\Movies"),
        Path(r"D:\movies"),
        Path(r"D:\Movie"),
        Path.home() / "Movies",
        Path.home() / "Videos",
        Path("/tmp/test-movies"),
    ):
        if candidate.is_dir():
            return candidate
    return Path(r"D:\Movies")


def find_tool(*names: str, extra: list[Path] | None = None) -> str | None:
    for name in names:
        env = os.environ.get(f"REEL_{name.upper()}") or os.environ.get(name.upper())
        if env and Path(env).is_file():
            return env
        which = shutil.which(name) or shutil.which(f"{name}.exe")
        if which:
            return which
    for path in extra or []:
        if path.is_file():
            return str(path)
    return None


def find_ffmpeg() -> str | None:
    return find_tool(
        "ffmpeg",
        extra=[
            Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
            Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
        ],
    )


def find_ffprobe(ffmpeg: str | None) -> str | None:
    probe = find_tool(
        "ffprobe",
        extra=[
            Path(r"C:\ffmpeg\bin\ffprobe.exe"),
            Path(r"C:\Program Files\ffmpeg\bin\ffprobe.exe"),
        ],
    )
    if probe:
        return probe
    if ffmpeg:
        cand = Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if cand.is_file():
            return str(cand)
    return None


def find_vlc() -> str | None:
    return find_tool(
        "vlc",
        extra=[
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "VideoLAN" / "VLC" / "vlc.exe",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "VideoLAN" / "VLC" / "vlc.exe",
            Path("/usr/bin/vlc"),
        ],
    )


def _ip_score(ip: str) -> int:
    if ip.startswith("192.168."):
        return 0
    if ip.startswith("10."):
        return 1
    if re.match(r"^172\.(1[6-9]|2\d|3[0-1])\.", ip):
        return 2
    if ip.startswith("169.254."):
        return 9
    if ip.startswith("127."):
        return 10
    return 5


def lan_ips() -> list[str]:
    found: set[str] = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip:
                found.add(ip)
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    cleaned = [ip for ip in found if ip and not ip.startswith("127.")]
    cleaned.sort(key=_ip_score)
    return cleaned or ["127.0.0.1"]


def movie_id(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode("utf-8", "replace")).hexdigest()[:16]


def pretty_title(path: Path) -> str:
    name = re.sub(r"[._]+", " ", path.stem)
    name = re.sub(r"\b(1080p|720p|2160p|4k|bluray|web[- ]?dl|x264|x265|hevc|aac|dts|hdr)\b", "", name, flags=re.I)
    return re.sub(r"\s+", " ", name).strip(" -_") or path.name


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def human_duration(seconds: float | None) -> str:
    if not seconds or seconds <= 0:
        return ""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m {sec:02d}s"


def probe_duration(path: Path) -> float | None:
    ffprobe = STATE.get("ffprobe")
    if not ffprobe:
        return None
    try:
        out = subprocess.check_output(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
        return float(out.decode().strip())
    except Exception:
        return None


def scan_movies(root: Path) -> dict:
    index = {}
    if not root.is_dir():
        return index
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d
            for d in dirnames
            if not d.startswith(".")
            and d.lower() not in {"@eadir", "system volume information", "$recycle.bin", "thumbs"}
        )
        for name in sorted(filenames):
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
                rel = str(path.relative_to(root)).replace("\\", "/")
            except ValueError:
                rel = path.name
            folder = str(Path(rel).parent).replace("\\", "/") if Path(rel).parent != Path(".") else ""
            index[mid] = {
                "id": mid,
                "title": pretty_title(path),
                "path": str(path),
                "rel": rel,
                "folder": folder,
                "size": st.st_size,
                "size_label": human_size(st.st_size),
                "ext": ext.lstrip(".").upper(),
                "mtime": int(st.st_mtime),
                "duration": None,
                "duration_label": "",
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


def esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def movies_payload() -> list[dict]:
    return [
        {
            "id": m["id"],
            "title": m["title"],
            "rel": m["rel"],
            "folder": m["folder"],
            "size": m["size"],
            "size_label": m["size_label"],
            "ext": m["ext"],
            "mtime": m["mtime"],
            "duration_label": m.get("duration_label") or "",
            "thumb": f"/thumb/{m['id']}.jpg",
        }
        for m in STATE["index"].values()
    ]


def primary_urls() -> list[str]:
    port = STATE["port"]
    urls = list(STATE["lan_urls"]) or [f"http://{ip}:{port}/" for ip in lan_ips()]
    announce = STATE.get("announce")
    if announce and announce not in ("", "REPLACE_WITH_IP_FROM_BELOW"):
        primary = f"http://{announce}:{port}/"
        urls = [primary] + [u for u in urls if u != primary]
    # de-dupe preserve order
    out, seen = [], set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def ensure_thumb(mid: str) -> Path | None:
    meta = resolve_movie(mid)
    ffmpeg = STATE.get("ffmpeg")
    thumb_dir = STATE.get("thumb_dir")
    if not meta or not ffmpeg or not thumb_dir:
        return None
    out = Path(thumb_dir) / f"{mid}.jpg"
    if out.is_file() and out.stat().st_size > 0:
        return out
    with STATE["thumb_lock"]:
        if out.is_file() and out.stat().st_size > 0:
            return out
        # grab a frame ~10% in (or 30s)
        duration = meta.get("duration")
        if duration is None:
            duration = probe_duration(Path(meta["path"]))
            meta["duration"] = duration
            meta["duration_label"] = human_duration(duration)
        ss = 3.0
        if duration and duration > 60:
            ss = min(duration * 0.12, 600)
        elif duration and duration > 5:
            ss = max(1.0, duration * 0.1)
        elif duration and duration > 0:
            ss = max(0.1, duration * 0.25)
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(ss),
            "-i",
            meta["path"],
            "-frames:v",
            "1",
            "-q:v",
            "4",
            "-vf",
            "scale=480:-2",
            "-y",
            str(out),
        ]
        try:
            subprocess.run(cmd, check=True, timeout=40, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            if out.exists():
                try:
                    out.unlink()
                except OSError:
                    pass
            return None
    return out if out.is_file() else None


def warmup_thumbs() -> None:
    if not STATE.get("ffmpeg"):
        return

    def worker() -> None:
        for mid in list(STATE["index"].keys())[:40]:
            ensure_thumb(mid)
            time.sleep(0.05)

    threading.Thread(target=worker, daemon=True).start()


def render_html() -> bytes:
    refresh_index()
    movies = movies_payload()
    urls = primary_urls()
    folders = sorted({m["folder"] for m in movies if m["folder"]})
    primary = urls[0] if urls else f"http://127.0.0.1:{STATE['port']}/"
    qr_src = (
        "https://quickchart.io/qr?size=280&margin=2&text="
        + urllib.parse.quote(primary, safe="")
    )

    ssr_cards = []
    for m in movies[:60]:
        raw = f"/raw/{urllib.parse.quote(m['id'])}/{urllib.parse.quote(Path(m['rel']).name)}"
        ssr_cards.append(
            f'<a class="tile" href="{esc(raw)}">'
            f'<div class="poster" style="background-image:url(/thumb/{esc(m["id"])}.jpg)">'
            f"<span>{esc(m['title'])}</span></div>"
            f'<div class="info"><h2>{esc(m["title"])}</h2>'
            f'<p>{esc(m["folder"] or "Movies")} · {esc(m["size_label"])}</p></div></a>'
        )
    grid_html = "\n".join(ssr_cards) if ssr_cards else (
        f'<div class="empty">No videos in <code>{esc(str(STATE["movies_dir"]))}</code>. '
        f"Drop .mp4 / .mkv files there, then Refresh.</div>"
    )

    boot = {
        "movies": movies,
        "movies_dir": str(STATE["movies_dir"]),
        "count": len(movies),
        "lan_urls": urls,
        "folders": folders,
        "ffmpeg": bool(STATE["ffmpeg"]),
        "vlc": bool(STATE["vlc"]),
        "primary": primary,
    }
    boot_json = json.dumps(boot, ensure_ascii=False).replace("</", "<\\/")
    url_html = "".join(f'<a class="url" href="{esc(u)}">{esc(u)}</a>' for u in urls)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<meta name="theme-color" content="#0b0a09"/>
<meta name="apple-mobile-web-app-capable" content="yes"/>
<title>Reel · {len(movies)} movies</title>
<style>
:root {{
  --bg:#0b0a09; --panel:#15120e; --panel2:#1c1813; --line:#322b22;
  --text:#f4ece2; --muted:#a7967d; --gold:#e2ad55; --gold2:#b8842a;
  --ok:#62c47a; --danger:#e07060; --haze:rgba(226,173,85,.14);
}}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; min-height:100%; }}
body {{
  color:var(--text);
  font-family:"Segoe UI", Candara, Calibri, sans-serif;
  background:
    radial-gradient(1000px 520px at 0% -10%, #2c2114 0%, transparent 55%),
    radial-gradient(800px 420px at 100% 0%, #1a140e 0%, transparent 50%),
    linear-gradient(180deg, #12100d, var(--bg) 45%, #080706);
  background-attachment:fixed;
}}
.shell {{ max-width:1100px; margin:0 auto; padding:20px 16px 88px; }}
.hero {{
  display:grid; gap:18px; grid-template-columns:1.3fr .7fr; align-items:end;
  margin-bottom:18px; animation:rise .55s ease both;
}}
@media (max-width:760px) {{ .hero {{ grid-template-columns:1fr; }} }}
.brand {{
  font-family: Impact, Haettenschweiler, "Arial Narrow Bold", sans-serif;
  font-size:clamp(3.2rem, 13vw, 6rem); line-height:.9; letter-spacing:.02em; margin:0;
}}
.brand em {{ font-style:normal; color:var(--gold); }}
.tag {{ margin:10px 0 0; color:var(--muted); max-width:34rem; line-height:1.45; }}
.pair {{
  background:linear-gradient(165deg,var(--panel2),var(--panel));
  border:1px solid var(--line); border-radius:16px; padding:14px;
  text-align:center; animation:rise .55s ease .08s both;
}}
.pair img {{
  width:min(100%, 220px); height:auto; border-radius:10px; background:#fff; padding:8px;
}}
.pair .lbl {{ margin:8px 0 0; color:var(--muted); font-size:.85rem; }}
.box {{
  border:1px solid var(--line); border-radius:14px; padding:14px 16px;
  background:linear-gradient(180deg,var(--panel2),var(--panel));
  margin:0 0 16px; animation:rise .55s ease .12s both;
}}
.box h2 {{ margin:0 0 8px; font-size:.95rem; color:var(--gold); letter-spacing:.04em; text-transform:uppercase; }}
.url {{
  display:block; color:var(--gold); word-break:break-all; text-decoration:none;
  font-family:Consolas, ui-monospace, monospace; font-size:1.02rem; margin:6px 0;
}}
.url:hover {{ text-decoration:underline; }}
.meta {{ color:var(--muted); margin:0 0 12px; font-size:.92rem; }}
.meta strong {{ color:var(--text); }}
.toolbar, .filters, .actions {{
  display:flex; flex-wrap:wrap; gap:8px; margin:0 0 14px; align-items:center;
}}
#q, select {{
  flex:1 1 160px; min-width:0; padding:11px 12px; border-radius:10px;
  border:1px solid var(--line); background:var(--panel); color:var(--text); font:inherit;
}}
#q:focus, select:focus {{ outline:none; border-color:var(--gold2); box-shadow:0 0 0 3px var(--haze); }}
button, .btn {{
  font:inherit; font-weight:700; border:1px solid var(--line); border-radius:10px;
  padding:11px 14px; cursor:pointer; background:var(--panel2); color:var(--text);
  text-decoration:none; display:inline-block;
}}
button.primary, .btn.primary {{
  background:linear-gradient(180deg,#f0b85a,var(--gold2)); border-color:transparent; color:#1a1206;
}}
button:active {{ transform:translateY(1px); }}
.chip {{
  border:1px solid var(--line); background:transparent; color:var(--muted);
  border-radius:999px; padding:7px 12px; font-size:.85rem; font-weight:600;
}}
.chip.on {{ color:var(--bg); background:var(--gold); border-color:transparent; }}
.grid {{
  display:grid; grid-template-columns:repeat(auto-fill,minmax(168px,1fr)); gap:12px;
  animation:rise .6s ease .16s both;
}}
.tile {{
  text-align:left; padding:0; overflow:hidden; width:100%;
  border:1px solid var(--line); border-radius:14px; color:inherit; font:inherit;
  background:linear-gradient(165deg,var(--panel2),var(--panel)); cursor:pointer;
  transition:transform .15s ease, border-color .15s ease;
}}
a.tile {{ display:block; text-decoration:none; color:inherit; }}
.tile:hover {{ transform:translateY(-2px); border-color:#4a3d2a; }}
.poster {{
  aspect-ratio:16/10; background:
    linear-gradient(180deg, transparent 30%, rgba(0,0,0,.85)),
    linear-gradient(135deg,#3a2d18,#1a1510 60%);
  background-size:cover; background-position:center;
  display:flex; align-items:flex-end; padding:10px;
  font-family:Impact, Haettenschweiler, sans-serif; font-size:1.15rem; line-height:1.05;
}}
.poster span {{
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;
  text-shadow:0 1px 8px #000;
}}
.progress {{
  height:3px; background:#2a241c; margin-top:-3px; position:relative; z-index:1;
}}
.progress > i {{ display:block; height:100%; background:var(--gold); width:0; }}
.info {{ padding:10px 11px 12px; }}
.info h2 {{ margin:0 0 4px; font-size:.95rem; line-height:1.25; }}
.info p {{ margin:0; color:var(--muted); font-size:.78rem; }}
.badge {{
  display:inline-block; margin-top:7px; margin-right:5px; font-size:.68rem; font-weight:800;
  letter-spacing:.05em; color:var(--gold); border:1px solid #4a3d2a; padding:2px 6px; border-radius:6px;
}}
.empty {{ text-align:center; color:var(--muted); padding:36px 10px; line-height:1.5; }}
#player {{ display:none; }}
#player.show {{ display:block; animation:rise .35s ease both; }}
#library.hide {{ display:none; }}
.player-head {{ display:flex; flex-wrap:wrap; gap:10px; justify-content:space-between; align-items:center; }}
.player-head h1 {{
  margin:0; font-family:Impact, Haettenschweiler, sans-serif;
  font-size:clamp(1.4rem,5vw,2.2rem); letter-spacing:.02em;
}}
video {{
  width:100%; max-height:min(72vh,740px); background:#000; border-radius:12px;
  border:1px solid var(--line); margin-top:8px;
}}
.hint {{ color:var(--muted); font-size:.9rem; line-height:1.45; margin-top:10px; }}
.ok {{ color:var(--ok); }}
@keyframes rise {{ from {{ opacity:0; transform:translateY(12px); }} to {{ opacity:1; transform:none; }} }}
</style>
</head>
<body>
<div class="shell">
  <div id="library">
    <div class="hero">
      <div>
        <h1 class="brand">Re<em>el</em></h1>
        <p class="tag">Your <code style="color:var(--gold)">{esc(str(STATE["movies_dir"]))}</code> library on Wi‑Fi.
          Scan the QR with your phone, then open titles in <b>VLC</b> for full audio.</p>
      </div>
      <div class="pair">
        <img src="{esc(qr_src)}" alt="QR code to open Reel on phone" width="220" height="220"
             onerror="this.style.display='none'"/>
        <div class="lbl">Scan on your phone · same Wi‑Fi</div>
      </div>
    </div>

    <div class="box">
      <h2>Phone URL</h2>
      {url_html}
      <p class="hint" style="margin:8px 0 0">Keep Reel.bat running. Never use 127.0.0.1 on the phone.
        <button type="button" id="copy-primary" class="btn" style="margin-left:6px;padding:6px 10px;font-size:.85rem">Copy link</button>
      </p>
    </div>

    <p class="meta"><strong id="count">{len(movies)}</strong> titles
      · <span id="engine">{'ffmpeg audio' if STATE['ffmpeg'] else 'VLC for audio'}</span></p>

    <div class="toolbar">
      <input id="q" type="search" placeholder="Search movies…" autocomplete="off"/>
      <select id="sort" aria-label="Sort">
        <option value="name">A–Z</option>
        <option value="new">Newest</option>
        <option value="size">Largest</option>
      </select>
      <button type="button" id="refresh" class="primary">Refresh</button>
    </div>
    <div class="filters" id="filters"></div>
    <div id="grid" class="grid">{grid_html}</div>
  </div>

  <div id="player">
    <div class="player-head">
      <h1 id="play-title">Playing</h1>
      <button type="button" id="back">← Library</button>
    </div>
    <div class="actions">
      <a id="vlc-link" class="btn primary" href="#">Open in VLC</a>
      <button type="button" id="copy-url">Copy stream URL</button>
      <button type="button" id="play-browser" class="primary">Play here</button>
      <button type="button" id="play-pc-vlc" hidden>VLC on this PC</button>
    </div>
    <video id="vid" controls playsinline preload="metadata"></video>
    <p class="hint" id="play-hint"></p>
  </div>
</div>
<script>
const BOOT = {boot_json};
const KEY = "reel-progress-v1";
let movies = BOOT.movies || [];
let folder = "";
let current = null;
const grid = document.getElementById("grid");
const q = document.getElementById("q");
const sortEl = document.getElementById("sort");
const filters = document.getElementById("filters");
const vid = document.getElementById("vid");
const playPcVlc = document.getElementById("play-pc-vlc");
playPcVlc.hidden = !BOOT.vlc;

function esc(s) {{
  return String(s).replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}}[c]));
}}
function progressMap() {{
  try {{ return JSON.parse(localStorage.getItem(KEY) || "{{}}"); }} catch (e) {{ return {{}}; }}
}}
function saveProgress(id, t, d) {{
  if (!id || !d || d < 30) return;
  const m = progressMap();
  const pct = Math.min(99, Math.round((t / d) * 100));
  if (pct < 2 || pct > 95) {{ delete m[id]; }}
  else {{ m[id] = {{ t, d, pct, at: Date.now() }}; }}
  localStorage.setItem(KEY, JSON.stringify(m));
}}
function rawUrl(m) {{
  const name = (m.rel || "movie").split("/").pop();
  return location.origin + "/raw/" + encodeURIComponent(m.id) + "/" + encodeURIComponent(name);
}}
function playUrl(m) {{
  return BOOT.ffmpeg ? (location.origin + "/play/" + encodeURIComponent(m.id)) : rawUrl(m);
}}
function sortedFiltered() {{
  let list = movies.slice();
  const needle = q.value.trim().toLowerCase();
  if (folder) list = list.filter(m => m.folder === folder);
  if (needle) list = list.filter(m =>
    m.title.toLowerCase().includes(needle) ||
    (m.rel || "").toLowerCase().includes(needle) ||
    (m.folder || "").toLowerCase().includes(needle)
  );
  const mode = sortEl.value;
  if (mode === "new") list.sort((a,b) => b.mtime - a.mtime);
  else if (mode === "size") list.sort((a,b) => b.size - a.size);
  else list.sort((a,b) => a.title.localeCompare(b.title));
  return list;
}}
function renderFilters() {{
  const folders = BOOT.folders || [];
  const bits = [`<button type="button" class="chip ${{folder===""?"on":""}}" data-f="">All</button>`];
  for (const f of folders) {{
    bits.push(`<button type="button" class="chip ${{folder===f?"on":""}}" data-f="${{esc(f)}}">${{esc(f)}}</button>`);
  }}
  filters.innerHTML = bits.join("");
  filters.querySelectorAll(".chip").forEach(btn => {{
    btn.onclick = () => {{ folder = btn.getAttribute("data-f") || ""; renderFilters(); render(); }};
  }});
}}
function render() {{
  const list = sortedFiltered();
  document.getElementById("count").textContent = String(list.length);
  const prog = progressMap();
  if (!list.length) {{
    grid.innerHTML = '<div class="empty">No matches. Try another search or folder.</div>';
    return;
  }}
  grid.innerHTML = list.map(m => {{
    const p = prog[m.id];
    const bar = p ? `<div class="progress"><i style="width:${{p.pct}}%"></i></div>` : "";
    const sub = [m.folder || "Movies", m.duration_label, m.size_label].filter(Boolean).join(" · ");
    return `<button type="button" class="tile" data-id="${{esc(m.id)}}">` +
      `<div class="poster" style="background-image:url('/thumb/${{esc(m.id)}}.jpg')"><span>${{esc(m.title)}}</span></div>` +
      bar +
      `<div class="info"><h2>${{esc(m.title)}}</h2><p>${{esc(sub)}}</p>` +
      `<span class="badge">${{esc(m.ext)}}</span>${{p?`<span class="badge">${{p.pct}}%</span>`:""}}</div></button>`;
  }}).join("");
  grid.querySelectorAll(".tile").forEach(btn => {{
    btn.onclick = () => {{
      const m = movies.find(x => x.id === btn.getAttribute("data-id"));
      if (m) openMovie(m);
    }};
  }});
}}
function openMovie(m) {{
  current = m;
  document.getElementById("play-title").textContent = m.title;
  const raw = rawUrl(m);
  const a = document.getElementById("vlc-link");
  if (/Android/i.test(navigator.userAgent)) {{
    a.href = "intent:" + raw.replace(/^https?:/, "") +
      "#Intent;action=android.intent.action.VIEW;scheme=http;type=video/*;package=org.videolan.vlc;S.browser_fallback_url=" +
      encodeURIComponent(raw) + ";end";
  }} else if (/iPhone|iPad|iPod/i.test(navigator.userAgent)) {{
    a.href = "vlc-x-callback://x-callback-url/stream?url=" + encodeURIComponent(raw);
  }} else {{
    a.href = raw;
  }}
  document.getElementById("play-hint").innerHTML =
    `<span class="ok">Best audio:</span> Open in VLC.<br>Stream URL: <span class="url">${{esc(raw)}}</span>` +
    (BOOT.ffmpeg ? "<br>Play here remuxes audio to AAC via ffmpeg." : "<br>Install ffmpeg on the PC for browser audio.");
  document.getElementById("library").classList.add("hide");
  document.getElementById("player").classList.add("show");
  // auto-start browser playback (with ffmpeg audio when available)
  const src = playUrl(m);
  vid.src = src;
  const saved = progressMap()[m.id];
  const start = () => {{
    if (saved && saved.t > 15) {{
      try {{ vid.currentTime = saved.t; }} catch (e) {{}}
    }}
    vid.play().catch(() => {{}});
  }};
  vid.onloadedmetadata = start;
  vid.play().catch(() => {{}});
}}
function closePlayer() {{
  if (current) saveProgress(current.id, vid.currentTime || 0, vid.duration || 0);
  vid.pause(); vid.removeAttribute("src"); vid.load();
  current = null;
  document.getElementById("player").classList.remove("show");
  document.getElementById("library").classList.remove("hide");
  render();
}}
vid.addEventListener("timeupdate", () => {{
  if (current && vid.duration) saveProgress(current.id, vid.currentTime, vid.duration);
}});
document.getElementById("back").onclick = closePlayer;
document.getElementById("play-browser").onclick = () => {{
  if (!current) return;
  vid.src = playUrl(current);
  vid.play().catch(() => {{}});
}};
document.getElementById("copy-url").onclick = async () => {{
  if (!current) return;
  const raw = rawUrl(current);
  try {{ await navigator.clipboard.writeText(raw); document.getElementById("play-hint").innerHTML = `<span class="ok">Copied.</span> ${{esc(raw)}}`; }}
  catch (e) {{ document.getElementById("play-hint").textContent = raw; }}
}};
document.getElementById("copy-primary").onclick = async () => {{
  try {{ await navigator.clipboard.writeText(BOOT.primary); }} catch (e) {{}}
}};
playPcVlc.onclick = async () => {{
  if (!current) return;
  const res = await fetch("/api/vlc/" + encodeURIComponent(current.id), {{ method:"POST" }});
  const data = await res.json().catch(() => ({{}}));
  document.getElementById("play-hint").textContent = res.ok ? "Opened in VLC on this PC." : (data.error || "VLC launch failed");
}};
document.getElementById("refresh").onclick = async () => {{
  const res = await fetch("/api/movies?refresh=1");
  const data = await res.json();
  movies = data.movies || [];
  BOOT.folders = [...new Set(movies.map(m => m.folder).filter(Boolean))].sort();
  BOOT.ffmpeg = data.ffmpeg; BOOT.vlc = data.vlc;
  document.getElementById("engine").textContent = data.ffmpeg ? "ffmpeg audio" : "VLC for audio";
  playPcVlc.hidden = !data.vlc;
  renderFilters(); render();
}};
q.oninput = render;
sortEl.onchange = render;
renderFilters();
render();
</script>
</body>
</html>
"""
    return html.encode("utf-8")


class ThreadingHTTPServerReuse(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class ReelHandler(BaseHTTPRequestHandler):
    server_version = "Reel/2.0"
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range, Content-Type")
        self.end_headers()

    def do_HEAD(self) -> None:
        self._route(True)

    def do_GET(self) -> None:
        self._route(False)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/vlc/"):
            mid = urllib.parse.unquote(parsed.path[len("/api/vlc/") :])
            self._launch_vlc(mid)
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def _route(self, head_only: bool) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html", "/connect"):
            self._send(200, render_html(), "text/html; charset=utf-8")
            return

        if path == "/health":
            self._json(
                200,
                {
                    "ok": True,
                    "movies": len(STATE["index"]),
                    "movies_dir": str(STATE["movies_dir"]),
                    "lan_urls": primary_urls(),
                    "ffmpeg": bool(STATE["ffmpeg"]),
                    "vlc": bool(STATE["vlc"]),
                },
            )
            return

        if path == "/api/movies":
            if qs.get("refresh", ["0"])[0] in ("1", "true", "yes"):
                refresh_index()
                warmup_thumbs()
            movies = movies_payload()
            self._json(
                200,
                {
                    "movies": movies,
                    "movies_dir": str(STATE["movies_dir"]),
                    "count": len(movies),
                    "lan_urls": primary_urls(),
                    "folders": sorted({m["folder"] for m in movies if m["folder"]}),
                    "ffmpeg": bool(STATE["ffmpeg"]),
                    "vlc": bool(STATE["vlc"]),
                },
            )
            return

        if path.startswith("/thumb/"):
            name = path[len("/thumb/") :]
            mid = name[:-4] if name.endswith(".jpg") else name
            mid = urllib.parse.unquote(mid)
            thumb = ensure_thumb(mid)
            if not thumb:
                gif = (
                    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
                    b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
                )
                self._send(200, gif, "image/gif", {"Cache-Control": "no-store"})
                return
            data = thumb.read_bytes()
            self._send(200, data, "image/jpeg", {"Cache-Control": "public, max-age=86400"})
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
            self._json(400, {"error": "VLC not installed on this PC"})
            return
        try:
            subprocess.Popen([vlc, "--fullscreen", meta["path"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            self._json(500, {"error": str(e)})
            return
        self._json(200, {"ok": True})

    def _stream_file(self, mid: str, head_only: bool) -> None:
        meta = resolve_movie(mid)
        if not meta:
            self._send(404, b"Movie not found", "text/plain; charset=utf-8")
            return
        path = Path(meta["path"])
        ext = path.suffix.lower()
        ctype = MIME.get(ext) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        size = path.stat().st_size
        disposition = 'inline; filename="%s"' % path.name.replace('"', "")
        range_header = self.headers.get("Range")

        if range_header:
            m = re.match(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not m:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            start = int(m.group(1)) if m.group(1) else 0
            end = int(m.group(2)) if m.group(2) else size - 1
            if start >= size or end < start:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
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
        meta = resolve_movie(mid)
        ffmpeg = STATE["ffmpeg"]
        if not meta:
            self._send(404, b"Movie not found", "text/plain; charset=utf-8")
            return
        if not ffmpeg:
            self._stream_file(mid, head_only=head_only)
            return
        if head_only:
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.end_headers()
            return
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-i", meta["path"],
            "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "copy", "-c:a", "aac", "-ac", "2", "-b:a", "192k",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "-f", "mp4", "pipe:1",
        ]
        # If video codec won't play in browsers (hevc/mpeg), re-encode lightly
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1024 * 64)
        except OSError as e:
            self._send(500, str(e).encode(), "text/plain; charset=utf-8")
            return
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
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
    parser = argparse.ArgumentParser(description="Reel — Wi‑Fi movies from D:\\Movies")
    parser.add_argument("--movies", "-m", type=Path, default=default_movies_dir())
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", "-p", type=int, default=8787)
    parser.add_argument("--announce", default="", help="Preferred LAN IP for phones")
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()

    movies_dir = args.movies.expanduser()
    STATE["movies_dir"] = movies_dir
    STATE["port"] = args.port
    STATE["ffmpeg"] = find_ffmpeg()
    STATE["ffprobe"] = find_ffprobe(STATE["ffmpeg"])
    STATE["vlc"] = find_vlc()
    STATE["announce"] = (args.announce or "").strip()
    STATE["thumb_dir"] = Path(tempfile.gettempdir()) / "reel-thumbs"
    STATE["thumb_dir"].mkdir(parents=True, exist_ok=True)
    refresh_index()

    ips = lan_ips()
    if STATE["announce"] and not STATE["announce"].startswith("REPLACE"):
        ips = [STATE["announce"]] + [i for i in ips if i != STATE["announce"]]
    STATE["lan_urls"] = [f"http://{ip}:{args.port}/" for ip in ips]

    print(f"Movies folder: {movies_dir}")
    print(f"Videos found:  {len(STATE['index'])}")
    for m in list(STATE["index"].values())[:10]:
        print(f"  - {m['rel']}")
    if len(STATE["index"]) > 10:
        print(f"  … +{len(STATE['index']) - 10} more")
    print(f"ffmpeg: {STATE['ffmpeg'] or 'not found'}")
    print(f"VLC:    {STATE['vlc'] or 'not found'}")

    try:
        httpd = ThreadingHTTPServerReuse((args.host, args.port), ReelHandler)
    except OSError as e:
        print(f"\nERROR: cannot listen on {args.host}:{args.port} — {e}", file=sys.stderr)
        return 1

    warmup_thumbs()

    phone_txt = Path(__file__).resolve().parent / "PHONE-URL.txt"
    urls = primary_urls()
    try:
        phone_txt.write_text(
            "Open on your PHONE (same Wi-Fi). Keep Reel.bat running.\n\n"
            + "\n".join(urls)
            + "\n\nScan the QR on the PC page, or type a URL above.\n"
            "Tap a movie → Open in VLC for best audio.\n",
            encoding="utf-8",
        )
    except OSError:
        pass

    print()
    print("=" * 56)
    print("  PHONE — open / scan QR on the PC page:")
    for u in urls:
        print(f"     {u}")
    print(f"  THIS PC: http://127.0.0.1:{args.port}/")
    print("=" * 56)
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
