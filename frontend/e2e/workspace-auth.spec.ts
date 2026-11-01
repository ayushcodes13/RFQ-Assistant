import { expect, test } from "@playwright/test";

test("protected proxy preserves each user's identity and role", async ({ page }) => {
  // This suite runs separately with runtime-generated per-user test credentials.
  const api = "/api/proxy/api/health";
  await expect.poll(async () => (await page.request.get(api)).status()).toBe(401);
  await page.goto("/login");
  await page.getByLabel("Personal access key").fill("incorrect-access-key-000000000");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Invalid access key.", { exact: true })).toBeVisible();

  const viewerKey = process.env.RFQ_WORKSPACE_TEST_VIEWER_KEY;
  const adminKey = process.env.RFQ_WORKSPACE_TEST_ADMIN_KEY;
  if (!viewerKey || !adminKey) throw new Error("Protected browser test requires runtime-generated user keys.");

  await page.getByLabel("Personal access key").fill(viewerKey);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/workspace/);
  expect((await page.request.get(api)).status()).toBe(200);
  const session = await page.request.get("/api/workspace-session");
  expect((await session.json()).user).toEqual({
    user_id: "demo-viewer",
    name: "Read-Only Auditor",
    role: "viewer",
  });
  const cookie = (await page.context().cookies()).find((item) => item.name === "rfq_workspace_session");
  expect(cookie).toBeDefined();
  expect(cookie?.value).not.toContain(viewerKey);
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("Strict");
  const originalCookie = cookie!;
  const lastCharacter = originalCookie.value.at(-1);
  const tamperedValue = `${originalCookie.value.slice(0, -1)}${lastCharacter === "A" ? "B" : "A"}`;
  await page.context().addCookies([{ ...originalCookie, value: tamperedValue }]);
  expect((await page.request.get(api)).status()).toBe(401);
  await page.context().addCookies([originalCookie]);

  const viewerWrite = await page.request.post("/api/proxy/api/rfqs", {
    multipart: { pasted_text: "10 pcs LC1D09BD Schneider" },
  });
  expect(viewerWrite.status()).toBe(403);

  await page.request.delete("/api/workspace-session");
  await expect.poll(async () => (await page.request.get(api)).status()).toBe(401);

  await page.goto("/login");
  await page.getByLabel("Personal access key").fill(adminKey);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/workspace/);
  const adminWrite = await page.request.post("/api/proxy/api/rfqs", {
    multipart: { pasted_text: "10 pcs LC1D09BD Schneider" },
  });
  expect(adminWrite.status()).toBe(200);
});
