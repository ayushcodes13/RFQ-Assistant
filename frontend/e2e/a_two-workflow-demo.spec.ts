import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

/**
 * Real browser test chaining the two distributor demos using only
 * deterministic local fixtures. Does not simulate sending customer mail
 * or claim that a live Luna provider was contacted.
 */
async function rejectUnfinishedProposals(request: import("@playwright/test").APIRequestContext) {
  const result = await request.get("/api/proxy/api/catalogs/updates");
  if (!result.ok()) return;
  const proposals: { proposal_id: string; version: number; review_status: string; change_type: string }[] =
    await result.json();
  const pending = proposals.filter((item) => item.review_status === "pending" && item.change_type !== "unchanged");
  if (!pending.length) return;
  const reviewed = await request.post("/api/proxy/api/catalogs/updates/review", {
    data: { decisions: pending.map((item) => ({
      proposal_id: item.proposal_id, expected_version: item.version, decision: "reject",
    })) },
  });
  expect(reviewed.ok(), "synthetic test must not leave global pending proposals").toBe(true);
}

test.afterEach(async ({ request }) => {
  await rejectUnfinishedProposals(request);
});

test("distributor reviews manufacturer changes before buyer RFQ uses accepted items", async ({ page }, testInfo) => {
  await rejectUnfinishedProposals(page.request);
  const suffix = `E2E-${process.pid}-${testInfo.retry}`;
  const skuOmron = `SKU-DEMO-OMR-${suffix}`;
  const skuWago = `SKU-DEMO-WAGO-${suffix}`;
  const mpnOmron = `G2R-1-S-${suffix}`;
  const mpnWago = `2002-1201-${suffix}`;
  const catalogCsv = readFileSync("../demo-data/distributor-update-demo.csv", "utf8")
    .replaceAll("SKU-DEMO-OMR-001", skuOmron)
    .replaceAll("SKU-DEMO-WAGO-001", skuWago)
    .replaceAll("G2R-1-S", mpnOmron)
    .replaceAll("2002-1201", mpnWago);
  const buyerCsv = readFileSync("../demo-data/buyer-two-line-bom-demo.csv", "utf8")
    .replaceAll("G2R-1-S", mpnOmron)
    .replaceAll("2002-1201", mpnWago);
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Update data" }).first().click();
  await expect(page.getByRole("heading", { name: "Update distributor data" })).toBeVisible();

  await page.getByLabel("Choose distributor source file").setInputFiles({
    name: `distributor-update-${suffix}.csv`,
    mimeType: "text/csv",
    buffer: Buffer.from(catalogCsv),
  });
  const stageResponse = page.waitForResponse((response) =>
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/api/catalogs/updates"),
  );
  await page.getByRole("button", { name: /Review file changes/ }).click();
  const stagedResponse = await stageResponse;
  expect(stagedResponse.ok(), await stagedResponse.text()).toBe(true);
  const stagedProposals: { proposal_id: string }[] = await stagedResponse.json();
  expect(stagedProposals).toHaveLength(3);

  const acceptedSkus = [skuOmron, skuWago];
  const pendingReview = page.locator('section[aria-labelledby="pending-heading"]');
  for (const sku of acceptedSkus) {
    const article = pendingReview.getByRole("article").filter({ hasText: sku });
    await expect(article).toBeVisible({ timeout: 20_000 });
    await article.getByRole("button", { name: /^Mark proposal .* accepted/ }).click();
  }
  const rejected = pendingReview.getByRole("article").filter({ hasText: "SKU-SCH-001" });
  await expect(rejected).toBeVisible();
  await rejected.getByRole("button", { name: /^Mark proposal .* rejected/ }).click();

  const before = await page.request.get("/api/proxy/api/catalogs");
  expect(before.ok()).toBe(true);
  const beforeItems: { internal_sku: string; stock_qty: number | null }[] = await before.json();
  expect(beforeItems.find((item) => item.internal_sku === skuOmron)).toBeUndefined();
  expect(beforeItems.find((item) => item.internal_sku === skuWago)).toBeUndefined();
  expect(beforeItems.find((item) => item.internal_sku === "SKU-SCH-001")?.stock_qty).toBe(150);

  await page.getByRole("button", { name: "Review done" }).click();
  await expect(page.getByText(/2 changes were applied; 1 was rejected/)).toBeVisible();
  const after = await page.request.get("/api/proxy/api/catalogs");
  const afterItems: { internal_sku: string; stock_qty: number | null }[] = await after.json();
  expect(afterItems.find((item) => item.internal_sku === skuOmron)?.stock_qty).toBe(35);
  expect(afterItems.find((item) => item.internal_sku === skuWago)?.stock_qty).toBe(42);
  expect(afterItems.find((item) => item.internal_sku === "SKU-SCH-001")?.stock_qty).toBe(150);

  await page.getByRole("button", { name: "Catalog", exact: true }).click();
  const search = page.getByPlaceholder("Search SKU, manufacturer, or part number");
  await search.fill(skuOmron);
  await expect(page.getByRole("row").filter({ hasText: skuOmron })).toBeVisible();

  await page.getByRole("button", { name: "RFQ inbox" }).click();
  await page.getByRole("button", { name: /New RFQ/i }).first().click();
  const intake = page.getByRole("dialog", { name: "New RFQ" });
  await intake.locator('input[type="file"]').setInputFiles({
    name: `buyer-bom-${suffix}.csv`,
    mimeType: "text/csv",
    buffer: Buffer.from(buyerCsv),
  });
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
  await expect(quote.getByText(mpnOmron, { exact: true })).toBeVisible();
  await expect(quote.getByText(mpnWago, { exact: true })).toBeVisible();
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
