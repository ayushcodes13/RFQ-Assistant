import { expect, test } from "@playwright/test";

test("An operator can view, edit and copy an unsent clarification without sending", async ({ page }) => {
  await page.goto("/workspace");
  await page.getByRole("button", { name: /New RFQ/i }).first().click();
  const intake = page.getByRole("dialog", { name: "New RFQ" });
  await intake.getByRole("textbox", { name: "Customer email text" }).fill(
    "Please quote 10 units of Schneider Electric LC1D09BD and confirm missing specifications."
  );
  await intake.getByPlaceholder("Optional case title").fill("Clarification UI synthetic case");
  await intake.getByRole("button", { name: /Extract line items/i }).click();
  await expect(intake).toBeHidden({ timeout: 30_000 });

  await page.getByRole("button", { name: "Unsent clarification" }).click();
  const dialog = page.getByRole("dialog", { name: "Unsent customer clarification" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/Nothing is sent automatically/i)).toBeVisible();

  const editor = dialog.getByRole("textbox", { name: "Editable clarification draft" });
  await expect(editor).toHaveValue(/UNSENT DRAFT/);
  const first = await editor.inputValue();
  await editor.fill(first + "\nPlease confirm the panel voltage.");
  await expect(editor).toHaveValue(/Please confirm the panel voltage\./);
  await expect(dialog.getByRole("button", { name: /send/i })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Close clarification draft" }).click();
  await expect(dialog).toBeHidden();
});
