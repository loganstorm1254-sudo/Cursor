#!/usr/bin/env python3
"""
Seekara Status Agent — runs on the VPS next to pm2.
Exposes http://0.0.0.0:5055/status with online/offline for:
  beacon, capsule, seekdesk
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List

HOST = os.environ.get("SEEKARA_STATUS_HOST", "0.0.0.0")
PORT = int(os.environ.get("SEEKARA_STATUS_PORT", "5055"))
WATCH = [
    name.strip().lower()
    for name in os.environ.get("SEEKARA_STATUS_APPS", "beacon,capsule,seekdesk").split(",")
    if name.strip()
]


def pm2_list() -> List[Dict[str, Any]]:
    pm2 = shutil.which("pm2")
    if not pm2:
        raise RuntimeError("pm2 not found on PATH")
    out = subprocess.check_output([pm2, "jlist"], text=True, timeout=15)
    data = json.loads(out or "[]")
    if not isinstance(data, list):
        raise RuntimeError("unexpected pm2 jlist output")
    return data


def collect_status() -> Dict[str, Any]:
    try:
        procs = pm2_list()
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "host": os.environ.get("SEEKARA_STATUS_PUBLIC_HOST", "13.140.151.124"),
            "services": {
                name: {"name": name, "up": False, "status": "unknown", "detail": str(e)}
                for name in WATCH
            },
        }

    by_name: Dict[str, Dict[str, Any]] = {}
    for proc in procs:
        name = str(proc.get("name") or "").lower()
        if not name:
            continue
        env = proc.get("pm2_env") or {}
        status = str(env.get("status") or "unknown")
        monit = proc.get("monit") or {}
        by_name[name] = {
            "name": name,
            "up": status == "online",
            "status": status,
            "pm_id": proc.get("pm_id"),
            "restarts": env.get("restart_time"),
            "cpu": monit.get("cpu"),
            "memory": monit.get("memory"),
        }

    services = {}
    for name in WATCH:
        if name in by_name:
            services[name] = by_name[name]
        else:
            services[name] = {
                "name": name,
                "up": False,
                "status": "missing",
                "detail": "not found in pm2",
            }

    return {
        "ok": True,
        "host": os.environ.get("SEEKARA_STATUS_PUBLIC_HOST", "13.140.151.124"),
        "services": services,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/health"):
            self._send(200, {"ok": True, "app": "seekara-status-agent"})
            return
        if path == "/status":
            self._send(200, collect_status())
            return
        self._send(404, {"ok": False, "error": "not found"})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Seekara Status Agent on http://{HOST}:{PORT}")
    print(f"Watching: {', '.join(WATCH)}")
    server.serve_forever()


if __name__ == "__main__":
    main()
