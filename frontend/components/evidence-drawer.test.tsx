import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EvidenceDrawer } from "@/components/evidence-drawer";

describe("EvidenceDrawer", () => {
  it("renders an exact source and a manuscript deep link", () => {
    const close = vi.fn();
    render(
      <EvidenceDrawer
        projectId="project-1"
        evidence={{
          id: "ev-1",
          chapter_id: "chapter-2",
          chapter: "Chapter 2",
          scene: "Scene 1",
          text: "His green eyes tracked the beam.",
        }}
        onClose={close}
      />,
    );
    expect(screen.getByText(/His green eyes/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open in manuscript" }),
    ).toHaveAttribute(
      "href",
      "/projects/project-1/manuscript?chapter=chapter-2&evidence=ev-1",
    );
    fireEvent.click(screen.getByRole("button", { name: "Close dialog" }));
    expect(close).toHaveBeenCalled();
  });
});
