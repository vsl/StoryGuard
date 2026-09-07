import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  EntityResolutionCard,
  EntityResolutionPanel,
} from "@/components/entity-resolution";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("EntityResolutionCard", () => {
  it("never applies decisions from the browser without a click and exposes both excerpts", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const evidence = [
      { id: "one", text: "First source" },
      { id: "two", text: "Second source" },
    ];
    const onEvidence = vi.fn();
    render(
      <EntityResolutionCard
        projectId="project-1"
        candidate={{
          id: "candidate-1",
          left: { id: "a", name: "Alex" },
          right: { id: "b", name: "Alex Reed" },
          llm_decision: "merge",
          evidence,
        }}
        onResolved={vi.fn()}
        onEvidence={onEvidence}
      />,
    );
    expect(
      screen.getByText("Suggested merge — not applied"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/% match/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Review evidence 2" }));
    expect(onEvidence).toHaveBeenCalledWith(evidence[1]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([true, false])(
    "shows automatic mode %s and pins the run to the server version",
    async (autoApply) => {
      const data = {
        manuscript_version_id: "version-2",
        items: [],
        total: 0,
        remaining: 0,
        review_count: 0,
        applied_count: 0,
        candidate_limit_reached: false,
        auto_apply: autoApply,
        model: "gemma4:e4b",
        pipeline: "coreference_gemma",
        coreference_merge_count: 0,
        gemma_comparison_count: 3,
        job: null,
      };
      const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
        async () =>
          new Response(JSON.stringify(data), {
            headers: { "content-type": "application/json" },
          }),
      );
      render(
        <QueryClientProvider
          client={
            new QueryClient({ defaultOptions: { queries: { retry: false } } })
          }
        >
          <EntityResolutionPanel projectId="project-1" onEvidence={vi.fn()} />
        </QueryClientProvider>,
      );
      expect(
        await screen.findByText(
          `Automatic merging: ${autoApply ? "ON" : "OFF"}`,
        ),
      ).toBeInTheDocument();
      expect(screen.getByText(/xCoRe \+ gemma4:e4b/)).toBeInTheDocument();
      expect(
        screen.getByText(
          /0 merges applied without Gemma; 3 pairs sent to Gemma/,
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          autoApply
            ? /Validated merge and keep-separate decisions are applied immediately/
            : /every merge or keep-separate decision requires your confirmation/,
        ),
      ).toBeInTheDocument();
      fireEvent.click(
        await screen.findByRole("button", { name: "Resolve entities" }),
      );
      await waitFor(() =>
        expect(
          fetchMock.mock.calls.some(
            ([url, options]) =>
              url === "/api/projects/project-1/entity-resolution/run" &&
              options?.body ===
                JSON.stringify({ manuscript_version_id: "version-2" }),
          ),
        ).toBe(true),
      );
    },
  );

  it("preserves the server candidate id when resolving", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 204 }));
    render(
      <QueryClientProvider client={new QueryClient()}>
        <EntityResolutionCard
          projectId="project-1"
          candidate={{
            id: "candidate-9",
            left: { id: "one", name: "Daniel Reed" },
            right: { id: "two", name: "Mr. Reed" },
            llm_decision: "needs_review",
          }}
          onResolved={vi.fn()}
          onEvidence={vi.fn()}
        />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /keep separate/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/projects/project-1/entity-resolution/candidate-9/resolve",
    );
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: "POST",
      body: JSON.stringify({ decision: "keep_separate" }),
    });
  });

  it.each(["running", "queued"])(
    "stops a %s job and offers Resume after reload",
    async (status) => {
      let stopped = false;
      const fetchMock = vi
        .spyOn(globalThis, "fetch")
        .mockImplementation(async (url) => {
          if (String(url).endsWith("/jobs/job-1/stop")) stopped = true;
          return new Response(
            JSON.stringify({
              manuscript_version_id: "version-2",
              items: [],
              total: 3,
              remaining: 3,
              review_count: 0,
              applied_count: 0,
              successful_count: 0,
              error_count: 0,
              candidate_limit_reached: false,
              auto_apply: true,
              model: "gemma4:e4b",
              request_timeout_seconds: 180,
              job: {
                id: "job-1",
                status: stopped ? "cancelled" : status,
                stage: "coreference",
                current_stage_elapsed_ms: 61_000,
                completed: 0,
                total: 3,
              },
            }),
            { headers: { "content-type": "application/json" } },
          );
        });
      const mount = () =>
        render(
          <QueryClientProvider
            client={
              new QueryClient({ defaultOptions: { queries: { retry: false } } })
            }
          >
            <EntityResolutionPanel projectId="project-1" onEvidence={vi.fn()} />
          </QueryClientProvider>,
        );
      const first = mount();
      expect(
        await screen.findByText(/Resolution continues automatically/),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Resume resolution" }),
      ).not.toBeInTheDocument();
      fireEvent.click(
        await screen.findByRole("button", { name: "Stop resolution" }),
      );
      expect(
        await screen.findByRole("button", { name: "Resume resolution" }),
      ).toBeEnabled();
      expect(
        fetchMock.mock.calls.find(([url]) =>
          String(url).endsWith("/jobs/job-1/stop"),
        )?.[1],
      ).toMatchObject({
        method: "POST",
        body: JSON.stringify({ manuscript_version_id: "version-2" }),
      });
      first.unmount();
      mount();
      expect(
        await screen.findByRole("button", { name: "Resume resolution" }),
      ).toBeEnabled();
      expect(
        screen.queryByRole("button", { name: "Stop resolution" }),
      ).not.toBeInTheDocument();
    },
  );

  it("explains technical failure without calling it a model review decision", () => {
    render(
      <EntityResolutionCard
        projectId="project-1"
        candidate={{
          id: "failed",
          left: { id: "a", name: "Bill" },
          right: { id: "b", name: "Bill" },
          llm_decision: "needs_review",
          error_code: "MODEL_TIMEOUT",
          latency_ms: 180012,
          timeout_seconds: 180,
          trace_id: "trace-123",
          attempt: 2,
        }}
        onResolved={vi.fn()}
        onEvidence={vi.fn()}
      />,
    );
    expect(screen.getByText("Comparison failed")).toBeInTheDocument();
    expect(screen.queryByText("Model: needs review")).not.toBeInTheDocument();
    expect(
      screen.getByText(/model request timed out.*limit 180s/),
    ).toHaveTextContent("Elapsed: 180.0s. Attempt 2.");
    expect(screen.getByText("Trace ID: trace-123")).toBeInTheDocument();
  });

  it("refreshes characters and details when a merge applies while the job is running", async () => {
    const data = {
      manuscript_version_id: "version-2",
      items: [],
      total: 3,
      remaining: 3,
      review_count: 0,
      applied_count: 0,
      candidate_limit_reached: false,
      auto_apply: true,
      model: "gemma4:e4b",
      job: { id: "job-1", status: "running", completed: 0, total: 3 },
    };
    vi.spyOn(globalThis, "fetch").mockImplementation(
      async () =>
        new Response(JSON.stringify(data), {
          headers: { "content-type": "application/json" },
        }),
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    render(
      <QueryClientProvider client={client}>
        <EntityResolutionPanel projectId="project-1" onEvidence={vi.fn()} />
      </QueryClientProvider>,
    );
    await screen.findByText("Automatic merging: ON");
    invalidate.mockClear();
    act(() =>
      client.setQueryData(["entity-resolution", "project-1", 0], {
        ...data,
        applied_count: 1,
      }),
    );
    await waitFor(() => {
      for (const key of ["story-bible", "characters", "entity"]) {
        expect(invalidate).toHaveBeenCalledWith({
          queryKey: [key, "project-1"],
        });
      }
    });
  });
});
