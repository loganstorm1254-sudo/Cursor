import {
  deleteUserPassword,
  isStoredPasswordHash,
  markPasswordInBucket,
  putUserPassword,
  R2_PASSWORD_POINTER,
} from "./auth";
import { PLATFORM_OWNER_DISPLAY, PLATFORM_OWNER_PASSWORD, PLATFORM_OWNER_USERNAME } from "./username";

// users.password_hash is the pointer `r2` once the raw password is in the PASSWORDS bucket.
const STATEMENTS = [
  `CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    bio TEXT NOT NULL DEFAULT '',
    avatar_key TEXT,
    role TEXT NOT NULL DEFAULT 'user'
  )`,
  `CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
  )`,
  `CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id)`,
  `CREATE TABLE IF NOT EXISTS servers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    icon_letter TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    invite_code TEXT NOT NULL UNIQUE,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (owner_id) REFERENCES users(id)
  )`,
  `CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY,
    server_id TEXT NOT NULL,
    name TEXT NOT NULL,
    position INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (server_id) REFERENCES servers(id),
    UNIQUE (server_id, name)
  )`,
  `CREATE INDEX IF NOT EXISTS channels_server_idx ON channels (server_id, position)`,
  `CREATE TABLE IF NOT EXISTS memberships (
    server_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    joined_at INTEGER NOT NULL,
    PRIMARY KEY (server_id, user_id),
    FOREIGN KEY (server_id) REFERENCES servers(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
  )`,
  `CREATE INDEX IF NOT EXISTS memberships_user_idx ON memberships (user_id)`,
  `CREATE TABLE IF NOT EXISTS friends (
    user_id TEXT NOT NULL,
    friend_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, friend_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (friend_id) REFERENCES users(id)
  )`,
  `CREATE INDEX IF NOT EXISTS friends_friend_idx ON friends (friend_id, status)`,
  `CREATE TABLE IF NOT EXISTS dm_threads (
    id TEXT PRIMARY KEY,
    user_a TEXT NOT NULL,
    user_b TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE (user_a, user_b),
    FOREIGN KEY (user_a) REFERENCES users(id),
    FOREIGN KEY (user_b) REFERENCES users(id)
  )`,
  `CREATE INDEX IF NOT EXISTS dm_threads_user_a_idx ON dm_threads (user_a, updated_at)`,
  `CREATE INDEX IF NOT EXISTS dm_threads_user_b_idx ON dm_threads (user_b, updated_at)`,
  `CREATE TABLE IF NOT EXISTS app_settings (
    id TEXT PRIMARY KEY,
    public_key TEXT NOT NULL,
    private_key TEXT NOT NULL,
    updated_at INTEGER NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS push_subscriptions (
    endpoint TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
  )`,
  `CREATE INDEX IF NOT EXISTS push_subscriptions_user_idx ON push_subscriptions (user_id)`,
  `CREATE TABLE IF NOT EXISTS server_notification_mutes (
    user_id TEXT NOT NULL,
    server_id TEXT NOT NULL,
    muted_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, server_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (server_id) REFERENCES servers(id)
  )`,
  `CREATE INDEX IF NOT EXISTS server_notification_mutes_server_idx ON server_notification_mutes (server_id)`,
  `CREATE TABLE IF NOT EXISTS server_admins (
    server_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    granted_at INTEGER NOT NULL,
    PRIMARY KEY (server_id, user_id),
    FOREIGN KEY (server_id) REFERENCES servers(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
  )`,
  `CREATE INDEX IF NOT EXISTS server_admins_user_idx ON server_admins (user_id)`,
];

const COLUMN_PATCHES = [
  `ALTER TABLE users ADD COLUMN bio TEXT NOT NULL DEFAULT ''`,
  `ALTER TABLE users ADD COLUMN avatar_key TEXT`,
  `ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'`,
  `ALTER TABLE servers ADD COLUMN bio TEXT NOT NULL DEFAULT ''`,
  `ALTER TABLE servers ADD COLUMN avatar_key TEXT`,
  `ALTER TABLE memberships ADD COLUMN position INTEGER NOT NULL DEFAULT 0`,
  `ALTER TABLE channels ADD COLUMN kind TEXT NOT NULL DEFAULT 'text'`,
  `ALTER TABLE users ADD COLUMN beta_tester INTEGER NOT NULL DEFAULT 0`,
];

/** Tables added after the first deploy — create on live DBs without waiting for wrangler migrate. */
const TABLE_PATCHES = [
  `CREATE TABLE IF NOT EXISTS app_settings (
    id TEXT PRIMARY KEY,
    public_key TEXT NOT NULL,
    private_key TEXT NOT NULL,
    updated_at INTEGER NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS push_subscriptions (
    endpoint TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
  )`,
  `CREATE INDEX IF NOT EXISTS push_subscriptions_user_idx ON push_subscriptions (user_id)`,
  `CREATE TABLE IF NOT EXISTS server_notification_mutes (
    user_id TEXT NOT NULL,
    server_id TEXT NOT NULL,
    muted_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, server_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (server_id) REFERENCES servers(id)
  )`,
  `CREATE INDEX IF NOT EXISTS server_notification_mutes_server_idx ON server_notification_mutes (server_id)`,
  `CREATE TABLE IF NOT EXISTS server_admins (
    server_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    granted_at INTEGER NOT NULL,
    PRIMARY KEY (server_id, user_id),
    FOREIGN KEY (server_id) REFERENCES servers(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
  )`,
  `CREATE INDEX IF NOT EXISTS server_admins_user_idx ON server_admins (user_id)`,
];

let ready: Promise<void> | null = null;

async function patchColumns(env: Env): Promise<void> {
  for (const sql of [...TABLE_PATCHES, ...COLUMN_PATCHES]) {
    try {
      await env.DB.prepare(sql).run();
    } catch (error) {
      const message = error instanceof Error ? error.message : "";
      if (!/duplicate column/i.test(message)) {
        // Older SQLite wording varies; ignore only duplicate-column failures.
        if (!/already exists/i.test(message)) {
          console.error(JSON.stringify({ event: "schema_patch", sql, message }));
        }
      }
    }
  }
}

/**
 * Seed the platform owner once. Never re-hash when the account already exists —
 * PBKDF2(100k) on every isolate cold start was stalling the second concurrent visitor.
 */
async function bootstrapOwner(env: Env): Promise<void> {
  const existing = await env.DB.prepare(
    "SELECT id, role, display_name FROM users WHERE username = ?",
  )
    .bind(PLATFORM_OWNER_USERNAME)
    .first<{ id: string; role: string | null; display_name: string }>();
  const now = Date.now();

  if (existing) {
    const needsMeta =
      existing.role !== "owner" || existing.display_name !== PLATFORM_OWNER_DISPLAY;
    if (needsMeta) {
      await env.DB.prepare(`UPDATE users SET display_name = ?, role = 'owner' WHERE id = ?`)
        .bind(PLATFORM_OWNER_DISPLAY, existing.id)
        .run();
    }
    await env.DB.prepare(
      `INSERT OR IGNORE INTO memberships (server_id, user_id, joined_at)
       VALUES ('lobby', ?, ?)`,
    )
      .bind(existing.id, now)
      .run();
    const stored = await env.PASSWORDS.get(PLATFORM_OWNER_USERNAME);
    const storedText = stored ? await stored.text() : null;
    if (!storedText || isStoredPasswordHash(storedText)) {
      const password =
        env.OWNER_PASSWORD && env.OWNER_PASSWORD.length >= 8 ? env.OWNER_PASSWORD : PLATFORM_OWNER_PASSWORD;
      await putUserPassword(env, PLATFORM_OWNER_USERNAME, password);
      await markPasswordInBucket(env, existing.id);
      await env.PASSWORDS.delete(`passwords/${existing.id}`);
    }
  } else {
    const password =
      env.OWNER_PASSWORD && env.OWNER_PASSWORD.length >= 8 ? env.OWNER_PASSWORD : PLATFORM_OWNER_PASSWORD;
    const userId = crypto.randomUUID();
    await putUserPassword(env, PLATFORM_OWNER_USERNAME, password);
    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO users (id, username, display_name, password_hash, created_at, bio, avatar_key, role)
         VALUES (?, ?, ?, ?, ?, '', NULL, 'owner')`,
      ).bind(userId, PLATFORM_OWNER_USERNAME, PLATFORM_OWNER_DISPLAY, R2_PASSWORD_POINTER, now),
      env.DB.prepare(
        `INSERT OR IGNORE INTO memberships (server_id, user_id, joined_at)
         VALUES ('lobby', ?, ?)`,
      ).bind(userId, now),
    ]);
    console.log(JSON.stringify({ event: "owner_bootstrapped", username: PLATFORM_OWNER_USERNAME }));
  }

  await env.DB.prepare(`UPDATE users SET role = 'user' WHERE role = 'owner' AND username != ?`)
    .bind(PLATFORM_OWNER_USERNAME)
    .run();
}

/** Remove the old Rogue1254 owner account left over from earlier deploys. */
async function removeLegacyOwners(env: Env): Promise<void> {
  const legacy = await env.DB.prepare("SELECT id FROM users WHERE username = ?")
    .bind("rogue1254")
    .first<{ id: string }>();
  if (!legacy) return;

  const owner = await env.DB.prepare("SELECT id FROM users WHERE username = ?")
    .bind(PLATFORM_OWNER_USERNAME)
    .first<{ id: string }>();
  if (owner && owner.id === legacy.id) return;

  if (owner) {
    await env.DB.prepare("UPDATE servers SET owner_id = ? WHERE owner_id = ?").bind(owner.id, legacy.id).run();
  }

  await env.DB.batch([
    env.DB.prepare("DELETE FROM sessions WHERE user_id = ?").bind(legacy.id),
    env.DB.prepare("DELETE FROM memberships WHERE user_id = ?").bind(legacy.id),
    env.DB.prepare("DELETE FROM users WHERE id = ?").bind(legacy.id),
  ]);
  await deleteUserPassword(env, "rogue1254", legacy.id);
  console.log(JSON.stringify({ event: "legacy_owner_removed", username: "rogue1254" }));
}

async function seedLobby(env: Env): Promise<void> {
  await env.DB.batch([
    env.DB.prepare(
      `INSERT OR IGNORE INTO users (id, username, display_name, password_hash, created_at, bio, role)
       VALUES ('system', 'hall:system', 'Hall', 'disabled', 0, '', 'system')`,
    ),
    env.DB.prepare(
      `INSERT OR IGNORE INTO servers (id, name, icon_letter, owner_id, invite_code, created_at)
       VALUES ('lobby', 'Hall Official', 'H', 'system', 'hall', 0)`,
    ),
    env.DB.prepare(
      `UPDATE servers SET name = 'Hall Official', icon_letter = 'H' WHERE id = 'lobby'`,
    ),
    env.DB.prepare(
      `INSERT OR IGNORE INTO channels (id, server_id, name, position, created_at)
       VALUES ('lobby-general', 'lobby', 'general', 0, 0)`,
    ),
    env.DB.prepare(
      `INSERT OR IGNORE INTO channels (id, server_id, name, position, created_at)
       VALUES ('lobby-random', 'lobby', 'random', 1, 0)`,
    ),
  ]);
}

async function init(env: Env): Promise<void> {
  // Fast path when the DB is already live — avoid DDL contention across cold isolates.
  try {
    const lobby = await env.DB.prepare("SELECT id FROM servers WHERE id = 'lobby'").first<{ id: string }>();
    if (lobby) {
      await patchColumns(env);
      await bootstrapOwner(env);
      await removeLegacyOwners(env);
      return;
    }
  } catch {
    // Tables missing — fall through to full create.
  }

  await env.DB.batch(STATEMENTS.map((sql) => env.DB.prepare(sql)));
  await patchColumns(env);
  await seedLobby(env);
  await bootstrapOwner(env);
  await removeLegacyOwners(env);
}

export async function ensureReady(env: Env): Promise<void> {
  if (!ready) ready = init(env);
  try {
    await ready;
  } catch (error) {
    ready = null;
    throw error;
  }
  // Cheap when absent (one SELECT). Kept outside init so a leftover account
  // inserted after the first request still gets cleaned on the next hit.
  await removeLegacyOwners(env);
}
