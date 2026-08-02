#!/usr/bin/env python3
"""
Reel — stream MKVs and MP4s from your Movies folder over Wi‑Fi.

Stdlib only. Run on the PC that has the movies (default D:\\Movies),
then open the printed URL on any phone/laptop on the same Wi‑Fi.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import socket
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
    "index": {},  # id -> {id, title, path, rel, size, ext, mtime}
}


def default_movies_dir() -> Path:
    env = os.environ.get("REEL_MOVIES_DIR")
    if env:
        return Path(env)
    # Windows D: drive first; fall back for other OSes / testing
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


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def movie_id(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode("utf-8", "replace")).hexdigest()[:16]


def pretty_title(path: Path) -> str:
    name = path.stem
    name = re.sub(r"[._]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or path.name


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return f"{n} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def scan_movies(root: Path) -> dict:
    index = {}
    if not root.is_dir():
        return index
    for dirpath, dirnames, filenames in os.walk(root):
        # skip junk / hidden folders
        dirnames[:] = [
            d for d in dirnames if not d.startswith(".") and d.lower() not in {"@eadir", "system volume information"}
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
    root = STATE["movies_dir"]
    STATE["index"] = scan_movies(root)


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
  body::before {
    content: "";
    pointer-events: none;
    position: fixed;
    inset: 0;
    opacity: 0.04;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
    z-index: 0;
  }
  .shell { position: relative; z-index: 1; max-width: 1100px; margin: 0 auto; padding: 28px 20px 80px; }
  header.hero {
    min-height: min(52vh, 420px);
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    gap: 10px;
    margin-bottom: 28px;
    padding-bottom: 8px;
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
  .brand em {
    font-style: normal;
    color: var(--gold);
  }
  .tagline {
    margin: 0;
    max-width: 28rem;
    color: var(--muted);
    font-size: 1.05rem;
    line-height: 1.45;
  }
  .meta-row {
    display: flex;
    flex-wrap: wrap;
    gap: 10px 16px;
    align-items: center;
    margin-top: 6px;
    color: var(--muted);
    font-size: 0.92rem;
  }
  .meta-row strong { color: var(--text); font-weight: 600; }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--gold); display: inline-block; animation: pulse 2.2s ease-in-out infinite; }
  .toolbar {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin: 8px 0 22px;
    animation: rise 0.7s ease-out 0.1s both;
  }
  #q {
    flex: 1 1 220px;
    min-width: 0;
    background: var(--panel);
    border: 1px solid var(--line);
    color: var(--text);
    border-radius: 10px;
    padding: 12px 14px;
    font: inherit;
    font-size: 1rem;
    outline: none;
  }
  #q:focus { border-color: var(--gold-dim); box-shadow: 0 0 0 3px var(--haze); }
  button, .btn {
    font: inherit;
    font-weight: 600;
    border: 1px solid var(--line);
    background: var(--panel2);
    color: var(--text);
    border-radius: 10px;
    padding: 12px 16px;
    cursor: pointer;
  }
  button.primary, .btn.primary {
    background: linear-gradient(180deg, #f0b85a, var(--gold-dim));
    border-color: transparent;
    color: #1a1206;
  }
  button:hover, .btn:hover { filter: brightness(1.06); }
  button:active, .btn:active { transform: translateY(1px); }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 14px;
    animation: rise 0.75s ease-out 0.18s both;
  }
  .tile {
    text-align: left;
    padding: 0;
    overflow: hidden;
    background: linear-gradient(165deg, var(--panel2), var(--panel));
    border: 1px solid var(--line);
    border-radius: 14px;
    transition: border-color 0.2s, transform 0.2s;
  }
  .tile:hover { border-color: #4a3d2a; transform: translateY(-2px); }
  .poster {
    height: 120px;
    display: flex;
    align-items: flex-end;
    padding: 14px;
    background:
      linear-gradient(180deg, transparent 20%, rgba(12,11,10,0.85) 100%),
      linear-gradient(135deg, #3a2d18 0%, #1a1510 55%, #241c12 100%);
    font-family: "Syne", sans-serif;
    font-weight: 700;
    font-size: 1.55rem;
    letter-spacing: -0.02em;
    line-height: 1.1;
  }
  .poster span { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .info { padding: 12px 14px 14px; }
  .info h2 {
    font-family: "Syne", sans-serif;
    font-size: 1.05rem;
    font-weight: 700;
    margin: 0 0 6px;
    line-height: 1.25;
  }
  .info p { margin: 0; color: var(--muted); font-size: 0.86rem; }
  .badge {
    display: inline-block;
    margin-top: 8px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--gold);
    border: 1px solid #4a3d2a;
    padding: 3px 7px;
    border-radius: 6px;
  }
  .empty, .error {
    padding: 28px 8px;
    color: var(--muted);
    text-align: center;
  }
  .error { color: var(--danger); }
  #player-view { display: none; }
  #player-view.show { display: block; animation: rise 0.45s ease-out both; }
  #library-view.hide { display: none; }
  .player-head {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
  }
  .player-head h1 {
    font-family: "Syne", sans-serif;
    font-size: clamp(1.4rem, 4vw, 2rem);
    margin: 0;
    letter-spacing: -0.02em;
  }
  video {
    width: 100%;
    max-height: min(70vh, 720px);
    background: #000;
    border-radius: 12px;
    border: 1px solid var(--line);
    outline: none;
  }
  .hint {
    margin-top: 12px;
    color: var(--muted);
    font-size: 0.88rem;
  }
  @keyframes rise {
    from { opacity: 0; transform: translateY(14px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes pulse {
    0%, 100% { opacity: 0.45; }
    50% { opacity: 1; }
  }
  @media (max-width: 560px) {
    .shell { padding: 18px 14px 64px; }
    header.hero { min-height: auto; margin-bottom: 18px; }
    .poster { height: 100px; }
  }
</style>
</head>
<body>
  <div class="shell">
    <div id="library-view">
      <header class="hero">
        <h1 class="brand">Re<em>el</em></h1>
        <p class="tagline">Your movies folder, streaming over Wi‑Fi — open this page from any phone on the same network.</p>
        <div class="meta-row">
          <span class="dot" aria-hidden="true"></span>
          <span><strong id="count">0</strong> titles</span>
          <span id="folder-label">…</span>
        </div>
      </header>
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
const q = document.getElementById("q");
const libraryView = document.getElementById("library-view");
const playerView = document.getElementById("player-view");
const vid = document.getElementById("vid");
const playTitle = document.getElementById("play-title");
const playHint = document.getElementById("play-hint");

let movies = [];

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

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
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
    countEl.textContent = String(movies.length);
    folderLabel.textContent = data.movies_dir || "";
    filter();
  } catch (e) {
    err.hidden = false;
    err.textContent = e.message || String(e);
  }
}

function openMovie(m) {
  playTitle.textContent = m.title;
  const typeHint = m.ext === "MKV"
    ? "MKV: works best in Chrome/Edge when the video is H.264. If playback fails, remux to MP4."
    : "Tip: scrubbing uses HTTP range requests — seek freely.";
  playHint.textContent = `${m.rel} · ${m.size_label}. ${typeHint}`;
  vid.src = `/stream/${encodeURIComponent(m.id)}`;
  libraryView.classList.add("hide");
  playerView.classList.add("show");
  vid.play().catch(() => {});
}

function closePlayer() {
  vid.pause();
  vid.removeAttribute("src");
  vid.load();
  playerView.classList.remove("show");
  libraryView.classList.remove("hide");
}

document.getElementById("refresh").addEventListener("click", load);
document.getElementById("back").addEventListener("click", closePlayer);
q.addEventListener("input", filter);
load();
</script>
</body>
</html>
"""


class ReelHandler(BaseHTTPRequestHandler):
    server_version = "Reel/1.0"

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
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, data, "application/json; charset=utf-8")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range")
        self.end_headers()

    def do_HEAD(self) -> None:
        self._route(head_only=True)

    def do_GET(self) -> None:
        self._route(head_only=False)

    def _route(self, head_only: bool) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            body = HTML.encode("utf-8")
            self._send(200, body, "text/html; charset=utf-8")
            return

        if path == "/api/movies":
            if qs.get("refresh", ["0"])[0] in ("1", "true", "yes"):
                refresh_index()
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
                },
            )
            return

        if path.startswith("/stream/"):
            mid = urllib.parse.unquote(path[len("/stream/") :])
            self._stream(mid, head_only=head_only)
            return

        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def _stream(self, mid: str, head_only: bool) -> None:
        meta = STATE["index"].get(mid)
        if not meta:
            # maybe library was refreshed / new file
            refresh_index()
            meta = STATE["index"].get(mid)
        if not meta:
            self._send(404, b"Movie not found", "text/plain; charset=utf-8")
            return

        path = Path(meta["path"])
        if not path.is_file():
            self._send(404, b"File missing on disk", "text/plain; charset=utf-8")
            return

        # stay inside movies dir
        try:
            path.resolve().relative_to(Path(STATE["movies_dir"]).resolve())
        except ValueError:
            self._send(403, b"Forbidden", "text/plain; charset=utf-8")
            return

        ext = path.suffix.lower()
        ctype = MIME.get(ext) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        size = path.stat().st_size
        range_header = self.headers.get("Range")

        if range_header:
            m = re.match(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not m:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            start_s, end_s = m.group(1), m.group(2)
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else size - 1
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Reel — stream local movies over Wi‑Fi")
    parser.add_argument(
        "--movies",
        "-m",
        type=Path,
        default=default_movies_dir(),
        help=r"Movies folder (default: D:\Movies or REEL_MOVIES_DIR)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default 0.0.0.0 for Wi‑Fi)")
    parser.add_argument("--port", "-p", type=int, default=8080, help="Port (default 8080)")
    parser.add_argument("--open", action="store_true", help="Open the library in your browser")
    args = parser.parse_args()

    movies_dir = args.movies.expanduser()
    STATE["movies_dir"] = movies_dir
    refresh_index()

    if not movies_dir.is_dir():
        print(f"Movies folder not found yet: {movies_dir}", file=sys.stderr)
        print("Create it (or pass --movies PATH). Server will still start.", file=sys.stderr)
    else:
        print(f"Scanning: {movies_dir}")
        print(f"Found {len(STATE['index'])} video(s) (.mp4 / .mkv / …)")

    httpd = ThreadingHTTPServer((args.host, args.port), ReelHandler)
    ip = local_ip()
    print()
    print("  Reel is live on your Wi‑Fi")
    print(f"  This PC:     http://127.0.0.1:{args.port}/")
    print(f"  Phones/TV:   http://{ip}:{args.port}/")
    print()
    print("  Keep this window open while watching. Ctrl+C to stop.")
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
