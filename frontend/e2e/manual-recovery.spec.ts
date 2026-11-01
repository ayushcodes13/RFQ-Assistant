import { expect, test } from "@playwright/test";

test("recover an unparsed buyer request by entering a clearly labeled manual line", async ({ page }) => {
  await page.goto("/workspace");
  await page.getByRole("button", { name: /New RFQ/i }).first().click();

  const dialog = page.getByRole("dialog", { name: "New RFQ" });
  await dialog.getByRole("textbox", { name: "Customer email text" }).fill(
    "Subject: Request for quotation\nDate: 2026-11-01",
  );
  await dialog.getByPlaceholder("Optional case title").fill("E2E manual recovery");
  const createResponse = page.waitForResponse((response) =>
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/api/rfqs"),
  );
  await dialog.getByRole("button", { name: /Extract line items/i }).click();
  expect((await createResponse).status()).toBe(200);

  await expect(dialog).toBeHidden({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "E2E manual recovery" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/0 lines · 0 need review/i)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/otherwise, heuristic parsing is used/i)).toBeVisible();
  await expect(page.getByText(/No RFQ line items could be extracted/i)).toBeVisible();
  const prepareDraft = page.getByRole("button", { name: "Prepare quote draft" });
  await expect(prepareDraft).toBeDisabled();
  await expect(page.getByText("Add or recover a request line before preparing a quote.")).toBeVisible();

  const manualForm = page.locator("details").filter({ hasText: "Missing a requested item? Add it manually" });
  await expect(manualForm).toHaveAttribute("open", "");
  await manualForm.getByRole("textbox", { name: "Request text" }).fill("the small blue relay from last month, about 3 pieces");
  await manualForm.getByRole("textbox", { name: "Manufacturer", exact: true }).fill("Schneider Electric");
  await manualForm.getByRole("textbox", { name: "Manufacturer part number", exact: true }).fill("LC1D09BD");
  await manualForm.getByRole("spinbutton", { name: "Quantity" }).fill("3");
  await manualForm.getByRole("textbox", { name: "Description" }).fill("small blue relay");

  const addResponse = page.waitForResponse((response) =>
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/lines"),
  );
  await manualForm.getByRole("button", { name: "Add line to review" }).click();
  expect((await addResponse).status()).toBe(201);
  await expect(page.getByText("1 line · 1 needs review", { exact: true })).toBeVisible();
  await expect(prepareDraft).toBeEnabled();
  await expect(page.getByRole("button", { name: "Review sample", exact: true })).toHaveCount(0);

  const row = page.getByRole("row").filter({ hasText: "LC1D09BD" });
  await expect(row).toBeVisible();
  await row.click();
  await expect(page.getByText("Manual operator entry · no document citation")).toBeVisible();
  await expect(page.getByText("the small blue relay from last month, about 3 pieces", { exact: true })).toBeVisible();
  await expect(page.getByText(/MANUAL_ENTRY_SOURCE_REVIEW_REQUIRED/)).toBeVisible();

  await row.getByRole("button", { name: "Approve line 1" }).click();
  await expect(row.getByText("Approved", { exact: true })).toBeVisible();
});
