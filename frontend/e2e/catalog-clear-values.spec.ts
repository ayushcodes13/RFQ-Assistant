import { expect, test } from "@playwright/test";

test("nullable catalog values clear through an explicit reviewed proposal", async ({ page }) => {
  const sku = `E2E-CLEAR-${Date.now()}`;
  const seedCsv = [
    "internal_sku,manufacturer,manufacturer_part_number,description,list_price,currency,stock_qty",
    `${sku},Synthetic Parts,E2E-CLEAR-MPN,Temporary clear test item,42.50,USD,8`,
  ].join("\r\n");

  const staged = await page.request.post("/api/proxy/api/catalogs/updates", {
    multipart: {
      file: {
        name: `${sku}.csv`,
        mimeType: "text/csv",
        buffer: Buffer.from(seedCsv),
      },
    },
  });
  expect(staged.ok()).toBe(true);
  const [seedProposal] = await staged.json();
  const acceptedSeed = await page.request.post(
    `/api/proxy/api/catalogs/updates/review`,
    { data: { decisions: [{ proposal_id: seedProposal.proposal_id, expected_version: seedProposal.version, decision: "accept" }] } },
  );
  expect(acceptedSeed.ok()).toBe(true);

  await page.goto("/workspace");
  await page.getByRole("button", { name: "Catalog" }).click();
  await page.getByRole("button", { name: `Edit ${sku}` }).click();

  const dialog = page.getByRole("dialog", { name: "Edit item" });
  await dialog.getByRole("checkbox", { name: /Clear list price/ }).check();
  await dialog.getByRole("checkbox", { name: /Clear stock on hand/ }).check();
  await dialog.getByRole("button", { name: "Create change proposal" }).click();
  await expect(dialog).toBeHidden();

  await page.locator("#main-content").getByRole("button", { name: "Update data" }).click();
  const proposal = page.getByRole("article").filter({ hasText: sku });
  await expect(proposal.getByText("This proposal clears the stored list price and currency and stock qty.")).toBeVisible();
  await expect(proposal.getByRole("row", { name: /list price.*Clear stored value/ })).toBeVisible();
  await expect(proposal.getByRole("row", { name: /stock qty.*Clear stored value/ })).toBeVisible();

  await proposal.getByRole("button", { name: /^Mark proposal .* accepted/ }).click();
  const stagedResponse = await page.request.get("/api/proxy/api/catalogs");
  expect(stagedResponse.ok()).toBe(true);
  const stagedItems = await stagedResponse.json();
  const stagedItem = stagedItems.find((row: { internal_sku: string }) => row.internal_sku === sku);
  expect(stagedItem.list_price).toBe(42.5);
  expect(stagedItem.stock_qty).toBe(8);

  await page.getByRole("button", { name: "Review done" }).click();
  const response = await page.request.get("/api/proxy/api/catalogs");
  expect(response.ok()).toBe(true);
  const items = await response.json();
  const item = items.find((row: { internal_sku: string }) => row.internal_sku === sku);
  expect(item.list_price).toBeNull();
  expect(item.currency).toBeNull();
  expect(item.stock_qty).toBeNull();
  expect(item.description).toBeTruthy();
  expect(item.manufacturer).toBe("Synthetic Parts");
  expect(item.manufacturer_part_number).toBe("E2E-CLEAR-MPN");
});
