"use client";

import { FormEvent, useEffect, useState, type CSSProperties } from "react";
import { useRouter } from "next/navigation";

export default function HomePage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [claimed, setClaimed] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/status", { cache: "no-store" });
        const data = await res.json();
        if (cancelled) return;
        setClaimed(Boolean(data.claimed));
        if (data.loggedIn) router.replace("/console");
      } catch {
        if (!cancelled) setClaimed(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Login failed");
        setBusy(false);
        return;
      }
      router.push("/console");
    } catch {
      setError("Could not reach the console.");
      setBusy(false);
    }
  }

  return (
    <main
      style={{
        minHeight: "100dvh",
        display: "grid",
        placeItems: "center",
        padding: "2rem 1.25rem",
        position: "relative",
        zIndex: 1,
      }}
    >
      <section
        className="fade-in"
        style={{
          width: "min(440px, 100%)",
          display: "flex",
          flexDirection: "column",
          gap: "1.35rem",
        }}
      >
        <header style={{ textAlign: "left" }}>
          <p
            style={{
              margin: 0,
              color: "var(--phosphor-dim)",
              letterSpacing: "0.28em",
              fontSize: "0.72rem",
              textTransform: "uppercase",
            }}
          >
            remote · read-only
          </p>
          <h1
            style={{
              margin: "0.35rem 0 0",
              fontFamily: "var(--font-display)",
              fontWeight: 800,
              fontSize: "clamp(2.8rem, 12vw, 4.4rem)",
              lineHeight: 0.92,
              letterSpacing: "-0.04em",
              color: "var(--phosphor)",
              textShadow: "0 0 28px rgba(61,255,122,0.35)",
            }}
          >
            BEACON
          </h1>
          <p
            style={{
              margin: "0.85rem 0 0",
              color: "var(--muted)",
              fontSize: "0.95rem",
              maxWidth: "32ch",
              lineHeight: 1.45,
            }}
          >
            Mirror of your server PC console. View only — no typing, no shell
            access.
          </p>
        </header>

        <form
          onSubmit={onSubmit}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.85rem",
            padding: "1.15rem 0 0",
            borderTop: "1px solid var(--line)",
          }}
        >
          <label style={{ display: "grid", gap: "0.35rem" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
              username
            </span>
            <input
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              style={inputStyle}
            />
          </label>
          <label style={{ display: "grid", gap: "0.35rem" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
              password
            </span>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={inputStyle}
            />
          </label>

          {error ? (
            <p style={{ margin: 0, color: "var(--danger)", fontSize: "0.85rem" }}>
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={busy}
            style={{
              marginTop: "0.35rem",
              border: "1px solid var(--phosphor)",
              background: "rgba(61,255,122,0.12)",
              color: "var(--phosphor)",
              padding: "0.85rem 1rem",
              cursor: busy ? "wait" : "pointer",
              boxShadow: "var(--glow)",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              fontSize: "0.8rem",
              fontWeight: 600,
            }}
          >
            {busy ? "Opening…" : "Open console"}
          </button>
        </form>

        <p style={{ margin: 0, color: "var(--muted)", fontSize: "0.75rem" }}>
          {claimed === null
            ? "Checking link…"
            : claimed
              ? "Bot bridge is linked. Use the username/password you set on the PC."
              : "Not linked yet — run the bridge on your server PC first."}
        </p>
      </section>
    </main>
  );
}

const inputStyle: CSSProperties = {
  width: "100%",
  border: "1px solid var(--line)",
  background: "rgba(0,0,0,0.45)",
  color: "var(--text)",
  padding: "0.75rem 0.85rem",
  outline: "none",
};
