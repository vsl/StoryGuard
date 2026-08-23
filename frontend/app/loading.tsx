import { LoadingState } from "@/components/ui";

export default function Loading() {
  return (
    <main className="grid min-h-screen place-items-center">
      <LoadingState label="Opening StoryGuard…" />
    </main>
  );
}
