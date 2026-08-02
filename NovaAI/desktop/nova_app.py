"""
Nova for Windows — local chat UI for the same from-scratch neural network.

Stdlib only. Starts a tiny localhost server and opens your browser.
First run downloads the encrypted model from GitHub; unlock with your
master API key (sk-nova-m00ny4xe or the long key).
"""
from __future__ import annotations

import json
import os
import random
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Resolve sibling bot3.py (repo root, or next to this file in the Windows bundle)
HERE = os.path.dirname(os.path.abspath(__file__))
for candidate in (HERE, os.path.join(HERE, "..", ".."), os.path.dirname(HERE)):
    if os.path.exists(os.path.join(candidate, "bot3.py")):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
        break

import bot3  # noqa: E402


STATE = {
    "engine": None,
    "session": None,
    "rng": random.Random(),
    "status": "locked",  # locked | loading | ready | error
    "message": "Enter your master API key to unlock Nova.",
}


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Nova AI</title>
<style>
  :root {
    --bg0: #0e1218;
    --bg1: #171d27;
    --bg2: #222b38;
    --line: #2e3a4d;
    --text: #e8eef7;
    --muted: #8b9bb2;
    --accent: #3d9cf0;
    --accent2: #1f6fbf;
    --user: #243044;
    --bot: #1a2433;
    --danger: #e35d6a;
    --ok: #3ecf8e;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    font-family: "Segoe UI", "Candara", "Calibri", sans-serif;
    background:
      radial-gradient(1200px 600px at 10% -10%, #1a3355 0%, transparent 55%),
      radial-gradient(900px 500px at 100% 0%, #13283f 0%, transparent 50%),
      var(--bg0);
    color: var(--text);
  }
  .wrap { max-width: 820px; margin: 0 auto; min-height: 100%; display: flex; flex-direction: column; padding: 20px; }
  header { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
  .brand { font-size: 1.8rem; font-weight: 700; letter-spacing: 0.02em; }
  .brand span { color: var(--accent); }
  .sub { color: var(--muted); font-size: 0.92rem; }
  #lock, #chat { flex: 1; display: none; flex-direction: column; }
  #lock.show, #chat.show { display: flex; }
  .card {
    background: linear-gradient(180deg, var(--bg1), #121821);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 28px;
    box-shadow: 0 20px 50px rgba(0,0,0,0.35);
  }
  label { display: block; color: var(--muted); margin-bottom: 8px; font-size: 0.9rem; }
  input[type=password], input[type=text], #msg {
    width: 100%;
    background: var(--bg0);
    border: 1px solid var(--line);
    color: var(--text);
    border-radius: 10px;
    padding: 12px 14px;
    font-size: 1rem;
    outline: none;
  }
  input:focus, #msg:focus { border-color: var(--accent); }
  .row { display: flex; gap: 10px; margin-top: 14px; }
  button {
    background: linear-gradient(180deg, var(--accent), var(--accent2));
    color: white; border: 0; border-radius: 10px; padding: 12px 18px;
    font-weight: 600; cursor: pointer; font-size: 0.95rem;
  }
  button.secondary { background: var(--bg2); border: 1px solid var(--line); }
  button:disabled { opacity: 0.5; cursor: wait; }
  #lockErr { color: var(--danger); min-height: 1.2em; margin-top: 10px; }
  #msgs {
    flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 10px;
    padding: 8px 2px 16px; min-height: 50vh; max-height: calc(100vh - 180px);
  }
  .bubble {
    max-width: 85%; padding: 12px 14px; border-radius: 14px; line-height: 1.45;
    white-space: pre-wrap; word-wrap: break-word; border: 1px solid var(--line);
  }
  .bubble.user { align-self: flex-end; background: var(--user); }
  .bubble.bot { align-self: flex-start; background: var(--bot); }
  .bubble.sys { align-self: center; background: transparent; border: 0; color: var(--muted); font-size: 0.9rem; }
  .composer { display: flex; gap: 10px; margin-top: auto; }
  #msg { flex: 1; resize: none; min-height: 48px; font-family: inherit; }
  .toolbar { display: flex; gap: 8px; margin-bottom: 8px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <div class="brand">✦ <span>Nova</span></div>
      <div class="sub">Your own AI · trained from scratch · runs on this PC</div>
    </div>
    <div class="sub" id="statusLine">locked</div>
  </header>

  <section id="lock" class="card show">
    <label for="key">Master API key</label>
    <input id="key" type="password" placeholder="sk-nova-m00ny4xe" autocomplete="off"/>
    <div class="row">
      <button id="unlockBtn" onclick="unlock()">Unlock Nova</button>
    </div>
    <div id="lockErr"></div>
    <p class="sub" style="margin-top:18px">
      On first unlock Nova downloads her brain (~11 MB) from GitHub, then works offline.
      Same key as the Android app and Discord bot.
    </p>
  </section>

  <section id="chat">
    <div class="toolbar">
      <button class="secondary" onclick="clearChat()">Clear chat</button>
      <button class="secondary" onclick="lockAgain()">Lock</button>
    </div>
    <div id="msgs"></div>
    <div class="composer">
      <textarea id="msg" rows="2" placeholder="Message Nova…" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send();}"></textarea>
      <button id="sendBtn" onclick="send()">Send</button>
    </div>
  </section>
</div>
<script>
const msgs = document.getElementById('msgs');
function bubble(text, cls) {
  const d = document.createElement('div');
  d.className = 'bubble ' + cls;
  d.textContent = text;
  msgs.appendChild(d);
  msgs.scrollTop = msgs.scrollHeight;
}
async function unlock() {
  const key = document.getElementById('key').value.trim();
  const err = document.getElementById('lockErr');
  const btn = document.getElementById('unlockBtn');
  err.textContent = '';
  if (!key) { err.textContent = 'Please enter your master API key.'; return; }
  btn.disabled = true; btn.textContent = 'Unlocking…';
  document.getElementById('statusLine').textContent = 'loading model…';
  try {
    const r = await fetch('/api/unlock', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({key})});
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || 'Wrong key');
    document.getElementById('lock').classList.remove('show');
    document.getElementById('chat').classList.add('show');
    document.getElementById('statusLine').textContent = j.info || 'ready';
    msgs.innerHTML = '';
    bubble(j.welcome || 'Hello! I am Nova.', 'bot');
  } catch (e) {
    err.textContent = e.message;
    document.getElementById('statusLine').textContent = 'locked';
  } finally {
    btn.disabled = false; btn.textContent = 'Unlock Nova';
  }
}
async function send() {
  const box = document.getElementById('msg');
  const text = box.value.trim();
  if (!text) return;
  box.value = '';
  bubble(text, 'user');
  const btn = document.getElementById('sendBtn');
  btn.disabled = true;
  const thinking = document.createElement('div');
  thinking.className = 'bubble bot';
  thinking.textContent = '…';
  msgs.appendChild(thinking);
  try {
    const r = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text})});
    const j = await r.json();
    thinking.textContent = j.ok ? j.reply : (j.error || 'Something went wrong.');
  } catch (e) {
    thinking.textContent = e.message;
  } finally {
    btn.disabled = false;
    msgs.scrollTop = msgs.scrollHeight;
    box.focus();
  }
}
async function clearChat() {
  await fetch('/api/clear', {method:'POST'});
  msgs.innerHTML = '';
  bubble('Fresh start — I forgot our chat.', 'sys');
}
function lockAgain() {
  location.reload();
}
</script>
</body>
</html>
"""


def unlock(key: str) -> dict:
    STATE["status"] = "loading"
    STATE["message"] = "Downloading / unlocking model…"
    try:
        # fetch once (cached next to bot3 / cwd)
        blob = bot3.fetch_model()
        data = bot3.decrypt_model(key, blob)
        if data is None:
            STATE["status"] = "locked"
            return {"ok": False, "error": "Wrong master API key — the model cannot be decrypted."}
        payload = __import__("zlib").decompress(data)
        clen = int.from_bytes(payload[:4], "little")
        config = payload[4:4 + clen].decode()
        engine = bot3.NovaEngine(config, payload[4 + clen:])
        STATE["engine"] = engine
        STATE["session"] = bot3.ChatSession(engine)
        STATE["status"] = "ready"
        info = (f"{engine.n_layer}L · {engine.n_embd}d · "
                f"{len(engine.vocab)} vocab · ready")
        welcome = (
            "Hello! I am Nova, your own personal AI, trained from scratch. "
            "Ask me for a joke, a story, math, capitals, spelling — or anything "
            "and I will check Wikipedia when I need to."
        )
        return {"ok": True, "info": info, "welcome": welcome}
    except SystemExit as e:
        STATE["status"] = "error"
        return {"ok": False, "error": str(e)}
    except Exception as e:
        STATE["status"] = "error"
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def chat(text: str) -> dict:
    engine = STATE["engine"]
    session = STATE["session"]
    if engine is None or session is None:
        return {"ok": False, "error": "Nova is locked."}
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "Empty message."}
    try:
        math = bot3.try_math(text)
        if math is not None:
            session.note(math.rstrip("."))
            return {"ok": True, "reply": math[0].upper() + math[1:]}

        subject = bot3.wiki_subject(text, engine.knows_word)
        if subject is not None:
            res = bot3.wiki_lookup_sync(subject)
            if res is not None:
                title, extract = res
                session.note("i looked that up on wikipedia for you .")
                return {"ok": True, "reply": f"📖 {title}\n\n{extract}\n\n— from Wikipedia"}

        out = session.reply(text, STATE["rng"])
        if not out:
            return {"ok": True, "reply": "Hmm, I am not sure what to say. Try a joke or a fact!"}
        return {"ok": True, "reply": engine.decode(out)}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
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

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._html()
        elif self.path == "/api/status":
            self._json(200, {"status": STATE["status"], "message": STATE["message"]})
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return self._json(400, {"ok": False, "error": "bad json"})

        if self.path == "/api/unlock":
            return self._json(200, unlock(str(data.get("key") or "")))
        if self.path == "/api/chat":
            return self._json(200, chat(str(data.get("text") or "")))
        if self.path == "/api/clear":
            if STATE["engine"] is not None:
                STATE["session"] = bot3.ChatSession(STATE["engine"])
            return self._json(200, {"ok": True})
        self.send_error(404)


def main():
    # Prefer a fixed port so refresh works; fall back if busy.
    port = int(os.environ.get("NOVA_PORT", "8765"))
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = httpd.server_address[1]

    url = f"http://127.0.0.1:{port}/"
    print(f"Nova is running at {url}")
    print("Leave this window open while you chat. Close it to quit.")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBye!")


if __name__ == "__main__":
    main()
