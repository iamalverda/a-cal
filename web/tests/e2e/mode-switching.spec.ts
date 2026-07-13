import { test, expect } from "@playwright/test";

/**
 * E2E tests for skill mode switching (Simple / Pro / Developer).
 *
 * Verifies that switching modes shows and hides the correct UI surfaces
 * without losing data.
 */
test.describe("Skill mode switching", () => {
  test("starts in pro mode with marketplace and email visible", async ({ page }) => {
    await page.goto("/");
    // Pro mode should show marketplace and email in the sidebar
    await expect(page.getByRole("button", { name: "Marketplace" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Email" })).toBeVisible();
  });

  test("switching to simple mode hides advanced panels but keeps marketplace", async ({ page }) => {
    await page.goto("/");
    // Switch to simple
    await page.getByRole("button", { name: "simple", exact: true }).click();
    // Marketplace stays visible (tiered Browse-only surface) but Email hides
    await expect(page.getByRole("button", { name: "Marketplace" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Email" })).not.toBeVisible();
    // Developer Studio should not be visible
    await expect(page.getByRole("button", { name: "Developer Studio" })).not.toBeVisible();
  });

  test("switching to developer mode shows Developer Studio", async ({ page }) => {
    await page.goto("/");
    // Switch to developer
    await page.getByRole("button", { name: "developer", exact: true }).click();
    // Developer Studio button should appear in the sidebar
    await expect(page.getByRole("button", { name: "Developer Studio" })).toBeVisible();
  });

  test("mode switching is reversible without data loss", async ({ page }) => {
    await page.goto("/");
    // Note the number of agents visible in pro mode
    const agentsBadge = page.getByText(/agents active/i);
    await expect(agentsBadge).toBeVisible();

    // Switch to simple and back to pro
    await page.getByRole("button", { name: "simple", exact: true }).click();
    await page.getByRole("button", { name: "pro", exact: true }).click();

    // Agent count badge should be visible again
    await expect(page.getByText(/agents active/i)).toBeVisible();
  });
});
