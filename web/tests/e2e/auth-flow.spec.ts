import { test, expect } from "@playwright/test";

/**
 * E2E tests for the authentication flow.
 *
 * Verifies the full cycle: auto demo-login → sign out → login panel →
 * register → app → sign out → login → app. Exercises the LoginPanel
 * component, the AuthProvider context, and the backend auth endpoints.
 */

/** The login panel submit button (inside the form, not the mode toggle). */
function submitButton(page: import("@playwright/test").Page) {
  return page.locator("form").getByRole("button", { name: /Sign In|Create Account/ });
}

test.describe("Auth flow", () => {
  test("auto demo-login on first visit shows the app", async ({ page }) => {
    await page.goto("/");
    // The conductor welcome message confirms the app loaded (not the login panel)
    await expect(
      page.getByText("Hi! I'm the A-Cal Conductor"),
    ).toBeVisible();
  });

  test("sign out reveals the login panel", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByText("Hi! I'm the A-Cal Conductor"),
    ).toBeVisible();

    // Click sign-out in the sidebar
    await page.getByRole("button", { name: "Sign Out" }).click();

    // Login panel should appear — check for the subtitle and email placeholder
    await expect(page.getByText("Agentic Calendar")).toBeVisible();
    await expect(page.getByPlaceholder("you@example.com")).toBeVisible();
  });

  test("register a new user and sign in", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByText("Hi! I'm the A-Cal Conductor"),
    ).toBeVisible();

    // Sign out to reveal login panel
    await page.getByRole("button", { name: "Sign Out" }).click();
    await expect(page.getByPlaceholder("you@example.com")).toBeVisible();

    // Switch to register mode
    await page.getByRole("button", { name: "Register" }).click();
    await expect(page.getByPlaceholder("Optional")).toBeVisible();

    // Fill in registration form
    const testEmail = `e2e-${Date.now()}@test.acal`;
    await page.getByPlaceholder("Optional").fill("E2E Test User");
    await page.getByPlaceholder("you@example.com").fill(testEmail);
    await page.getByPlaceholder("••••••••").fill("testpass123");

    // Submit
    await submitButton(page).click();

    // App should appear
    await expect(
      page.getByText("Hi! I'm the A-Cal Conductor"),
    ).toBeVisible({ timeout: 10_000 });

    // Verify the new user's email is shown in the sidebar
    await expect(page.getByText(testEmail)).toBeVisible();
  });

  test("login with registered credentials after sign out", async ({ page }) => {
    // Register a user first via the API for a clean state
    const testEmail = `e2e-login-${Date.now()}@test.acal`;
    const testPassword = "testpass123";

    await page.request.post("/api/a-cal/auth/register", {
      data: { email: testEmail, password: testPassword, display_name: "Login Test" },
    });

    // Load page — auto demo-login fires, then we sign out
    await page.goto("/");
    await expect(
      page.getByText("Hi! I'm the A-Cal Conductor"),
    ).toBeVisible();

    await page.getByRole("button", { name: "Sign Out" }).click();
    await expect(page.getByPlaceholder("you@example.com")).toBeVisible();

    // Make sure we're in Sign In mode (default after sign-out)
    await page.getByPlaceholder("you@example.com").fill(testEmail);
    await page.getByPlaceholder("••••••••").fill(testPassword);
    await submitButton(page).click();

    // App should appear with our user's email
    await expect(
      page.getByText("Hi! I'm the A-Cal Conductor"),
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(testEmail)).toBeVisible();
  });

  test("invalid login shows error message", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByText("Hi! I'm the A-Cal Conductor"),
    ).toBeVisible();

    await page.getByRole("button", { name: "Sign Out" }).click();
    await expect(page.getByPlaceholder("you@example.com")).toBeVisible();

    // Try to log in with non-existent credentials
    await page.getByPlaceholder("you@example.com").fill("nobody@test.acal");
    await page.getByPlaceholder("••••••••").fill("wrongpass123");
    await submitButton(page).click();

    // Error message should appear
    await expect(page.getByText(/invalid|failed|incorrect|not found|unauthorized|401/i)).toBeVisible({
      timeout: 5_000,
    });
  });
});
