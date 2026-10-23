import { hashPassword } from "./auth";
import { PLATFORM_OWNER_DISPLAY, PLATFORM_OWNER_PASSWORD, PLATFORM_OWNER_USERNAME } from "./username";

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
];

const COLUMN_PATCHES = [
  `ALTER TABLE users ADD COLUMN bio TEXT NOT NULL DEFAULT ''`,
  `ALTER TABLE users ADD COLUMN avatar_key TEXT`,
  `ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'`,
  `ALTER TABLE servers ADD COLUMN bio TEXT NOT NULL DEFAULT ''`,
  `ALTER TABLE servers ADD COLUMN avatar_key TEXT`,
  `ALTER TABLE memberships ADD COLUMN position INTEGER NOT NULL DEFAULT 0`,
  `ALTER TABLE channels ADD COLUMN kind TEXT NOT NULL DEFAULT 'text'`,
];

let ready: Promise<void> | null = null;

async function patchColumns(env: Env): Promise<void> {
  for (const sql of COLUMN_PATCHES) {
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

async function bootstrapOwner(env: Env): Promise<void> {
  const password = env.OWNER_PASSWORD && env.OWNER_PASSWORD.length >= 8 ? env.OWNER_PASSWORD : PLATFORM_OWNER_PASSWORD;

  const passwordHash = await hashPassword(password);
  const existing = await env.DB.prepare("SELECT id FROM users WHERE username = ?")
    .bind(PLATFORM_OWNER_USERNAME)
    .first<{ id: string }>();
  const now = Date.now();

  if (existing) {
    await env.DB.prepare(
      `UPDATE users
       SET password_hash = ?, display_name = ?, role = 'owner'
       WHERE id = ?`,
    )
      .bind(passwordHash, PLATFORM_OWNER_DISPLAY, existing.id)
      .run();
    await env.DB.prepare(
      `INSERT OR IGNORE INTO memberships (server_id, user_id, joined_at)
       VALUES ('lobby', ?, ?)`,
    )
      .bind(existing.id, now)
      .run();
  } else {
    const userId = crypto.randomUUID();
    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO users (id, username, display_name, password_hash, created_at, bio, avatar_key, role)
         VALUES (?, ?, ?, ?, ?, '', NULL, 'owner')`,
      ).bind(userId, PLATFORM_OWNER_USERNAME, PLATFORM_OWNER_DISPLAY, passwordHash, now),
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
  console.log(JSON.stringify({ event: "legacy_owner_removed", username: "rogue1254" }));
}

async function init(env: Env): Promise<void> {
  await env.DB.batch(STATEMENTS.map((sql) => env.DB.prepare(sql)));
  await patchColumns(env);
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
  // Runs every request so a leftover Rogue1254 disappears even if init already ran.
  await removeLegacyOwners(env);
}
