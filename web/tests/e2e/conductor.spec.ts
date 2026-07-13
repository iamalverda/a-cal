import { test, expect } from "@playwright/test";

/**
 * E2E tests for the conductor chat panel.
 *
 * Verifies that the conductor panel renders, accepts user input, and
 * returns a response (either from the backend or from mock fallback).
 */
test.describe("Conductor panel", () => {
  test("renders welcome message", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByText("Hi! I'm the A-Cal Conductor")
    ).toBeVisible();
  });

  test("accepts user input and returns a response", async ({ page }) => {
    await page.goto("/");
    const input = page.getByPlaceholder("Ask the conductor anything...");
    await expect(input).toBeVisible();
    await input.fill("What events do I have today?");
    await input.press("Enter");

    // The user message should appear in the chat
    await expect(
      page.getByText("What events do I have today?")
    ).toBeVisible({ timeout: 5_000 });

    // Wait for a conductor response — a second bot avatar should appear
    // (the welcome message has the first one).
    const botAvatars = page.locator("[class*='bg-[var(--primary)]/15']").filter({ has: page.locator("svg") });
    await expect(botAvatars.nth(1)).toBeVisible({ timeout: 10_000 });
  });

  test("suggestion chips are clickable", async ({ page }) => {
    await page.goto("/");
    const suggestion = page.getByRole("button", { name: "Find a free 30-min slot tomorrow afternoon" });
    await expect(suggestion).toBeVisible();
    await suggestion.click();
    // The suggestion text should appear in the input after clicking
    await expect(
      page.getByPlaceholder("Ask the conductor anything...")
    ).toHaveValue("Find a free 30-min slot tomorrow afternoon");
  });

  test("clear button resets chat", async ({ page }) => {
    await page.goto("/");

    // Send a unique message (not one of the suggestion chips)
    const input = page.getByPlaceholder("Ask the conductor anything...");
    await input.fill("Tell me about my schedule for next week");
    await input.press("Enter");

    // Wait for the user message to appear
    await expect(
      page.getByText("Tell me about my schedule for next week")
    ).toBeVisible({ timeout: 5_000 });

    // Click clear
    const clearBtn = page.getByRole("button", { name: /Clear/i });
    await clearBtn.click();

    // The user message should be removed, leaving only the welcome message
    await expect(
      page.getByText("Tell me about my schedule for next week")
    ).not.toBeVisible({ timeout: 5_000 });
  });
});
