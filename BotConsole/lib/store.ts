import { createHash, randomBytes, scryptSync, timingSafeEqual } from "crypto";

const SESSION_COOKIE = "beacon_session";
const AGENT_COOKIE = "beacon_agent"; // not used as cookie; agent bearer token
const MAX_LINES = 2500;
const HEARTBEAT_STALE_MS = 25_000;

export type LogLine = {
  id: number;
  t: number;
  text: string;
};

export type ConsoleState = {
  username: string;
  passwordHash: string; // scrypt encoded
  salt: string;
  lines: LogLine[];
  nextId: number;
  lastHeartbeat: number;
  botLabel: string;
  claimedAt: number;
};

type GlobalStore = {
  state: ConsoleState | null;
};

function g(): GlobalStore {
  const key = "__beacon_console_store__";
  const root = globalThis as typeof globalThis & { [key]?: GlobalStore };
  if (!root[key]) root[key] = { state: null };
  return root[key];
}

function encodeHash(salt: Buffer, hash: Buffer): string {
  return `scrypt$${salt.toString("base64")}$${hash.toString("base64")}`;
}

export function hashPassword(password: string, saltB64?: string): string {
  const salt = saltB64 ? Buffer.from(saltB64, "base64") : randomBytes(16);
  const hash = scryptSync(password, salt, 32, { N: 16384, r: 8, p: 1 });
  return encodeHash(salt, hash);
}

export function verifyPassword(password: string, encoded: string): boolean {
  const parts = encoded.split("$");
  if (parts.length !== 3 || parts[0] !== "scrypt") return false;
  const salt = Buffer.from(parts[1], "base64");
  const expected = Buffer.from(parts[2], "base64");
  const actual = scryptSync(password, salt, expected.length, {
    N: 16384,
    r: 8,
    p: 1,
  });
  if (actual.length !== expected.length) return false;
  return timingSafeEqual(actual, expected);
}

function upstashConfigured(): boolean {
  return Boolean(
    process.env.UPSTASH_REDIS_REST_URL && process.env.UPSTASH_REDIS_REST_TOKEN
  );
}

async function redisCommand(command: (string | number)[]): Promise<unknown> {
  const url = process.env.UPSTASH_REDIS_REST_URL!;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN!;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(command),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Upstash HTTP ${res.status}`);
  const data = (await res.json()) as { result: unknown };
  return data.result;
}

async function redisGet(key: string): Promise<string | null> {
  const result = await redisCommand(["GET", key]);
  return typeof result === "string" ? result : null;
}

async function redisSet(key: string, value: string): Promise<void> {
  await redisCommand(["SET", key, value]);
}

const REDIS_KEY = "beacon:console:state";

export async function loadState(): Promise<ConsoleState | null> {
  if (upstashConfigured()) {
    try {
      const raw = await redisGet(REDIS_KEY);
      if (!raw) return null;
      return JSON.parse(raw) as ConsoleState;
    } catch {
      return g().state;
    }
  }
  return g().state;
}

export async function saveState(state: ConsoleState): Promise<void> {
  g().state = state;
  if (upstashConfigured()) {
    try {
      await redisSet(REDIS_KEY, JSON.stringify(state));
    } catch {
      // memory still holds it for this instance
    }
  }
}

export async function claimConsole(opts: {
  username: string;
  password: string;
  botLabel?: string;
  force?: boolean;
  newPassword?: string;
}): Promise<{ ok: true } | { ok: false; error: string }> {
  const username = opts.username.trim();
  const password = opts.password;
  if (username.length < 2 || username.length > 32) {
    return { ok: false, error: "Username must be 2–32 characters." };
  }
  if (password.length < 4 || password.length > 128) {
    return { ok: false, error: "Password must be 4–128 characters." };
  }

  const existing = await loadState();

  // Same username + password → refresh claim (keep log history)
  if (existing && existing.username === username && verifyPassword(password, existing.passwordHash)) {
    existing.lastHeartbeat = Date.now();
    existing.botLabel = opts.botLabel?.trim() || existing.botLabel;
    await saveState(existing);
    return { ok: true };
  }

  // Already claimed by someone else (or wrong password)
  if (existing) {
    const reset = process.env.CONSOLE_RESET_SECRET || "";
    const canReset =
      opts.force &&
      (verifyPassword(password, existing.passwordHash) ||
        (reset.length > 0 && password === reset));

    if (!canReset) {
      return {
        ok: false,
        error:
          existing.username === username
            ? "Wrong password."
            : "Console already claimed. Reclaim with the current password and force=true, or CONSOLE_RESET_SECRET.",
      };
    }
  }

  const newPass =
    opts.newPassword && opts.newPassword.length >= 4 ? opts.newPassword : password;

  const state: ConsoleState = {
    username,
    passwordHash: hashPassword(newPass),
    salt: "",
    lines: [
      {
        id: 1,
        t: Date.now(),
        text: `[beacon] Console claimed by ${username}. Waiting for bot output…`,
      },
    ],
    nextId: 2,
    lastHeartbeat: Date.now(),
    botLabel: opts.botLabel?.trim() || "smmod",
    claimedAt: Date.now(),
  };
  await saveState(state);
  return { ok: true };
}

export async function appendLines(
  lines: string[],
  botLabel?: string
): Promise<number> {
  const state = await loadState();
  if (!state) return 0;
  const now = Date.now();
  for (const raw of lines) {
    const text = String(raw).replace(/\r/g, "").slice(0, 4000);
    if (!text.length) continue;
    state.lines.push({ id: state.nextId++, t: now, text });
  }
  if (state.lines.length > MAX_LINES) {
    state.lines = state.lines.slice(-MAX_LINES);
  }
  state.lastHeartbeat = now;
  if (botLabel?.trim()) state.botLabel = botLabel.trim();
  await saveState(state);
  return state.lines.length;
}

export async function touchHeartbeat(botLabel?: string): Promise<boolean> {
  const state = await loadState();
  if (!state) return false;
  state.lastHeartbeat = Date.now();
  if (botLabel?.trim()) state.botLabel = botLabel.trim();
  await saveState(state);
  return true;
}

export function isOnline(state: ConsoleState | null): boolean {
  if (!state) return false;
  return Date.now() - state.lastHeartbeat < HEARTBEAT_STALE_MS;
}

export function getSessionCookieName(): string {
  return SESSION_COOKIE;
}

export function sessionSecret(): Uint8Array {
  const raw =
    process.env.SESSION_SECRET ||
    process.env.CONSOLE_RESET_SECRET ||
    "beacon-dev-secret-change-me";
  return createHash("sha256").update(raw).digest();
}

export { AGENT_COOKIE, HEARTBEAT_STALE_MS, MAX_LINES };
