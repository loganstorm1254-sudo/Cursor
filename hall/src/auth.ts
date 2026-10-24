import { HttpError } from "./http";
import { isPlatformOwnerUsername } from "./username";

const SESSION_MS = 30 * 24 * 60 * 60 * 1000;
const PBKDF2_ITERATIONS = 100_000;
const COOKIE = "hall_session";

// Valid format, not the hash of any chosen password. Used so a missing account
// still pays for a full PBKDF2 derivation.
const DUMMY_PASSWORD_HASH = "pbkdf2$100000$AQEBAQEBAQEBAQEBAQEBAQ$AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI";

export type PublicUser = {
  id: string;
  username: string;
  displayName: string;
  bio: string;
  avatarUrl: string | null;
  isPlatformOwner: boolean;
  isBetaTester: boolean;
};

export type UserRow = {
  id: string;
  username: string;
  display_name: string;
  password_hash: string;
  bio: string | null;
  avatar_key: string | null;
  role: string | null;
  beta_tester?: number | null;
};

function bytesToBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function base64UrlToBytes(value: string): Uint8Array {
  const padded = value.replaceAll("-", "+").replaceAll("_", "/") + "===".slice((value.length + 3) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function pbkdf2(password: string, salt: Uint8Array, iterations: number): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt, iterations }, key, 256);
  return new Uint8Array(bits);
}

export async function hashPassword(password: string): Promise<string> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const hash = await pbkdf2(password, salt, PBKDF2_ITERATIONS);
  return `pbkdf2$${PBKDF2_ITERATIONS}$${bytesToBase64Url(salt)}$${bytesToBase64Url(hash)}`;
}

export async function verifyPassword(password: string, stored: string): Promise<boolean> {
  const parts = stored.split("$");
  if (parts.length !== 4 || parts[0] !== "pbkdf2") return false;
  const iterations = Number(parts[1]);
  if (!Number.isInteger(iterations) || iterations < 10_000 || iterations > 2_000_000) return false;
  let salt: Uint8Array;
  let expected: Uint8Array;
  try {
    salt = base64UrlToBytes(parts[2] ?? "");
    expected = base64UrlToBytes(parts[3] ?? "");
  } catch {
    return false;
  }
  if (expected.byteLength !== 32 || salt.byteLength < 8) return false;
  const actual = await pbkdf2(password, salt, iterations);
  return crypto.subtle.timingSafeEqual(actual, expected);
}

function sessionCookie(token: string, request: Request, maxAge: number): string {
  const secure = new URL(request.url).protocol === "https:" ? "; Secure" : "";
  return `${COOKIE}=${token}; HttpOnly; Path=/; SameSite=Lax; Max-Age=${maxAge}${secure}`;
}

export function sessionHeaders(token: string, request: Request): HeadersInit {
  return { "set-cookie": sessionCookie(token, request, SESSION_MS / 1000) };
}

export function clearSessionHeaders(request: Request): HeadersInit {
  return { "set-cookie": sessionCookie("", request, 0) };
}

function readCookie(request: Request): string | null {
  const header = request.headers.get("cookie");
  if (!header) return null;
  for (const part of header.split(";")) {
    const [name, ...rest] = part.trim().split("=");
    if (name === COOKIE) return rest.join("=");
  }
  return null;
}

export function avatarUrlFor(avatarKey: string | null | undefined): string | null {
  if (!avatarKey) return null;
  return `/api/avatars/${encodeURIComponent(avatarKey)}`;
}

export function toPublicUser(row: {
  id: string;
  username: string;
  display_name: string;
  bio?: string | null;
  avatar_key?: string | null;
  role?: string | null;
  beta_tester?: number | null;
}): PublicUser {
  return {
    id: row.id,
    username: row.username,
    displayName: row.display_name,
    bio: row.bio ?? "",
    avatarUrl: avatarUrlFor(row.avatar_key),
    isPlatformOwner: row.role === "owner" || isPlatformOwnerUsername(row.username),
    isBetaTester: Boolean(row.beta_tester),
  };
}

export async function createSession(env: Env, userId: string): Promise<string> {
  const tokenBytes = crypto.getRandomValues(new Uint8Array(32));
  const token = bytesToBase64Url(tokenBytes);
  const tokenHash = await sha256Hex(token);
  const expiresAt = Date.now() + SESSION_MS;
  await env.DB.prepare("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)").bind(tokenHash, userId, expiresAt).run();
  return token;
}

export async function destroySession(env: Env, request: Request): Promise<void> {
  const token = readCookie(request);
  if (!token) return;
  const tokenHash = await sha256Hex(token);
  await env.DB.prepare("DELETE FROM sessions WHERE token_hash = ?").bind(tokenHash).run();
}

const USER_SELECT = `u.id, u.username, u.display_name, u.bio, u.avatar_key, u.role, COALESCE(u.beta_tester, 0) AS beta_tester`;

export async function currentUser(env: Env, request: Request): Promise<PublicUser | null> {
  const token = readCookie(request);
  if (!token) return null;
  const tokenHash = await sha256Hex(token);
  const row = await env.DB.prepare(
    `SELECT ${USER_SELECT}, s.expires_at
     FROM sessions s
     JOIN users u ON u.id = s.user_id
     WHERE s.token_hash = ?`,
  )
    .bind(tokenHash)
    .first<{
      id: string;
      username: string;
      display_name: string;
      bio: string | null;
      avatar_key: string | null;
      role: string | null;
      beta_tester: number | null;
      expires_at: number;
    }>();
  if (!row) return null;
  if (row.expires_at < Date.now()) {
    await env.DB.prepare("DELETE FROM sessions WHERE token_hash = ?").bind(tokenHash).run();
    return null;
  }
  return toPublicUser(row);
}

export async function requireUser(env: Env, request: Request): Promise<PublicUser> {
  const user = await currentUser(env, request);
  if (!user) throw new HttpError(401, "Sign in to continue");
  return user;
}

export async function findUserByUsername(env: Env, username: string): Promise<UserRow | null> {
  return env.DB.prepare(
    `SELECT id, username, display_name, password_hash, bio, avatar_key, role, COALESCE(beta_tester, 0) AS beta_tester FROM users WHERE username = ?`,
  )
    .bind(username)
    .first<UserRow>();
}

export async function findUserById(env: Env, id: string): Promise<UserRow | null> {
  return env.DB.prepare(
    `SELECT id, username, display_name, password_hash, bio, avatar_key, role, COALESCE(beta_tester, 0) AS beta_tester FROM users WHERE id = ?`,
  )
    .bind(id)
    .first<UserRow>();
}

export async function passwordMatches(password: string, stored: string | null): Promise<boolean> {
  return verifyPassword(password, stored ?? DUMMY_PASSWORD_HASH);
}
