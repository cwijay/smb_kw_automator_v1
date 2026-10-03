import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const shots = process.env.SHOTS_DIR;
const shot = async (page: Page, name: string) => {
  if (shots) await page.screenshot({ path: path.join(shots, `${name}.png`), fullPage: true });
};
const fixture = (name: string) => path.join(__dirname, "fixtures", name);

async function upload(page: Page, kind: string, file: string) {
  await page.goto("/");
  await page.click(`#kind_${kind}`);
  await page.setInputFiles("#file_input", fixture(file));
  const row = page.getByRole("link", { name: new RegExp(`^${file}`) });
  await expect(row.getByText("Waiting for you", { exact: true })).toBeVisible({ timeout: 45_000 });
  await row.click();
}

test("batch sheet → HACCP log → lot trace to the customer", async ({ page }) => {
  await page.goto("/signup");
  await page.fill("#org_name", "Lotus Creamery");
  await page.fill("#name", "Ravi Perera");
  await page.fill("#signup_email", `e2e-prod-${Date.now()}@example.com`);
  await page.fill("#signup_password", "correct-horse-battery");
  await page.click("button[type=submit]");
  await expect(page.getByText("Drop today's paper here")).toBeVisible();

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

  // Batch sheet: a blank lot code blocks sign-off until a person records the gap
  await upload(page, "batch_sheet", "batch-sheet.pdf");
  await expect(page.getByText("Approval needed · sign off batch")).toBeVisible();
  await expect(page.getByText("no lot code", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign off batch" })).toBeDisabled();
  await shot(page, "11-batch-review");
  await page.click("#ack_missing");
  await expect(page.getByText("Recorded as a trace gap", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Sign off batch" }).click();
  await expect(page.getByText("Batch signed off.")).toBeVisible();
  await page.getByText("Open the batch record").click();
  await expect(page.getByRole("heading", { name: "Batch B-001" })).toBeVisible();
  await shot(page, "12-batch-record");

  // HACCP: control points first, then a log with a blank and an out-of-range reading
  await page.goto("/food-safety");
  for (const [name, min, unit] of [["Fill temperature", "165", "F"], ["Pack weight", "6.0", "lb"]]) {
    await page.fill("#ccp_name", name);
    await page.fill("#ccp_min", min);
    await page.fill("#ccp_unit", unit);
    await page.getByRole("button", { name: "Add control point" }).click();
    await expect(page.getByText(name, { exact: true })).toBeVisible();
  }
  await upload(page, "haccp_log", "haccp-log.pdf");
  await expect(page.getByText("Approval needed · verify HACCP log")).toBeVisible();
  await expect(page.getByText("missing", { exact: true })).toBeVisible();
  await expect(page.getByText("out of range", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Verify and record readings" })).toBeDisabled();
  await shot(page, "13-haccp-review");
  await page.fill("#action_1", "Probe not used; batch held and re-checked at 169F");
  await page.fill("#action_2", "Underweight pouch topped up to 6.1 lb");
  await page.getByRole("button", { name: "Update the log" }).click();
  await expect(page.getByText("Corrective action: Probe not used", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Verify and record readings" }).click();
  await expect(page.getByText("3 HACCP reading(s) verified.")).toBeVisible();
  await page.goto("/food-safety");
  await expect(page.getByText("2 needed a corrective action")).toBeVisible();
  await shot(page, "14-food-safety");

  // Ship the batch's lot on an order, then trace a milk lot forward to the customer
  await upload(page, "order_pad", "order-pad.pdf");
  await page.getByRole("button", { name: "Approve and create order" }).click();
  await page.getByText("Open the order").click();
  await page.getByRole("button", { name: "+ lot" }).first().click();
  await page.locator("input[id^=lot_]").fill("L-1042");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("link", { name: "L-1042" })).toBeVisible();

  await page.goto("/trace");
  await page.fill("#trace_lot", "M-0129");
  await page.getByRole("button", { name: "Trace" }).click();
  await expect(page.getByText("Rasoi Kitchen")).toBeVisible();
  await shot(page, "15-trace-forward");

  // Backward from the finished lot: supplier lots, and the ingredient nobody wrote a lot for
  await page.getByRole("link", { name: "L-1042" }).click();
  await expect(page.locator("#trace_lot")).toHaveValue("L-1042");
  await expect(page.getByText("1 trace gap(s)")).toBeVisible();
  await expect(page.getByText("Rose Water has no lot code", { exact: false })).toBeVisible();
  await shot(page, "16-trace-backward");

  // Search tolerates the way people misspell things
  await page.goto("/search");
  await page.fill("#search_q", "temprature");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByRole("link", { name: /haccp-log\.pdf/ })).toBeVisible();
  await expect(page.getByText("close spelling").first()).toBeVisible();
  await shot(page, "17-search");
});
