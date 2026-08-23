import { DeveloperScreen } from "@/components/operations-screens";

export default async function DeveloperPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <DeveloperScreen projectId={projectId} />;
}
