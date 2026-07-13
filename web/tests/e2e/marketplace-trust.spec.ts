import { test, expect } from "@playwright/test";

/**
 * E2E tests for the marketplace trust & moderation UI (charter §9).
 *
 * Verifies that marketplace items display trust badges, verification status,
 * and a flag button for moderation.
 */
test.describe("Marketplace trust & moderation", () => {
  test("browse tab shows trust score for unverified items", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Conductor").first()).toBeVisible({ timeout: 10_000 });

    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByPlaceholder("Search marketplace...")).toBeVisible({ timeout: 5_000 });

    // Items should show a trust indicator (Trust: NN for unverified items)
    await expect(page.getByText(/Trust:\s*\d+/).first()).toBeVisible({ timeout: 10_000 });
  });

  test("flag button is visible on marketplace items in Pro mode", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Conductor").first()).toBeVisible({ timeout: 10_000 });

    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByPlaceholder("Search marketplace...")).toBeVisible({ timeout: 5_000 });

    // The Flag button should be visible on items (Pro mode is default)
    await expect(page.getByRole("button", { name: "Flag" }).first()).toBeVisible({ timeout: 10_000 });
  });

  test("clicking flag opens a reason input form", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Conductor").first()).toBeVisible({ timeout: 10_000 });

    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByPlaceholder("Search marketplace...")).toBeVisible({ timeout: 5_000 });

    // Click the first Flag button
    await page.getByRole("button", { name: "Flag" }).first().click();

    // The flag reason input should appear
    await expect(page.getByPlaceholder("Reason for flagging")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByRole("button", { name: "Submit Flag" })).toBeVisible();
  });

  test("submitting a flag calls the API and shows confirmation", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Conductor").first()).toBeVisible({ timeout: 10_000 });

    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByPlaceholder("Search marketplace...")).toBeVisible({ timeout: 5_000 });

    // Click the first Flag button
    await page.getByRole("button", { name: "Flag" }).first().click();

    // Listen for the POST to the flag endpoint
    const flagPromise = page.waitForResponse(
      (resp) =>
        resp.url().includes("/marketplace/items/") &&
        resp.url().includes("/flag") &&
        resp.request().method() === "POST",
      { timeout: 10_000 },
    );

    // Type a reason and submit
    await page.getByPlaceholder("Reason for flagging").fill("Test flag — suspicious config");
    await page.getByRole("button", { name: "Submit Flag" }).click();

    const response = await flagPromise;
    expect(response.ok()).toBeTruthy();

    // Confirmation message should appear
    await expect(page.getByText("Item flagged for review.")).toBeVisible({ timeout: 5_000 });
  });
});
