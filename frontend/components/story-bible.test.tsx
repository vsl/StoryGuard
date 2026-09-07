import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ManuscriptScreen,
  StoryBibleScreen,
  TimelineScreen,
} from "@/components/core-screens";

const replace = vi.fn();
let queryString = "tab=characters&selected=alice";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(queryString),
}));

afterEach(() => {
  cleanup();
  replace.mockClear();
  queryString = "tab=characters&selected=alice";
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
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
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

  it("shows persisted facts and story-memory coverage", async () => {
    queryString = "tab=facts&selected=fact-1";
    let rebuild: boolean | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (request, init) => {
      const url = String(request);
      if (url.includes("structured-memory/run")) {
        rebuild = JSON.parse(String(init?.body)).rebuild;
        return Response.json({
          job_id: "job-2",
          manuscript_version_id: "version-1",
          status: "queued",
        });
      }
      if (url.includes("structured-memory/status"))
        return Response.json({
          manuscript_version_id: "version-1",
          job: { id: "job-1", status: "completed" },
          completed_chunks: 2,
          failed_chunks: 0,
          total_chunks: 2,
          facts: 1,
          events: 2,
          relationships: 1,
        });
      if (url.endsWith("/facts"))
        return Response.json([
          {
            id: "fact-1",
            subject: "Mara",
            predicate: "eye_color",
            value: "green",
            fact_type: "attribute",
            confidence: null,
            source: "Chapter 1",
            status: "active",
            evidence: [],
          },
        ]);
      return Response.json({});
    });

    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <StoryBibleScreen projectId="project-1" />
      </QueryClientProvider>,
    );

    expect(
      await screen.findByRole("heading", { name: "Mara · eye_color" }),
    ).toBeVisible();
    expect(screen.getByText("Story memory ready")).toBeVisible();
    expect(
      screen.getByText(/2\/2 chunks · 1 facts · 2 events · 1 relationships/),
    ).toBeVisible();
    const factType = screen.getByRole("combobox", { name: "Fact type" });
    expect(
      within(factType).getByRole("option", { name: "attribute" }),
    ).toBeVisible();
    expect(
      within(factType).queryByRole("option", { name: "eye_color" }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /Rebuild story memory/ }),
    );
    await waitFor(() => expect(rebuild).toBe(true));
  });

  it("keeps event participants visible in Story Bible details", async () => {
    queryString = "tab=events&selected=event-1";
    vi.spyOn(globalThis, "fetch").mockImplementation(async (request) => {
      const url = String(request);
      if (url.includes("structured-memory/status"))
        return Response.json({
          manuscript_version_id: "version-1",
          job: { id: "job-1", status: "completed" },
          completed_chunks: 1,
          failed_chunks: 0,
          total_chunks: 1,
          facts: 0,
          events: 1,
          relationships: 0,
        });
      if (url.endsWith("/events"))
        return Response.json([
          {
            id: "event-1",
            type: "relationship_ended",
            title: "Mara and Ilya divorced",
            participants: ["Mara", "Ilya"],
            evidence: [],
          },
        ]);
      return Response.json({});
    });

    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <StoryBibleScreen projectId="project-1" />
      </QueryClientProvider>,
    );

    const details = screen.getByLabelText("Story Bible details");
    expect(await within(details).findByText("Mara")).toBeVisible();
    expect(within(details).getByText("Ilya")).toBeVisible();
  });

  it("shows a recoverable story-memory status error and current empty-state copy", async () => {
    queryString = "tab=relationships";
    vi.spyOn(globalThis, "fetch").mockImplementation(async (request) => {
      const url = String(request);
      if (url.includes("structured-memory/status"))
        return Response.json(
          { error: { message: "Story-memory status is unavailable." } },
          { status: 503 },
        );
      if (url.endsWith("/relationships")) return Response.json([]);
      return Response.json({});
    });

    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <StoryBibleScreen projectId="project-1" />
      </QueryClientProvider>,
    );

    expect(
      await screen.findByText("Story-memory status is unavailable."),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Retry status" })).toBeEnabled();
    expect(
      screen.getByText(
        "Build story memory to extract supported records from the current manuscript.",
      ),
    ).toBeVisible();
    expect(
      screen.queryByText(/later course capability/i),
    ).not.toBeInTheDocument();
  });
});

describe("TimelineScreen", () => {
  it("sorts chronological time, preserves narrative order, filters participants, and opens evidence", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (request) => {
      const url = String(request);
      if (url.includes("structured-memory/status"))
        return Response.json({
          manuscript_version_id: null,
          job: null,
          completed_chunks: 0,
          failed_chunks: 0,
          total_chunks: 0,
          facts: 0,
          events: 0,
          relationships: 0,
        });
      if (url.endsWith("/events"))
        return Response.json([
          {
            id: "later",
            type: "relationship_ended",
            title: "Later event",
            chronological_time: "2024",
            chronological_time_normalized: "2024-01-01",
            narrative_position: "Chapter 1",
            participants: ["Ilya"],
            location: "Porto",
            evidence: [],
          },
          {
            id: "earlier",
            type: "relationship_started",
            title: "Earlier event",
            chronological_time: "2020",
            chronological_time_normalized: "2020-01-01",
            narrative_position: "Chapter 2",
            participants: ["Mara", "Ilya"],
            evidence: [
              {
                id: "evidence-1",
                chapter_id: "chapter-2",
                text: "Mara married Ilya.",
                start_offset: 18,
                end_offset: 37,
              },
            ],
          },
        ]);
      return Response.json({});
    });

    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <TimelineScreen projectId="project-1" />
      </QueryClientProvider>,
    );

    let articles = await screen.findAllByRole("article");
    expect(articles[0]).toHaveTextContent("Earlier event");
    const characters = screen.getByRole("combobox", { name: "Character" });
    expect(
      within(characters).getByRole("option", { name: "Mara" }),
    ).toBeVisible();
    fireEvent.change(characters, { target: { value: "Mara" } });
    expect(screen.getAllByRole("article")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Source evidence 1" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Mara married Ilya.");
    expect(
      screen.getByRole("link", { name: "Open in manuscript" }),
    ).toHaveAttribute(
      "href",
      "/projects/project-1/manuscript?chapter=chapter-2&evidence=evidence-1&start=18&end=37",
    );
    fireEvent.click(screen.getByRole("button", { name: "Close dialog" }));

    fireEvent.change(characters, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Narrative" }));
    articles = screen.getAllByRole("article");
    expect(articles[0]).toHaveTextContent("Later event");
    expect(articles[0]).toHaveTextContent("Chronological: 2024");
  });
});

describe("ManuscriptScreen", () => {
  it("highlights the server-issued evidence range in production chapter text", async () => {
    queryString = "chapter=chapter-2&evidence=evidence-1&start=7&end=12";
    vi.spyOn(globalThis, "fetch").mockImplementation(async (request) => {
      const url = String(request);
      if (url.endsWith("/chapters/chapter-2"))
        return Response.json({
          id: "chapter-2",
          number: 2,
          title: "Echoes",
          text: "🙂Start green ending.",
        });
      if (url.endsWith("/chapters"))
        return Response.json([{ id: "chapter-2", number: 2, title: "Echoes" }]);
      return Response.json({});
    });

    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <ManuscriptScreen projectId="project-1" />
      </QueryClientProvider>,
    );

    expect(
      await screen.findByText("green", { selector: "mark" }),
    ).toBeVisible();
  });
});
