import { expect, test } from "@playwright/test";

test("Protected single-operator proxy requires signed cookie session", async ({ page }) => {
  // This suite runs in a separate CI invocation with synthetic auth secrets.
  const api = "/api/proxy/api/health";
  await expect.poll(async () => (await page.request.get(api)).status()).toBe(401);
  await page.goto("/login");
  await page.getByLabel("Workspace password").fill("incorrect-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("Invalid workspace password");

  const testPassword = process.env.RFQ_WORKSPACE_PASSWORD;
  if (!testPassword) throw new Error("Protected browser test requires runtime-generated credentials.");
  await page.getByLabel("Workspace password").fill(testPassword);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/workspace/);
  expect((await page.request.get(api)).status()).toBe(200);

  const logout = await page.request.delete("/api/workspace-session");
  expect(logout.status()).toBe(200);
  await expect.poll(async () => (await page.request.get(api)).status()).toBe(401);
});
