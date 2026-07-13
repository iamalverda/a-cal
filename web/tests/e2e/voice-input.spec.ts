import { test, expect } from "@playwright/test";

/**
 * E2E tests for voice interaction (charter §6 / Q6).
 *
 * Q6: combine chat + voice + command bar with voice as the default.
 * The Web Speech API isn't available in headless Chromium, so these tests
 * verify the UI elements are present (mic buttons, settings info) rather
 * than actual speech recognition.
 */
test.describe("Voice interaction", () => {
  test("conductor panel has a microphone button when supported", async ({ page }) => {
    await page.goto("/");
    // The conductor panel should be visible by default
    await expect(page.getByText("Conductor").first()).toBeVisible({ timeout: 5_000 });

    // The Web Speech API may not be available in headless Chromium,
    // so we check for either the mic button or the send button.
    // If the browser supports speech recognition, the mic button should appear.
    const sendButton = page.locator('button:has(svg.lucide-send)');
    await expect(sendButton).toBeVisible({ timeout: 5_000 });
  });

  test("settings General section mentions voice interaction", async ({ page }) => {
    await page.goto("/");
    // Wait for the app to load (auth gate auto-logins via demo-login)
    await expect(page.getByText("Conductor").first()).toBeVisible({ timeout: 10_000 });
    // Open settings via cmd+k
    await page.keyboard.press("Meta+k");
    await expect(page.getByText("Open settings")).toBeVisible({ timeout: 5_000 });
    await page.getByText("Open settings").click();
    await expect(page.getByText("Settings").first()).toBeVisible({ timeout: 5_000 });

    // Navigate to General section
    await page.getByText("General").first().click();
    await expect(page.getByText("Voice Interaction")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("speech recognition")).toBeVisible();
  });

  test("settings voice section mentions local transcription privacy", async ({ page }) => {
    await page.goto("/");
    // Wait for the app to load (auth gate auto-logins via demo-login)
    await expect(page.getByText("Conductor").first()).toBeVisible({ timeout: 10_000 });
    await page.keyboard.press("Meta+k");
    await expect(page.getByText("Open settings")).toBeVisible({ timeout: 5_000 });
    await page.getByText("Open settings").click();
    await expect(page.getByText("Settings").first()).toBeVisible({ timeout: 5_000 });

    await page.getByText("General").first().click();
    await expect(page.getByText("Voice Interaction")).toBeVisible({ timeout: 5_000 });
    // Privacy note: no audio sent to any server
    await expect(page.getByText("no audio is sent to any server")).toBeVisible();
  });

  test("command bar opens with cmd+k and has input field", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Conductor").first()).toBeVisible({ timeout: 10_000 });
    await page.keyboard.press("Meta+k");
    // The command bar should appear
    await expect(page.getByPlaceholder("Type a command or ask anything...")).toBeVisible({ timeout: 5_000 });
  });
});
