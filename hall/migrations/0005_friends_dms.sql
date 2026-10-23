CREATE TABLE IF NOT EXISTS friends (
  user_id TEXT NOT NULL,
  friend_id TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, friend_id),
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (friend_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS friends_friend_idx ON friends (friend_id, status);

CREATE TABLE IF NOT EXISTS dm_threads (
  id TEXT PRIMARY KEY,
  user_a TEXT NOT NULL,
  user_b TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE (user_a, user_b),
  FOREIGN KEY (user_a) REFERENCES users(id),
  FOREIGN KEY (user_b) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS dm_threads_user_a_idx ON dm_threads (user_a, updated_at);
CREATE INDEX IF NOT EXISTS dm_threads_user_b_idx ON dm_threads (user_b, updated_at);
