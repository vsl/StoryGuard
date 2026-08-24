import { expect, test } from "@playwright/test";

test.skip(
  process.env.RUN_REAL_STACK_E2E !== "1",
  "set RUN_REAL_STACK_E2E=1 with the Docker stack running",
);

test("real upload reaches the worker and chapter viewer", async ({ page }) => {
  let projectId = "";
  try {
    await page.goto("http://127.0.0.1:3000/projects/new");
    await page
      .getByLabel("Story title")
      .fill(`Real ingestion ${Date.now()}`);
    await page.getByRole("button", { name: "Create Story" }).click();
    await expect(page).toHaveURL(/\/projects\/[^/]+\/versions/);
    projectId = new URL(page.url()).pathname.split("/")[2];

    await page.locator('input[type="file"]').setInputFiles({
      name: "real-story.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Chapter 1\nAlice waited by the lighthouse."),
    });
    await page.getByRole("button", { name: "Upload manuscript" }).click();
    await expect(page.getByText("completed", { exact: true })).toBeVisible({
      timeout: 60_000,
    });

    await page.getByRole("link", { name: "Manuscript" }).click();
    await page.getByRole("button", { name: /Chapter 1/ }).click();
    await expect(
      page.getByText("Alice waited by the lighthouse."),
    ).toBeVisible();
  } finally {
    if (projectId) {
      await page.request.delete(
        `http://127.0.0.1:8000/api/projects/${projectId}`,
      );
    }
  }
});
