/**
 * E2E tests for the workflow builder — open, add nodes, export, save/load.
 */

import { test, expect } from "@playwright/test";

test.describe("Workflow Builder", () => {
  test("should export workflow as JSON", async ({ page }) => {
    await page.goto("/");

    // Open the workflow builder overlay
    await page.getByRole("button", { name: "Workflow Builder" }).click();

    // Wait for the name input to appear (overlay is open)
    const nameInput = page.getByPlaceholder("Workflow name");
    await expect(nameInput).toBeVisible({ timeout: 10000 });

    // Click Export JSON
    await page.getByRole("button", { name: /Export JSON/i }).click();

    // Should show the export preview
    await expect(page.getByText("Exported Workflow JSON")).toBeVisible({ timeout: 5000 });
  });

  test("should save and load a workflow", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("button", { name: "Workflow Builder" }).click();
    const nameInput = page.getByPlaceholder("Workflow name");
    await expect(nameInput).toBeVisible({ timeout: 10000 });

    // Change the workflow name
    await nameInput.fill("E2E Saved Workflow");

    // Click Save
    await page.getByRole("button", { name: /^Save$/ }).click();
    await page.waitForTimeout(1000);

    // Click Load to see saved workflows
    await page.getByRole("button", { name: /^Load$/ }).click();

    // Should show the saved workflow in the list (use first to handle
    // duplicate entries from previous test runs that weren't cleaned up)
    await expect(page.getByText("E2E Saved Workflow").first()).toBeVisible({ timeout: 5000 });
  });

  test("should add a node and show step count", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("button", { name: "Workflow Builder" }).click();
    const nameInput = page.getByPlaceholder("Workflow name");
    await expect(nameInput).toBeVisible({ timeout: 10000 });

    // Find the agent palette — agents are in buttons with a Plus icon
    // Click the first agent button in the palette (inside the overlay)
    const overlay = page.locator(".fixed.inset-0.z-50");
    const agentBtn = overlay.locator("button").filter({ hasText: /Conductor/i }).first();
    await agentBtn.click();

    // Step count should update to 1 step
    await expect(overlay.getByText(/1 step/)).toBeVisible({ timeout: 5000 });
  });
});
