import { expect, test, type Page } from "@playwright/test";

const project = {
  id: "project-1",
  title: "The Last Signal",
  description: "A lighthouse mystery",
  language: "en",
  current_manuscript_version_id: null,
  created_at: "2026-08-23T10:00:00Z",
  updated_at: "2026-08-23T10:00:00Z",
};

async function mockProject(page: Page) {
  await page.route("**/api/projects", async (route) => {
    if (route.request().method() === "POST")
      await route.fulfill({ status: 201, json: project });
    else await route.fulfill({ json: [project] });
  });
  await page.route("**/api/projects/project-1", (route) =>
    route.fulfill({ json: project }),
  );
}

test("create story and upload manuscript", async ({ page }) => {
  await mockProject(page);
  await page.route("**/api/projects/project-1/manuscripts", (route) =>
    route.fulfill({
      status: 201,
      json: {
        manuscript_version_id: "mv-1",
        version: "v1",
        job_id: "job-1",
        status: "queued",
      },
    }),
  );
  await page.route("**/api/jobs/job-1", (route) =>
    route.fulfill({
      json: { id: "job-1", status: "queued", stage: "file_uploaded" },
    }),
  );
  await page.goto("/projects/new");
  await page.getByLabel("Story title").fill("The Last Signal");
  await page.getByRole("button", { name: "Create Story" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "story.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Chapter 1"),
  });
  await page.getByRole("button", { name: "Upload manuscript" }).click();
  await expect(page.getByText("queued", { exact: true })).toBeVisible();
});

test("open chapter and preserve evidence deep link", async ({ page }) => {
  await mockProject(page);
  await page.route("**/api/projects/project-1/chapters", (route) =>
    route.fulfill({ json: [{ id: "ch-2", number: 2, title: "Echoes" }] }),
  );
  await page.route("**/api/projects/project-1/chapters/ch-2", (route) =>
    route.fulfill({
      json: {
        id: "ch-2",
        number: 2,
        title: "Echoes",
        paragraphs: [
          {
            id: "p-1",
            text: "His green eyes tracked the beam.",
            evidence_ids: ["ev-1"],
          },
        ],
      },
    }),
  );
  await page.goto("/projects/project-1/manuscript?chapter=ch-2&evidence=ev-1");
  await expect(
    page.getByText("His green eyes tracked the beam."),
  ).toBeVisible();
});

test("review a continuity issue", async ({ page }) => {
  await mockProject(page);
  const issue = {
    id: "issue-1",
    title: "Daniel’s eye color",
    severity: "Likely",
    description: "Green in chapter 2, blue in chapter 17.",
    evidence: [],
  };
  await page.route("**/api/projects/project-1/issues", (route) =>
    route.fulfill({ json: [issue] }),
  );
  await page.route("**/api/projects/project-1/issues/issue-1", (route) =>
    route.fulfill({ json: issue }),
  );
  await page.route(
    "**/api/projects/project-1/issues/issue-1/feedback",
    (route) => route.fulfill({ status: 204 }),
  );
  await page.goto("/projects/project-1/issues");
  await page.getByRole("button", { name: /Daniel’s eye color/ }).click();
  await page.getByRole("button", { name: "Not an issue" }).click();
  await page.getByRole("button", { name: "Save review" }).click();
  await expect(page.getByText("Why is this not an issue?")).not.toBeVisible();
});

test("ask and open citation evidence", async ({ page }) => {
  await mockProject(page);
  await page.route("**/api/projects/project-1/chat/stream", (route) =>
    route.fulfill({
      json: {
        answer: "Daniel’s eyes are green.",
        citations: [
          {
            id: "ev-1",
            chapter: "Chapter 2",
            chapter_id: "ch-2",
            text: "His green eyes tracked the beam.",
          },
        ],
      },
    }),
  );
  await page.goto("/projects/project-1/ask");
  await page.getByLabel("Ask StoryGuard").fill("What color are Daniel’s eyes?");
  await page.getByRole("button", { name: "Send question" }).click();
  await page.getByRole("button", { name: /Chapter 2/ }).click();
  await expect(page.getByText(/His green eyes/)).toBeVisible();
});

test("upload a new manuscript version", async ({ page }) => {
  await mockProject(page);
  await page.route("**/api/projects/project-1/manuscripts", async (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          status: 201,
          json: { job_id: "job-2", status: "queued" },
        })
      : route.fulfill({
          json: [
            {
              id: "mv-1",
              version_number: 1,
              original_filename: "draft.txt",
              status: "ready",
            },
          ],
        }),
  );
  await page.route("**/api/jobs/job-2", (route) =>
    route.fulfill({
      json: { id: "job-2", status: "queued", stage: "file_uploaded" },
    }),
  );
  await page.goto("/projects/project-1/versions");
  const dataTransfer = await page.evaluateHandle(() => {
    const transfer = new DataTransfer();
    transfer.items.add(
      new File(["Revision"], "revision.txt", { type: "text/plain" }),
    );
    return transfer;
  });
  await page
    .locator("label")
    .filter({ hasText: "Choose or drop a manuscript" })
    .dispatchEvent("drop", { dataTransfer });
  await expect(page.getByText("revision.txt")).toBeVisible();
  await page.getByRole("button", { name: "Upload manuscript" }).click();
  await expect(page.getByText("queued", { exact: true })).toBeVisible();
});
