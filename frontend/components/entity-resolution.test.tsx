import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EntityResolutionCard } from "@/components/entity-resolution";

afterEach(() => vi.restoreAllMocks());

describe("EntityResolutionCard", () => {
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
            confidence: 0.82,
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
});
