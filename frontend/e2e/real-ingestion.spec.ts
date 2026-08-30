import { expect, test } from "@playwright/test";

test.skip(
  process.env.RUN_REAL_STACK_E2E !== "1",
  "set RUN_REAL_STACK_E2E=1 with the Docker stack running",
);

for (const model of ["gliner2.5-base-v1", "gemma4-e4b", "qwen3.5-9b"]) {
  test(`real upload with ${model} reaches the worker and chapter viewer`, async ({
    page,
  }) => {
    test.setTimeout(180_000);
    let projectId = "";
    try {
      await page.goto("http://127.0.0.1:3000/projects/new");
      await page.getByLabel("Story title").fill(`Real ingestion ${Date.now()}`);
      await page.getByRole("button", { name: "Create Story" }).click();
      await expect(page).toHaveURL(/\/projects\/[^/]+\/versions/);
      projectId = new URL(page.url()).pathname.split("/")[2];
      await expect(page.getByLabel("Entity extraction model")).toHaveValue(
        "gemma4-e4b",
      );
      if (model !== "gemma4-e4b") {
        await page.getByLabel("Entity extraction model").selectOption(model);
      }

      await page.locator('input[type="file"]').setInputFiles({
        name: "real-story.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("Chapter 1\nAlice waited by the lighthouse."),
      });
      const uploaded = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          response.url().endsWith("/manuscripts"),
      );
      await page.getByRole("button", { name: "Upload manuscript" }).click();
      const payload = await (await uploaded).json();
      expect(payload.extraction_model).toBe(model);
      await expect(page.getByText("completed", { exact: true })).toBeVisible({
        timeout: 150_000,
      });
      const job = await (
        await page.request.get(`/api/jobs/${payload.job_id}`)
      ).json();
      expect(job.stage_durations_ms.entity_extraction).toBeGreaterThan(0);
      expect(Object.keys(job.stage_durations_ms).sort()).toEqual([
        "embedding",
        "entity_extraction",
        "indexing",
        "parsing",
      ]);
      await test.info().attach("ingestion-job", {
        body: JSON.stringify({ model, ...job }, null, 2),
        contentType: "application/json",
      });
      console.log(
        JSON.stringify({ model, stage_durations_ms: job.stage_durations_ms }),
      );
      const versions = await (
        await page.request.get(`/api/projects/${projectId}/manuscripts`)
      ).json();
      expect(versions[0].extraction_model).toBe(model);
      await expect(page.getByText(/^Extractor:/)).toBeVisible();

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
}
