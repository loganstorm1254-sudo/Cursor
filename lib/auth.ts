import { SignJWT, jwtVerify } from "jose";
import { cookies } from "next/headers";
import {
  getSessionCookieName,
  loadState,
  sessionSecret,
  verifyPassword,
  type ConsoleState,
} from "./store";

export type SessionPayload = {
  u: string;
  role: "viewer" | "agent";
};

export async function createSessionToken(
  username: string,
  role: "viewer" | "agent" = "viewer"
): Promise<string> {
  return new SignJWT({ u: username, role })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(role === "agent" ? "30d" : "7d")
    .sign(sessionSecret());
}

export async function readSession(): Promise<SessionPayload | null> {
  const jar = await cookies();
  const token = jar.get(getSessionCookieName())?.value;
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, sessionSecret());
    const u = String(payload.u || "");
    const role = payload.role === "agent" ? "agent" : "viewer";
    if (!u) return null;
    return { u, role };
  } catch {
    return null;
  }
}

export async function verifyAgentBearer(
  authHeader: string | null
): Promise<SessionPayload | null> {
  if (!authHeader?.startsWith("Bearer ")) return null;
  const token = authHeader.slice(7).trim();
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, sessionSecret());
    const u = String(payload.u || "");
    if (!u || payload.role !== "agent") return null;
    return { u, role: "agent" };
  } catch {
    return null;
  }
}

export async function authenticateWithPassword(
  username: string,
  password: string
): Promise<ConsoleState | null> {
  const state = await loadState();
  if (!state) return null;
  if (state.username !== username.trim()) return null;
  if (!verifyPassword(password, state.passwordHash)) return null;
  return state;
}

export function sessionCookieOptions(maxAgeSec: number) {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: maxAgeSec,
  };
}
