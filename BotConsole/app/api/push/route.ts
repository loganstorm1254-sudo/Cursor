import { NextRequest, NextResponse } from "next/server";
import {
  authenticateWithPassword,
  verifyAgentBearer,
} from "../../../lib/auth";
import { appendLines, loadState } from "../../../lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * PC bridge pushes console lines here. Read-only replication — no commands.
 */
export async function POST(req: NextRequest) {
  let body: {
    username?: string;
    password?: string;
    lines?: string[];
    botLabel?: string;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const bearer = await verifyAgentBearer(req.headers.get("authorization"));
  let ok = false;
  if (bearer) {
    const state = await loadState();
    ok = Boolean(state && state.username === bearer.u);
  } else {
    const username = String(body.username || "").trim();
    const password = String(body.password || "");
    ok = Boolean(await authenticateWithPassword(username, password));
  }

  if (!ok) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const lines = Array.isArray(body.lines) ? body.lines.map(String) : [];
  if (lines.length > 200) {
    return NextResponse.json(
      { error: "Max 200 lines per push." },
      { status: 400 }
    );
  }

  const total = await appendLines(lines, body.botLabel);
  return NextResponse.json({ ok: true, total });
}
