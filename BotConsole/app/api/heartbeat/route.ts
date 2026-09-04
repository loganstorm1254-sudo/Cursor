import { NextRequest, NextResponse } from "next/server";
import {
  authenticateWithPassword,
  verifyAgentBearer,
} from "../../../lib/auth";
import { loadState, touchHeartbeat } from "../../../lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let body: {
    username?: string;
    password?: string;
    botLabel?: string;
  } = {};
  try {
    body = await req.json();
  } catch {
    // empty body ok if bearer present
  }

  const bearer = await verifyAgentBearer(req.headers.get("authorization"));
  let ok = false;
  if (bearer) {
    const state = await loadState();
    ok = Boolean(state && state.username === bearer.u);
  } else {
    ok = Boolean(
      await authenticateWithPassword(
        String(body.username || "").trim(),
        String(body.password || "")
      )
    );
  }

  if (!ok) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  await touchHeartbeat(body.botLabel);
  return NextResponse.json({ ok: true });
}
