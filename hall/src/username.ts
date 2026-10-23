const RESERVED = new Set(["admin"]);

/** Platform owner account — bootstrapped on startup. */
export const PLATFORM_OWNER_USERNAME = "owner";
export const PLATFORM_OWNER_DISPLAY = "owner";
/** Default password when OWNER_PASSWORD secret is not set. */
export const PLATFORM_OWNER_PASSWORD = "rogue1254!!";

export type Username = {
  username: string;
  displayName: string;
};

export function normalizeUsername(input: string): Username | { error: string } {
  let raw = input.trim();
  if (raw.startsWith("@")) raw = raw.slice(1);
  if (!/^[A-Za-z0-9_]{2,32}$/.test(raw)) {
    return { error: "Usernames are 2–32 letters, numbers, or underscores." };
  }
  const username = raw.toLowerCase();
  if (RESERVED.has(username)) {
    return { error: `@${username} is reserved.` };
  }
  const displayName = username === PLATFORM_OWNER_USERNAME ? PLATFORM_OWNER_DISPLAY : raw;
  return { username, displayName };
}

export function isReservedUsername(username: string): boolean {
  return RESERVED.has(username.toLowerCase());
}

export function isPlatformOwnerUsername(username: string): boolean {
  return username.toLowerCase() === PLATFORM_OWNER_USERNAME;
}

export function normalizeChannelName(input: string): string | null {
  const name = input
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9-]/g, "")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  if (name.length < 1 || name.length > 32) return null;
  return name;
}

export function normalizeServerName(input: string): string | null {
  const name = input.trim().replace(/\s+/g, " ");
  if (name.length < 1 || name.length > 80) return null;
  if (/[\u0000-\u001F\u007F]/.test(name)) return null;
  return name;
}

export function iconLetter(name: string): string {
  const match = name.match(/[A-Za-z0-9]/);
  return (match?.[0] ?? "H").toUpperCase();
}

export function normalizePassword(input: string): string | { error: string } {
  if (input.length < 8 || input.length > 200) {
    return { error: "Passwords are 8–200 characters." };
  }
  return input;
}

export function normalizeBio(input: string): string | { error: string } {
  const bio = input.replace(/\r\n/g, "\n").trim();
  if (bio.length > 280) return { error: "Bios are at most 280 characters." };
  if (/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/.test(bio)) {
    return { error: "Bio has invalid characters." };
  }
  return bio;
}
