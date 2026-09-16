import { expect, test } from "@playwright/test";

// Violations: playwright no-conditional-in-test, missing-playwright-await.
test("home", async ({ page }) => {
  if (Math.random() > 0.5) {
    await page.goto("/");
  }
  expect(page.locator("p")).toBeVisible();
});
