import { expect, test } from "@playwright/test";
import "./console";
import path from "node:path";

const shots = process.env.SHOTS_DIR;
const shot = async (page: import("@playwright/test").Page, name: string) => {
  if (shots) await page.screenshot({ path: path.join(shots, `${name}.png`), fullPage: true });
};

test("paper order → approved order → invoice → ask Keel", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;
  await page.goto("/signup");
  await shot(page, "01-signup");
  await page.fill("#org_name", "Sweet Spoon Kulfi");
  await page.fill("#name", "Asha Perera");
  await page.fill("#signup_email", email);
  await page.fill("#signup_password", "correct-horse-battery");
  await page.click("button[type=submit]");
  await expect(page.getByText("Drop today's paper here")).toBeVisible();

  // Catalog: products and a customer with the shorthand people actually write
  await page.goto("/catalog");
  for (const [sku, name, price, alias] of [
    ["MK", "Malai Kulfi", "4.50", "malai"],
    ["MG", "Mango Kulfi", "5.50", "mango"],
    ["PM", "Paan Masala", "6.00", "paan"],
  ]) {
    await page.fill("#p_sku", sku);
    await page.fill("#p_name", name);
    await page.fill("#p_price", price);
    await page.fill("#p_aliases", alias);
    await page.getByRole("button", { name: "Add product" }).click();
    await expect(page.getByText(`${name} ${sku}`, { exact: false })).toBeVisible();
  }
  await page.fill("#c_name", "Rasoi Kitchen");
  await page.fill("#c_aliases", "Rasoi, Rasoi III");
  await page.getByRole("button", { name: "Add customer" }).click();
  await expect(page.getByText("Rasoi Kitchen")).toBeVisible();
  await shot(page, "02-catalog");

  // Paper in
  await page.goto("/");
  await page.setInputFiles("#file_input", path.join(__dirname, "fixtures", "order-pad.pdf"));
  await page.setInputFiles("#camera_input", path.join(__dirname, "fixtures", "order-photo.png"));
  await expect(page.getByText("Waiting for you", { exact: true }).first()).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText("Waiting for you", { exact: true })).toHaveCount(2, { timeout: 45_000 });
  await shot(page, "03-desk");

  // Review the order pad: evidence boxes, held crossed-out line, approval gate
  await page.getByRole("link", { name: /^order-pad\.pdf/ }).click();
  await expect(page.getByText("Approval needed · create order")).toBeVisible();
  await expect(page.getByText("held back and not ordered", { exact: false })).toBeVisible();
  await page.locator("figure button").first().hover();
  await shot(page, "04-review");
  await page.getByRole("button", { name: "Approve and create order" }).click();
  await expect(page.getByText("Order created.")).toBeVisible();

  // Second gate: invoice
  await page.getByText("Open the order").click();
  await page.getByRole("button", { name: "Prepare invoice" }).click();
  await expect(page.getByText("Approval needed · issue invoice")).toBeVisible();
  await shot(page, "05-invoice-gate");
  await page.getByRole("button", { name: "Approve and issue" }).click();
  await expect(page.getByText(/Invoice INV-\d+ issued/)).toBeVisible();

  // The photo from an unknown customer is blocked until a person picks the customer
  await page.goto("/");
  await page.getByRole("link", { name: /^order-photo\.png/ }).click();
  await expect(page.getByText("is not a customer yet")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve and create order" })).toBeDisabled();
  await shot(page, "06-blocked-unknown-customer");

  // Ask Keel
  await page.keyboard.press("Control+k");
  await page.getByRole("button", { name: "Best selling products this month" }).click();
  await expect(page.getByText("looked at sales_by_product")).toBeVisible();
  await expect(page.getByText("Malai Kulfi:", { exact: false })).toBeVisible();
  await shot(page, "07-ask-keel");

  await page.goto("/invoices");
  await expect(page.getByText("Rasoi Kitchen")).toBeVisible();
  await shot(page, "08-invoices");
});
