#!/usr/bin/env python3
"""
Beacon Remote Shell — Ubuntu agent
- PIN lives ONLY on this server (hashed)
- Website never stores the PIN
- Web terminal over WebSocket after PIN auth
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import getpass
import hashlib
import hmac
import json
import os
import pty
import secrets
import select
import signal
import struct
import termios
import time
from pathlib import Path
from typing import Dict, Optional

from aiohttp import WSMsgType, web

APP_NAME = "beacon-remote"
DEFAULT_PORT = 7788
DEFAULT_HOST = "0.0.0.0"

# Data dir: /var/lib/beacon-remote if root, else ~/.beacon-remote
def data_dir() -> Path:
    env = os.environ.get("BEACON_REMOTE_DATA")
    if env:
        p = Path(env)
    elif os.geteuid() == 0:
        p = Path("/var/lib/beacon-remote")
    else:
        p = Path.home() / ".beacon-remote"
    p.mkdir(parents=True, exist_ok=True)
    return p


def pin_path() -> Path:
    return data_dir() / "pin.pbkdf2"


def secret_path() -> Path:
    return data_dir() / "session.secret"


def hash_pin(pin: str, salt: Optional[bytes] = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 200_000)
    return f"pbkdf2_sha256$200000${salt.hex()}${digest.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        algo, rounds_s, salt_hex, digest_hex = stored.strip().split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        rounds = int(rounds_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        got = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, rounds)
        return hmac.compare_digest(got, expected)
    except Exception:
        return False


def load_pin_hash() -> Optional[str]:
    p = pin_path()
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8").strip() or None


def save_pin_hash(pin: str) -> None:
    pin = pin.strip()
    if len(pin) < 4:
        raise SystemExit("PIN must be at least 4 characters")
    pin_path().write_text(hash_pin(pin) + "\n", encoding="utf-8")
    os.chmod(pin_path(), 0o600)


def session_secret() -> bytes:
    p = secret_path()
    if p.exists():
        return bytes.fromhex(p.read_text(encoding="utf-8").strip())
    raw = secrets.token_bytes(32)
    p.write_text(raw.hex() + "\n", encoding="utf-8")
    os.chmod(p, 0o600)
    return raw


def make_token(secret: bytes, ttl: int = 3600) -> str:
    exp = int(time.time()) + ttl
    nonce = secrets.token_hex(8)
    body = f"{exp}.{nonce}".encode()
    sig = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return f"{exp}.{nonce}.{sig}"


def check_token(secret: bytes, token: str) -> bool:
    try:
        exp_s, nonce, sig = token.split(".", 2)
        exp = int(exp_s)
        if exp < int(time.time()):
            return False
        body = f"{exp}.{nonce}".encode()
        expect = hmac.new(secret, body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expect, sig)
    except Exception:
        return False


# brute-force protection
_fails: Dict[str, list] = {}


def rate_limited(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _fails.get(ip, []) if now - t < 300]
    _fails[ip] = hits
    return len(hits) >= 8


def record_fail(ip: str) -> None:
    _fails.setdefault(ip, []).append(time.time())


def cors_headers(request: web.Request) -> dict:
    origin = request.headers.get("Origin", "*")
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }


async def handle_options(request: web.Request) -> web.Response:
    return web.Response(status=204, headers=cors_headers(request))


async def handle_health(request: web.Request) -> web.Response:
    has_pin = load_pin_hash() is not None
    body = {"ok": True, "app": APP_NAME, "pin_set": has_pin}
    return web.json_response(body, headers=cors_headers(request))


async def handle_auth(request: web.Request) -> web.Response:
    ip = request.remote or "unknown"
    if rate_limited(ip):
        return web.json_response(
            {"ok": False, "error": "too many attempts — wait 5 minutes"},
            status=429,
            headers=cors_headers(request),
        )

    try:
        data = await request.json()
    except Exception:
        return web.json_response(
            {"ok": False, "error": "invalid json"},
            status=400,
            headers=cors_headers(request),
        )

    pin = str(data.get("pin", ""))
    stored = load_pin_hash()
    if stored is None:
        return web.json_response(
            {"ok": False, "error": "PIN not set on server. Run: beacon-remote pin-set"},
            status=400,
            headers=cors_headers(request),
        )

    if not verify_pin(pin, stored):
        record_fail(ip)
        return web.json_response(
            {"ok": False, "error": "wrong PIN"},
            status=401,
            headers=cors_headers(request),
        )

    token = make_token(request.app["secret"], ttl=6 * 3600)
    return web.json_response(
        {"ok": True, "token": token, "expires_in": 6 * 3600},
        headers=cors_headers(request),
    )


async def handle_pin_set(request: web.Request) -> web.Response:
    """
    Set / change PIN on the server.
    - If no PIN exists yet: body { "new_pin": "...." }
    - If PIN exists: body { "current_pin": "...", "new_pin": "...." }
    Website must NOT store either value.
    """
    ip = request.remote or "unknown"
    if rate_limited(ip):
        return web.json_response(
            {"ok": False, "error": "too many attempts — wait 5 minutes"},
            status=429,
            headers=cors_headers(request),
        )

    try:
        data = await request.json()
    except Exception:
        return web.json_response(
            {"ok": False, "error": "invalid json"},
            status=400,
            headers=cors_headers(request),
        )

    new_pin = str(data.get("new_pin") or data.get("pin") or "").strip()
    if len(new_pin) < 4:
        return web.json_response(
            {"ok": False, "error": "new PIN must be at least 4 characters"},
            status=400,
            headers=cors_headers(request),
        )

    stored = load_pin_hash()
    if stored is None:
        save_pin_hash(new_pin)
        return web.json_response(
            {"ok": True, "message": "PIN set. It is stored only on the server."},
            headers=cors_headers(request),
        )

    current = str(data.get("current_pin", ""))
    if not verify_pin(current, stored):
        record_fail(ip)
        return web.json_response(
            {"ok": False, "error": "wrong current PIN"},
            status=401,
            headers=cors_headers(request),
        )

    save_pin_hash(new_pin)
    return web.json_response(
        {"ok": True, "message": "PIN updated. Old PIN no longer works."},
        headers=cors_headers(request),
    )


async def _pty_reader(master_fd: int, ws: web.WebSocketResponse):
    loop = asyncio.get_running_loop()
    try:
        while not ws.closed:
            ready = await loop.run_in_executor(
                None, lambda: select.select([master_fd], [], [], 0.2)
            )
            if master_fd in ready[0]:
                try:
                    data = os.read(master_fd, 8192)
                except OSError:
                    break
                if not data:
                    break
                await ws.send_bytes(data)
    except Exception:
        pass
    finally:
        if not ws.closed:
            await ws.close()


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    try:
        winsize = struct.pack("HHHH", max(1, rows), max(1, cols), 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
    except Exception:
        pass


async def handle_term_ws(request: web.Request) -> web.WebSocketResponse:
    token = request.query.get("token", "")
    if not check_token(request.app["secret"], token):
        return web.Response(status=401, text="unauthorized")

    ws = web.WebSocketResponse(heartbeat=30, max_msg_size=2 * 1024 * 1024)
    await ws.prepare(request)

    shell = os.environ.get("SHELL") or "/bin/bash"
    pid, master_fd = pty.fork()
    if pid == 0:
        # child
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["BEACON_REMOTE"] = "1"
        os.chdir(os.path.expanduser("~"))
        try:
            os.execvpe(shell, [shell, "-l"], env)
        except Exception:
            os._exit(1)

    # parent
    reader_task = asyncio.create_task(_pty_reader(master_fd, ws))
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                except Exception:
                    # treat as raw input
                    os.write(master_fd, msg.data.encode("utf-8", errors="ignore"))
                    continue
                typ = payload.get("type")
                if typ == "input":
                    data = payload.get("data", "")
                    if isinstance(data, str) and data:
                        os.write(master_fd, data.encode("utf-8", errors="ignore"))
                elif typ == "resize":
                    rows = int(payload.get("rows") or 24)
                    cols = int(payload.get("cols") or 80)
                    _set_winsize(master_fd, rows, cols)
            elif msg.type == WSMsgType.BINARY:
                if msg.data:
                    os.write(master_fd, msg.data)
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                break
    finally:
        reader_task.cancel()
        try:
            os.close(master_fd)
        except Exception:
            pass
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    return ws


def build_app(secret: bytes) -> web.Application:
    app = web.Application()
    app["secret"] = secret
    app.router.add_route("OPTIONS", "/{path:.*}", handle_options)
    app.router.add_get("/health", handle_health)
    app.router.add_post("/api/auth", handle_auth)
    app.router.add_post("/api/pin-set", handle_pin_set)
    app.router.add_get("/ws/term", handle_term_ws)
    return app


def cmd_pin_set(_: argparse.Namespace) -> None:
    print("Set Beacon Remote PIN (stored hashed on this server only).")
    pin1 = getpass.getpass("New PIN: ")
    pin2 = getpass.getpass("Confirm PIN: ")
    if pin1 != pin2:
        raise SystemExit("PINs do not match")
    save_pin_hash(pin1)
    print(f"PIN saved to {pin_path()}")
    print("The website never stores this PIN.")


def cmd_serve(args: argparse.Namespace) -> None:
    secret = session_secret()
    app = build_app(secret)
    host = args.host
    port = args.port
    has_pin = load_pin_hash() is not None
    print(f"Beacon Remote listening on http://{host}:{port}")
    print(f"PIN set: {has_pin}")
    if not has_pin:
        print("WARNING: no PIN yet. Run: beacon-remote pin-set")
        print("Or open the website Set PIN page (first-time only).")
    web.run_app(app, host=host, port=port, print=None)


def main() -> None:
    parser = argparse.ArgumentParser(prog="beacon-remote")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_serve = sub.add_parser("serve", help="Start remote shell agent")
    p_serve.add_argument("--host", default=os.environ.get("BEACON_REMOTE_HOST", DEFAULT_HOST))
    p_serve.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("BEACON_REMOTE_PORT", DEFAULT_PORT)),
    )
    p_serve.set_defaults(func=cmd_serve)

    p_pin = sub.add_parser("pin-set", help="Set / change PIN (server-side only)")
    p_pin.set_defaults(func=cmd_pin_set)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
