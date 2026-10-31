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

  await page.getByRole("button", { name: /Export draft/i }).click();
  const exportDialog = page.getByRole("dialog", { name: "Export draft" });
  await expect(exportDialog).toBeVisible();
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
