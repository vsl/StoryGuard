import { AnalysisScreen } from "@/components/operations-screens";

export default async function AnalysisPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <AnalysisScreen projectId={projectId} />;
}
