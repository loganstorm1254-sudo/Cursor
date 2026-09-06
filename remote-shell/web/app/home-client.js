"use client";

import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";

function normalizeAgent(url) {
  return url.trim().replace(/\/+$/, "");
}

function toWs(httpBase, path) {
  const u = new URL(httpBase);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.pathname = path;
  u.search = "";
  u.hash = "";
  return u.toString();
}

function connectErrorMessage(err, agentUrl) {
  const raw = (err && err.message) || "Could not reach agent";
  const pageHttps = typeof window !== "undefined" && window.location.protocol === "https:";
  let agentHttp = false;
  try {
    agentHttp = new URL(agentUrl).protocol === "http:";
  } catch {
    /* ignore */
  }
  if (pageHttps && agentHttp) {
    return "Browser blocked login: HTTPS site cannot talk to HTTP agent. Open http://YOUR_IP:7788 in the browser, or put HTTPS on the agent.";
  }
  if (/failed to fetch|networkerror|load failed/i.test(raw)) {
    return "Could not reach agent. On the VPS run: systemctl status beacon-remote";
  }
  return raw;
}

export default function Home() {
  const [mode, setMode] = useState("connect");
  const [agent, setAgent] = useState("");
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [msgKind, setMsgKind] = useState("");
  const [token, setToken] = useState("");

  const hostRef = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    if (mode !== "term" || !token || !agent) return;
    const el = hostRef.current;
    if (!el) return;

    const term = new Terminal({
      cursorBlink: true,
      fontFamily: '"IBM Plex Mono", ui-monospace, monospace',
      fontSize: 14,
      theme: {
        background: "#000000",
        foreground: "#e8edf5",
        cursor: "#3d9cf0",
      },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(el);
    fit.fit();

    const url = `${toWs(normalizeAgent(agent), "/ws/term")}?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => {
      setMsg("Connected");
      setMsgKind("ok");
      const dims = fit.proposeDimensions();
      if (dims) {
        ws.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
      }
    };

    ws.onmessage = (ev) => {
      if (typeof ev.data === "string") {
        try {
          const j = JSON.parse(ev.data);
          if (j.type === "error") {
            setMsg(j.message || "Session error");
            setMsgKind("err");
          }
        } catch {
          term.write(ev.data);
        }
        return;
      }
      term.write(new Uint8Array(ev.data));
    };

    ws.onclose = () => {
      setMsg("Disconnected");
      setMsgKind("err");
    };

    ws.onerror = () => {
      setMsg("WebSocket error");
      setMsgKind("err");
    };

    const onData = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data }));
      }
    });

    const onResize = () => {
      fit.fit();
      const dims = fit.proposeDimensions();
      if (dims && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
      }
    };
    window.addEventListener("resize", onResize);

    return () => {
      onData.dispose();
      window.removeEventListener("resize", onResize);
      ws.close();
      term.dispose();
      wsRef.current = null;
    };
  }, [mode, token, agent]);

  async function connect() {
    setBusy(true);
    setMsg("");
    setMsgKind("");
    try {
      const base = normalizeAgent(agent);
      if (!base || !pin) {
        setMsg("Agent URL and PIN required");
        setMsgKind("err");
        return;
      }
      const res = await fetch(`${base}/api/auth`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg(data.error || "Auth failed");
        setMsgKind("err");
        setPin("");
        return;
      }
      setToken(data.token);
      setPin("");
      setMode("term");
    } catch (e) {
      setMsg(connectErrorMessage(e, normalizeAgent(agent)));
      setMsgKind("err");
    } finally {
      setBusy(false);
    }
  }

  function disconnect() {
    wsRef.current?.close();
    setToken("");
    setMode("connect");
    setMsg("");
    setMsgKind("");
  }

  if (mode === "term") {
    return (
      <div className="term-wrap">
        <div className="bar">
          <h1>Beacon Remote</h1>
          <button type="button" className="btn ghost" onClick={disconnect}>
            Disconnect
          </button>
        </div>
        <div className="term-host" ref={hostRef} />
      </div>
    );
  }

  return (
    <main className="shell">
      <div className="panel">
        <h1 className="brand">Beacon Remote</h1>
        <p className="tag">
          Browser terminal for your Ubuntu box. PIN lives on the server only — never in this site.
        </p>

        <label className="label" htmlFor="agent">
          Agent URL
        </label>
        <input
          id="agent"
          className="field"
          placeholder="http://YOUR_VPS_IP:7788"
          value={agent}
          onChange={(e) => setAgent(e.target.value)}
          autoComplete="off"
          spellCheck={false}
        />

        <label className="label" htmlFor="pin">
          PIN
        </label>
        <input
          id="pin"
          className="field"
          type="password"
          placeholder="Server PIN"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          autoComplete="off"
          onKeyDown={(e) => e.key === "Enter" && connect()}
        />
        <div className="row">
          <button type="button" className="btn" disabled={busy} onClick={connect}>
            Open terminal
          </button>
        </div>

        <p className={`msg ${msgKind}`}>{msg}</p>
        <p className="hint">
          Set the PIN on the VPS with <code>sudo beacon-remote pin-set</code>. PIN is sent once for
          login, then cleared from this page. Nothing is stored in localStorage or cookies.
        </p>
      </div>
    </main>
  );
}
