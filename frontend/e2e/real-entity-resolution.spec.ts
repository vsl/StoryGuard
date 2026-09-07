import { expect, test } from "@playwright/test";

test.skip(
  process.env.RUN_REAL_STACK_E2E !== "1",
  "set RUN_REAL_STACK_E2E=1 with the Docker stack running",
);

test("real resolution stops, resumes, and automatically applies an evidence-backed merge", async ({
  page,
}) => {
  test.setTimeout(600_000);
  let projectId = "";
  try {
    await page.goto("/projects/new");
    await page.getByLabel("Story title").fill(`Resolution smoke ${Date.now()}`);
    await page.getByRole("button", { name: "Create Story" }).click();
    await expect(page).toHaveURL(/\/projects\/[^/]+\/versions/);
    projectId = new URL(page.url()).pathname.split("/")[2];
    await page
      .getByLabel("Entity extraction model")
      .selectOption("gliner2.5-base-v1");
    await page.locator('input[type="file"]').setInputFiles({
      name: "resolution-smoke.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(
        "Chapter 1\nA letter mentioned Alex. Another letter mentioned Alex. Both letters described the same person.\n\nChapter 2\nNora Vale introduced herself as Nori, her lifelong nickname.",
      ),
    });
    await page.getByRole("button", { name: "Upload manuscript" }).click();
    await expect(page.getByText("completed", { exact: true })).toBeVisible({
      timeout: 150_000,
    });
    await page.getByRole("link", { name: "Story Bible" }).click();
    for (const label of [
      "characters",
      "facilities",
      "Countries & cities",
      "locations",
      "organizations",
      "vehicles",
    ]) {
      await expect(
        page.getByRole("button", { name: label, exact: true }),
      ).toBeVisible();
    }
    await expect(
      page.getByRole("button", { name: "objects", exact: true }),
    ).toHaveCount(0);
    for (const category of [
      "facility",
      "gpe",
      "location",
      "organization",
      "vehicle",
    ]) {
      const response = await page.request.get(
        `/api/projects/${projectId}/entities?type=${category}`,
      );
      expect(response.ok()).toBe(true);
    }
    expect(
      (
        await page.request.get(
          `/api/projects/${projectId}/entities?type=object`,
        )
      ).status(),
    ).toBe(422);
    await expect(
      page.getByText("Automatic merging: ON", { exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Resolve entities", exact: true })
      .click();
    await expect
      .poll(
        async () => {
          const state = await (
            await page.request.get(
              `/api/projects/${projectId}/entity-resolution/candidates`,
            )
          ).json();
          return state.job?.stage;
        },
        { timeout: 30_000 },
      )
      .toBe("entity_resolution");
    await page
      .getByRole("button", { name: "Stop resolution", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText("Resolution stopped:");
    await page.screenshot({
      path: test.info().outputPath("resolution-stopped.png"),
      fullPage: true,
    });
    await page.reload();
    await page
      .getByRole("button", { name: "Resume resolution", exact: true })
      .click();
    await expect(
      page.getByRole("status").filter({ hasText: "Resolution completed:" }),
    ).toBeVisible({ timeout: 420_000 });
    const payload = await (
      await page.request.get(
        `/api/projects/${projectId}/entity-resolution/candidates`,
      )
    ).json();
    await test.info().attach("resolution-candidates", {
      body: JSON.stringify(payload, null, 2),
      contentType: "application/json",
    });
    expect(payload.auto_apply).toBe(true);
    expect(payload.pipeline).toBe("coreference_gemma");
    expect(payload.coreference_merge_count).toBe(1);
    expect(payload.gemma_comparison_count).toBe(1);
    expect(payload.applied_count).toBe(2);
    expect(payload.job.error_code).toBeNull();
    expect(payload.items).toHaveLength(0);
    await expect(
      page.getByRole("status").filter({ hasText: "2 decisions applied" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Merge", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Nora Vale", exact: true }).click();
    await page
      .getByRole("button", { name: "Source evidence 1", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toContainText("introduced herself");
    await page.getByRole("button", { name: "Close dialog" }).click();
    const characters = await (
      await page.request.get(`/api/projects/${projectId}/characters`)
    ).json();
    expect(
      characters.some(
        (item: { aliases: string[] }) =>
          item.aliases.includes("Nora Vale") && item.aliases.includes("Nori"),
      ),
    ).toBe(true);
    const versions = await (
      await page.request.get(`/api/projects/${projectId}/manuscripts`)
    ).json();
    expect(versions[0].status).toBe("ready");
    expect(versions[0].extraction_model).toBe("gliner2.5-base-v1");
    await page.screenshot({
      path: test.info().outputPath("combined-resolution.png"),
      fullPage: true,
    });
  } finally {
    if (projectId) await page.request.delete(`/api/projects/${projectId}`);
  }
});
