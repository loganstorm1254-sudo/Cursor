"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type LogLine = { id: number; t: number; text: string };

export default function ConsolePage() {
  const router = useRouter();
  const [lines, setLines] = useState<LogLine[]>([]);
  const [online, setOnline] = useState(false);
  const [botLabel, setBotLabel] = useState("smmod");
  const [username, setUsername] = useState("");
  const afterRef = useRef(0);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function tick() {
      try {
        const res = await fetch(`/api/logs?after=${afterRef.current}`, {
          cache: "no-store",
        });
        if (res.status === 401 || res.status === 404) {
          router.replace("/");
          return;
        }
        const data = await res.json();
        if (cancelled) return;
        setOnline(Boolean(data.online));
        setBotLabel(data.botLabel || "smmod");
        setUsername(data.username || "");
        if (Array.isArray(data.lines) && data.lines.length) {
          setLines((prev) => {
            const merged =
              afterRef.current === 0 ? data.lines : [...prev, ...data.lines];
            const last = merged[merged.length - 1];
            if (last) afterRef.current = last.id;
            return merged.slice(-2000);
          });
        }
      } catch {
        // keep polling
      }
      if (!cancelled) timer = setTimeout(tick, 900);
    }

    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [router]);

  useEffect(() => {
    if (!stickRef.current) return;
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  async function logout() {
    await fetch("/api/logout", { method: "POST" });
    router.replace("/");
  }

  return (
    <main
      style={{
        minHeight: "100dvh",
        display: "flex",
        flexDirection: "column",
        position: "relative",
        zIndex: 1,
      }}
    >
      <header
        className="fade-in"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "1rem",
          padding: "0.85rem 1.1rem",
          borderBottom: "1px solid var(--line)",
          background: "rgba(5,8,6,0.82)",
          backdropFilter: "blur(8px)",
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: "0.75rem" }}>
          <strong
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "1.35rem",
              letterSpacing: "-0.03em",
              color: "var(--phosphor)",
            }}
          >
            BEACON
          </strong>
          <span style={{ color: "var(--muted)", fontSize: "0.78rem" }}>
            {botLabel}.py · view only
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.9rem" }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.45rem",
              fontSize: "0.75rem",
              color: online ? "var(--phosphor)" : "var(--danger)",
              letterSpacing: "0.06em",
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: online ? "var(--phosphor)" : "var(--danger)",
                animation: online ? "pulse-dot 1.6s infinite" : undefined,
              }}
            />
            {online ? "LIVE" : "OFFLINE"}
          </span>
          <span style={{ color: "var(--muted)", fontSize: "0.75rem" }}>
            {username}
          </span>
          <button
            type="button"
            onClick={logout}
            style={{
              border: "1px solid var(--line)",
              background: "transparent",
              color: "var(--muted)",
              padding: "0.35rem 0.65rem",
              cursor: "pointer",
              fontSize: "0.72rem",
            }}
          >
            Log out
          </button>
        </div>
      </header>

      <div
        ref={scrollerRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stickRef.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 48;
        }}
        style={{
          flex: 1,
          overflow: "auto",
          padding: "1rem 1.1rem 2rem",
          fontSize: "0.86rem",
          lineHeight: 1.45,
          background:
            "linear-gradient(180deg, rgba(0,0,0,0.35), rgba(0,0,0,0.55))",
        }}
        aria-live="polite"
      >
        <div
          style={{
            color: "var(--muted)",
            marginBottom: "0.75rem",
            fontSize: "0.75rem",
          }}
        >
          C:\Windows\System32\cmd.exe — py {botLabel}.py
        </div>
        {lines.map((line) => (
          <div
            key={line.id}
            style={{
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              color: colorFor(line.text),
            }}
          >
            {line.text}
          </div>
        ))}
        <div
          aria-hidden
          style={{
            display: "inline-block",
            width: "0.55ch",
            height: "1.1em",
            background: "var(--phosphor)",
            verticalAlign: "text-bottom",
            marginLeft: 2,
            animation: "blink 1.05s step-end infinite",
          }}
        />
      </div>

      <footer
        style={{
          borderTop: "1px solid var(--line)",
          padding: "0.55rem 1.1rem",
          color: "var(--muted)",
          fontSize: "0.7rem",
          display: "flex",
          justifyContent: "space-between",
          gap: "1rem",
          background: "rgba(5,8,6,0.9)",
        }}
      >
        <span>Read-only mirror · no input · no remote shell</span>
        <span>{lines.length} lines</span>
      </footer>
    </main>
  );
}

function colorFor(text: string): string {
  const t = text.toLowerCase();
  if (t.includes("error") || t.includes("traceback") || t.includes("exception")) {
    return "var(--danger)";
  }
  if (t.includes("warn")) return "var(--amber)";
  if (t.startsWith("[beacon]")) return "var(--phosphor-dim)";
  return "var(--text)";
}
