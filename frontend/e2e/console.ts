import { test } from "@playwright/test";

// Print uncaught browser errors into the test output, so a client crash in CI explains itself.
test.beforeEach(async ({ page }) => {
  page.on("pageerror", (e) => console.log(`[pageerror] ${e.message}\n${e.stack ?? ""}`));
  page.on("console", (m) => m.type() === "error" && console.log(`[console.error] ${m.text()}`));
});
