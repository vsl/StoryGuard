import { ManuscriptScreen } from "@/components/core-screens";

export default async function ManuscriptPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <ManuscriptScreen projectId={projectId} />;
}
