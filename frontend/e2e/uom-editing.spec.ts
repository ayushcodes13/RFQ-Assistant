import { expect, test } from "@playwright/test";

test("resolve a missing unit of measure from the workbench", async ({ page }) => {
  const caseTitle = `UOM editor E2E ${Date.now()}`;
  await page.goto("/workspace");
  await expect(
    page.getByRole("button", { name: /New RFQ/i }).first(),
  ).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: /New RFQ/i }).first().click();

  const intake = page.getByRole("dialog", { name: "New RFQ" });
  await intake.getByRole("button", { name: /Paste text/i }).click();
  await intake
    .getByPlaceholder(/Paste email or RFQ text here/i)
    .fill("1. 2 EA Omron E2E-X7D1-N proximity sensor");
  await intake.getByPlaceholder("Optional case title").fill(caseTitle);

  const createResponsePromise = page.waitForResponse((response) =>
    response.request().method() === "POST" &&
    new URL(response.url()).pathname.endsWith("/api/rfqs"),
  );
  await intake.getByRole("button", { name: /Extract line items/i }).click();
  const createResponse = await createResponsePromise;
  expect(createResponse.status()).toBe(200);
  const createdCase = await createResponse.json() as { case_id: string };

  await expect(intake).toBeHidden({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: caseTitle })).toBeVisible({
    timeout: 30_000,
  });
  const linesPath = `/api/proxy/api/rfqs/${createdCase.case_id}/lines`;
  await expect.poll(async () => {
    const response = await page.request.get(linesPath);
    if (response.status() !== 200) return -1;
    return (await response.json()).length;
  }, { timeout: 30_000 }).toBe(1);
  const lineResponse = await page.request.get(linesPath);
  expect(lineResponse.status()).toBe(200);
  const lines = await lineResponse.json() as Array<{
    line_id: string;
    line_number: number;
    version: number;
    unit: string | null;
  }>;
  expect(lines).toHaveLength(1);

  const missingUomResponse = await page.request.patch(
    `/api/proxy/api/rfqs/${createdCase.case_id}/lines/${lines[0].line_id}`,
    { data: { expected_version: lines[0].version, unit: "" } },
  );
  expect(missingUomResponse.status()).toBe(200);
  expect((await missingUomResponse.json()).unit).toBe("");

  await page.goto("/workspace");
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("button", { name: /RFQ inbox/ })
    .click();
  await page.getByRole("button", { name: `Open ${caseTitle}` }).click();
  const uomEditor = page.getByRole("button", {
    name: "Set unit of measure for line 1",
  });
  await expect(uomEditor).toBeVisible();

  await page.getByRole("button", { name: "Export draft" }).click();
  const exportDialog = page.getByRole("dialog", { name: /Export Draft/i });
  await exportDialog.getByRole("button", { name: /Generate draft export/i }).click();
  await expect(exportDialog.getByRole("alert")).toContainText(
    "missing unit of measure",
  );
  await exportDialog.getByRole("button", { name: "Close" }).last().click();

  await uomEditor.focus();
  await page.keyboard.press("Enter");
  const input = page.getByRole("textbox", { name: "Unit of measure for line 1" });
  await input.fill("EA");
  const saveResponsePromise = page.waitForResponse((response) =>
    response.request().method() === "PATCH" &&
    new URL(response.url()).pathname.endsWith(`/lines/${lines[0].line_id}`),
  );
  await input.press("Enter");
  const saveResponse = await saveResponsePromise;
  expect(saveResponse.status()).toBe(200);
  await expect(
    page.getByRole("button", { name: "Edit unit of measure for line 1" }),
  ).toContainText("EA");

  const auditResponse = await page.request.get(
    `/api/proxy/api/rfqs/${createdCase.case_id}/audit`,
  );
  expect(auditResponse.status()).toBe(200);
  const events = await auditResponse.json() as Array<{
    line_id: string;
    actor: string;
    field_name: string | null;
    old_value: string | null;
    new_value: string | null;
  }>;
  const unitEdit = events.find((event) =>
    event.line_id === lines[0].line_id &&
    event.field_name === "unit" &&
    event.new_value === "EA",
  );
  expect(unitEdit).toMatchObject({
    actor: expect.any(String),
    old_value: "",
    new_value: "EA",
  });
  expect(unitEdit?.actor).toBeTruthy();

  await page.getByRole("button", { name: "Export draft" }).click();
  const afterEditDialog = page.getByRole("dialog", { name: /Export Draft/i });
  await afterEditDialog.getByRole("button", { name: /Generate draft export/i }).click();
  await expect(afterEditDialog.getByRole("alert")).not.toContainText(
    "missing unit of measure",
  );
});
