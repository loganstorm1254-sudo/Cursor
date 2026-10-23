import { DurableObject } from "cloudflare:workers";

type HubAttachment = {
  userId: string;
};

/** Per-server fanout for live channel / member list updates. */
export class ServerHub extends DurableObject<Env> {
  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("Upgrade") !== "websocket") {
      if (request.method === "POST") {
        const payload = await request.text();
        this.broadcast(payload);
        return new Response("ok");
      }
      return new Response("Expected WebSocket", { status: 426 });
    }
    const userId = request.headers.get("x-hall-user-id") ?? "";
    if (!userId) return new Response("Missing member", { status: 401 });
    const [client, server] = Object.values(new WebSocketPair());
    if (!client || !server) return new Response("Could not open WebSocket", { status: 500 });
    this.ctx.acceptWebSocket(server);
    server.serializeAttachment({ userId } satisfies HubAttachment);
    server.send(JSON.stringify({ type: "hub_ready" }));
    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    if (message === "ping") {
      try {
        ws.send("pong");
      } catch {
        // ignore
      }
    }
  }

  private broadcast(payload: string): void {
    for (const socket of this.ctx.getWebSockets()) {
      if (socket.readyState !== WebSocket.OPEN) continue;
      try {
        socket.send(payload);
      } catch {
        // ignore
      }
    }
  }
}
