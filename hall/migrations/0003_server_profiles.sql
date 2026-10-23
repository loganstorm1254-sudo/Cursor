-- Server bios/avatars and per-user server rail order.

ALTER TABLE servers ADD COLUMN bio TEXT NOT NULL DEFAULT '';
ALTER TABLE servers ADD COLUMN avatar_key TEXT;
ALTER TABLE memberships ADD COLUMN position INTEGER NOT NULL DEFAULT 0;
