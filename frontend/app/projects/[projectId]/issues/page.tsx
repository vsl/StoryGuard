import { IssuesScreen } from "@/components/core-screens";

export default async function IssuesPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <IssuesScreen projectId={projectId} />;
}
