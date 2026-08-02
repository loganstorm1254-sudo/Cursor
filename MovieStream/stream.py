#!/usr/bin/env python3
"""
Reel — stream MKVs/MP4s from D:\\Movies over Wi‑Fi.

Phone: open the printed http://IP:PORT/ URL, then Open in VLC for audio.
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
    "port": 8787,
    "ffmpeg": None,
    "vlc": None,
    "announce": None,
    "lan_urls": [],
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
    ):
        if candidate.is_file():
            return str(candidate)
    return None


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
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    # Windows: ipconfig parse via hostname aliases already covered; also try all hostnames
    try:
        for info in socket.getaddrinfo(None, 0, socket.AF_INET, socket.SOCK_DGRAM):
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
    return re.sub(r"\s+", " ", name).strip() or path.name


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
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
            if not d.startswith(".") and d.lower() not in {"@eadir", "system volume information", "$recycle.bin"}
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
        }
        for m in STATE["index"].values()
    ]


def render_html() -> bytes:
    refresh_index()
    movies = movies_payload()
    port = STATE["port"]
    urls = list(STATE["lan_urls"]) or [f"http://{ip}:{port}/" for ip in lan_ips()]
    announce = STATE.get("announce")
    if announce and announce not in ("", "REPLACE_WITH_IP_FROM_BELOW"):
        primary = f"http://{announce}:{port}/"
        urls = [primary] + [u for u in urls if u != primary]

    cards = []
    for m in movies:
        raw = f"/raw/{urllib.parse.quote(m['id'])}/{urllib.parse.quote(Path(m['rel']).name)}"
        cards.append(
            f'<a class="tile" href="{esc(raw)}">'
            f'<div class="poster"><span>{esc(m["title"])}</span></div>'
            f'<div class="info"><h2>{esc(m["title"])}</h2>'
            f'<p>{esc(m["folder"] or "Movies")} · {esc(m["size_label"])}</p>'
            f'<span class="badge">{esc(m["ext"])}</span>'
            f'<span class="badge open">Tap = open / VLC</span></div></a>'
        )
    grid_html = "\n".join(cards) if cards else (
        f'<div class="empty">No .mp4 / .mkv files in<br><code>{esc(str(STATE["movies_dir"]))}</code>'
        f"<br><br>Copy movies there, then tap Refresh.</div>"
    )
    url_html = "".join(f'<div class="url">{esc(u)}</div>' for u in urls)
    boot = {
        "movies": movies,
        "movies_dir": str(STATE["movies_dir"]),
        "count": len(movies),
        "lan_urls": urls,
        "ffmpeg": bool(STATE["ffmpeg"]),
        "vlc": bool(STATE["vlc"]),
    }
    boot_json = json.dumps(boot, ensure_ascii=False).replace("</", "<\\/")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="theme-color" content="#0c0b0a"/>
<title>Reel — {len(movies)} movies</title>
<style>
  :root {{
    --ink:#0c0b0a; --panel:#161310; --panel2:#1e1a15; --line:#2f2920;
    --text:#f3ebe0; --muted:#a89880; --gold:#e0a84a; --gold-dim:#b07a22; --ok:#6cbc7a;
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; font-family: Georgia, "Times New Roman", serif; color:var(--text);
    background:
      radial-gradient(900px 500px at 0% 0%, #2a2114 0%, transparent 55%),
      linear-gradient(180deg,#100e0c,#0a0908);
    min-height:100%;
  }}
  .shell {{ max-width:960px; margin:0 auto; padding:22px 16px 72px; }}
  .brand {{
    font-family: Impact, Haettenschweiler, "Arial Narrow Bold", sans-serif;
    font-size:clamp(3rem,14vw,5.5rem); letter-spacing:.02em; margin:0; line-height:.95;
  }}
  .brand em {{ font-style:normal; color:var(--gold); }}
  .tag {{ color:var(--muted); font-family: system-ui,sans-serif; font-size:1rem; max-width:34rem; }}
  .box {{
    margin:16px 0; padding:14px; border:1px solid var(--line); border-radius:12px;
    background:linear-gradient(180deg,var(--panel2),var(--panel));
    font-family: system-ui,sans-serif;
  }}
  .box h2 {{ margin:0 0 8px; font-size:1rem; color:var(--gold); }}
  .url {{ color:var(--gold); word-break:break-all; font-family: Consolas, monospace; margin:6px 0; font-size:1.05rem; }}
  .meta {{ color:var(--muted); font-family:system-ui,sans-serif; margin:8px 0 16px; }}
  .meta strong {{ color:var(--text); }}
  .toolbar {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px; font-family:system-ui,sans-serif; }}
  #q {{
    flex:1; min-width:140px; padding:12px; border-radius:10px; border:1px solid var(--line);
    background:var(--panel); color:var(--text); font:inherit;
  }}
  button {{
    font:inherit; font-weight:700; border:0; border-radius:10px; padding:12px 16px; cursor:pointer;
    background:linear-gradient(180deg,#f0b85a,var(--gold-dim)); color:#1a1206;
  }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:12px; }}
  a.tile {{
    text-decoration:none; color:inherit; display:block; border:1px solid var(--line);
    border-radius:14px; overflow:hidden; background:linear-gradient(165deg,var(--panel2),var(--panel));
  }}
  .poster {{
    min-height:100px; padding:14px; display:flex; align-items:flex-end;
    background:linear-gradient(135deg,#3a2d18,#1a1510 55%,#241c12);
    font-family: Impact, Haettenschweiler, sans-serif; font-size:1.4rem; line-height:1.1;
  }}
  .info {{ padding:12px 14px 14px; font-family:system-ui,sans-serif; }}
  .info h2 {{ margin:0 0 6px; font-size:1rem; }}
  .info p {{ margin:0; color:var(--muted); font-size:.86rem; }}
  .badge {{
    display:inline-block; margin-top:8px; margin-right:6px; font-size:.7rem; font-weight:800;
    letter-spacing:.06em; color:var(--gold); border:1px solid #4a3d2a; padding:3px 7px; border-radius:6px;
  }}
  .badge.open {{ color:var(--ok); border-color:#2a4a32; }}
  .empty {{ text-align:center; color:var(--muted); padding:28px 8px; font-family:system-ui,sans-serif; line-height:1.5; }}
  code {{ color:var(--gold); }}
  #player {{ display:none; }}
  #player.show {{ display:block; }}
  #library.hide {{ display:none; }}
  video {{ width:100%; max-height:70vh; background:#000; border-radius:12px; border:1px solid var(--line); }}
  .actions {{ display:flex; flex-wrap:wrap; gap:8px; margin:12px 0; font-family:system-ui,sans-serif; }}
  .actions a, .actions button {{
    background:var(--panel2); color:var(--text); border:1px solid var(--line); text-decoration:none;
  }}
  .actions a.primary, .actions button.primary {{
    background:linear-gradient(180deg,#f0b85a,var(--gold-dim)); color:#1a1206; border:0;
  }}
</style>
</head>
<body>
<div class="shell">
  <div id="library">
    <h1 class="brand">Re<em>el</em></h1>
    <p class="tag">Movies on this PC. On your phone use the Wi‑Fi link below, then open titles in <b>VLC</b> for sound.</p>
    <div class="box">
      <h2>Phone link (same Wi‑Fi)</h2>
      {url_html}
      <p style="color:var(--muted);margin:10px 0 0;font-size:.9rem">
        If this page opened on the PC but not the phone: keep Reel.bat running as Administrator,
        and type the link into the phone browser. Not 127.0.0.1.
      </p>
    </div>
    <p class="meta"><strong id="count">{len(movies)}</strong> titles · <span id="folder">{esc(str(STATE["movies_dir"]))}</span></p>
    <div class="toolbar">
      <input id="q" type="search" placeholder="Search…" autocomplete="off"/>
      <button type="button" id="refresh" onclick="location.reload()">Refresh</button>
    </div>
    <div id="grid" class="grid">
      {grid_html}
    </div>
  </div>

  <div id="player">
    <h1 id="play-title" class="brand" style="font-size:2rem">Playing</h1>
    <div class="actions">
      <a id="vlc-link" class="primary" href="#">Open in VLC (audio)</a>
      <button type="button" id="copy-url">Copy URL</button>
      <button type="button" id="play-browser">Try browser</button>
      <button type="button" id="back">← Library</button>
    </div>
    <video id="vid" controls playsinline preload="metadata"></video>
    <p id="play-hint" class="tag"></p>
  </div>
</div>
<script>
const BOOT = {boot_json};
let movies = BOOT.movies || [];
let current = null;
const grid = document.getElementById("grid");
const q = document.getElementById("q");

function esc(s) {{
  return String(s).replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}}[c]));
}}
function rawUrl(m) {{
  const name = (m.rel || "movie").split("/").pop();
  return location.origin + "/raw/" + encodeURIComponent(m.id) + "/" + encodeURIComponent(name);
}}
function render(list) {{
  if (!list.length) {{
    grid.innerHTML = '<div class="empty">No matches.</div>';
    return;
  }}
  grid.innerHTML = list.map(m =>
    `<button type="button" class="tile" data-id="${{esc(m.id)}}" style="width:100%;text-align:left;padding:0;cursor:pointer;font:inherit;color:inherit">` +
    `<div class="poster"><span>${{esc(m.title)}}</span></div>` +
    `<div class="info"><h2>${{esc(m.title)}}</h2>` +
    `<p>${{esc(m.folder || "Movies")}} · ${{esc(m.size_label)}}</p>` +
    `<span class="badge">${{esc(m.ext)}}</span></div></button>`
  ).join("");
  grid.querySelectorAll("button.tile").forEach(btn => {{
    btn.addEventListener("click", () => {{
      const m = movies.find(x => x.id === btn.getAttribute("data-id"));
      if (m) openMovie(m);
    }});
  }});
}}
function openMovie(m) {{
  current = m;
  document.getElementById("play-title").textContent = m.title;
  const raw = rawUrl(m);
  const a = document.getElementById("vlc-link");
  if (/Android/i.test(navigator.userAgent)) {{
    a.href = "intent:" + raw.replace(/^https?:/, "") +
      "#Intent;action=android.intent.action.VIEW;scheme=http;type=video/*;package=org.videolan.vlc;end";
  }} else {{
    a.href = raw;
  }}
  document.getElementById("play-hint").innerHTML =
    "For audio: <b>Open in VLC</b> or paste this in VLC → Network:<br><span class='url'>" + esc(raw) + "</span>";
  document.getElementById("library").classList.add("hide");
  document.getElementById("player").classList.add("show");
  document.getElementById("vid").removeAttribute("src");
}}
document.getElementById("back").onclick = () => {{
  const v = document.getElementById("vid");
  v.pause(); v.removeAttribute("src"); v.load();
  document.getElementById("player").classList.remove("show");
  document.getElementById("library").classList.remove("hide");
}};
document.getElementById("play-browser").onclick = () => {{
  if (!current) return;
  const v = document.getElementById("vid");
  v.src = BOOT.ffmpeg ? ("/play/" + encodeURIComponent(current.id)) : rawUrl(current);
  v.play().catch(() => {{}});
}};
document.getElementById("copy-url").onclick = async () => {{
  if (!current) return;
  const raw = rawUrl(current);
  try {{ await navigator.clipboard.writeText(raw); }} catch (e) {{}}
  document.getElementById("play-hint").textContent = "Copied: " + raw;
}};
q.addEventListener("input", () => {{
  const n = q.value.trim().toLowerCase();
  render(!n ? movies : movies.filter(m =>
    m.title.toLowerCase().includes(n) || (m.rel || "").toLowerCase().includes(n)));
}});
// Enhance SSR anchors into interactive player when JS works
if (movies.length) {{
  render(movies);
}}
</script>
</body>
</html>
"""
    return html.encode("utf-8")


class ThreadingHTTPServerReuse(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class ReelHandler(BaseHTTPRequestHandler):
    server_version = "Reel/1.2"
    protocol_version = "HTTP/1.0"  # simpler for flaky phone stacks

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

        if path in ("/", "/index.html"):
            body = render_html()
            self._send(200, body, "text/html; charset=utf-8")
            return

        if path == "/health":
            self._json(
                200,
                {
                    "ok": True,
                    "movies": len(STATE["index"]),
                    "movies_dir": str(STATE["movies_dir"]),
                    "lan_urls": STATE["lan_urls"],
                },
            )
            return

        if path == "/api/movies":
            if qs.get("refresh", ["0"])[0] in ("1", "true", "yes"):
                refresh_index()
            self._json(
                200,
                {
                    "movies": movies_payload(),
                    "movies_dir": str(STATE["movies_dir"]),
                    "count": len(STATE["index"]),
                    "lan_urls": STATE["lan_urls"],
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
    parser.add_argument("--announce", default="", help="Preferred LAN IP to show phones")
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()

    movies_dir = args.movies.expanduser()
    STATE["movies_dir"] = movies_dir
    STATE["port"] = args.port
    STATE["ffmpeg"] = find_ffmpeg()
    STATE["vlc"] = find_vlc()
    STATE["announce"] = (args.announce or "").strip()
    refresh_index()

    ips = lan_ips()
    if STATE["announce"] and STATE["announce"] not in ips and not STATE["announce"].startswith("REPLACE"):
        ips = [STATE["announce"]] + ips
    STATE["lan_urls"] = [f"http://{ip}:{args.port}/" for ip in ips]

    if not movies_dir.is_dir():
        print(f"WARNING: folder missing: {movies_dir}", file=sys.stderr)
    print(f"Movies folder: {movies_dir}")
    print(f"Videos found:  {len(STATE['index'])}")
    if STATE["index"]:
        for m in list(STATE["index"].values())[:12]:
            print(f"  - {m['rel']}")
        if len(STATE["index"]) > 12:
            print(f"  … +{len(STATE['index']) - 12} more")
    else:
        print("  (none — put .mkv / .mp4 files in the folder above)")

    try:
        httpd = ThreadingHTTPServerReuse((args.host, args.port), ReelHandler)
    except OSError as e:
        print(f"\nERROR: cannot listen on {args.host}:{args.port} — {e}", file=sys.stderr)
        return 1

    # Confirm we are actually listening on all interfaces
    try:
        sockname = httpd.socket.getsockname()
        print(f"Listening:    {sockname[0]}:{sockname[1]}")
    except OSError:
        pass

    phone_txt = Path(__file__).resolve().parent / "PHONE-URL.txt"
    primary = STATE["lan_urls"][0] if STATE["lan_urls"] else f"http://127.0.0.1:{args.port}/"
    try:
        phone_txt.write_text(
            "Open this on your PHONE (same Wi-Fi). Keep Reel.bat running.\n\n"
            + "\n".join(STATE["lan_urls"])
            + "\n\nThen tap a movie -> Open in VLC for audio.\n",
            encoding="utf-8",
        )
    except OSError:
        pass

    print()
    print("================================================")
    print("  ON YOUR PHONE browser open:")
    for u in STATE["lan_urls"]:
        print(f"     {u}")
    print("================================================")
    print("  Test on this PC first:")
    print(f"     http://127.0.0.1:{args.port}/")
    print(f"     http://127.0.0.1:{args.port}/health")
    print("  Movies should list immediately (no login).")
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
