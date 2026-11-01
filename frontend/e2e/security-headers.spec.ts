import { expect, test } from "@playwright/test";

test("application pages include baseline browser security headers", async ({ page }) => {
  const response = await page.request.get("/");
  expect(response.status()).toBe(200);
  const headers = response.headers();

  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  expect(headers["x-dns-prefetch-control"]).toBe("off");
  expect(headers["permissions-policy"]).toBe("camera=(), microphone=(), geolocation=()");
});
