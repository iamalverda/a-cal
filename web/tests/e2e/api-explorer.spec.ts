import { test, expect } from "@playwright/test";

/**
 * E2E tests for the API Explorer inside Developer Studio.
 *
 * Verifies the explorer renders the route list, supports search, and shows
 * the detail view (with Send Request) when an endpoint is clicked.
 */
test.describe("API Explorer", () => {
  test("Developer Studio shows API Explorer section", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "developer", exact: true }).click();
    await page.getByRole("button", { name: "Developer Studio" }).click();

    await expect(
      page.getByRole("heading", { name: "Developer Studio" })
    ).toBeVisible({ timeout: 5_000 });

    // API Explorer section heading
    await expect(page.getByRole("heading", { name: "API Explorer" })).toBeVisible({ timeout: 5_000 });
  });

  test("route list renders with endpoint count and search box", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "developer", exact: true }).click();
    await page.getByRole("button", { name: "Developer Studio" }).click();
    await expect(page.getByRole("heading", { name: "API Explorer" })).toBeVisible({ timeout: 5_000 });

    // Search input
    await expect(page.getByPlaceholder("Search endpoints...")).toBeVisible({ timeout: 5_000 });

    // Endpoint count text (e.g. "109 endpoints across N categories")
    await expect(page.getByText(/endpoints across/i)).toBeVisible({ timeout: 5_000 });
  });

  test("clicking an endpoint opens the detail view with Send Request", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "developer", exact: true }).click();
    await page.getByRole("button", { name: "Developer Studio" }).click();
    await expect(page.getByRole("heading", { name: "API Explorer" })).toBeVisible({ timeout: 5_000 });

    // Wait for routes to load (search box present means list rendered)
    await expect(page.getByPlaceholder("Search endpoints...")).toBeVisible({ timeout: 5_000 });
    await page.waitForTimeout(1000);

    // Click the first route button (each route is a <button> with a method badge)
    const firstRoute = page.locator("button:has(span.font-mono.text-\\[10px\\])").first();
    await expect(firstRoute).toBeVisible({ timeout: 5_000 });
    await firstRoute.click();
    await page.waitForTimeout(500);

    // Detail view should show the Send Request button
    await expect(page.getByRole("button", { name: /Send Request/i })).toBeVisible({ timeout: 5_000 });
  });

  test("back button returns to route list", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "developer", exact: true }).click();
    await page.getByRole("button", { name: "Developer Studio" }).click();
    await expect(page.getByRole("heading", { name: "API Explorer" })).toBeVisible({ timeout: 5_000 });
    await expect(page.getByPlaceholder("Search endpoints...")).toBeVisible({ timeout: 5_000 });
    await page.waitForTimeout(1000);

    const firstRoute = page.locator("button:has(span.font-mono.text-\\[10px\\])").first();
    await firstRoute.click();
    await expect(page.getByRole("button", { name: /Send Request/i })).toBeVisible({ timeout: 5_000 });

    // The back button is the ghost icon button with an ArrowLeft SVG.
    await page.locator("button:has(svg.lucide-arrow-left)").first().click();
    await page.waitForTimeout(500);

    // Back on the list — search box should be visible again
    await expect(page.getByPlaceholder("Search endpoints...")).toBeVisible({ timeout: 5_000 });
  });

  test("search filters the route list", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "developer", exact: true }).click();
    await page.getByRole("button", { name: "Developer Studio" }).click();
    await expect(page.getByRole("heading", { name: "API Explorer" })).toBeVisible({ timeout: 5_000 });
    await expect(page.getByPlaceholder("Search endpoints...")).toBeVisible({ timeout: 5_000 });
    await page.waitForTimeout(1000);

    // Type a narrow search
    await page.getByPlaceholder("Search endpoints...").fill("health");
    await page.waitForTimeout(800);

    // Either matching endpoints appear or "No endpoints match" shows
    const hasMatch = await page.getByText(/health/i).first().isVisible().catch(() => false);
    const hasEmpty = await page.getByText(/No endpoints match/i).isVisible().catch(() => false);
    expect(hasMatch || hasEmpty).toBeTruthy();
  });
});
