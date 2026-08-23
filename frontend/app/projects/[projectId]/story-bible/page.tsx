import { StoryBibleScreen } from "@/components/core-screens";

export default async function StoryBiblePage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <StoryBibleScreen projectId={projectId} />;
}
