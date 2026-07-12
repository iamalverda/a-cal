import { test, expect } from "@playwright/test";

/**
 * E2E tests for the plugin runtime management UI in the developer panel.
 *
 * Verifies that the Developer Studio opens in developer mode, shows the
 * Runtime Plugins section, and has a Scan Directory button.
 */
test.describe("Plugin runtime management", () => {
  test("developer mode shows Developer Studio button", async ({ page }) => {
    await page.goto("/");
    // Default is pro mode — Developer Studio should not be visible
    await expect(page.getByRole("button", { name: "Developer Studio" })).not.toBeVisible();

    // Switch to developer mode
    await page.getByRole("button", { name: "developer", exact: true }).click();
    await expect(page.getByRole("button", { name: "Developer Studio" })).toBeVisible();
  });

  test("Developer Studio shows Runtime Plugins section", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "developer", exact: true }).click();
    await page.getByRole("button", { name: "Developer Studio" }).click();

    // The overlay heading should appear (distinct from the sidebar button)
    await expect(
      page.getByRole("heading", { name: "Developer Studio" })
    ).toBeVisible({ timeout: 5_000 });

    // Runtime Plugins section should be visible
    await expect(page.getByText("Runtime Plugins")).toBeVisible({ timeout: 5_000 });
  });

  test("Scan Directory button is present and clickable", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "developer", exact: true }).click();
    await page.getByRole("button", { name: "Developer Studio" }).click();
    await expect(page.getByText("Runtime Plugins")).toBeVisible({ timeout: 5_000 });

    // Scan Directory button should be present
    const scanBtn = page.getByRole("button", { name: /Scan Directory/i });
    await expect(scanBtn).toBeVisible();
    // Click it — should not crash
    await scanBtn.click();
    // Wait for either plugins to load or the "No plugins" message
    await page.waitForTimeout(2000);
  });
});
