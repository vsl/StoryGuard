"use client";

import { ErrorState } from "@/components/ui";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <main className="mx-auto grid min-h-screen max-w-xl place-items-center p-6">
      <ErrorState error={error} retry={reset} />
    </main>
  );
}
