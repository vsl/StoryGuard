import { describe, expect, it } from "vitest";

import { readSse } from "@/lib/api";

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
