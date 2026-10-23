-- text | voice channels
ALTER TABLE channels ADD COLUMN kind TEXT NOT NULL DEFAULT 'text';
