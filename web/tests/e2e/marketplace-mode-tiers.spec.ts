import { test, expect } from "@playwright/test";

/**
 * E2E tests for mode-tiered marketplace discovery (Q9).
 *
 * Verifies that the marketplace surface adapts to the user's skill mode:
 *  - Simple: only the Browse tab (curated templates/themes)
 *  - Pro: Browse + Share + Remote tabs
 *  - Developer: all three tabs plus per-item config/provenance details
 */
test.describe("Mode-tiered marketplace discovery", () => {
  test("Simple mode shows only the Browse tab", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "simple", exact: true }).click();

    // Marketplace is visible in Simple mode now
    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByText("Marketplace").first()).toBeVisible({ timeout: 5_000 });

    // Only Browse tab should be present
    await expect(page.getByRole("button", { name: "Browse" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Share" })).not.toBeVisible();
    await expect(page.getByRole("button", { name: "Remote" })).not.toBeVisible();
  });

  test("Pro mode shows Browse, Share, and Remote tabs", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByText("Marketplace").first()).toBeVisible({ timeout: 5_000 });

    await expect(page.getByRole("button", { name: "Browse" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Share" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Remote" })).toBeVisible();
  });

  test("Developer mode shows all tabs and per-item config details", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "developer", exact: true }).click();

    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByText("Marketplace").first()).toBeVisible({ timeout: 5_000 });

    // All three tabs visible
    await expect(page.getByRole("button", { name: "Browse" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Share" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Remote" })).toBeVisible();

    // Wait for marketplace items to load, then check for the developer-only
    // "Config & provenance" disclosure on at least one item card.
    const details = page.getByText("Config & provenance").first();
    await expect(details).toBeVisible({ timeout: 10_000 });
  });

  test("tier-preview banner shows what the next mode unlocks", async ({ page }) => {
    // Simple mode — preview should mention Pro
    await page.goto("/");
    await page.getByRole("button", { name: "simple", exact: true }).click();
    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByText("Marketplace").first()).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/Pro mode unlocks/)).toBeVisible({ timeout: 5_000 });

    // Close the overlay so we can reach the sidebar mode switcher
    await page.locator("button", { hasText: String.fromCharCode(0xd7) }).click();
    await expect(page.getByRole("button", { name: "pro", exact: true })).toBeVisible({ timeout: 5_000 });

    // Pro mode — preview should mention Developer
    await page.getByRole("button", { name: "pro", exact: true }).click();
    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByText("Marketplace").first()).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/Developer mode unlocks/)).toBeVisible({ timeout: 5_000 });
  });

  test("Developer mode shows no tier-preview banner (top tier)", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "developer", exact: true }).click();
    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByText("Marketplace").first()).toBeVisible({ timeout: 5_000 });
    // Developer is the top tier — no preview banner
    await expect(page.getByText(/mode unlocks/)).not.toBeVisible();
  });
});
