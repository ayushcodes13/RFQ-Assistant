import { expect, test } from "@playwright/test";

test("operator verifies a customer company suggested by an explicit email header", async ({ page }) => {
  await page.goto("/workspace");
  await page.getByRole("button", { name: /New RFQ/i }).first().click();
  const modal = page.getByRole("dialog", { name: "New RFQ" });
  const email = modal.getByRole("textbox", { name: "Customer email text" });
  await email.fill([
    "From: purchasing@example.invalid",
    "Company: Northstar Controls",
    "",
    "Please quote 2 units Siemens 6ES7223-1BL32-0XB0.",
  ].join("\n"));
  const customer = modal.getByPlaceholder("Optional customer label");
  await expect(customer).toHaveValue("");
  await expect(modal.getByText(/Customer not verified/)).toBeVisible();
  const choose = modal.getByRole("button", { name: /Email header suggests Northstar Controls/ });
  await expect(choose).toBeVisible();
  await choose.click();
  await expect(customer).toHaveValue("Northstar Controls");

  const create = page.waitForResponse((response) =>
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/api/rfqs"),
  );
  await modal.getByRole("button", { name: /Extract line items/i }).click();
  const response = await create;
  expect(response.ok()).toBe(true);
  expect((await response.json()).customer_label).toBe("Northstar Controls");
});

test("conflicting customer headers do not propose an automatic identity", async ({ page }) => {
  await page.goto("/workspace");
  await page.getByRole("button", { name: /New RFQ/i }).first().click();
  const modal = page.getByRole("dialog", { name: "New RFQ" });
  await modal.getByRole("textbox", { name: "Customer email text" }).fill(
    "Company: Alpha Controls\\nCompany: Beta Controls\\nPlease quote 2 pcs Siemens 6ES7223-1BL32-0XB0.",
  );
  await expect(modal.getByRole("button", { name: /Email header suggests/ })).toHaveCount(0);
  await expect(modal.getByPlaceholder("Optional customer label")).toHaveValue("");
});
