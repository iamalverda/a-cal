import { test, expect } from "@playwright/test";

/**
 * E2E tests for sub-account management.
 *
 * Verifies the sub-account sidebar renders and the add-account wizard
 * opens when "Add Sub-Calendar" is clicked, stepping through the
 * name to provider selection flow.
 */
test.describe("Sub-accounts", () => {
  test("sub-account sidebar renders with main account", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Main Calendar")).toBeVisible();
  });

  test("Add Sub-Calendar button opens wizard at name step", async ({ page }) => {
    await page.goto("/");
    const addBtn = page.getByRole("button", { name: /Add Sub-Calendar/i });
    await expect(addBtn).toBeVisible();
    await addBtn.click();

    // Wizard opens at step 0: name input
    await expect(
      page.getByText("What do you want to call this sub-calendar?")
    ).toBeVisible({ timeout: 5_000 });
  });

  test("wizard proceeds to provider selection after entering name", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Add Sub-Calendar/i }).click();

    // Step 0: Enter a name
    const nameInput = page.getByPlaceholder("e.g. Work Google, Personal, Side Project Email");
    await expect(nameInput).toBeVisible({ timeout: 5_000 });
    await nameInput.fill("Test Calendar");

    // Click Next to proceed to step 1
    const nextBtn = page.getByRole("button", { name: /Next/i });
    await nextBtn.click();

    // Step 1: Provider selection should show provider options.
    // Provider labels are in span.text-sm.font-medium; use .first() since
    // the description text also contains the provider name.
    await expect(page.getByText("Choose a provider")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("Google Calendar").first()).toBeVisible();
    await expect(page.getByText("Outlook Calendar").first()).toBeVisible();
    await expect(page.getByText("CalDAV Server").first()).toBeVisible();
  });

  test("wizard can be closed", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Add Sub-Calendar/i }).click();

    // Verify wizard is open
    await expect(
      page.getByText("What do you want to call this sub-calendar?")
    ).toBeVisible({ timeout: 5_000 });

    // Close the wizard via the Cancel button (step 0)
    const cancelBtn = page.getByRole("button", { name: /Cancel/i });
    await cancelBtn.click();

    // Wizard should be gone
    await expect(
      page.getByText("What do you want to call this sub-calendar?")
    ).not.toBeVisible({ timeout: 5_000 });
  });
});
