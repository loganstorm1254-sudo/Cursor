import { NextResponse } from "next/server";
import { readSession } from "../../../lib/auth";
import { isOnline, loadState } from "../../../lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const session = await readSession();
  const state = await loadState();

  if (!session) {
    return NextResponse.json({
      claimed: Boolean(state),
      loggedIn: false,
      online: false,
    });
  }

  if (!state || state.username !== session.u) {
    return NextResponse.json({
      claimed: Boolean(state),
      loggedIn: false,
      online: false,
    });
  }

  return NextResponse.json({
    claimed: true,
    loggedIn: true,
    online: isOnline(state),
    username: state.username,
    botLabel: state.botLabel,
    lastHeartbeat: state.lastHeartbeat,
    lineCount: state.lines.length,
  });
}
