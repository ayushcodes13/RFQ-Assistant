import { expect, test } from "@playwright/test";

const RFQ_TEXT = "2 pcs of Schneider Electric LC1D09BD contactors";

test("catalog replacement flags old matches and supports reviewed rematching", async ({ page }) => {
  await page.goto("/workspace");
  await page.getByRole("button", { name: /New RFQ/i }).first().click();

  const intake = page.getByRole("dialog", { name: "New RFQ" });
  await intake.getByRole("button", { name: /Paste text/i }).click();
  await intake.getByPlaceholder(/Paste email or RFQ text here/i).fill(RFQ_TEXT);
  await intake.getByPlaceholder("Optional case title").fill("Catalog rematch end-to-end");
  const createResponse = page.waitForResponse((response) =>
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/api/rfqs"),
  );
  await intake.getByRole("button", { name: /Extract line items/i }).click();
  const createdCase = await (await createResponse).json();
  await expect(intake).toBeHidden({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Catalog rematch end-to-end" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: /^Approve line 1$/ })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /^Approve line 1$/ }).click();
  await expect(page.getByText("Ready", { exact: true })).toBeVisible();

  const beforeResponse = await page.request.get(`/api/proxy/api/rfqs/${createdCase.case_id}/lines`);
  const [beforeLine] = await beforeResponse.json();
  expect(beforeLine.review_decision).toBe("APPROVED");
  expect(beforeLine.catalog_rematch_required).toBe(false);

  await page.getByRole("button", { name: "Catalog" }).click();
  const catalogFile = page.locator("#catalog-file-input");
  await catalogFile.setInputFiles({
    name: "synthetic-replacement-catalog.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "internal_sku,manufacturer,manufacturer_part_number,description,list_price,stock_qty\n" +
      "SKU-SCH-001,Schneider Electric,LC1D09BD,Updated synthetic contactor,43.00,12\n",
    ),
  });
  await page.getByLabel(/This replaces the active catalog snapshot/).check();
  const importResponse = page.waitForResponse((response) =>
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/api/catalogs/import"),
  );
  await page.getByRole("button", { name: "Import catalog" }).click();
  const imported = await (await importResponse).json();
  expect(imported.summary.catalog_version).toMatch(/^sha256:/);
  await expect(page.getByText("Import results")).toBeVisible();

  const staleResponse = await page.request.get(`/api/proxy/api/rfqs/${createdCase.case_id}/lines`);
  const [staleLine] = await staleResponse.json();
  expect(staleLine.catalog_rematch_required).toBe(true);
  expect(staleLine.matched_catalog_version).not.toBe(imported.summary.catalog_version);
  const blockedExport = await page.request.post(`/api/proxy/api/rfqs/${createdCase.case_id}/exports`, {
    data: { case_id: createdCase.case_id, allow_partial: false, format: "xlsx", actor: "E2E reviewer" },
  });
  expect(blockedExport.status()).toBe(400);
  expect((await blockedExport.json()).detail).toContain("rematch required");

  await page.getByRole("button", { name: /RFQ inbox/ }).click();
  await page.getByRole("button", { name: /Open Catalog rematch end-to-end/ }).click();
  await page.getByRole("row").filter({ hasText: "LC1D09BD" }).click();
  await expect(page.getByRole("alert").getByText("The catalog has changed since this match.")).toBeVisible();
  await page.getByRole("button", { name: "Refresh catalog match" }).click();
  await expect(page.getByRole("alert").getByText("The catalog has changed since this match.")).toHaveCount(0);

  const rematchedResponse = await page.request.get(`/api/proxy/api/rfqs/${createdCase.case_id}/lines`);
  const [rematchedLine] = await rematchedResponse.json();
  expect(rematchedLine.catalog_rematch_required).toBe(false);
  expect(rematchedLine.matched_catalog_version).toBe(imported.summary.catalog_version);
  expect(rematchedLine.review_decision).toBe("PENDING");
  const auditResponse = await page.request.get(`/api/proxy/api/rfqs/${createdCase.case_id}/audit`);
  expect((await auditResponse.json()).some((event: { action: string }) => event.action === "CATALOG_REMATCHED")).toBe(true);

  await page.getByRole("button", { name: /^Approve line 1$/ }).click();
  await expect(page.getByText("Ready", { exact: true })).toBeVisible();
});
