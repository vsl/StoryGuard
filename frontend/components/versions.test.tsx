import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { VersionsScreen } from "@/components/operations-screens";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it.each([false, true])(
  "cancels a processing version after reload (failure=%s)",
  async (failure) => {
    let status = "processing";
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (url, options) => {
        if (options?.method === "POST") {
          if (failure)
            return new Response(
              JSON.stringify({ detail: "Cancellation unavailable" }),
              { status: 503 },
            );
          status = "cancelled";
          return Response.json({ id: "old", status });
        }
        if (String(url).endsWith("/manuscripts"))
          return Response.json([
            {
              id: "current",
              version_number: 7,
              status: "ready",
              original_filename: "new.txt",
            },
            {
              id: "old",
              version_number: 6,
              status,
              original_filename: "old.txt",
            },
          ]);
        if (String(url).endsWith("/extraction-models"))
          return Response.json({ default: "gemma", items: [] });
        return Response.json({
          id: "project-1",
          title: "Story",
          description: "",
          language: "en",
          current_manuscript_version_id: "current",
          created_at: "2026-08-30",
          updated_at: "2026-08-30",
        });
      });
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    render(
      <QueryClientProvider client={client}>
        <VersionsScreen projectId="project-1" />
      </QueryClientProvider>,
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Cancel processing version 6",
      }),
    );
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project-1/manuscripts/old/cancel",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    expect(
      screen.queryByRole("button", { name: "Cancel processing version 7" }),
    ).not.toBeInTheDocument();
    if (failure) {
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Cancellation unavailable",
      );
      expect(
        screen.getByRole("button", { name: "Cancel processing version 6" }),
      ).toBeEnabled();
    } else {
      expect(await screen.findByText("cancelled")).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Cancel processing version 6" }),
      ).not.toBeInTheDocument();
    }
    client.clear();
  },
);
