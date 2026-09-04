import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StoryBibleScreen } from "@/components/core-screens";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () =>
    new URLSearchParams("tab=characters&selected=alice"),
}));

afterEach(() => {
  cleanup();
  replace.mockClear();
  vi.restoreAllMocks();
});

describe("StoryBibleScreen", () => {
  it("keeps independent panes and puts the selected entity before resolution", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (request) => {
      const url = String(request);
      if (url.includes("entity-resolution/candidates"))
        return Response.json({
          manuscript_version_id: "version-1",
          items: [],
          total: 0,
          remaining: 0,
          review_count: 0,
          applied_count: 0,
          successful_count: 0,
          error_count: 0,
          candidate_limit_reached: false,
          auto_apply: true,
          model: "gemma4:e4b",
          pipeline: "coreference_gemma",
          job: null,
        });
      if (url.endsWith("/characters/alice"))
        return Response.json({ id: "alice", name: "Alice", aliases: [] });
      if (url.endsWith("/characters"))
        return Response.json([
          { id: "alice", name: "Alice", aliases: [] },
          { id: "bob", name: "Bob", aliases: [] },
        ]);
      return Response.json({});
    });

    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <StoryBibleScreen projectId="project-1" />
      </QueryClientProvider>,
    );

    const list = await screen.findByLabelText("characters list");
    const pane = screen.getByLabelText("Story Bible details");
    const entityHeading = await screen.findByRole("heading", { name: "Alice" });
    const resolutionHeading = await screen.findByRole("heading", {
      name: "Entity resolution",
    });
    expect(list).toHaveClass("lg:overflow-y-auto");
    expect(pane).toHaveClass("lg:overflow-y-auto");
    expect(
      entityHeading.compareDocumentPosition(resolutionHeading) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    pane.scrollTo = vi.fn();
    fireEvent.click(screen.getByRole("button", { name: "Bob" }));
    expect(pane.scrollTo).toHaveBeenCalledWith({ top: 0 });
    expect(replace).toHaveBeenCalledWith("?tab=characters&selected=bob");
  });
});
