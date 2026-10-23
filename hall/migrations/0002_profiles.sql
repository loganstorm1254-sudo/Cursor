-- Profile fields and platform owner role.
ALTER TABLE users ADD COLUMN bio TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN avatar_key TEXT;
ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user';
