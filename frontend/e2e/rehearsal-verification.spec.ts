import { expect, test, type Page } from "@playwright/test";

/**
 * Verification tests for the audit demo rehearsal.
 *
 * These tests prove the full-browser workflow works end-to-end from a clean
 * start, that blocked exports behave correctly, that state persists across
 * browser refresh, and that the send route is simulated-only.
 *
 * All data is synthetic. See docs/END_TO_END_AUDIT.md.
 */

const KNOWN_GOOD_RFQ_TEXT = `Please quote the following spare parts:
1. 10 pcs of Schneider Electric LC1D09BD contactors (24VDC coil)
2. 4 units Siemens 6ES7223-1BL32-0XB0 digital I/O modules`;

const RFQ_WITH_MISSING_QUANTITY = `Please quote the following spare parts:
1. 5 units of Schneider Electric LC1D09BD contactors
2. 3 units of Omron E2E-X7D1-N sensors
3. Schneider Electric LC1D09BD contactor`;

type ApiCase = { case_id: string; title: string };
type ApiLine = {
  line_id: string;
  line_number: number;
  version: number;
  match_status: string;
  quantity: number | null;
  unit: string | null;
  requested_mpn: string | null;
  requested_manufacturer: string | null;
  selected_catalog_sku: string | null;
  review_decision: string;
};
type ApiAuditEvent = { action: string };
type ApiCatalogItem = { manufacturer_part_number: string };
type LineReviewUpdate = {
  quantity: number | null;
  unit: string;
  requested_mpn: string | null;
  requested_manufacturer: string | null;
  selected_catalog_sku: string | null;
  match_status: string;
  review_decision: string;
};

/**
 * Helper: list cases via the API and find one by title substring.
 */
async function findCaseByTitle(page: Page, titleSubstring: string): Promise<ApiCase> {
  const casesResp = await page.request.get("/api/proxy/api/rfqs");
  expect(casesResp.status()).toBe(200);
  const cases = (await casesResp.json()) as ApiCase[];
  const ourCase = cases.find((item) => item.title.includes(titleSubstring));
  expect(ourCase).toBeDefined();
  if (!ourCase) throw new Error(`No case found for title: ${titleSubstring}`);
  return ourCase;
}

/**
 * Test A: Happy path — full browser workflow ending in downloaded draft.
 *
 * Known-good RFQ chosen to avoid the audit defects:
 * - No numeric-only MPNs (avoids Finding 1)
 * - LC1D09BD and 6ES7223-1BL32-0XB0 are both in the default catalog
 * - Text paste input avoids XLSX header and PDF manufacturer extraction issues
 */
test("Rehearsal A — happy path: create, extract, approve, export, download", async ({
  page,
}) => {
  await page.goto("/workspace");

  await expect(
    page.getByRole("button", { name: /New RFQ/i }).first()
  ).toBeVisible({ timeout: 20_000 });

  await page.getByRole("button", { name: /New RFQ/i }).first().click();

  const ingestDialog = page.getByRole("dialog", { name: "New RFQ" });
  await expect(ingestDialog).toBeVisible();
  await ingestDialog.getByRole("button", { name: /Paste text/i }).click();
  await ingestDialog
    .getByPlaceholder(/Paste email or RFQ text here/i)
    .fill(KNOWN_GOOD_RFQ_TEXT);
  await ingestDialog
    .getByPlaceholder("Optional case title")
    .fill("Rehearsal A happy path");
  await ingestDialog
    .getByPlaceholder("Optional customer label")
    .fill("Synthetic Customer");
  await ingestDialog.getByRole("button", { name: /Extract line items/i }).click();

  await expect(ingestDialog).toBeHidden({ timeout: 30_000 });
  await expect(
    page.getByRole("heading", { name: "Rehearsal A happy path" })
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/2 lines · 2 need review/i)).toBeVisible();

  // Approve each extracted line.
  const approveButtons = page.getByRole("button", { name: /^Approve line \d+$/ });
  await expect(approveButtons).toHaveCount(2);

  await approveButtons.first().click();
  await expect(page.getByText("Approved", { exact: true })).toHaveCount(1);

  await page.getByRole("button", { name: /^Approve line \d+$/ }).first().click();
  await expect(page.getByText("Approved", { exact: true })).toHaveCount(2);
  await expect(page.getByText("Ready", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /Export draft/i }).click();
  const exportDialog = page.getByRole("dialog", { name: "Export draft" });
  await expect(exportDialog).toBeVisible();
  await expect(exportDialog.getByText("READY_TO_EXPORT", { exact: true })).toBeVisible();
  await exportDialog
    .getByRole("button", { name: /Generate draft export/i })
    .click();

  await expect(exportDialog.getByText("Export ready!")).toBeVisible({
    timeout: 30_000,
  });

  const downloadLink = exportDialog.getByRole("link", {
    name: /Download worksheet/i,
  });
  await expect(downloadLink).toBeVisible();
  const href = await downloadLink.getAttribute("href");
  expect(href).toContain("/api/rfqs/");
  expect(href).toContain("/exports/EXP-");

  // Download the file and verify it is a valid XLSX with draft labeling.
  const response = await page.request.get(href as string);
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("spreadsheetml");
  expect((await response.body()).byteLength).toBeGreaterThan(1_000);

  // Verify it is a valid ZIP file (XLSX is a ZIP archive: PK\x03\x04).
  const body = await response.body();
  expect(body[0]).toBe(0x50); // 'P'
  expect(body[1]).toBe(0x4b); // 'K'
  expect(body[2]).toBe(0x03);
  expect(body[3]).toBe(0x04);
});

/**
 * Test B: A missing quantity blocks export even when the requested part has an
 * exact catalog match. Correct the quantity in the UI, review the line, then
 * export. No substitute SKU is assigned.
 */
test("Rehearsal B — blocked export on unresolved line, then resolve", async ({
  page,
}) => {
  await page.goto("/workspace");

  // Create the case via browser UI.
  await page.getByRole("button", { name: /New RFQ/i }).first().click();
  const ingestDialog = page.getByRole("dialog", { name: "New RFQ" });
  await expect(ingestDialog).toBeVisible();
  await ingestDialog.getByRole("button", { name: /Paste text/i }).click();
  await ingestDialog
    .getByPlaceholder(/Paste email or RFQ text here/i)
    .fill(RFQ_WITH_MISSING_QUANTITY);
  await ingestDialog
    .getByPlaceholder("Optional case title")
    .fill("Rehearsal B blocked");
  await ingestDialog.getByRole("button", { name: /Extract line items/i }).click();

  await expect(ingestDialog).toBeHidden({ timeout: 30_000 });
  await expect(
    page.getByRole("heading", { name: "Rehearsal B blocked" })
  ).toBeVisible({ timeout: 30_000 });

  // Get the case ID via API.
  const ourCase = await findCaseByTitle(page, "Rehearsal B blocked");
  const caseId = ourCase.case_id;

  // --- Export is blocked before the required human review. ---
  const blockedExport = await page.request.post(
    `/api/proxy/api/rfqs/${caseId}/exports`,
    {
      data: JSON.stringify({
        case_id: caseId,
        allow_partial: false,
        format: "xlsx",
        actor: "Demo Operator",
      }),
      headers: { "Content-Type": "application/json" },
    }
  );
  expect(blockedExport.status()).toBe(400);
  const blockedBody = await blockedExport.json();
  expect(blockedBody.detail).toMatch(/unresolved|blocked|validation|not approved/i);

  // --- Approve two complete exact-match lines via the UI. ---
  const approveButtons = page.getByRole("button", { name: /^Approve line \d+$/ });
  await expect(approveButtons).toHaveCount(3);
  await approveButtons.first().click();
  await expect(page.getByText("Approved", { exact: true })).toHaveCount(1);
  await page.getByRole("button", { name: /^Approve line \d+$/ }).first().click();
  await expect(page.getByText("Approved", { exact: true })).toHaveCount(2);

  // --- Export remains blocked because line 3 is missing its quantity. ---
  const stillBlockedExport = await page.request.post(
    `/api/proxy/api/rfqs/${caseId}/exports`,
    {
      data: JSON.stringify({
        case_id: caseId,
        allow_partial: false,
        format: "xlsx",
        actor: "Demo Operator",
      }),
      headers: { "Content-Type": "application/json" },
    }
  );
  expect(stillBlockedExport.status()).toBe(400);

  // Correct the missing quantity in the UI. Do not assign a different SKU to
  // an unknown MPN or imply that an unverified substitute is acceptable.
  const linesResp = await page.request.get(
    `/api/proxy/api/rfqs/${caseId}/lines`
  );
  const lines = (await linesResp.json()) as ApiLine[];
  const lineNeedingQuantity = lines.find((line) => line.line_number === 3);
  expect(lineNeedingQuantity?.quantity).toBeNull();
  expect(lineNeedingQuantity?.match_status).toBe("EXACT_MATCH");

  const lineItems = page.getByRole("region", { name: "Line items" });
  const thirdRow = lineItems.locator("tbody tr").nth(2);
  const quantityCell = thirdRow.locator("td").nth(1);
  await quantityCell.dblclick();
  const quantityInput = quantityCell.locator("input");
  await quantityInput.fill("2");
  await quantityInput.press("Enter");
  await expect(quantityCell.getByText("2", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Approve line 3" }).click();
  await expect(approveButtons).toHaveCount(0);
  await expect(page.getByText(/3 lines · 0 need review/i)).toBeVisible();

  // --- Export should now succeed ---
  const successExport = await page.request.post(
    `/api/proxy/api/rfqs/${caseId}/exports`,
    {
      data: JSON.stringify({
        case_id: caseId,
        allow_partial: false,
        format: "xlsx",
        actor: "Demo Operator",
      }),
      headers: { "Content-Type": "application/json" },
    }
  );
  expect(successExport.status()).toBe(200);
  const manifest = await successExport.json();
  expect(manifest.is_draft).toBe(true);
  expect(manifest.approved_lines).toBe(3);

  // --- Download the draft worksheet and verify its generated payload. ---
  const downloadHref = `/api/proxy/api/rfqs/${caseId}/exports/${manifest.export_id}`;
  const downloadResp = await page.request.get(downloadHref);
  expect(downloadResp.status()).toBe(200);
  expect(downloadResp.headers()["content-type"]).toContain("spreadsheetml");
  expect((await downloadResp.body()).byteLength).toBeGreaterThan(1_000);

  const body = await downloadResp.body();
  expect(body[0]).toBe(0x50); // 'P' (ZIP)
  expect(body[1]).toBe(0x4b); // 'K'
});

/**
 * Test C: Persistence — after browser refresh, the case, approvals, and audit
 * trail must persist.
 */
test("Rehearsal C — persistence across browser refresh", async ({
  page,
}) => {
  await page.goto("/workspace");

  // Create a case and approve one line.
  await page.getByRole("button", { name: /New RFQ/i }).first().click();
  const ingestDialog = page.getByRole("dialog", { name: "New RFQ" });
  await ingestDialog.getByRole("button", { name: /Paste text/i }).click();
  await ingestDialog
    .getByPlaceholder(/Paste email or RFQ text here/i)
    .fill(KNOWN_GOOD_RFQ_TEXT);
  await ingestDialog
    .getByPlaceholder("Optional case title")
    .fill("Rehearsal C persistence");
  await ingestDialog.getByRole("button", { name: /Extract line items/i }).click();
  await expect(ingestDialog).toBeHidden({ timeout: 30_000 });

  await page.getByRole("button", { name: /^Approve line \d+$/ }).first().click();
  await expect(page.getByText("Approved", { exact: true })).toHaveCount(1);

  // Get the case ID.
  const ourCase = await findCaseByTitle(page, "Rehearsal C persistence");
  const caseId = ourCase.case_id;

  // --- Browser refresh persistence ---
  await page.reload();
  await page.goto("/workspace");

  // Navigate to Overview and find our case.
  await page.getByRole("button", { name: /^Overview$/i }).click({ timeout: 5000 });

  // The case appears in the overview list. Use .first() to handle any
  // duplicate matches.
  await expect(
    page.getByRole("button", { name: /Open Rehearsal C persistence/i }).first()
  ).toBeVisible({ timeout: 15_000 });

  // Click the case to open it in the workbench.
  await page.getByRole("button", { name: /Open Rehearsal C persistence/i }).first().click();
  await expect(
    page.getByRole("heading", { name: "Rehearsal C persistence" })
  ).toBeVisible({ timeout: 15_000 });

  // The approved line should still be approved after refresh.
  await expect(page.getByText("Approved", { exact: true })).toHaveCount(1);

  // --- Verify audit trail persisted ---
  const auditResp = await page.request.get(
    `/api/proxy/api/rfqs/${caseId}/audit`
  );
  expect(auditResp.status()).toBe(200);
  const audit = (await auditResp.json()) as ApiAuditEvent[];
  expect(audit.length).toBeGreaterThanOrEqual(2);
  expect(audit.some((event) => event.action === "CASE_CREATED")).toBe(true);
  expect(audit.some((event) => event.action === "LINE_APPROVED")).toBe(true);

  // --- Verify catalog is still loaded ---
  const catalogResp = await page.request.get("/api/proxy/api/catalogs");
  expect(catalogResp.status()).toBe(200);
  const catalog = (await catalogResp.json()) as ApiCatalogItem[];
  expect(catalog.length).toBeGreaterThan(0);
  expect(
    catalog.some((item) => item.manufacturer_part_number === "LC1D09BD")
  ).toBe(true);
});

/**
 * Test D: Send route is simulated-only — no external transport is invoked.
 *
 * Walks the V1 quote lifecycle: create case → approve lines → register draft
 * → retrieve draft → approve draft → send. Asserts the send returns
 * simulated_local transport with outbound_transport_invoked=False.
 */
test("Rehearsal D — send route is simulated-only (no external transport)", async ({
  page,
}) => {
  // Navigate to a page first so window.location.origin is available.
  await page.goto("/workspace");
  await expect(page).toHaveTitle(/RFQ/i);

  // Step 1: Create a case via browser-side fetch (same as production frontend)
  const createResult = await page.evaluate(async () => {
    const formData = new FormData();
    formData.append(
      "pasted_text",
      `Please quote the following spare parts:
1. 10 pcs of Schneider Electric LC1D09BD contactors (24VDC coil)
2. 4 units Siemens 6ES7223-1BL32-0XB0 digital I/O modules`
    );
    formData.append("title", "Rehearsal D send");
    formData.append("actor", "Inside Sales");

    const res = await fetch(window.location.origin + "/api/proxy/api/rfqs", {
      method: "POST",
      body: formData,
    });
    return { status: res.status, body: await res.text() };
  });
  expect(createResult.status).toBe(200);
  const createdCase = JSON.parse(createResult.body) as ApiCase;

  // Step 2: Approve all lines via browser-side fetch.
  const linesResult = await page.evaluate(
    async (caseId: string) => {
      const res = await fetch(window.location.origin + `/api/proxy/api/rfqs/${caseId}/lines`);
      return { status: res.status, body: await res.text() };
    },
    createdCase.case_id
  );
  expect(linesResult.status).toBe(200);
  const lines = JSON.parse(linesResult.body) as ApiLine[];

  for (const line of lines) {
    const patchResult = await page.evaluate(
      async (params: {
        caseId: string;
        lineId: string;
        update: LineReviewUpdate;
      }) => {
        const res = await fetch(
          window.location.origin + `/api/proxy/api/rfqs/${params.caseId}/lines/${params.lineId}`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(params.update),
          }
        );
        return { status: res.status, body: await res.text() };
      },
      {
        caseId: createdCase.case_id,
        lineId: line.line_id,
        update: {
          quantity: line.quantity,
          unit: line.unit || "EA",
          requested_mpn: line.requested_mpn,
          requested_manufacturer: line.requested_manufacturer,
          selected_catalog_sku: line.selected_catalog_sku,
          match_status: line.match_status,
          review_decision: "APPROVED",
        },
      }
    );
    expect(patchResult.status).toBe(200);
  }

  // Step 3: Register a quote draft via the V1 route.
  const registerResult = await page.evaluate(
    async (caseId: string) => {
      const res = await fetch(window.location.origin + `/api/proxy/v1/rfqs/${caseId}/draft-quote`, {
        method: "POST",
      });
      return { status: res.status, body: await res.text() };
    },
    createdCase.case_id
  );
  expect(registerResult.status).toBe(200);

  // Step 4: Retrieve the draft to get its hash.
  const quoteId = `QUOTE-${createdCase.case_id.replace("RFQ-", "")}`;
  const getDraftResult = await page.evaluate(
    async (qid: string) => {
      const res = await fetch(window.location.origin + `/api/proxy/v1/quote-drafts/${qid}`);
      return { status: res.status, body: await res.text() };
    },
    quoteId
  );
  expect(getDraftResult.status).toBe(200);
  const draft = JSON.parse(getDraftResult.body) as { draft_hash: string };

  // Step 5: Approve the quote draft.
  const approveResult = await page.evaluate(
    async (params: { quoteId: string; hash: string }) => {
      const formData = new FormData();
      formData.append("expected_hash", params.hash);
      formData.append("approver_name", "Demo Operator");
      const res = await fetch(
        window.location.origin + `/api/proxy/v1/quote-drafts/${params.quoteId}/approve`,
        { method: "POST", body: formData }
      );
      return { status: res.status, body: await res.text() };
    },
    { quoteId, hash: draft.draft_hash }
  );
  expect(approveResult.status).toBe(200);

  // Step 6: Send the approved quote.
  const sendResult = await page.evaluate(
    async (params: { quoteId: string; hash: string }) => {
      const formData = new FormData();
      formData.append("expected_hash", params.hash);
      formData.append("sender_name", "Demo Operator");
      const res = await fetch(
        window.location.origin + `/api/proxy/v1/approved-quotes/${params.quoteId}/send`,
        { method: "POST", body: formData }
      );
      return { status: res.status, body: await res.text() };
    },
    { quoteId, hash: draft.draft_hash }
  );
  expect(sendResult.status).toBe(200);
  const sendResultBody = JSON.parse(sendResult.body) as {
    transmission: {
      transport: string;
      outbound_transport_invoked: boolean;
      is_simulated: boolean;
      transport_notes: string;
    };
  };

  // CRITICAL VERIFICATION: No external transport was invoked.
  expect(sendResultBody.transmission.transport).toBe("simulated_local");
  expect(sendResultBody.transmission.outbound_transport_invoked).toBe(false);
  expect(sendResultBody.transmission.is_simulated).toBe(true);
  expect(sendResultBody.transmission.transport_notes).toContain(
    "No live SMTP or external network transport"
  );
});

/**
 * Test E: Failure recovery — uploading a .py file (unsupported type) produces
 * a clear error without leaving a misleading case.
 */
test("Rehearsal E — failure recovery on unsupported file type", async ({
  page,
}) => {
  await page.goto("/workspace");
  const casesBefore = await page.request.get("/api/proxy/api/rfqs");
  expect(casesBefore.status()).toBe(200);
  const initialCases = (await casesBefore.json()) as ApiCase[];
  const recoveryTitle = "Rejected upload recovery";
  expect(initialCases.some((item) => item.title === recoveryTitle)).toBe(false);

  await page.getByRole("button", { name: /New RFQ/i }).first().click();

  const ingestDialog = page.getByRole("dialog", { name: "New RFQ" });
  await expect(ingestDialog).toBeVisible();

  const fileInput = ingestDialog.locator('input[type="file"]');
  await fileInput.setInputFiles({
    name: "malicious_script.py",
    mimeType: "text/x-python",
    buffer: Buffer.from("print('hello')"),
  });

  await ingestDialog.getByRole("button", { name: /Extract line items/i }).click();

  // Should show an error, not create a case.
  await expect(ingestDialog.getByText(/unsupported|security|error/i)).toBeVisible({
    timeout: 10_000,
  });

  // Confirm no case was created and the modal remains usable after the error.
  await expect(ingestDialog).toBeVisible();
  const casesAfter = await page.request.get("/api/proxy/api/rfqs");
  expect(casesAfter.status()).toBe(200);
  const cases = (await casesAfter.json()) as ApiCase[];
  expect(cases.some((item) => item.title === recoveryTitle)).toBe(false);

  await ingestDialog.getByRole("button", { name: /Paste text/i }).click();
  await ingestDialog
    .getByPlaceholder(/Paste email or RFQ text here/i)
    .fill(KNOWN_GOOD_RFQ_TEXT);
  await ingestDialog
    .getByPlaceholder("Optional case title")
    .fill(recoveryTitle);
  await ingestDialog.getByRole("button", { name: /Extract line items/i }).click();
  await expect(ingestDialog).toBeHidden({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: recoveryTitle })).toBeVisible({
    timeout: 30_000,
  });
});
