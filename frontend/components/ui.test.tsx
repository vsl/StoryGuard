import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ErrorState } from "@/components/ui";
import { ApiError } from "@/lib/api";

describe("ErrorState", () => {
  it("distinguishes an unimplemented endpoint from a generic failure", () => {
    render(<ErrorState error={new ApiError("Not Found", 404)} />);
    expect(
      screen.getByText("This view is waiting for its API"),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "backend endpoint has not been implemented",
    );
  });
});
