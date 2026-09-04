import { NextRequest, NextResponse } from "next/server";
import {
  authenticateWithPassword,
  createSessionToken,
  sessionCookieOptions,
} from "../../../lib/auth";
import { getSessionCookieName } from "../../../lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let body: { username?: string; password?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const username = String(body.username || "").trim();
  const password = String(body.password || "");
  if (!username || !password) {
    return NextResponse.json(
      { error: "Username and password required." },
      { status: 400 }
    );
  }

  const state = await authenticateWithPassword(username, password);
  if (!state) {
    return NextResponse.json(
      { error: "Wrong username or password." },
      { status: 401 }
    );
  }

  const token = await createSessionToken(username, "viewer");
  const res = NextResponse.json({
    ok: true,
    username: state.username,
    botLabel: state.botLabel,
  });
  res.cookies.set(
    getSessionCookieName(),
    token,
    sessionCookieOptions(60 * 60 * 24 * 7)
  );
  return res;
}
