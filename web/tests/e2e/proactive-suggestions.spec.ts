import { test, expect } from "@playwright/test";

/**
 * E2E tests for proactive suggestions — the self-model's unprompted nudges.
 *
 * Tests the settings toggle, the API endpoint, and the floating notification
 * component behavior.
 */
test.describe("Proactive Suggestions", () => {
  test("suggestions API returns 200 and an array", async ({ page }) => {
    await page.request.post("/api/a-cal/auth/demo-login");
    const resp = await page.request.get("/api/a-cal/self-model/suggestions");
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(Array.isArray(body)).toBeTruthy();
  });

  test("suggestions API respects limit parameter", async ({ page }) => {
    await page.request.post("/api/a-cal/auth/demo-login");
    const resp = await page.request.get("/api/a-cal/self-model/suggestions?limit=2");
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(Array.isArray(body)).toBeTruthy();
    expect(body.length).toBeLessThanOrEqual(2);
  });

  test("proactive toggle is visible in self-model settings", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Conductor").first()).toBeVisible({ timeout: 10_000 });
    await page.locator("button:has(.lucide-settings)").click();
    await expect(page.getByText("Settings").first()).toBeVisible({ timeout: 5_000 });

    // Navigate to the Self-Model section
    await page.getByText("Self-Model").click();
    await expect(page.getByText("Proactive suggestions")).toBeVisible({ timeout: 5_000 });
  });

  test("enabling proactive suggestions persists the setting", async ({ page }) => {
    // Authenticate first — page.request shares cookies with the browser context
    await page.request.post("/api/a-cal/auth/demo-login");
    // Enable via API
    await page.request.post("/api/a-cal/settings/self-model", {
      data: {
        depth: "attention_intent",
        enabled_categories: {},
        cloud_sync_enabled: false,
        proactive_suggestions_enabled: true,
        feed_into_calendar_view: true,
        feed_into_agents: true,
        feed_into_proactive: true,
      },
    });

    // Verify the setting persisted
    const resp = await page.request.get("/api/a-cal/settings/self-model");
    expect(resp.ok()).toBeTruthy();
    const settings = await resp.json();
    expect(settings.proactive_suggestions_enabled).toBe(true);

    // Reset to default for cleanup
    await page.request.post("/api/a-cal/settings/self-model", {
      data: {
        depth: "pattern_memory",
        enabled_categories: {},
        cloud_sync_enabled: false,
        proactive_suggestions_enabled: false,
        feed_into_calendar_view: true,
        feed_into_agents: true,
        feed_into_proactive: false,
      },
    });
  });
});
