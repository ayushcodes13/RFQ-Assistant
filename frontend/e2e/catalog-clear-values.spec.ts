import { expect, test } from "@playwright/test";

test("nullable catalog values clear through an explicit reviewed proposal", async ({ page }) => {
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Catalog" }).click();
  await page.getByRole("button", { name: "Edit SKU-SCH-001" }).click();

  const dialog = page.getByRole("dialog", { name: "Edit item" });
  await dialog.getByRole("checkbox", { name: /Clear list price/ }).check();
  await dialog.getByRole("checkbox", { name: /Clear stock on hand/ }).check();
  await dialog.getByRole("button", { name: "Create change proposal" }).click();
  await expect(dialog).toBeHidden();

  await page.locator("#main-content").getByRole("button", { name: "Update data" }).click();
  const proposal = page.getByRole("article").filter({ hasText: "SKU-SCH-001" });
  await expect(proposal.getByText("This proposal clears the stored list price and stock qty.")).toBeVisible();
  await expect(proposal.getByRole("row", { name: /list price.*Clear stored value/ })).toBeVisible();
  await expect(proposal.getByRole("row", { name: /stock qty.*Clear stored value/ })).toBeVisible();

  await proposal.getByRole("button", { name: /^Accept proposal/ }).click();
  const response = await page.request.get("/api/proxy/api/catalogs");
  expect(response.ok()).toBe(true);
  const items = await response.json();
  const item = items.find((row: { internal_sku: string }) => row.internal_sku === "SKU-SCH-001");
  expect(item.list_price).toBeNull();
  expect(item.currency).toBeNull();
  expect(item.stock_qty).toBeNull();
  expect(item.description).toBeTruthy();
  expect(item.manufacturer).toBe("Schneider Electric");
  expect(item.manufacturer_part_number).toBe("LC1D09BD");
});
