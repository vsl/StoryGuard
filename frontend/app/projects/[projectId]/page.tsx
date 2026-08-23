import { OverviewScreen } from "@/components/core-screens";

export default async function OverviewPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <OverviewScreen projectId={projectId} />;
}
