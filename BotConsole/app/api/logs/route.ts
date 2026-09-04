import { NextRequest, NextResponse } from "next/server";
import { readSession } from "../../../lib/auth";
import { isOnline, loadState } from "../../../lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const session = await readSession();
  if (!session) {
    return NextResponse.json({ error: "Not logged in" }, { status: 401 });
  }

  const state = await loadState();
  if (!state || state.username !== session.u) {
    return NextResponse.json({ error: "No console" }, { status: 404 });
  }

  const afterParam = req.nextUrl.searchParams.get("after");
  const after = afterParam ? Number(afterParam) : 0;
  const lines =
    after > 0 ? state.lines.filter((l) => l.id > after) : state.lines.slice(-400);

  return NextResponse.json({
    ok: true,
    username: state.username,
    botLabel: state.botLabel,
    online: isOnline(state),
    lastHeartbeat: state.lastHeartbeat,
    lines,
  });
}
