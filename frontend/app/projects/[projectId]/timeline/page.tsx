import { TimelineScreen } from "@/components/core-screens";

export default async function TimelinePage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <TimelineScreen projectId={projectId} />;
}
