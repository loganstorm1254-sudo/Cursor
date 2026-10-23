interface Env {
  /** Optional override for the owner account password (default: rogue1254!!). */
  OWNER_PASSWORD?: string;
  DB: D1Database;
  AVATARS: R2Bucket;
  CHANNELS: DurableObjectNamespace;
  SERVERS: DurableObjectNamespace;
  ASSETS: Fetcher;
}
