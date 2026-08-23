import { CheckTextScreen } from "@/components/operations-screens";

export default async function CheckPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <CheckTextScreen projectId={projectId} />;
}
