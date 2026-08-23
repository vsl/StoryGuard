import { VersionsScreen } from "@/components/operations-screens";

export default async function VersionsPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <VersionsScreen projectId={projectId} />;
}
