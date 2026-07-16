import { test, expect } from "@playwright/test";

test.describe("Sync rules editor", () => {
  test("sub-account shows sync rules section when selected", async ({ page }) => {
    await page.goto("http://localhost:3456");
    await expect(page.getByText("Conductor").first()).toBeVisible({ timeout: 10_000 });

    // Click on a sub-account to select it
    await page.locator("text=Work Google").first().click();
    await page.waitForTimeout(500);

    // Sync Rules button should appear
    const syncRulesBtn = page.locator("button:has-text('Sync Rules')").first();
    await expect(syncRulesBtn).toBeVisible();
  });

  test("expanding sync rules shows add rule button", async ({ page }) => {
    await page.goto("http://localhost:3456");
    await expect(page.getByText("Conductor").first()).toBeVisible({ timeout: 10_000 });

    // Select sub-account
    await page.locator("text=Work Google").first().click();
    await page.waitForTimeout(500);

    // Expand sync rules
    await page.locator("button:has-text('Sync Rules')").first().click();
    await page.waitForTimeout(500);

    // Add Rule button should appear
    await expect(page.locator("button:has-text('Add Rule')").first()).toBeVisible();
  });

  test("add rule form shows rule type options", async ({ page }) => {
    await page.goto("http://localhost:3456");
    await expect(page.getByText("Conductor").first()).toBeVisible({ timeout: 10_000 });

    // Select sub-account and expand sync rules
    await page.locator("text=Work Google").first().click();
    await page.waitForTimeout(500);
    await page.locator("button:has-text('Sync Rules')").first().click();
    await page.waitForTimeout(500);

    // Click Add Rule
    await page.locator("button:has-text('Add Rule')").first().click();
    await page.waitForTimeout(500);

    // Rule type buttons should be visible
    await expect(page.locator("button:has-text('Include')").first()).toBeVisible();
    await expect(page.locator("button:has-text('Exclude')").first()).toBeVisible();
    await expect(page.locator("button:has-text('Transform')").first()).toBeVisible();
    await expect(page.locator("button:has-text('Agent Review')").first()).toBeVisible();
  });

  test("selecting exclude shows description and pattern input", async ({ page }) => {
    await page.goto("http://localhost:3456");
    await expect(page.getByText("Conductor").first()).toBeVisible({ timeout: 10_000 });

    // Select sub-account, expand sync rules, click add
    await page.locator("text=Work Google").first().click();
    await page.waitForTimeout(500);
    await page.locator("button:has-text('Sync Rules')").first().click();
    await page.waitForTimeout(500);
    await page.locator("button:has-text('Add Rule')").first().click();
    await page.waitForTimeout(500);

    // Click Exclude rule type
    await page.locator("button:has-text('Exclude')").first().click();
    await page.waitForTimeout(300);

    // Pattern input should be visible
    const patternInput = page.locator("input[placeholder*='private']").first();
    await expect(patternInput).toBeVisible();

    // Type a pattern
    await patternInput.fill("*private*");
    await page.waitForTimeout(200);

    // Verify the pattern was typed
    await expect(patternInput).toHaveValue("*private*");
  });

  test("cancel button closes the add rule form", async ({ page }) => {
    await page.goto("http://localhost:3456");
    await expect(page.getByText("Conductor").first()).toBeVisible({ timeout: 10_000 });

    // Select sub-account, expand sync rules, click add
    await page.locator("text=Work Google").first().click();
    await page.waitForTimeout(500);
    await page.locator("button:has-text('Sync Rules')").first().click();
    await page.waitForTimeout(500);
    await page.locator("button:has-text('Add Rule')").first().click();
    await page.waitForTimeout(500);

    // Click Cancel
    await page.locator("button:has-text('Cancel')").first().click();
    await page.waitForTimeout(500);

    // The Add Rule button should reappear (form is closed)
    await expect(page.locator("button:has-text('Add Rule')").first()).toBeVisible();

    // The pattern input should not be visible
    const patternInput = page.locator("input[placeholder*='private']").first();
    await expect(patternInput).not.toBeVisible();
  });
});
