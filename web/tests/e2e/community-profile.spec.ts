import { test, expect } from "@playwright/test";

/**
 * E2E tests for the community profile / showcase panel (charter §9).
 *
 * Verifies that Pro and Developer users can open the My Profile panel
 * and see their marketplace stats and authored items.
 */
test.describe("Community profile / showcase", () => {
  test("My Profile button visible in Pro mode and opens profile panel", async ({ page }) => {
    await page.goto("/");
    // Pro is the default mode
    await page.getByRole("button", { name: "My Profile" }).click();
    await expect(page.getByText("My Profile").first()).toBeVisible({ timeout: 5_000 });

    // Stats grid should be visible
    await expect(page.getByText("Authored").first()).toBeVisible();
    await expect(page.getByText("Remixes").first()).toBeVisible();
    await expect(page.getByText("Installs").first()).toBeVisible();
  });

  test("Export Showcase button is present", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "My Profile" }).click();
    await expect(page.getByText("My Profile").first()).toBeVisible({ timeout: 5_000 });
    await expect(page.getByRole("button", { name: /Export Showcase/ })).toBeVisible();
  });

  test("My Profile button hidden in Simple mode", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "simple", exact: true }).click();
    await expect(page.getByRole("button", { name: "My Profile" })).not.toBeVisible();
  });
});
