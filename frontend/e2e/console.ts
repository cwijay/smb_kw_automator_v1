import { test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  // Print uncaught browser errors into the test output, so a client crash in CI explains itself.
  page.on("pageerror", (e) => console.log(`[pageerror] ${e.message}\n${e.stack ?? ""}`));
  page.on("console", (m) => m.type() === "error" && console.log(`[console.error] ${m.text()}`));
  // Newer Chromium returns a Promise from scrollIntoView. Emulate it so older local browsers catch the
  // same bugs CI does (an effect returning it crashed Ask Keel only in CI).
  await page.addInitScript(() => {
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (this: Element, ...args: Parameters<typeof original>) {
      original.apply(this, args);
      return Promise.resolve() as unknown as void;
    };
  });
});
