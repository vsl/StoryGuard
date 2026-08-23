"use client";

import { GitMerge, Split } from "lucide-react";
import { useState } from "react";

import { Badge, Button, Card, ErrorState, LoadingState } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useEndpoint } from "@/lib/hooks";
import type { Evidence } from "@/lib/types";

type Candidate = {
  id: string;
  left: { id: string; name: string };
  right: { id: string; name: string };
  confidence?: number;
  evidence?: Evidence[];
};

export function EntityResolutionPanel({
  projectId,
  onEvidence,
}: {
  projectId: string;
  onEvidence: (evidence: Evidence) => void;
}) {
  const candidates = useEndpoint<Candidate[] | { items?: Candidate[] }>(
    ["entity-resolution", projectId],
    `/projects/${projectId}/entity-resolution/candidates`,
  );
  const items = Array.isArray(candidates.data)
    ? candidates.data
    : (candidates.data?.items ?? []);
  if (candidates.isLoading)
    return <LoadingState label="Checking entity matches…" />;
  if (candidates.error)
    return (
      <ErrorState error={candidates.error} retry={() => candidates.refetch()} />
    );
  if (!items.length) return null;
  return (
    <div className="mb-6">
      <h2 className="page-title text-xl font-semibold">
        Possible duplicate characters
      </h2>
      <div className="mt-3 space-y-3">
        {items.map((candidate) => (
          <EntityResolutionCard
            key={candidate.id}
            projectId={projectId}
            candidate={candidate}
            onResolved={() => candidates.refetch()}
            onEvidence={onEvidence}
          />
        ))}
      </div>
    </div>
  );
}

export function EntityResolutionCard({
  projectId,
  candidate,
  onResolved,
  onEvidence,
}: {
  projectId: string;
  candidate: Candidate;
  onResolved: () => void;
  onEvidence: (evidence: Evidence) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  async function resolve(decision: "merge" | "keep_separate") {
    setSaving(true);
    setError("");
    try {
      await api(
        `/projects/${projectId}/entity-resolution/${candidate.id}/resolve`,
        {
          method: "POST",
          body: JSON.stringify({ decision }),
        },
      );
      onResolved();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSaving(false);
    }
  }
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1">
          <p className="font-semibold">{candidate.left.name}</p>
          <p className="text-xs text-muted">Entity {candidate.left.id}</p>
        </div>
        <span className="text-muted">↔</span>
        <div className="flex-1">
          <p className="font-semibold">{candidate.right.name}</p>
          <p className="text-xs text-muted">Entity {candidate.right.id}</p>
        </div>
        {candidate.confidence !== undefined && (
          <Badge tone="warn">
            {Math.round(
              candidate.confidence * (candidate.confidence <= 1 ? 100 : 1),
            )}
            % match
          </Badge>
        )}
      </div>
      {error && (
        <p className="mt-3 text-sm text-[var(--danger)]" role="alert">
          {error}
        </p>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        <Button disabled={saving} onClick={() => resolve("merge")}>
          <GitMerge className="size-4" />
          Merge
        </Button>
        <Button
          disabled={saving}
          variant="secondary"
          onClick={() => resolve("keep_separate")}
        >
          <Split className="size-4" />
          Keep separate
        </Button>
        {candidate.evidence?.[0] && (
          <Button
            variant="ghost"
            onClick={() => onEvidence(candidate.evidence![0])}
          >
            Review evidence
          </Button>
        )}
      </div>
    </Card>
  );
}
