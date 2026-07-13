import { test, expect } from "@playwright/test";

/**
 * E2E tests for the marketplace remix (fork) flow.
 *
 * Verifies that Pro and Developer users can fork an existing marketplace
 * item into their own remix via an inline form, and that the backend
 * creates the forked item.
 */
test.describe("Marketplace remix flow", () => {
  test("Remix button visible in Pro mode and opens inline form", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByText("Marketplace").first()).toBeVisible({ timeout: 5_000 });

    // Wait for items to load
    await expect(page.getByRole("button", { name: "Install" }).first()).toBeVisible({
      timeout: 10_000,
    });

    // Remix button should be visible (Pro is default mode)
    const remixBtn = page.getByRole("button", { name: "Remix" }).first();
    await expect(remixBtn).toBeVisible();

    // Click it to open the inline form
    await remixBtn.click();
    await expect(page.getByPlaceholder("Remix name")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByPlaceholder(/Config overrides JSON/)).toBeVisible();
    await expect(page.getByRole("button", { name: /Fork & Publish/ })).toBeVisible();
  });

  test("submitting the remix form calls the API and creates a fork", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByText("Marketplace").first()).toBeVisible({ timeout: 5_000 });

    await expect(page.getByRole("button", { name: "Install" }).first()).toBeVisible({
      timeout: 10_000,
    });

    const remixBtn = page.getByRole("button", { name: "Remix" }).first();
    await remixBtn.click();
    await expect(page.getByPlaceholder("Remix name")).toBeVisible({ timeout: 5_000 });

    // Fill in a custom name
    const nameInput = page.getByPlaceholder("Remix name");
    await nameInput.fill("E2E Test Remix");
    await page.getByPlaceholder("What changed? (optional)").fill("tweaked for testing");

    // Listen for the remix API call
    const remixPromise = page.waitForResponse(
      (resp) => resp.url().includes("/api/a-cal/marketplace/items/") && resp.url().includes("/remix"),
      { timeout: 10_000 },
    );

    await page.getByRole("button", { name: /Fork & Publish/ }).click();
    const response = await remixPromise;
    expect(response.ok()).toBeTruthy();

    const body = await response.json();
    expect(body.name).toBe("E2E Test Remix");
    expect(body.remixed_from).toBeTruthy();
  });

  test("Remix button is hidden in Simple mode", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "simple", exact: true }).click();

    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByText("Marketplace").first()).toBeVisible({ timeout: 5_000 });

    // Simple mode filters to curated items; Remix button should not appear
    // (give items a moment to load, then assert absence)
    await page.waitForTimeout(1500);
    await expect(page.getByRole("button", { name: "Remix" })).not.toBeVisible();
  });
});
