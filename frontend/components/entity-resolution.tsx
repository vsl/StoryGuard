"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { GitMerge, Split } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge, Button, Card, ErrorState, LoadingState } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { Evidence } from "@/lib/types";

type Candidate = {
  id: string;
  left: { id: string; name: string; type?: string; canonical_id?: string };
  right: { id: string; name: string; type?: string; canonical_id?: string };
  llm_decision?: "merge" | "keep_separate" | "needs_review" | null;
  applied_decision?: "merge" | "keep_separate" | null;
  error_code?: string | null;
  latency_ms?: number | null;
  trace_id?: string | null;
  attempt?: number;
  timeout_seconds?: number | null;
  http_status?: number | null;
  evidence?: Evidence[];
};

type CandidatePage = {
  manuscript_version_id: string | null;
  items: Candidate[];
  total: number;
  remaining: number;
  review_count: number;
  applied_count: number;
  successful_count?: number;
  error_count?: number;
  request_timeout_seconds?: number;
  candidate_limit_reached: boolean;
  auto_apply: boolean;
  model: string;
  pipeline?: "gemma" | "coreference_gemma";
  coreference_merge_count?: number;
  gemma_comparison_count?: number;
  job: {
    id: string;
    status: string;
    stage: string | null;
    completed: number | null;
    total: number | null;
    error_message_safe: string | null;
    current_stage_elapsed_ms?: number | null;
  } | null;
};

export function EntityResolutionPanel({
  projectId,
  onEvidence,
}: {
  projectId: string;
  onEvidence: (evidence: Evidence) => void;
}) {
  const queryClient = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState("");
  const candidates = useQuery({
    queryKey: ["entity-resolution", projectId, offset],
    queryFn: () =>
      api<CandidatePage>(
        `/projects/${projectId}/entity-resolution/candidates?offset=${offset}&limit=20`,
      ),
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.job?.status ?? "")
        ? 1500
        : false,
  });
  const data = candidates.data;
  const busy = ["queued", "running"].includes(data?.job?.status ?? "");
  useEffect(() => {
    if (
      (data?.applied_count ?? 0) > 0 ||
      ["completed", "failed", "cancelled"].includes(data?.job?.status ?? "")
    ) {
      void queryClient.invalidateQueries({
        queryKey: ["story-bible", projectId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["characters", projectId],
      });
      void queryClient.invalidateQueries({ queryKey: ["entity", projectId] });
    }
  }, [data?.job?.status, data?.applied_count, projectId, queryClient]);
  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["entity-resolution", projectId],
      }),
      queryClient.invalidateQueries({ queryKey: ["story-bible", projectId] }),
      queryClient.invalidateQueries({ queryKey: ["entity", projectId] }),
      queryClient.invalidateQueries({ queryKey: ["characters", projectId] }),
    ]);
  }
  async function start() {
    setStarting(true);
    setError("");
    try {
      await api(`/projects/${projectId}/entity-resolution/run`, {
        method: "POST",
        body: JSON.stringify({
          manuscript_version_id: data?.manuscript_version_id,
        }),
      });
      await refresh();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setStarting(false);
    }
  }
  async function stop() {
    if (!data?.job) return;
    setStopping(true);
    setError("");
    try {
      await api(
        `/projects/${projectId}/entity-resolution/jobs/${data.job.id}/stop`,
        {
          method: "POST",
          body: JSON.stringify({
            manuscript_version_id: data.manuscript_version_id,
          }),
        },
      );
      await refresh();
    } catch (reason) {
      setError(errorMessage(reason));
      await refresh();
    } finally {
      setStopping(false);
    }
  }
  if (candidates.isLoading)
    return <LoadingState label="Checking entity matches…" />;
  if (candidates.error)
    return (
      <ErrorState error={candidates.error} retry={() => candidates.refetch()} />
    );
  if (!data) return null;
  return (
    <section className="mb-6" aria-label="Entity resolution">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="page-title text-xl font-semibold">Entity resolution</h2>
        <Button
          disabled={
            starting ||
            stopping ||
            busy ||
            !data.manuscript_version_id ||
            (data.job?.status === "completed" && data.remaining === 0)
          }
          onClick={start}
        >
          {busy
            ? "Resolving entities…"
            : data.job
              ? "Resume resolution"
              : "Resolve entities"}
        </Button>
        {busy && (
          <Button variant="secondary" disabled={stopping} onClick={stop}>
            {stopping ? "Stopping…" : "Stop resolution"}
          </Button>
        )}
      </div>
      <p className="mt-2 text-sm font-semibold">
        Automatic merging: {data.auto_apply ? "ON" : "OFF"}
      </p>
      <p className="mt-1 text-sm text-muted">
        {data.pipeline === "coreference_gemma"
          ? `xCoRe + ${data.model}`
          : data.model}{" "}
        ·{" "}
        {data.auto_apply
          ? "Validated merge and keep-separate decisions are applied immediately. Applied pairs leave this list, and the character list updates as processing continues. Only uncertain or conflicting cases need review; technical failures are shown separately."
          : "Review mode: every merge or keep-separate decision requires your confirmation."}
      </p>
      {data.pipeline === "coreference_gemma" && (
        <p className="mt-2 text-sm">
          {data.coreference_merge_count ?? 0} merges applied without Gemma;{" "}
          {data.gemma_comparison_count ?? 0} pairs sent to Gemma. Coreference
          links can be wrong; they are not a certainty score.
        </p>
      )}
      {busy && data.job?.stage === "coreference" && (
        <p className="mt-2 text-sm">
          Preparing coreference groups…{" "}
          {Math.floor((data.job.current_stage_elapsed_ms ?? 0) / 1000)}s
          elapsed. Loading and scanning can take more than a minute. Completed
          groups are cached for Resume; Stop discards an unfinished scan.
        </p>
      )}
      <p className="mt-1 text-sm text-muted">
        Candidate pairs are comparisons, not confirmed matches. You do not need
        to decide pairs marked Not evaluated while the model is processing them.
      </p>
      {!data.manuscript_version_id && (
        <p className="mt-2 text-sm">Upload and process a manuscript first.</p>
      )}
      {data.job && (
        <p className="mt-2 text-sm" role="status">
          Resolution{" "}
          {data.job.status === "cancelled" ? "stopped" : data.job.status}:{" "}
          {data.job.completed ?? 0}/{data.job.total ?? 0} comparisons processed.{" "}
          {data.successful_count ?? 0} successful; {data.error_count ?? 0}{" "}
          technical failures; {data.review_count} awaiting review;{" "}
          {data.applied_count} decisions applied.
        </p>
      )}
      {busy && (
        <p className="mt-2 text-sm">
          Resolution continues automatically until the current candidate list is
          processed or you press Stop. You can leave this page while it runs.
        </p>
      )}
      <p className="mt-2 text-sm text-muted">
        Each model request can take up to {data.request_timeout_seconds ?? 180}{" "}
        seconds; one correction request may follow. A failed comparison does not
        stop the others. Temporary failures get one retry after untouched pairs;
        failures that remain are shown separately and are not merged.
      </p>
      {busy && (
        <p className="mt-1 text-sm text-muted">
          Stop preserves saved decisions and discards the active comparison’s
          late result. The model server may briefly finish its current request.
        </p>
      )}
      {data.candidate_limit_reached && (
        <p className="mt-2 text-sm">
          Candidate limit reached; coverage is incomplete. This run does not
          establish that all aliases were found.
        </p>
      )}
      {(error || data.job?.error_message_safe) && (
        <p className="mt-2 text-sm text-[var(--danger)]" role="alert">
          {error || data.job?.error_message_safe}
        </p>
      )}
      <div className="mt-3 space-y-3">
        {data.items.map((candidate) => (
          <EntityResolutionCard
            key={candidate.id}
            projectId={projectId}
            candidate={candidate}
            onResolved={() => {
              setOffset(0);
              void refresh();
            }}
            onEvidence={onEvidence}
          />
        ))}
      </div>
      {data.total > 20 && (
        <div className="mt-3 flex items-center gap-3">
          <Button
            variant="secondary"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - 20))}
          >
            Previous candidates
          </Button>
          <span className="text-sm">
            {offset + 1}–{Math.min(offset + 20, data.total)} of {data.total}
          </span>
          <Button
            variant="secondary"
            disabled={offset + 20 >= data.total}
            onClick={() => setOffset(offset + 20)}
          >
            Next candidates
          </Button>
        </div>
      )}
    </section>
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
          <p className="text-xs text-muted">
            {candidate.left.type ?? "Entity"} · {candidate.left.id}
          </p>
        </div>
        <span className="text-muted">↔</span>
        <div className="flex-1">
          <p className="font-semibold">{candidate.right.name}</p>
          <p className="text-xs text-muted">
            {candidate.right.type ?? "Entity"} · {candidate.right.id}
          </p>
        </div>
        <Badge tone="warn">
          {candidate.error_code && candidate.error_code !== "CLUSTER_CONFLICT"
            ? "Comparison failed"
            : candidate.llm_decision
              ? candidate.error_code === "CLUSTER_CONFLICT"
                ? "Blocked by conflicting decision"
                : candidate.llm_decision === "needs_review"
                  ? "Needs review"
                  : `Suggested ${candidate.llm_decision.replaceAll("_", " ")} — not applied`
              : "Not evaluated"}
        </Badge>
      </div>
      {candidate.error_code && (
        <p className="mt-2 text-sm text-muted">
          {candidate.error_code === "MODEL_TIMEOUT"
            ? `The model request timed out${candidate.timeout_seconds ? ` (limit ${candidate.timeout_seconds}s)` : ""}. It can be retried.`
            : candidate.error_code === "MODEL_CONNECTION_ERROR"
              ? "Could not connect to the model service. It can be retried."
              : candidate.error_code === "MODEL_RATE_LIMITED"
                ? "The model service rate-limited this request. It can be retried."
                : candidate.error_code === "MODEL_SERVER_ERROR"
                  ? "The model service returned a server error. It can be retried."
                  : candidate.error_code === "MODEL_REQUEST_REJECTED"
                    ? "The model service rejected the request. Check the model configuration."
                    : candidate.error_code === "INVALID_MODEL_OUTPUT"
                      ? "The model answer failed JSON or evidence validation after one correction. No identity decision was accepted."
                      : candidate.error_code === "CLUSTER_CONFLICT"
                        ? "This decision conflicts with an existing identity decision. Review the evidence."
                        : "An earlier model request failed without a specific recorded cause. Resume can retry it."}
          {candidate.http_status ? ` HTTP ${candidate.http_status}.` : ""}
          {candidate.latency_ms != null
            ? ` Elapsed: ${(candidate.latency_ms / 1000).toFixed(1)}s.`
            : ""}
          {candidate.attempt ? ` Attempt ${candidate.attempt}.` : ""} No
          automatic merge was applied to this pair.
        </p>
      )}
      {candidate.trace_id && (
        <p className="mt-1 break-all text-xs text-muted">
          Trace ID: {candidate.trace_id}
        </p>
      )}
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
        {candidate.evidence?.map((evidence, index) => (
          <Button
            key={evidence.id}
            variant="ghost"
            onClick={() => onEvidence(evidence)}
          >
            Review evidence {index + 1}
          </Button>
        ))}
      </div>
    </Card>
  );
}
