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
});
