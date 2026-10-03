import { defineConfig } from "@playwright/test";

// Runs against a running stack: `make dev` (or docker compose up). BASE_URL defaults to the Next app.
export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    viewport: { width: 1360, height: 900 },
    launchOptions: process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
  },
  reporter: [["list"]],
});
