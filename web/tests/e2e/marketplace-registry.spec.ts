import { test, expect } from "@playwright/test";

/**
 * E2E tests for the marketplace registry features — export/import bundles
 * and remote registry browsing.
 */
test.describe("Marketplace Registry", () => {
  test("tab switcher shows Browse, Share, and Remote tabs", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByText("Marketplace").first()).toBeVisible({ timeout: 5_000 });

    // All three tabs should be visible
    await expect(page.getByRole("button", { name: "Browse" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Share" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Remote" })).toBeVisible();
  });

  test("Share tab shows export and import UI", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByText("Marketplace").first()).toBeVisible({ timeout: 5_000 });

    // Switch to Share tab
    await page.getByRole("button", { name: "Share" }).click();

    // Export section
    await expect(page.getByText("Export Bundle")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByRole("button", { name: /Export All Items/ })).toBeVisible();

    // Import section
    await expect(page.getByText("Import Bundle")).toBeVisible();
    await expect(page.getByPlaceholder(/format/)).toBeVisible();
  });

  test("export triggers API call and returns a valid bundle", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByText("Marketplace").first()).toBeVisible({ timeout: 5_000 });

    await page.getByRole("button", { name: "Share" }).click();
    await expect(page.getByText("Export Bundle")).toBeVisible({ timeout: 5_000 });

    const exportPromise = page.waitForResponse(
      (resp) => resp.url().includes("/api/a-cal/marketplace/export"),
      { timeout: 10_000 }
    );

    await page.getByRole("button", { name: /Export All Items/ }).click();

    const response = await exportPromise;
    expect(response.ok()).toBeTruthy();

    const body = await response.json();
    expect(body.format).toBe("acal-marketplace-bundle");
    expect(body.version).toBe("1.0.0");
    expect(Array.isArray(body.items)).toBeTruthy();
  });

  test("Remote tab shows registry URL input and browse button", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByText("Marketplace").first()).toBeVisible({ timeout: 5_000 });

    // Switch to Remote tab
    await page.getByRole("button", { name: "Remote" }).click();

    await expect(page.getByText("Browse Remote Registry")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByPlaceholder(/other-a-cal/)).toBeVisible();
    // The action Browse button is the second one (first is the tab)
    await expect(page.getByRole("button", { name: "Browse" }).nth(1)).toBeVisible();
  });

  test("browsing a bad registry URL shows an error", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Marketplace" }).click();
    await expect(page.getByText("Marketplace").first()).toBeVisible({ timeout: 5_000 });

    await page.getByRole("button", { name: "Remote" }).click();
    await expect(page.getByPlaceholder(/other-a-cal/)).toBeVisible({ timeout: 5_000 });

    // Enter an invalid URL and try to browse
    await page.getByPlaceholder(/other-a-cal/).fill("http://localhost:9999/not-a-registry");
    await page.getByRole("button", { name: "Browse" }).nth(1).click();

    // Should show an error message
    await expect(page.getByText(/failed to fetch registry/i)).toBeVisible({
      timeout: 10_000,
    });
  });
});
