import { describe, expect, it } from "vitest";

import { projectSchema, readSse } from "@/lib/api";

it("accepts an empty manuscript state from the project API", () => {
  expect(
    projectSchema.parse({
      id: "project-1",
      title: "Story",
      description: "",
      language: "en",
      current_manuscript_version_id: null,
      current_manuscript_version: null,
      chapter_count: null,
      created_at: "2026-08-24T00:00:00Z",
      updated_at: "2026-08-24T00:00:00Z",
    }).chapter_count,
  ).toBeNull();
});

describe("readSse", () => {
  it("parses chunked named events without exposing implementation details", async () => {
    const events: [string, unknown][] = [];
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(
          new TextEncoder().encode(
            'event: retrieval.completed\ndata: {"count":6}\n\n',
          ),
        );
        controller.enqueue(
          new TextEncoder().encode(
            'event: answer.delta\ndata: {"delta":"Daniel"}\n\n',
          ),
        );
        controller.close();
      },
    });
    await readSse(new Response(body, { status: 200 }), (name, data) =>
      events.push([name, data]),
    );
    expect(events).toEqual([
      ["retrieval.completed", { count: 6 }],
      ["answer.delta", { delta: "Daniel" }],
    ]);
  });
});
