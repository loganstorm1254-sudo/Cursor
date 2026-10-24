import { DurableObject } from "cloudflare:workers";
import { POLL_PREFIX } from "./username";

export type ChatMessage = {
  id: string;
  userId: string;
  username: string;
  displayName: string;
  avatarUrl: string | null;
  body: string;
  createdAt: number;
  replyTo?: {
    id: string;
    userId: string;
    username: string;
    displayName: string;
    body: string;
    deleted?: boolean;
  } | null;
};

type PollPayload = {
  question: string;
  options: string[];
  votes: Record<string, string[]>;
};

export type PresenceUser = {
  userId: string;
  username: string;
  displayName: string;
  avatarUrl: string | null;
};

export type VoiceUser = PresenceUser & {
  muted: boolean;
  sharing: boolean;
};

type Attachment = PresenceUser & {
  inVoice?: boolean;
  voiceMuted?: boolean;
  voiceSharing?: boolean;
  serverId?: string;
  channelId?: string;
};

type VoiceSignal = {
  type?: string;
  body?: string;
  to?: string;
  signal?: { kind?: string; sdp?: unknown; candidate?: unknown };
  muted?: boolean;
  sharing?: boolean;
  messageId?: string;
  optionIndex?: number;
  replyTo?: string;
};

type MessageRow = {
  id: string;
  user_id: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  body: string;
  created_at: number;
  reply_to?: string | null;
};

const COOLDOWN_MS = 250;
const MAX_BODY = 4000;

function toMessage(row: MessageRow, replyTo: ChatMessage["replyTo"] = null): ChatMessage {
  return {
    id: row.id,
    userId: row.user_id,
    username: row.username,
    displayName: row.display_name,
    avatarUrl: row.avatar_url,
    body: row.body,
    createdAt: row.created_at,
    replyTo,
  };
}

export class ChannelRoom extends DurableObject<Env> {
  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    ctx.blockConcurrencyWhile(async () => {
      this.ctx.storage.sql.exec(`
        CREATE TABLE IF NOT EXISTS messages (
          id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL,
          username TEXT NOT NULL,
          display_name TEXT NOT NULL,
          avatar_url TEXT,
          body TEXT NOT NULL,
          created_at INTEGER NOT NULL
        )
      `);
      try {
        this.ctx.storage.sql.exec(`ALTER TABLE messages ADD COLUMN avatar_url TEXT`);
      } catch {
        // Column already exists on newer objects.
      }
      try {
        this.ctx.storage.sql.exec(`ALTER TABLE messages ADD COLUMN reply_to TEXT`);
      } catch {
        // Column already exists on newer objects.
      }
      this.ctx.storage.sql.exec(`
        CREATE INDEX IF NOT EXISTS messages_created_idx ON messages (created_at)
      `);
      this.ctx.storage.sql.exec(`
        CREATE TABLE IF NOT EXISTS rate (
          user_id TEXT PRIMARY KEY,
          last_at INTEGER NOT NULL
        )
      `);
    });
    this.ctx.setWebSocketAutoResponse(new WebSocketRequestResponsePair("ping", "pong"));
  }

  private lookupReply(replyToId: string | null | undefined): ChatMessage["replyTo"] {
    if (!replyToId) return null;
    const parent = this.ctx.storage.sql
      .exec<MessageRow>(
        `SELECT id, user_id, username, display_name, avatar_url, body, created_at, reply_to
         FROM messages WHERE id = ?`,
        replyToId,
      )
      .toArray()[0];
    if (!parent) return { id: replyToId, userId: "", username: "", displayName: "", body: "", deleted: true };
    return {
      id: parent.id,
      userId: parent.user_id,
      username: parent.username,
      displayName: parent.display_name,
      body: parent.body,
    };
  }

  private hydrate(row: MessageRow): ChatMessage {
    return toMessage(row, this.lookupReply(row.reply_to));
  }

  async getMessage(messageId: string): Promise<ChatMessage | null> {
    const row = this.ctx.storage.sql
      .exec<MessageRow>(
        `SELECT id, user_id, username, display_name, avatar_url, body, created_at, reply_to
         FROM messages WHERE id = ?`,
        messageId,
      )
      .toArray()[0];
    return row ? this.hydrate(row) : null;
  }

  async deleteMessage(messageId: string): Promise<{ ok: true } | { ok: false; error: string }> {
    const existing = await this.getMessage(messageId);
    if (!existing) return { ok: false, error: "Message not found" };
    this.ctx.storage.sql.exec(`DELETE FROM messages WHERE id = ?`, messageId);
    this.broadcast(JSON.stringify({ type: "message_deleted", messageId }));
    return { ok: true };
  }

  async listMessages(limit: number, before: number | null): Promise<ChatMessage[]> {
    const capped = Math.min(Math.max(limit, 1), 100);
    const rows =
      before === null
        ? this.ctx.storage.sql
            .exec<MessageRow>(
              `SELECT id, user_id, username, display_name, avatar_url, body, created_at, reply_to
               FROM messages
               ORDER BY created_at DESC
               LIMIT ?`,
              capped,
            )
            .toArray()
        : this.ctx.storage.sql
            .exec<MessageRow>(
              `SELECT id, user_id, username, display_name, avatar_url, body, created_at, reply_to
               FROM messages
               WHERE created_at < ?
               ORDER BY created_at DESC
               LIMIT ?`,
              before,
              capped,
            )
            .toArray();
    return rows.reverse().map((row) => this.hydrate(row));
  }

  async postMessage(
    author: PresenceUser,
    body: string,
    replyToId?: string | null,
  ): Promise<{ ok: true; message: ChatMessage } | { ok: false; error: string }> {
    const saved = this.insertMessage(author, body, replyToId);
    if ("error" in saved) return { ok: false, error: saved.error };
    this.broadcast(JSON.stringify({ type: "message", message: saved }));
    return { ok: true, message: saved };
  }

  async votePoll(
    userId: string,
    messageId: string,
    optionIndex: number,
  ): Promise<{ ok: true; message: ChatMessage } | { ok: false; error: string }> {
    const row = this.ctx.storage.sql
      .exec<MessageRow>(
        `SELECT id, user_id, username, display_name, avatar_url, body, created_at, reply_to
         FROM messages WHERE id = ?`,
        messageId,
      )
      .toArray()[0];
    if (!row) return { ok: false, error: "Poll not found" };
    if (!row.body.startsWith(POLL_PREFIX)) return { ok: false, error: "Not a poll" };
    let poll: PollPayload;
    try {
      poll = JSON.parse(row.body.slice(POLL_PREFIX.length)) as PollPayload;
    } catch {
      return { ok: false, error: "Broken poll" };
    }
    if (!Array.isArray(poll.options) || optionIndex < 0 || optionIndex >= poll.options.length) {
      return { ok: false, error: "Bad option" };
    }
    if (!poll.votes || typeof poll.votes !== "object") poll.votes = {};
    for (const key of Object.keys(poll.votes)) {
      poll.votes[key] = (poll.votes[key] ?? []).filter((id) => id !== userId);
    }
    const bucket = String(optionIndex);
    const list = poll.votes[bucket] ?? [];
    list.push(userId);
    poll.votes[bucket] = list;
    const body = `${POLL_PREFIX}${JSON.stringify(poll)}`;
    this.ctx.storage.sql.exec(`UPDATE messages SET body = ? WHERE id = ?`, body, messageId);
    const message = this.hydrate({ ...row, body });
    this.broadcast(JSON.stringify({ type: "poll_update", message }));
    return { ok: true, message };
  }

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("Expected WebSocket", { status: 426 });
    }
    const userId = request.headers.get("x-hall-user-id") ?? "";
    const username = request.headers.get("x-hall-username") ?? "";
    const displayName = request.headers.get("x-hall-display-name") ?? "";
    const avatarUrl = request.headers.get("x-hall-avatar-url");
    const serverId = request.headers.get("x-hall-server-id") ?? "";
    const channelId = request.headers.get("x-hall-channel-id") ?? "";
    if (!userId || !username || !displayName) {
      return new Response("Missing member", { status: 401 });
    }

    const [client, server] = Object.values(new WebSocketPair());
    if (!client || !server) return new Response("Could not open WebSocket", { status: 500 });
    const attachment: Attachment = {
      userId,
      username,
      displayName,
      avatarUrl: avatarUrl && avatarUrl.length > 0 ? avatarUrl : null,
      inVoice: false,
      voiceMuted: false,
      voiceSharing: false,
      serverId,
      channelId,
    };
    this.ctx.acceptWebSocket(server);
    server.serializeAttachment(attachment);

    const online = this.onlineUsers();
    server.send(JSON.stringify({ type: "ready", online, voice: this.voiceUsers() }));
    this.broadcast(JSON.stringify({ type: "presence", online }), server);

    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    if (typeof message !== "string" || message === "ping") return;
    let parsed: VoiceSignal;
    try {
      parsed = JSON.parse(message) as VoiceSignal;
    } catch {
      return;
    }
    const attachment = ws.deserializeAttachment() as Attachment | null;
    if (!attachment?.userId) {
      ws.close(1008, "Unauthorized");
      return;
    }
    if (parsed.type === "poll_vote" && typeof parsed.messageId === "string") {
      const optionIndex = Number(parsed.optionIndex);
      const result = await this.votePoll(attachment.userId, parsed.messageId, optionIndex);
      if (!result.ok) ws.send(JSON.stringify({ type: "error", error: result.error }));
      return;
    }
    if (parsed.type === "voice_join") {
      if (this.voiceUsers().length >= 8 && !attachment.inVoice) {
        ws.send(JSON.stringify({ type: "error", error: "Voice is full (8 people)" }));
        return;
      }
      attachment.inVoice = true;
      attachment.voiceMuted = false;
      attachment.voiceSharing = false;
      ws.serializeAttachment(attachment);
      this.broadcastVoice();
      return;
    }
    if (parsed.type === "voice_leave") {
      attachment.inVoice = false;
      attachment.voiceMuted = false;
      attachment.voiceSharing = false;
      ws.serializeAttachment(attachment);
      this.broadcastVoice();
      return;
    }
    if (parsed.type === "voice_mute") {
      attachment.voiceMuted = Boolean(parsed.muted);
      ws.serializeAttachment(attachment);
      this.broadcastVoice();
      return;
    }
    if (parsed.type === "voice_share") {
      if (!attachment.inVoice) return;
      attachment.voiceSharing = Boolean(parsed.sharing);
      ws.serializeAttachment(attachment);
      this.broadcastVoice();
      return;
    }
    if (parsed.type === "voice_signal" && typeof parsed.to === "string" && parsed.signal) {
      if (!attachment.inVoice) return;
      const target = this.socketForUser(parsed.to);
      if (!target) return;
      try {
        target.send(
          JSON.stringify({
            type: "voice_signal",
            from: attachment.userId,
            fromUser: {
              userId: attachment.userId,
              username: attachment.username,
              displayName: attachment.displayName,
              avatarUrl: attachment.avatarUrl,
              muted: Boolean(attachment.voiceMuted),
              sharing: Boolean(attachment.voiceSharing),
            },
            signal: parsed.signal,
          }),
        );
      } catch {
        // Target may have disconnected.
      }
      return;
    }
    if (parsed.type !== "message" || typeof parsed.body !== "string") return;
    const replyTo = typeof parsed.replyTo === "string" ? parsed.replyTo : null;
    const saved = this.insertMessage(attachment, parsed.body, replyTo);
    if ("error" in saved) {
      ws.send(JSON.stringify({ type: "error", error: saved.error }));
      return;
    }
    this.broadcast(JSON.stringify({ type: "message", message: saved }));
  }

  async webSocketClose(ws: WebSocket): Promise<void> {
    const attachment = ws.deserializeAttachment() as Attachment | null;
    const wasVoice = Boolean(attachment?.inVoice);
    const online = this.onlineUsers(ws);
    this.broadcast(JSON.stringify({ type: "presence", online }), ws);
    if (wasVoice) this.broadcastVoice(ws);
  }

  async webSocketError(ws: WebSocket): Promise<void> {
    try {
      ws.close(1011, "Error");
    } catch {
      // The socket may already be gone.
    }
  }

  private insertMessage(
    author: PresenceUser,
    body: string,
    replyToId?: string | null,
  ): ChatMessage | { error: string } {
    const text = body.trim();
    if (!text) return { error: "Message is empty" };
    if (text.length > MAX_BODY) return { error: "Message is too long" };
    const now = Date.now();
    const previous = this.ctx.storage.sql
      .exec<{ last_at: number }>("SELECT last_at FROM rate WHERE user_id = ?", author.userId)
      .toArray()[0];
    if (previous && now - previous.last_at < COOLDOWN_MS) {
      return { error: "Slow down a little" };
    }
    let replyTo: ChatMessage["replyTo"] = null;
    let storedReply: string | null = null;
    if (replyToId) {
      const parent = this.lookupReply(replyToId);
      if (!parent || parent.deleted) return { error: "Message to reply to was not found" };
      replyTo = parent;
      storedReply = parent.id;
    }
    const message: ChatMessage = {
      id: crypto.randomUUID(),
      userId: author.userId,
      username: author.username,
      displayName: author.displayName,
      avatarUrl: author.avatarUrl,
      body: text,
      createdAt: now,
      replyTo,
    };
    this.ctx.storage.sql.exec(
      `INSERT INTO messages (id, user_id, username, display_name, avatar_url, body, created_at, reply_to)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      message.id,
      message.userId,
      message.username,
      message.displayName,
      message.avatarUrl,
      message.body,
      message.createdAt,
      storedReply,
    );
    this.ctx.storage.sql.exec(
      `INSERT INTO rate (user_id, last_at) VALUES (?, ?)
       ON CONFLICT(user_id) DO UPDATE SET last_at = excluded.last_at`,
      author.userId,
      now,
    );
    return message;
  }

  private onlineUsers(except?: WebSocket): PresenceUser[] {
    const seen = new Map<string, PresenceUser>();
    for (const socket of this.ctx.getWebSockets()) {
      if (socket === except || socket.readyState !== WebSocket.OPEN) continue;
      const attachment = socket.deserializeAttachment() as Attachment | null;
      if (!attachment?.userId) continue;
      seen.set(attachment.userId, {
        userId: attachment.userId,
        username: attachment.username,
        displayName: attachment.displayName,
        avatarUrl: attachment.avatarUrl,
      });
    }
    return [...seen.values()];
  }

  private voiceUsers(except?: WebSocket): VoiceUser[] {
    const seen = new Map<string, VoiceUser>();
    for (const socket of this.ctx.getWebSockets()) {
      if (socket === except || socket.readyState !== WebSocket.OPEN) continue;
      const attachment = socket.deserializeAttachment() as Attachment | null;
      if (!attachment?.userId || !attachment.inVoice) continue;
      seen.set(attachment.userId, {
        userId: attachment.userId,
        username: attachment.username,
        displayName: attachment.displayName,
        avatarUrl: attachment.avatarUrl,
        muted: Boolean(attachment.voiceMuted),
        sharing: Boolean(attachment.voiceSharing),
      });
    }
    return [...seen.values()].sort((a, b) => a.displayName.localeCompare(b.displayName));
  }

  private socketForUser(userId: string): WebSocket | null {
    for (const socket of this.ctx.getWebSockets()) {
      if (socket.readyState !== WebSocket.OPEN) continue;
      const attachment = socket.deserializeAttachment() as Attachment | null;
      if (attachment?.userId === userId) return socket;
    }
    return null;
  }

  private broadcastVoice(except?: WebSocket): void {
    const voice = this.voiceUsers(except);
    this.broadcast(JSON.stringify({ type: "voice_state", voice }), except);
    void this.publishVoiceRoster(voice);
  }

  private async publishVoiceRoster(voice: VoiceUser[]): Promise<void> {
    let serverId = "";
    let channelId = "";
    for (const socket of this.ctx.getWebSockets()) {
      const attachment = socket.deserializeAttachment() as Attachment | null;
      if (attachment?.serverId && attachment.channelId) {
        serverId = attachment.serverId;
        channelId = attachment.channelId;
        break;
      }
    }
    if (!serverId || !channelId || !this.env.SERVERS) return;
    try {
      await this.env.SERVERS.getByName(serverId).fetch(
        new Request("https://hub/publish", {
          method: "POST",
          body: JSON.stringify({ type: "voice_roster", channelId, voice }),
        }),
      );
    } catch (error) {
      console.error(
        JSON.stringify({
          event: "voice_roster_publish_failed",
          channelId,
          message: error instanceof Error ? error.message : "unknown",
        }),
      );
    }
  }

  private broadcast(payload: string, except?: WebSocket): void {
    for (const socket of this.ctx.getWebSockets()) {
      if (socket === except || socket.readyState !== WebSocket.OPEN) continue;
      try {
        socket.send(payload);
      } catch (error) {
        console.error(
          JSON.stringify({
            event: "broadcast_failed",
            message: error instanceof Error ? error.message : "unknown",
          }),
        );
      }
    }
  }
}
