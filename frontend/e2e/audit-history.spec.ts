import { expect, test } from "@playwright/test";

test("Operator can inspect persisted approval history in the RFQ workspace", async ({ page }) => {
  await page.goto("/workspace");
  await page.getByRole("button", { name: /New RFQ/i }).first().click();
  const intake = page.getByRole("dialog", { name: "New RFQ" });
  await intake.getByRole("textbox", { name: "Customer email text" }).fill(
    "Please quote 10 units Schneider Electric LC1D09BD contactor."
  );
  await intake.getByPlaceholder("Optional case title").fill("Synthetic audit history demo");
  await intake.getByRole("button", { name: /Extract line items/i }).click();
  await expect(intake).toBeHidden({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Synthetic audit history demo" })).toBeVisible();
  await page.getByRole("button", { name: /Activity history/i }).click();
  const history = page.getByRole("dialog", { name: "RFQ activity history" });
  await expect(history).toBeVisible();
  await expect(history.getByRole("list", { name: "Recorded RFQ events" })).toBeVisible();
  await expect(history.getByText(/CASE CREATED/i)).toBeVisible();
  await history.getByRole("button", { name: "Close" }).click();
  await expect(history).toBeHidden();

  const approve = page.getByRole("button", { name: /^Approve line \d+$/ });
  await approve.first().click();
  await expect(page.getByText("Approved", { exact: true })).toHaveCount(1);
  await page.getByRole("button", { name: /Activity history/i }).click();
  const after = page.getByRole("dialog", { name: "RFQ activity history" });
  await expect(after.getByText(/LINE APPROVED/i)).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "RFQ inbox" }).first().click();
  await page.getByRole("button", { name: "Open Synthetic audit history demo" }).first().click();
  await page.getByRole("button", { name: /Activity history/i }).click();
  await expect(page.getByRole("dialog", { name: "RFQ activity history" }).getByText(/LINE APPROVED/i)).toBeVisible();
});
