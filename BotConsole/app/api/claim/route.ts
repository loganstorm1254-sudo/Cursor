import { NextRequest, NextResponse } from "next/server";
import { createSessionToken } from "../../../lib/auth";
import { claimConsole } from "../../../lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Called by the PC bridge on startup.
 * Sets (or re-confirms) the username/password that unlocks the web console.
 */
export async function POST(req: NextRequest) {
  let body: {
    username?: string;
    password?: string;
    botLabel?: string;
    force?: boolean;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const username = String(body.username || "").trim();
  const password = String(body.password || "");
  const result = await claimConsole({
    username,
    password,
    botLabel: body.botLabel,
    force: Boolean(body.force),
  });

  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: 403 });
  }

  const agentToken = await createSessionToken(username, "agent");
  return NextResponse.json({
    ok: true,
    agentToken,
    message: "Console claimed. Use agentToken for push/heartbeat.",
  });
}
