"use client";

import { Badge, ButtonLink, Dialog } from "@/components/ui";
import type { Evidence } from "@/lib/types";

export function EvidenceDrawer({
  projectId,
  evidence,
  onClose,
}: {
  projectId: string;
  evidence: Evidence | null;
  onClose: () => void;
}) {
  if (!evidence) return null;
  const query = new URLSearchParams();
  if (evidence.chapter_id) query.set("chapter", evidence.chapter_id);
  query.set("evidence", evidence.id);
  return (
    <Dialog open title="Source evidence" onClose={onClose}>
      <div className="flex flex-wrap gap-2">
        <Badge tone="info">{evidence.chapter ?? "Manuscript source"}</Badge>
        {evidence.scene && <Badge>{evidence.scene}</Badge>}
        {evidence.manuscript_version_id && (
          <Badge>{evidence.manuscript_version_id}</Badge>
        )}
      </div>
      {evidence.claim && (
        <p className="mt-5 text-sm">
          <strong>Supports:</strong> {evidence.claim}
        </p>
      )}
      <blockquote className="mt-5 border-l-4 border-[var(--amber)] bg-[var(--amber-soft)] px-5 py-4 font-serif text-base leading-7">
        “{evidence.text}”
      </blockquote>
      <p className="mt-3 text-xs text-muted">Evidence ID: {evidence.id}</p>
      <ButtonLink
        className="mt-6"
        href={`/projects/${projectId}/manuscript?${query}`}
      >
        Open in manuscript
      </ButtonLink>
    </Dialog>
  );
}
