import { SettingsScreen } from "@/components/operations-screens";

export default async function SettingsPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <SettingsScreen projectId={projectId} />;
}
