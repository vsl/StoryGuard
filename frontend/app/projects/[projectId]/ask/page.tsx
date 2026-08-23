import { AskOverview } from "@/components/chat";
import { PageHeader } from "@/components/ui";

export default async function AskPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return (
    <>
      <PageHeader
        eyebrow="Evidence-first AI"
        title="Ask StoryGuard"
        description="Ask about this story. Answers should cite the exact manuscript passages that support them."
      />
      <AskOverview projectId={projectId} />
    </>
  );
}
