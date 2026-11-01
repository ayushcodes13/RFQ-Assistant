import { expect, test } from "@playwright/test";

test("quote draft surfaces requested quantity above recorded catalog stock", async ({ page }) => {
  await page.goto("/workspace");
  await page.getByRole("button", { name: /New RFQ/i }).first().click();
  const intake = page.getByRole("dialog", { name: "New RFQ" });
  await intake.getByRole("textbox", { name: "Customer email text" }).fill(
    "Please quote 175 pcs Schneider Electric LC1D09BD contactors. Synthetic test request.",
  );
  await intake.getByPlaceholder("Optional case title").fill("Stock shortfall review");
  const createResponse = page.waitForResponse((response) =>
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/api/rfqs"),
  );
  await intake.getByRole("button", { name: /Extract line items/i }).click();
  const createdCase = await (await createResponse).json();
  await expect(intake).toBeHidden();
  await expect(page.getByRole("heading", { name: "Stock shortfall review" })).toBeVisible();
  await expect.poll(async () => {
    const response = await page.request.get(`/api/proxy/api/rfqs/${createdCase.case_id}`);
    return (await response.json()).status;
  }, { timeout: 30_000 }).toBe("NEEDS_REVIEW");
  const linesResponse = await page.request.get(`/api/proxy/api/rfqs/${createdCase.case_id}/lines`);
  expect(await linesResponse.json()).toHaveLength(1);

  await page.getByRole("button", { name: "Prepare quote draft" }).click();
  await expect(page.getByText(/Requested quantity 175(?:\.0)? exceeds catalog stock 150/)).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Catalog stock" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "150", exact: true })).toBeVisible();
  await expect(page.getByText("175.0 EA", { exact: true })).toBeVisible();
});
