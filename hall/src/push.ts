import webpush from "web-push";
import type { ChatMessage } from "./channel";
import { POLL_PREFIX } from "./username";

const VAPID_SUBJECT = "mailto:hall@hallchat.lopro.cc";
const VAPID_ROW = "vapid";

type VapidKeys = { publicKey: string; privateKey: string };

type PushRow = {
  endpoint: string;
  p256dh: string;
  auth: string;
  user_id: string;
};

let cachedKeys: VapidKeys | null = null;

function fromEnv(env: Env): VapidKeys | null {
  const publicKey = env.VAPID_PUBLIC_KEY?.trim();
  const privateKey = env.VAPID_PRIVATE_KEY?.trim();
  if (publicKey && privateKey) return { publicKey, privateKey };
  return null;
}

async function loadStoredKeys(env: Env): Promise<VapidKeys | null> {
  const row = await env.DB.prepare(
    "SELECT public_key, private_key FROM app_settings WHERE id = ?",
  )
    .bind(VAPID_ROW)
    .first<{ public_key: string; private_key: string }>();
  if (!row?.public_key || !row?.private_key) return null;
  return { publicKey: row.public_key, privateKey: row.private_key };
}

async function ensureVapidKeys(env: Env): Promise<VapidKeys> {
  if (cachedKeys) return cachedKeys;
  const fromSecret = fromEnv(env);
  if (fromSecret) {
    cachedKeys = fromSecret;
    return cachedKeys;
  }
  const existing = await loadStoredKeys(env);
  if (existing) {
    cachedKeys = existing;
    return cachedKeys;
  }
  const generated = webpush.generateVAPIDKeys();
  const now = Date.now();
  await env.DB.prepare(
    `INSERT OR IGNORE INTO app_settings (id, public_key, private_key, updated_at)
     VALUES (?, ?, ?, ?)`,
  )
    .bind(VAPID_ROW, generated.publicKey, generated.privateKey, now)
    .run();
  const stored = (await loadStoredKeys(env)) ?? {
    publicKey: generated.publicKey,
    privateKey: generated.privateKey,
  };
  cachedKeys = stored;
  return cachedKeys;
}

export async function getVapidPublicKey(env: Env): Promise<string> {
  const keys = await ensureVapidKeys(env);
  return keys.publicKey;
}

export async function savePushSubscription(
  env: Env,
  userId: string,
  subscription: { endpoint: string; keys: { p256dh: string; auth: string } },
): Promise<void> {
  const endpoint = subscription.endpoint?.trim();
  const p256dh = subscription.keys?.p256dh?.trim();
  const auth = subscription.keys?.auth?.trim();
  if (!endpoint || !p256dh || !auth) throw new Error("Invalid push subscription");
  if (endpoint.length > 2048 || p256dh.length > 256 || auth.length > 256) {
    throw new Error("Push subscription too large");
  }
  await env.DB.prepare(
    `INSERT INTO push_subscriptions (endpoint, user_id, p256dh, auth, created_at)
     VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(endpoint) DO UPDATE SET
       user_id = excluded.user_id,
       p256dh = excluded.p256dh,
       auth = excluded.auth,
       created_at = excluded.created_at`,
  )
    .bind(endpoint, userId, p256dh, auth, Date.now())
    .run();
}

export async function removePushSubscription(env: Env, userId: string, endpoint: string): Promise<void> {
  await env.DB.prepare("DELETE FROM push_subscriptions WHERE endpoint = ? AND user_id = ?")
    .bind(endpoint, userId)
    .run();
}

export async function isServerMuted(env: Env, userId: string, serverId: string): Promise<boolean> {
  if (!serverId || serverId === "dm") return false;
  const row = await env.DB.prepare(
    "SELECT 1 AS ok FROM server_notification_mutes WHERE user_id = ? AND server_id = ?",
  )
    .bind(userId, serverId)
    .first<{ ok: number }>();
  return Boolean(row);
}

export async function setServerMuted(env: Env, userId: string, serverId: string, muted: boolean): Promise<void> {
  if (muted) {
    await env.DB.prepare(
      `INSERT INTO server_notification_mutes (user_id, server_id, muted_at)
       VALUES (?, ?, ?)
       ON CONFLICT(user_id, server_id) DO UPDATE SET muted_at = excluded.muted_at`,
    )
      .bind(userId, serverId, Date.now())
      .run();
    return;
  }
  await env.DB.prepare("DELETE FROM server_notification_mutes WHERE user_id = ? AND server_id = ?")
    .bind(userId, serverId)
    .run();
}

function previewBody(body: string): string {
  const raw = String(body || "");
  if (raw.startsWith(POLL_PREFIX)) return `Poll: ${raw.slice(POLL_PREFIX.length).slice(0, 100)}`;
  return raw.slice(0, 120) || "New message";
}

async function sendOne(
  env: Env,
  keys: VapidKeys,
  row: PushRow,
  payload: string,
): Promise<void> {
  webpush.setVapidDetails(env.VAPID_SUBJECT?.trim() || VAPID_SUBJECT, keys.publicKey, keys.privateKey);
  try {
    await webpush.sendNotification(
      {
        endpoint: row.endpoint,
        keys: { p256dh: row.p256dh, auth: row.auth },
      },
      payload,
      { TTL: 60 * 60, urgency: "high" },
    );
  } catch (error) {
    const status =
      error && typeof error === "object" && "statusCode" in error
        ? Number((error as { statusCode?: number }).statusCode)
        : 0;
    if (status === 404 || status === 410) {
      await env.DB.prepare("DELETE FROM push_subscriptions WHERE endpoint = ?").bind(row.endpoint).run();
      return;
    }
    console.error(
      JSON.stringify({
        event: "push_send_failed",
        status,
        message: error instanceof Error ? error.message : "unknown",
      }),
    );
  }
}

/** Notify members with push subscriptions (skips sender + muted servers). */
export async function notifyChannelMessage(
  env: Env,
  opts: {
    channelId: string;
    serverId: string;
    message: ChatMessage;
    channelName?: string | null;
    serverName?: string | null;
  },
): Promise<void> {
  const { channelId, serverId, message } = opts;
  if (!message?.id || !message.userId) return;

  let userIds: string[] = [];
  if (serverId === "dm" || channelId.startsWith("dm:")) {
    const thread = await env.DB.prepare("SELECT user_a, user_b FROM dm_threads WHERE id = ?")
      .bind(channelId)
      .first<{ user_a: string; user_b: string }>();
    if (!thread) return;
    userIds = [thread.user_a, thread.user_b].filter((id) => id !== message.userId);
  } else {
    const members = await env.DB.prepare(
      `SELECT m.user_id AS id
       FROM memberships m
       WHERE m.server_id = ?
         AND m.user_id != ?
         AND NOT EXISTS (
           SELECT 1 FROM server_notification_mutes mute
           WHERE mute.user_id = m.user_id AND mute.server_id = m.server_id
         )`,
    )
      .bind(serverId, message.userId)
      .all<{ id: string }>();
    userIds = (members.results ?? []).map((row) => row.id);
  }
  if (userIds.length === 0) return;

  const placeholders = userIds.map(() => "?").join(",");
  const subs = await env.DB.prepare(
    `SELECT endpoint, p256dh, auth, user_id FROM push_subscriptions WHERE user_id IN (${placeholders})`,
  )
    .bind(...userIds)
    .all<PushRow>();
  const rows = subs.results ?? [];
  if (rows.length === 0) return;

  const keys = await ensureVapidKeys(env);
  const title = message.displayName || message.username || "Hall";
  const body = previewBody(message.body);
  const url =
    serverId === "dm" || channelId.startsWith("dm:")
      ? `/?dm=${encodeURIComponent(channelId)}`
      : `/?server=${encodeURIComponent(serverId)}&channel=${encodeURIComponent(channelId)}`;
  const payload = JSON.stringify({
    title,
    body,
    tag: `hall-msg-${message.id}`,
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    data: {
      url,
      serverId,
      channelId,
      messageId: message.id,
      serverName: opts.serverName || null,
      channelName: opts.channelName || null,
    },
  });

  await Promise.all(rows.map((row) => sendOne(env, keys, row, payload)));
}
