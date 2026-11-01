import { expect, test } from "@playwright/test";

test("quote evidence preserves each attachment citation when the first source is email text", async ({ page }) => {
  await page.goto("/workspace");
  await page.getByRole("button", { name: /New RFQ/i }).first().click();
  const intake = page.getByRole("dialog", { name: "New RFQ" });
  await intake.getByRole("textbox", { name: "Customer email text" }).fill(
    "Hello, please quote 2 units Siemens 6ES7223-1BL32-0XB0. The attached BOM adds other parts.",
  );
  await intake.locator('input[type="file"]').setInputFiles([{
    name: "additional-parts.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Manufacturer,MPN,QTY,Description\\nSchneider Electric,LC1D09BD,10,TeSys D contactor\\n",
    ),
  }]);
  await intake.getByPlaceholder("Optional case title").fill("Mixed source citation E2E");
  const createResponse = page.waitForResponse((response) =>
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/api/rfqs"),
  );
  await intake.getByRole("button", { name: /Extract line items/i }).click();
  const result = await createResponse;
  expect(result.ok()).toBe(true);
  const createdCase = await result.json();
  expect(createdCase.source_type).toBe("EMAIL_TEXT");
  const attachment = createdCase.source_documents.find(
    (item: { source_file: { file_name: string; file_id: string } }) => item.source_file.file_name === "additional-parts.csv",
  );
  expect(attachment).toBeDefined();
  await expect(page.getByRole("heading", { name: "Mixed source citation E2E" })).toBeVisible();
  await expect(page.getByText(/2 lines ·/)).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Prepare quote draft" }).click();
  const quote = page.locator('section[aria-labelledby="quote-preparation-heading"]');
  await expect(quote.getByText("LC1D09BD", { exact: true })).toBeVisible();
  const csvRow = quote.getByRole("row").filter({ hasText: "LC1D09BD" });
  const evidenceButton = csvRow.getByRole("button", { name: /Show evidence for line/i });
  await expect(evidenceButton).toBeVisible();
  await evidenceButton.click();
  const drawer = page.getByRole("dialog", { name: "Source evidence" });
  await expect(drawer.getByText(/Schneider Electric/)).toBeVisible();
  const link = drawer.getByRole("link", { name: /Open original source/ });
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute(
    "href", new RegExp(`source\\?source_file_id=${attachment.source_file.file_id}`),
  );
  await drawer.getByRole("button", { name: "Close evidence drawer" }).click();

  // The email body is evidence too, but not a separate document-opening link.
  const emailRow = quote.getByRole("row").filter({ hasText: "6ES7223-1BL32-0XB0" });
  await emailRow.getByRole("button", { name: /Show evidence for line/i }).first().click();
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText(/This is a source excerpt/)).toBeVisible();
  await expect(drawer.getByRole("link", { name: /Open original source/ })).toHaveCount(0);
});
