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

function fromB64Url(value: string): Uint8Array {
  const padded = `${value.replace(/-/g, "+").replace(/_/g, "/")}${"=".repeat((4 - (value.length % 4)) % 4)}`;
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function toB64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function concat(...parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

function asBuffer(bytes: Uint8Array): ArrayBuffer {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

function textBytes(value: string): Uint8Array {
  return new TextEncoder().encode(value);
}

async function generateVapidKeys(): Promise<VapidKeys> {
  const pair = (await crypto.subtle.generateKey(
    { name: "ECDSA", namedCurve: "P-256" },
    true,
    ["sign", "verify"],
  )) as CryptoKeyPair;
  const rawPub = new Uint8Array((await crypto.subtle.exportKey("raw", pair.publicKey)) as ArrayBuffer);
  const jwk = (await crypto.subtle.exportKey("jwk", pair.privateKey)) as JsonWebKey;
  if (!jwk.d) throw new Error("VAPID key export failed");
  return { publicKey: toB64Url(rawPub), privateKey: jwk.d };
}

async function hkdf(ikm: Uint8Array, salt: Uint8Array, info: Uint8Array, length: number): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey("raw", asBuffer(ikm), "HKDF", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "HKDF", hash: "SHA-256", salt: asBuffer(salt), info: asBuffer(info) },
    key,
    length * 8,
  );
  return new Uint8Array(bits);
}

async function vapidJwt(audience: string, subject: string, keys: VapidKeys): Promise<string> {
  const pub = fromB64Url(keys.publicKey);
  if (pub.length !== 65 || pub[0] !== 4) throw new Error("Bad VAPID public key");
  const key = await crypto.subtle.importKey(
    "jwk",
    {
      kty: "EC",
      crv: "P-256",
      d: keys.privateKey,
      x: toB64Url(pub.subarray(1, 33)),
      y: toB64Url(pub.subarray(33, 65)),
    },
    { name: "ECDSA", namedCurve: "P-256" },
    false,
    ["sign"],
  );
  const header = toB64Url(textBytes(JSON.stringify({ typ: "JWT", alg: "ES256" })));
  const payload = toB64Url(
    textBytes(
      JSON.stringify({
        aud: audience,
        exp: Math.floor(Date.now() / 1000) + 12 * 60 * 60,
        sub: subject,
      }),
    ),
  );
  const data = textBytes(`${header}.${payload}`);
  const sig = new Uint8Array(await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, asBuffer(data)));
  return `${header}.${payload}.${toB64Url(sig)}`;
}

/** RFC 8291 / RFC 8188 aes128gcm payload for Web Push. */
async function encryptPayload(p256dh: string, auth: string, payload: string): Promise<Uint8Array> {
  const uaPublic = fromB64Url(p256dh);
  const authSecret = fromB64Url(auth);
  if (uaPublic.length !== 65) throw new Error("Bad p256dh");
  if (authSecret.length < 16) throw new Error("Bad auth");

  const local = (await crypto.subtle.generateKey(
    { name: "ECDH", namedCurve: "P-256" },
    true,
    ["deriveBits"],
  )) as CryptoKeyPair;
  const asPublic = new Uint8Array((await crypto.subtle.exportKey("raw", local.publicKey)) as ArrayBuffer);
  const uaKey = await crypto.subtle.importKey(
    "raw",
    asBuffer(uaPublic),
    { name: "ECDH", namedCurve: "P-256" },
    false,
    [],
  );
  const shared = new Uint8Array(
    await crypto.subtle.deriveBits(
      { name: "ECDH", public: uaKey } as unknown as SubtleCryptoDeriveKeyAlgorithm,
      local.privateKey,
      256,
    ),
  );

  const ikm = await hkdf(shared, authSecret, concat(textBytes("WebPush: info\0"), uaPublic, asPublic), 32);
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const cek = await hkdf(ikm, salt, textBytes("Content-Encoding: aes128gcm\0"), 16);
  const nonce = await hkdf(ikm, salt, textBytes("Content-Encoding: nonce\0"), 12);
  const aes = await crypto.subtle.importKey("raw", asBuffer(cek), "AES-GCM", false, ["encrypt"]);
  const plaintext = concat(textBytes(payload), new Uint8Array([2]));
  const ciphertext = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv: asBuffer(nonce), tagLength: 128 }, aes, asBuffer(plaintext)),
  );

  const rs = 4096;
  const header = new Uint8Array(21 + asPublic.length);
  header.set(salt, 0);
  header[16] = (rs >>> 24) & 0xff;
  header[17] = (rs >>> 16) & 0xff;
  header[18] = (rs >>> 8) & 0xff;
  header[19] = rs & 0xff;
  header[20] = asPublic.length;
  header.set(asPublic, 21);
  return concat(header, ciphertext);
}

function fromEnv(env: Env): VapidKeys | null {
  const publicKey = env.VAPID_PUBLIC_KEY?.trim();
  const privateKey = env.VAPID_PRIVATE_KEY?.trim();
  if (publicKey && privateKey) return { publicKey, privateKey };
  return null;
}

async function loadStoredKeys(env: Env): Promise<VapidKeys | null> {
  const row = await env.DB.prepare("SELECT public_key, private_key FROM app_settings WHERE id = ?")
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
  const generated = await generateVapidKeys();
  const now = Date.now();
  await env.DB.prepare(
    `INSERT OR IGNORE INTO app_settings (id, public_key, private_key, updated_at)
     VALUES (?, ?, ?, ?)`,
  )
    .bind(VAPID_ROW, generated.publicKey, generated.privateKey, now)
    .run();
  cachedKeys = (await loadStoredKeys(env)) ?? generated;
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

async function sendOne(env: Env, keys: VapidKeys, row: PushRow, payload: string): Promise<void> {
  try {
    const audience = new URL(row.endpoint).origin;
    const jwt = await vapidJwt(audience, env.VAPID_SUBJECT?.trim() || VAPID_SUBJECT, keys);
    const body = await encryptPayload(row.p256dh, row.auth, payload);
    const response = await fetch(row.endpoint, {
      method: "POST",
      headers: {
        TTL: "3600",
        Urgency: "high",
        "Content-Type": "application/octet-stream",
        "Content-Encoding": "aes128gcm",
        Authorization: `vapid t=${jwt}, k=${keys.publicKey}`,
      },
      body: asBuffer(body),
    });
    if (response.status === 404 || response.status === 410) {
      await env.DB.prepare("DELETE FROM push_subscriptions WHERE endpoint = ?").bind(row.endpoint).run();
      return;
    }
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      console.error(
        JSON.stringify({
          event: "push_send_failed",
          status: response.status,
          message: detail.slice(0, 200),
        }),
      );
    }
  } catch (error) {
    console.error(
      JSON.stringify({
        event: "push_send_failed",
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
    mentionIds?: string[];
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
  for (const id of opts.mentionIds ?? []) {
    if (id && id !== message.userId && !userIds.includes(id)) userIds.push(id);
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
