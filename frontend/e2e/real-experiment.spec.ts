import { expect, test } from "@playwright/test";

test.skip(
  process.env.RUN_REAL_EXPERIMENT_E2E !== "1",
  "set RUN_REAL_EXPERIMENT_E2E=1 with the Docker stack running",
);

test("real Experiment Lab run reaches the worker and returns metrics", async ({
  page,
}) => {
  test.setTimeout(20 * 60_000);
  const created = await page.request.post(
    "http://127.0.0.1:8000/api/projects",
    { data: { title: `Experiment E2E ${Date.now()}` } },
  );
  expect(created.ok()).toBeTruthy();
  const project = await created.json();
  try {
    await page.goto(
      `http://127.0.0.1:3000/projects/${project.id}/developer/experiments`,
    );
    await page.getByLabel("Dataset").selectOption("gacha-smoke");
    await expect(
      page.getByText("Diagnostic only · not eligible for promotion"),
    ).toBeVisible();
    await page.getByRole("button", { name: "Run experiment" }).click();
    await expect(page.getByText("completed", { exact: true })).toBeVisible({
      timeout: 20 * 60_000,
    });
    await expect(
      page.getByRole("row", { name: /recall at 10/i }),
    ).toBeVisible();
  } finally {
    await page.request.delete(
      `http://127.0.0.1:8000/api/projects/${project.id}`,
    );
  }
});
