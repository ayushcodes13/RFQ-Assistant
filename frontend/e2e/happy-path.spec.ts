import { expect, test } from "@playwright/test";

/**
 * One deterministic, synthetic happy path:
 * paste RFQ text -> extract two exact-match lines -> approve both -> export a
 * draft worksheet -> download it.
 *
 * This is intentionally the narrowest end-to-end proof that the redesigned UI
 * speaks the real backend contract. It is not a claim about extraction quality.
 */
const RFQ_TEXT = `Please quote the following spare parts:
1. 10 pcs of Schneider Electric LC1D09BD contactors (24VDC coil)
2. 4 units Siemens 6ES7223-1BL32-0XB0 digital I/O modules`;

test("paste RFQ, approve every line, export and download a draft worksheet", async ({
  page,
}) => {
  await page.goto("/workspace");

  // Open the product workspace directly; the landing page lives at `/`.
  await expect(
    page.getByRole("button", { name: /New RFQ/i }).first()
  ).toBeVisible({ timeout: 20_000 });

  await page.getByRole("button", { name: /New RFQ/i }).first().click();

  const ingestDialog = page.getByRole("dialog", { name: "New RFQ" });
  await expect(ingestDialog).toBeVisible();
  await ingestDialog.getByRole("button", { name: /Paste text/i }).click();
  await ingestDialog
    .getByPlaceholder(/Paste email or RFQ text here/i)
    .fill(RFQ_TEXT);
  await ingestDialog
    .getByPlaceholder("Optional case title")
    .fill("E2E synthetic happy path");
  await ingestDialog
    .getByPlaceholder("Optional customer label")
    .fill("Synthetic Customer");
  await ingestDialog.getByRole("button", { name: /Extract line items/i }).click();

  await expect(ingestDialog).toBeHidden({ timeout: 30_000 });
  await expect(
    page.getByRole("heading", { name: "E2E synthetic happy path" })
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/2 lines · 2 need review/i)).toBeVisible();

  // Approve each extracted line. Refetch after each approval replaces the row,
  // so always target the first remaining Approve button and wait for the badge.
  const approveButtons = page.getByRole("button", { name: /^Approve line \d+$/ });
  await expect(approveButtons).toHaveCount(2);

  await approveButtons.first().click();
  await expect(page.getByText("Approved", { exact: true })).toHaveCount(1);

  await page.getByRole("button", { name: /^Approve line \d+$/ }).first().click();
  await expect(page.getByText("Approved", { exact: true })).toHaveCount(2);
  await expect(page.getByText("Ready", { exact: true })).toBeVisible();

  const exportTrigger = page.getByRole("button", { name: /Export draft/i });
  await exportTrigger.click();
  const exportDialog = page.getByRole("dialog", { name: /Export draft/i });
  await expect(exportDialog).toBeVisible();
  await expect(exportDialog).toHaveAttribute("aria-modal", "true");
  const headerClose = exportDialog.locator('button[aria-label="Close"]');
  await expect(headerClose).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(exportDialog.getByRole("button", { name: "Close" }).last()).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(headerClose).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(exportDialog).toBeHidden();
  await expect(exportTrigger).toBeFocused();
  await exportTrigger.click();
  await expect(exportDialog).toBeVisible();
  await expect(exportDialog.getByText("READY_TO_EXPORT", { exact: true })).toBeVisible();
  await exportDialog
    .getByRole("button", { name: /Generate draft export/i })
    .click();

  await expect(exportDialog.getByText("Export ready!")).toBeVisible({
    timeout: 30_000,
  });

  const downloadLink = exportDialog.getByRole("link", {
    name: /Download worksheet/i,
  });
  await expect(downloadLink).toBeVisible();
  const href = await downloadLink.getAttribute("href");
  expect(href).toContain("/api/rfqs/");
  expect(href).toContain("/exports/EXP-");

  const response = await page.request.get(href as string);
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("spreadsheetml");
  expect((await response.body()).byteLength).toBeGreaterThan(1_000);
});

test("open an extracted XLSX line at its source row and field cells", async ({ page }) => {
  await page.goto("/workspace");
  await expect(page.getByRole("button", { name: /New RFQ/i }).first()).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: /New RFQ/i }).first().click();

  const ingestDialog = page.getByRole("dialog", { name: "New RFQ" });
  await ingestDialog.locator('input[type="file"]').setInputFiles("../fixtures/rfq_samples/industrial_control_bom_20lines.xlsx");
  await ingestDialog.getByPlaceholder("Optional case title").fill("Source navigation E2E");
  await ingestDialog.getByRole("button", { name: /Extract line items/i }).click();

  await expect(ingestDialog).toBeHidden({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Source navigation E2E" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("row").nth(1)).toBeVisible();
  await page.getByRole("row").nth(1).click();
  await page.getByRole("button", { name: "Open source row and cells" }).click();

  const sourceDialog = page.getByRole("dialog", { name: /· row \d+/i });
  await expect(sourceDialog).toBeVisible();
  await expect(sourceDialog.getByText(/Selected row:/)).toBeVisible();
  await expect(sourceDialog.locator("td[aria-label*='selected source cell']").first()).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(sourceDialog).toBeHidden();
});

test("open a PDF line at its original source page", async ({ page }) => {
  await page.goto("/workspace");
  await expect(page.getByRole("button", { name: /New RFQ/i }).first()).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: /New RFQ/i }).first().click();

  const ingestDialog = page.getByRole("dialog", { name: "New RFQ" });
  await ingestDialog.locator('input[type="file"]').setInputFiles("../fixtures/rfq_samples/formal_rfq_native.pdf");
  await ingestDialog.getByPlaceholder("Optional case title").fill("PDF source navigation E2E");
  await ingestDialog.getByRole("button", { name: /Extract line items/i }).click();

  await expect(ingestDialog).toBeHidden({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "PDF source navigation E2E" })).toBeVisible({ timeout: 30_000 });
  const lineItems = page.getByRole("region", { name: "Line items" });
  await expect(lineItems.getByRole("row").nth(1)).toBeVisible();
  await lineItems.getByRole("row").nth(1).click();
  await page.getByRole("button", { name: "View original page" }).click();

  const sourceDialog = page.getByRole("dialog", { name: /Page \d+/i });
  await expect(sourceDialog).toBeVisible();
  const sourceImage = sourceDialog.locator('img[alt*="formal_rfq_native.pdf"]');
  await expect(sourceImage).toBeVisible();
  await expect.poll(() => sourceImage.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
});
