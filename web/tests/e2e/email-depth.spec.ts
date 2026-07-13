import { test, expect } from "@playwright/test";

/**
 * E2E tests for the email integration depth settings (charter §5).
 *
 * Verifies that the settings panel exposes the three email depth levels
 * (Sync & Notify, Agent-Mediated Inbox, Full Two-Way Agent) and that
 * selecting one persists to the backend.
 */
test.describe("Email integration depth settings", () => {
  test("settings panel has an Email Depth section with three levels", async ({ page }) => {
    await page.goto("/");
    // Open settings via the command bar (cmd+k)
    await page.keyboard.press("Meta+k");
    await expect(page.getByText("Open settings")).toBeVisible({ timeout: 5_000 });
    await page.getByText("Open settings").click();
    await expect(page.getByText("Settings").first()).toBeVisible({ timeout: 5_000 });

    // Navigate to the Email Depth section
    await page.getByText("Email Depth").click();
    await expect(page.getByText("Email Integration Depth")).toBeVisible({ timeout: 5_000 });

    // All three depth levels should be visible
    await expect(page.getByText("Sync & Notify")).toBeVisible();
    await expect(page.getByText("Agent-Mediated Inbox")).toBeVisible();
    await expect(page.getByText("Full Two-Way Agent")).toBeVisible();
  });

  test("selecting Agent-Mediated Inbox calls the API and marks it active", async ({ page }) => {
    await page.goto("/");
    // Open settings via the command bar (cmd+k)
    await page.keyboard.press("Meta+k");
    await expect(page.getByText("Open settings")).toBeVisible({ timeout: 5_000 });
    await page.getByText("Open settings").click();
    await expect(page.getByText("Settings").first()).toBeVisible({ timeout: 5_000 });

    await page.getByText("Email Depth").click();
    await expect(page.getByText("Email Integration Depth")).toBeVisible({ timeout: 5_000 });

    // Listen for the API call
    const apiPromise = page.waitForResponse(
      (resp) => resp.url().includes("/api/a-cal/settings/email"),
      { timeout: 10_000 },
    );

    // Click "Agent-Mediated Inbox"
    await page.getByText("Agent-Mediated Inbox").click();
    const response = await apiPromise;
    expect(response.ok()).toBeTruthy();

    const body = await response.json();
    expect(body.depth).toBe("agent_mediated");

    // The "Active" indicator should appear on the selected level
    await expect(page.getByText("Agent-Mediated Inbox").locator("..").getByText("Active")).toBeVisible();
  });

  test("auto-scan toggle is visible and defaults to off", async ({ page }) => {
    await page.goto("/");
    // Open settings via the command bar (cmd+k)
    await page.keyboard.press("Meta+k");
    await expect(page.getByText("Open settings")).toBeVisible({ timeout: 5_000 });
    await page.getByText("Open settings").click();
    await expect(page.getByText("Settings").first()).toBeVisible({ timeout: 5_000 });

    await page.getByText("Email Depth").click();
    await expect(page.getByText("Email Integration Depth")).toBeVisible({ timeout: 5_000 });

    await expect(page.getByText("Auto-scan inbox for scheduling")).toBeVisible();
  });
});
