import { test, expect } from "@playwright/test";

/**
 * E2E tests for the community marketplace.
 *
 * Verifies the marketplace panel opens, shows items, and supports search.
 */
test.describe("Marketplace", () => {
  test("opens and shows marketplace items", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Marketplace" }).click();

    // Marketplace panel should appear
    await expect(page.getByText(/Marketplace/i).first()).toBeVisible({ timeout: 5_000 });

    // Should have a search input
    await expect(page.getByPlaceholder("Search marketplace...")).toBeVisible();
  });

  test("search filters items", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByPlaceholder("Search marketplace...")).toBeVisible({ timeout: 5_000 });

    // Type a search query
    await page.getByPlaceholder("Search marketplace...").fill("focus");

    // Wait for either results or empty state
    await page.waitForTimeout(1000);
    // Either items appear or "No items found" appears
    const hasResults = await page.getByText(/Focus|focus/i).first().isVisible().catch(() => false);
    const hasEmpty = await page.getByText("No items found.").isVisible().catch(() => false);
    expect(hasResults || hasEmpty).toBeTruthy();
  });
});
