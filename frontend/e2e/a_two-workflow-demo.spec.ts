import { expect, test } from "@playwright/test";

/**
 * Real browser test chaining the two distributor demos using only
 * deterministic local fixtures. Does not simulate sending customer mail
 * or claim that a live Luna provider was contacted.
 */
test("distributor reviews manufacturer changes before buyer RFQ uses accepted items", async ({ page }) => {
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Update data" }).first().click();
  await expect(page.getByRole("heading", { name: "Update distributor data" })).toBeVisible();

  await page.getByRole("button", { name: "Attach a file" }).click();
  await page.getByLabel("Choose distributor source file").setInputFiles(
    "../demo-data/distributor-update-demo.csv",
  );
  await page.getByRole("button", { name: /Review file changes/ }).click();

  const acceptedSkus = ["SKU-DEMO-OMR-001", "SKU-DEMO-WAGO-001"];
  for (const sku of acceptedSkus) {
    const article = page.getByRole("article").filter({ hasText: sku });
    await expect(article).toBeVisible();
    await article.getByRole("button", { name: /^Mark proposal .* accepted/ }).click();
  }
  const rejected = page.getByRole("article").filter({ hasText: "SKU-SCH-001" });
  await expect(rejected).toBeVisible();
  await rejected.getByRole("button", { name: /^Mark proposal .* rejected/ }).click();

  const before = await page.request.get("/api/proxy/api/catalogs");
  expect(before.ok()).toBe(true);
  const beforeItems: { internal_sku: string; stock_qty: number | null }[] = await before.json();
  expect(beforeItems.find((item) => item.internal_sku === "SKU-DEMO-OMR-001")).toBeUndefined();
  expect(beforeItems.find((item) => item.internal_sku === "SKU-DEMO-WAGO-001")).toBeUndefined();
  expect(beforeItems.find((item) => item.internal_sku === "SKU-SCH-001")?.stock_qty).toBe(150);

  await page.getByRole("button", { name: "Review done" }).click();
  await expect(page.getByText(/2 changes were applied; 1 was rejected/)).toBeVisible();
  const after = await page.request.get("/api/proxy/api/catalogs");
  const afterItems: { internal_sku: string; stock_qty: number | null }[] = await after.json();
  expect(afterItems.find((item) => item.internal_sku === "SKU-DEMO-OMR-001")?.stock_qty).toBe(35);
  expect(afterItems.find((item) => item.internal_sku === "SKU-DEMO-WAGO-001")?.stock_qty).toBe(42);
  expect(afterItems.find((item) => item.internal_sku === "SKU-SCH-001")?.stock_qty).toBe(150);

  await page.getByRole("button", { name: "Catalog", exact: true }).click();
  const search = page.getByPlaceholder("Search SKU, manufacturer, or part number");
  await search.fill("SKU-DEMO-OMR-001");
  await expect(page.getByRole("row").filter({ hasText: "SKU-DEMO-OMR-001" })).toBeVisible();

  await page.getByRole("button", { name: "RFQ inbox" }).click();
  await page.getByRole("button", { name: /New RFQ/i }).first().click();
  const intake = page.getByRole("dialog", { name: "New RFQ" });
  await intake.locator('input[type="file"]').setInputFiles("../demo-data/buyer-two-line-bom-demo.csv");
  await intake.getByPlaceholder("Optional case title").fill("Synthetic two-workflow buyer");
  await intake.getByPlaceholder("Optional customer label").fill("Northstar Demo Buyer");
  const create = page.waitForResponse((response) =>
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/api/rfqs"),
  );
  await intake.getByRole("button", { name: /Extract line items/i }).click();
  const response = await create;
  expect(response.ok()).toBe(true);
  expect((await response.json()).customer_label).toBe("Northstar Demo Buyer");
  await expect(page.getByRole("heading", { name: "Synthetic two-workflow buyer" })).toBeVisible();
  await expect(page.getByText(/2 lines ·/)).toBeVisible({ timeout: 30_000 });

  const approve = page.getByRole("button", { name: /^Approve line \d+$/ });
  await expect(approve).toHaveCount(2);
  await approve.first().click();
  await expect(page.getByText("Approved", { exact: true })).toHaveCount(1);
  await approve.first().click();
  await expect(page.getByText("Approved", { exact: true })).toHaveCount(2);

  await page.getByRole("button", { name: "Prepare quote draft" }).click();
  const quote = page.locator('section[aria-labelledby="quote-preparation-heading"]');
  await expect(quote.getByText("G2R-1-S", { exact: true })).toBeVisible();
  await expect(quote.getByText("2002-1201", { exact: true })).toBeVisible();
  await expect(quote.getByRole("cell", { name: "35", exact: true })).toBeVisible();
  await expect(quote.getByRole("cell", { name: "42", exact: true })).toBeVisible();
  await quote.getByRole("button", { name: /Show evidence for line 1,/ }).first().click();
  const evidence = page.getByRole("dialog", { name: "Source evidence" });
  await expect(evidence.getByRole("link", { name: /Open original source/ })).toBeVisible();
  await evidence.getByRole("button", { name: "Close evidence drawer" }).click();

  await page.getByRole("button", { name: /Export draft/i }).click();
  const exportDialog = page.getByRole("dialog", { name: /Export draft/i });
  await expect(exportDialog.getByText("READY_TO_EXPORT", { exact: true })).toBeVisible();
  await exportDialog.getByRole("button", { name: /Generate draft export/i }).click();
  await expect(exportDialog.getByText("Export ready!")).toBeVisible({ timeout: 30_000 });
  const download = exportDialog.getByRole("link", { name: /Download worksheet/i });
  const path = await download.getAttribute("href");
  expect(path).toBeTruthy();
  const worksheet = await page.request.get(path!);
  expect(worksheet.ok()).toBe(true);
  expect(worksheet.headers()["content-type"]).toContain("spreadsheetml");
  expect((await worksheet.body()).byteLength).toBeGreaterThan(1000);
});
