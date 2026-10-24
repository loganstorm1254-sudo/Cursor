-- Hall account, server, and channel records.
-- Channel message history lives in each channel's Durable Object.
-- Keep this file in sync with src/schema.ts.

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  -- Pointer `r2` after the raw password is written to the hall-passwords R2 bucket (object key = username).
  password_hash TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id);

CREATE TABLE IF NOT EXISTS servers (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  icon_letter TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  invite_code TEXT NOT NULL UNIQUE,
  created_at INTEGER NOT NULL,
  FOREIGN KEY (owner_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS channels (
  id TEXT PRIMARY KEY,
  server_id TEXT NOT NULL,
  name TEXT NOT NULL,
  position INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  FOREIGN KEY (server_id) REFERENCES servers(id),
  UNIQUE (server_id, name)
);

CREATE INDEX IF NOT EXISTS channels_server_idx ON channels (server_id, position);

CREATE TABLE IF NOT EXISTS memberships (
  server_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  joined_at INTEGER NOT NULL,
  PRIMARY KEY (server_id, user_id),
  FOREIGN KEY (server_id) REFERENCES servers(id),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS memberships_user_idx ON memberships (user_id);
