"use client";

import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";

function normalizeAgent(url) {
  return url.trim().replace(/\/+$/, "");
}

function wsUrl(httpBase, path) {
  const u = new URL(httpBase);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.pathname = path;
  u.search = "";
  u.hash = "";
  return u.toString();
}

export default function Home() {
  const [mode, setMode] = useState("connect");
  const [agent, setAgent] = useState("");
  const [pin, setPin] = useState("");
  const [currentPin, setCurrentPin] = useState("");
  const [pin2, setPin2] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [msgKind, setMsgKind] = useState("");
  const [token, setToken] = useState("");
  const [pinAlreadySet, setPinAlreadySet] = useState(false);

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

    const url = `${wsUrl(normalizeAgent(agent), "/ws/term")}?token=${encodeURIComponent(token)}`;
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

  async function probePin() {
    const base = normalizeAgent(agent);
    if (!base) return;
    try {
      const res = await fetch(`${base}/health`);
      const data = await res.json();
      setPinAlreadySet(Boolean(data.pin_set));
    } catch {
      /* ignore — connect will show error */
    }
  }

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
      setMsg((e && e.message) || "Could not reach agent");
      setMsgKind("err");
    } finally {
      setBusy(false);
    }
  }

  async function setServerPin() {
    setBusy(true);
    setMsg("");
    setMsgKind("");
    try {
      const base = normalizeAgent(agent);
      if (!base || !pin || pin !== pin2) {
        setMsg(pin !== pin2 ? "PINs do not match" : "Agent URL and PIN required");
        setMsgKind("err");
        return;
      }
      const body = { new_pin: pin };
      if (pinAlreadySet) {
        body.current_pin = currentPin;
      }
      const res = await fetch(`${base}/api/pin-set`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg(data.error || "Could not set PIN");
        setMsgKind("err");
        return;
      }
      setMsg("PIN set on server. Nothing was stored in this website.");
      setMsgKind("ok");
      setPin("");
      setPin2("");
      setCurrentPin("");
      setPinAlreadySet(true);
      setMode("connect");
    } catch (e) {
      setMsg((e && e.message) || "Could not reach agent");
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
          onBlur={probePin}
          autoComplete="off"
          spellCheck={false}
        />

        {mode === "connect" ? (
          <>
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
              <button
                type="button"
                className="btn ghost"
                onClick={() => {
                  probePin();
                  setMode("setpin");
                }}
              >
                Set PIN
              </button>
            </div>
          </>
        ) : (
          <>
            {pinAlreadySet && (
              <>
                <label className="label" htmlFor="pin-current">
                  Current PIN
                </label>
                <input
                  id="pin-current"
                  className="field"
                  type="password"
                  value={currentPin}
                  onChange={(e) => setCurrentPin(e.target.value)}
                  autoComplete="off"
                />
              </>
            )}
            <label className="label" htmlFor="pin-new">
              New PIN
            </label>
            <input
              id="pin-new"
              className="field"
              type="password"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              autoComplete="new-password"
            />
            <label className="label" htmlFor="pin-confirm">
              Confirm PIN
            </label>
            <input
              id="pin-confirm"
              className="field"
              type="password"
              value={pin2}
              onChange={(e) => setPin2(e.target.value)}
              autoComplete="new-password"
            />
            <div className="row">
              <button type="button" className="btn" disabled={busy} onClick={setServerPin}>
                Save PIN on server
              </button>
              <button type="button" className="btn ghost" onClick={() => setMode("connect")}>
                Back
              </button>
            </div>
          </>
        )}

        <p className={`msg ${msgKind}`}>{msg}</p>
        <p className="hint">
          PIN is sent once to your agent, hashed on the server, and cleared from this page. Nothing is
          written to localStorage or cookies.
        </p>
      </div>
    </main>
  );
}
