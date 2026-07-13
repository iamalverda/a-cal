import { test, expect } from "@playwright/test";

/**
 * E2E tests for the contextual command bar (cmd+k palette).
 */
test.describe("Command Bar", () => {
  test("opens with cmd+k and shows quick actions", async ({ page }) => {
    await page.goto("/");

    // Open command bar with cmd+k
    await page.keyboard.press("Meta+k");

    // Should show the command bar input
    await expect(page.getByPlaceholder(/Type a command or ask anything/)).toBeVisible({
      timeout: 5_000,
    });

    // Should show some quick actions
    await expect(page.getByText("Sync calendars")).toBeVisible();
    await expect(page.getByText("Open settings")).toBeVisible();
    await expect(page.getByText("Open marketplace")).toBeVisible();
  });

  test("typing filters quick actions", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Meta+k");
    await expect(page.getByPlaceholder(/Type a command or ask anything/)).toBeVisible({
      timeout: 5_000,
    });

    // Type a search query
    await page.getByPlaceholder(/Type a command or ask anything/).fill("email");

    // Should show the email-related action
    await expect(page.getByText("Check email for schedule")).toBeVisible({ timeout: 3_000 });

    // Should not show unrelated actions
    await expect(page.getByText("Sync calendars")).not.toBeVisible();
  });

  test("escape closes the command bar", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Meta+k");
    await expect(page.getByPlaceholder(/Type a command or ask anything/)).toBeVisible({
      timeout: 5_000,
    });

    // Press escape
    await page.keyboard.press("Escape");

    // Command bar should be gone
    await expect(page.getByPlaceholder(/Type a command or ask anything/)).not.toBeVisible({
      timeout: 3_000,
    });
  });

  test("selecting 'Open settings' opens the settings panel", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Meta+k");
    await expect(page.getByPlaceholder(/Type a command or ask anything/)).toBeVisible({
      timeout: 5_000,
    });

    // Click the "Open settings" action
    await page.getByText("Open settings").click();

    // Settings panel should appear
    await expect(page.getByText("Settings").first()).toBeVisible({ timeout: 5_000 });
  });

  test("arrow keys navigate the action list", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Meta+k");
    await expect(page.getByPlaceholder(/Type a command or ask anything/)).toBeVisible({
      timeout: 5_000,
    });

    // Press arrow down a few times — should highlight different actions
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowUp");

    // The command bar should still be open
    await expect(page.getByPlaceholder(/Type a command or ask anything/)).toBeVisible();
  });
});
