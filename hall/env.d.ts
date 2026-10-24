interface Env {
  /** Optional override for the owner account password (default: rogue1254!!). */
  OWNER_PASSWORD?: string;
  /** Optional VAPID keys; when unset Hall generates and stores a pair in D1. */
  VAPID_PUBLIC_KEY?: string;
  VAPID_PRIVATE_KEY?: string;
  VAPID_SUBJECT?: string;
  DB: D1Database;
  AVATARS: R2Bucket;
  CHANNELS: DurableObjectNamespace<import("./src/channel").ChannelRoom>;
  SERVERS: DurableObjectNamespace<import("./src/hub").ServerHub>;
  ASSETS: Fetcher;
}
