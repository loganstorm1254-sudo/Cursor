import { cloudflareTest } from "@cloudflare/vitest-plugin";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [
    cloudflareTest({
      wrangler: { configPath: "./wrangler.jsonc" },
      miniflare: {
        bindings: {
          // Empty so tests use PLATFORM_OWNER_PASSWORD (rogue1254!!)
          OWNER_PASSWORD: "",
        },
      },
    }),
  ],
});
