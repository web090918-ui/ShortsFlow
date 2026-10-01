import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    env: {
      // Tests assert on absolute API URLs; production uses the /api proxy path.
      NEXT_PUBLIC_API_URL: "http://localhost:8000",
    },
  },
});
