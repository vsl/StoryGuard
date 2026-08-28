import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExperimentLabScreen } from "@/components/operations-screens";

afterEach(() => vi.restoreAllMocks());

function response(value: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(value), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );
}

describe("ExperimentLabScreen", () => {
  it("submits only a server-known diagnostic suite and controlled pair", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation((input, init) => {
        const path = String(input);
        if (path.endsWith("/developer/datasets"))
          return response([
            {
              id: "gacha-smoke",
              name: "Gacha smoke · 3 queries",
              purpose: "smoke",
              stories: ["A Christmas Carol"],
              query_count: 3,
              promotion_eligible: false,
            },
          ]);
        if (path.endsWith("/developer/experiment-configs"))
          return response([
            { id: "hybrid-rrf", name: "Hybrid RRF", reranker: false },
            {
              id: "hybrid-rrf-reranker",
              name: "Hybrid RRF + cross-encoder",
              reranker: true,
            },
          ]);
        if (path.endsWith("/developer/experiments") && init?.method === "POST")
          return response({ id: "run-1", status: "queued" }, 201);
        if (path.endsWith("/developer/experiments")) return response([]);
        return response({}, 404);
      });
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    render(
      <QueryClientProvider client={client}>
        <ExperimentLabScreen />
      </QueryClientProvider>,
    );

    fireEvent.change(await screen.findByLabelText("Dataset"), {
      target: { value: "gacha-smoke" },
    });
    expect(screen.getByText(/not eligible for promotion/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run experiment" }));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.find(
          ([path, init]) =>
            String(path).endsWith("/developer/experiments") &&
            init?.method === "POST",
        ),
      ).toBeDefined(),
    );
    const request = fetchMock.mock.calls.find(
      ([path, init]) =>
        String(path).endsWith("/developer/experiments") &&
        init?.method === "POST",
    );
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      dataset_id: "gacha-smoke",
      baseline_config_id: "hybrid-rrf",
      candidate_config_id: "hybrid-rrf-reranker",
    });
  });
});
