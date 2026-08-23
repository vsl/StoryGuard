import type { ReactNode } from "react";

import { ProjectShell } from "@/components/project-shell";

export default async function Layout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <ProjectShell projectId={projectId}>{children}</ProjectShell>;
}
