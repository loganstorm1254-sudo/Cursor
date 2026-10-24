CREATE TABLE IF NOT EXISTS server_admins (
  server_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  granted_at INTEGER NOT NULL,
  PRIMARY KEY (server_id, user_id),
  FOREIGN KEY (server_id) REFERENCES servers(id),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS server_admins_user_idx ON server_admins (user_id);
