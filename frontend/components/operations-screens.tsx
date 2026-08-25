"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  Beaker,
  CircleDollarSign,
  Code2,
  FileCheck2,
  FileUp,
  FlaskConical,
  Gauge,
  History,
  LoaderCircle,
  Play,
  Save,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  Badge,
  Button,
  ButtonLink,
  Card,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  PageHeader,
  SuccessNote,
  inputClass,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useEndpoint, useProject, useProjectUpdate } from "@/lib/hooks";

type Job = {
  id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  stage?: string;
  completed?: number;
  total?: number;
  progress?: { completed?: number; total?: number };
  error?: string;
  error_message_safe?: string;
};
type ManuscriptVersion = {
  id: string;
  version?: string;
  version_number?: number;
  status?: string;
  original_filename?: string;
  file_size?: number;
  pipeline_version?: string;
  created_at?: string;
  ready_at?: string;
};
type AnalysisRun = {
  id?: string;
  analysis_run_id?: string;
  status?: string;
  created_at?: string;
  manuscript_version?: string;
  completed_chapters?: number;
  total_chapters?: number;
  claims_extracted?: number;
  potential_conflicts?: number;
  verified_issues?: number;
  duration?: string;
  estimated_cost?: number;
  pipeline_version?: string;
  model?: string;
  retrieval_strategy?: string;
  job_id?: string;
};
type CheckResult = {
  status?: string;
  summary?: string;
  issues?: {
    id?: string;
    title?: string;
    description?: string;
    severity?: string;
    evidence?: { id: string; chapter?: string; text?: string }[];
  }[];
};

function listOf<T>(data: T[] | { items?: T[] } | undefined) {
  return Array.isArray(data) ? data : (data?.items ?? []);
}

export function VersionsScreen({ projectId }: { projectId: string }) {
  const welcome = useSearchParams().get("welcome") === "1";
  const project = useProject(projectId);
  const versions = useEndpoint<
    ManuscriptVersion[] | { items?: ManuscriptVersion[] }
  >(["versions", projectId], `/projects/${projectId}/manuscripts`);
  const [file, setFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState("");
  const [jobId, setJobId] = useState("");
  const job = useQuery<Job>({
    queryKey: ["job", jobId],
    queryFn: () => api(`/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.status ?? "")
        ? 2000
        : false,
  });
  const refetchVersions = versions.refetch;
  const refetchProject = project.refetch;

  useEffect(() => {
    if (["completed", "failed"].includes(job.data?.status ?? "")) {
      void Promise.all([refetchVersions(), refetchProject()]);
    }
  }, [job.data?.status, refetchProject, refetchVersions]);

  function upload(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setUploadError("");
    setUploadProgress(0);
    const form = new FormData();
    form.set("file", file);
    const request = new XMLHttpRequest();
    request.open("POST", `/api/projects/${projectId}/manuscripts`);
    request.upload.onprogress = (progress) => {
      if (progress.lengthComputable)
        setUploadProgress(Math.round((progress.loaded / progress.total) * 100));
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        const result = JSON.parse(request.responseText);
        setJobId(result.job_id ?? "");
        setUploadProgress(100);
        void versions.refetch();
      } else {
        const body = (() => {
          try {
            return JSON.parse(request.responseText);
          } catch {
            return null;
          }
        })();
        setUploadError(
          request.status === 404
            ? "The manuscript upload endpoint is not implemented yet."
            : (body?.error?.message ??
                body?.detail ??
                `Upload failed (${request.status})`),
        );
        setUploadProgress(null);
      }
    };
    request.onerror = () => {
      setUploadError("Could not reach the manuscript upload endpoint.");
      setUploadProgress(null);
    };
    request.send(form);
  }
  const items = listOf(versions.data);
  const activeCompleted =
    job.data?.progress?.completed ?? job.data?.completed ?? 0;
  const activeTotal = job.data?.progress?.total ?? job.data?.total ?? 0;
  return (
    <>
      <PageHeader
        eyebrow="Manuscript lifecycle"
        title={
          welcome
            ? "Your story is ready for a manuscript"
            : "Manuscript Versions"
        }
        description="Uploading a new version parses its chapters and rebuilds the manuscript search index. The previous ready version stays current until processing succeeds."
      />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Card className="p-6">
          <h2 className="page-title text-xl font-semibold">Version history</h2>
          {versions.isLoading && <LoadingState />}
          {versions.error && (
            <ErrorState
              error={versions.error}
              retry={() => versions.refetch()}
            />
          )}
          {!versions.isLoading && !versions.error && !items.length && (
            <EmptyState
              title="No manuscript versions"
              description="Upload a .docx, .md, or .txt file to create version 1."
            />
          )}
          {items.map((version, index) => (
            <article
              key={version.id}
              className="mt-4 flex flex-wrap items-center gap-4 rounded-xl border border-[var(--line)] p-4"
            >
              <span className="grid size-12 place-items-center rounded-xl bg-[var(--brand-soft)] font-serif text-lg font-bold text-[var(--brand)]">
                v{version.version_number ?? items.length - index}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex gap-2">
                  <h3 className="font-semibold">
                    {version.original_filename ??
                      version.version ??
                      "Manuscript"}
                  </h3>
                  {version.id ===
                    project.data?.current_manuscript_version_id && (
                    <Badge tone="good">Current</Badge>
                  )}
                </div>
                <p className="mt-1 text-xs text-muted">
                  {version.created_at
                    ? new Date(version.created_at).toLocaleString()
                    : "Upload date unavailable"}{" "}
                  · {version.pipeline_version ?? "pipeline —"}
                </p>
              </div>
              <Badge>{version.status ?? "unknown"}</Badge>
              <Button variant="ghost" disabled aria-label="Delete old version">
                <Trash2 className="size-4" />
              </Button>
            </article>
          ))}
        </Card>
        <Card className="h-fit p-6">
          <h2 className="page-title text-xl font-semibold">
            Upload new version
          </h2>
          <form className="mt-5" onSubmit={upload}>
            <label className="grid min-h-44 cursor-pointer place-items-center rounded-xl border-2 border-dashed border-[#b9c9c3] bg-[#fafbf9] p-5 text-center hover:border-[var(--brand)]">
              <input
                className="sr-only"
                type="file"
                accept=".docx,.md,.txt"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              <span>
                <FileUp className="mx-auto size-8 text-[var(--brand)]" />
                <strong className="mt-3 block text-sm">
                  {file ? file.name : "Choose or drop a manuscript"}
                </strong>
                <span className="mt-1 block text-xs text-muted">
                  .docx, .md, or .txt
                </span>
              </span>
            </label>
            {uploadProgress !== null && (
              <div
                className="mt-4"
                role="progressbar"
                aria-valuenow={uploadProgress}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div className="h-2 overflow-hidden rounded bg-[#e7ebe8]">
                  <div
                    className="h-full bg-[var(--brand)] transition-all"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-muted">
                  Uploading · {uploadProgress}%
                </p>
              </div>
            )}
            {uploadError && (
              <p className="mt-3 text-sm text-[var(--danger)]" role="alert">
                {uploadError}
              </p>
            )}
            <Button
              className="mt-4 w-full"
              disabled={
                !file || (uploadProgress !== null && uploadProgress < 100)
              }
            >
              <FileUp className="size-4" />
              Upload manuscript
            </Button>
          </form>
          {job.data && (
            <div className="mt-5 border-t border-[var(--line)] pt-5">
              <div className="flex items-center justify-between">
                <Badge
                  tone={
                    job.data.status === "failed"
                      ? "danger"
                      : job.data.status === "completed"
                        ? "good"
                        : "info"
                  }
                >
                  {job.data.status}
                </Badge>
                {activeTotal > 0 && (
                  <span className="text-xs text-muted">
                    {activeCompleted} / {activeTotal}
                  </span>
                )}
              </div>
              <p className="mt-3 text-sm font-semibold">
                {job.data.stage?.replaceAll("_", " ") ?? "Waiting for worker"}
              </p>
              {job.data.status === "failed" && (
                <p className="mt-2 text-sm text-[var(--danger)]">
                  {job.data.error_message_safe ??
                    job.data.error ??
                    "Processing failed."}
                </p>
              )}
            </div>
          )}
          {job.error && (
            <div className="mt-4">
              <ErrorState error={job.error} retry={() => job.refetch()} />
            </div>
          )}
        </Card>
      </div>
    </>
  );
}

export function AnalysisScreen({ projectId }: { projectId: string }) {
  const runs = useEndpoint<AnalysisRun[] | { items?: AnalysisRun[] }>(
    ["analysis", projectId],
    `/projects/${projectId}/analysis`,
  );
  const [jobId, setJobId] = useState("");
  const start = useMutation({
    mutationFn: () =>
      api<AnalysisRun>(`/projects/${projectId}/analysis/continuity`, {
        method: "POST",
        body: "{}",
      }),
    onSuccess: (result) => setJobId(result.job_id ?? ""),
  });
  const job = useQuery<Job>({
    queryKey: ["job", jobId],
    queryFn: () => api(`/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.status ?? "")
        ? 2000
        : false,
  });
  const items = listOf(runs.data);
  const latest = items[0];
  const metrics: [string, string | number, LucideIcon][] = latest
    ? [
        [
          "Chapters",
          `${latest.completed_chapters ?? "—"} / ${latest.total_chapters ?? "—"}`,
          FileCheck2,
        ],
        ["Claims", latest.claims_extracted ?? "—", FileCheck2],
        ["Potential conflicts", latest.potential_conflicts ?? "—", Activity],
        ["Verified issues", latest.verified_issues ?? "—", ShieldCheck],
        [
          "Estimated cost",
          latest.estimated_cost !== undefined
            ? `$${latest.estimated_cost}`
            : "—",
          CircleDollarSign,
        ],
      ]
    : [];
  return (
    <>
      <PageHeader
        eyebrow="Pipeline"
        title="Analysis"
        description="Current and historical runs stay scoped to their manuscript version."
        actions={
          <Button onClick={() => start.mutate()} disabled={start.isPending}>
            <Play className="size-4" />
            {start.isPending ? "Starting…" : "Run analysis"}
          </Button>
        }
      />
      {start.error && (
        <Card className="mb-5">
          <ErrorState error={start.error} />
        </Card>
      )}
      {job.data && (
        <Card className="mb-5 p-5">
          <div className="flex items-center gap-3">
            <LoaderCircle
              className={`size-5 ${["queued", "running"].includes(job.data.status) ? "animate-spin" : ""}`}
            />
            <div>
              <p className="font-semibold capitalize">
                {job.data.stage?.replaceAll("_", " ") ?? job.data.status}
              </p>
              <p className="text-xs text-muted">Job {job.data.id}</p>
            </div>
          </div>
        </Card>
      )}{" "}
      {runs.isLoading && <LoadingState label="Loading analysis history…" />}
      {runs.error && (
        <Card>
          <ErrorState error={runs.error} retry={() => runs.refetch()} />
        </Card>
      )}
      {!runs.isLoading && !runs.error && !latest && (
        <Card>
          <EmptyState
            title="No analysis has been run"
            description="Analysis results will include real pipeline status, metrics, cost, and version metadata."
          />
        </Card>
      )}
      {latest && (
        <>
          <Card className="p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <Badge
                  tone={
                    latest.status === "completed"
                      ? "good"
                      : latest.status === "failed"
                        ? "danger"
                        : "info"
                  }
                >
                  {latest.status ?? "unknown"}
                </Badge>
                <h2 className="page-title mt-3 text-2xl font-semibold">
                  Latest analysis
                </h2>
              </div>
              <p className="text-sm text-muted">
                {latest.created_at
                  ? new Date(latest.created_at).toLocaleString()
                  : "Date unavailable"}
              </p>
            </div>
            <div className="mt-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
              {metrics.map(([label, value, Icon]) => (
                <div
                  key={label}
                  className="rounded-xl border border-[var(--line)] p-4"
                >
                  <Icon className="size-5 text-[var(--brand)]" />
                  <p className="mt-4 text-xs text-muted">{label}</p>
                  <p className="mt-1 text-xl font-semibold">{String(value)}</p>
                </div>
              ))}
            </div>
            <dl className="mt-7 grid gap-3 border-t border-[var(--line)] pt-5 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-muted">Manuscript version</dt>
                <dd className="font-semibold">
                  {latest.manuscript_version ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="text-muted">Pipeline version</dt>
                <dd className="font-semibold">
                  {latest.pipeline_version ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="text-muted">Model</dt>
                <dd className="font-semibold">{latest.model ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-muted">Retrieval</dt>
                <dd className="font-semibold">
                  {latest.retrieval_strategy ?? "—"}
                </dd>
              </div>
            </dl>
          </Card>
          <Card className="mt-5 p-6">
            <h2 className="page-title text-xl font-semibold">History</h2>
            <div className="mt-4 divide-y divide-[var(--line)]">
              {items.map((run, index) => (
                <article
                  key={run.id ?? run.analysis_run_id ?? index}
                  className="flex items-center gap-4 py-4"
                >
                  <History className="size-4 text-muted" />
                  <div className="flex-1">
                    <p className="font-semibold">
                      {run.manuscript_version ?? `Run ${items.length - index}`}
                    </p>
                    <p className="text-xs text-muted">
                      {run.created_at ?? "Date unavailable"}
                    </p>
                  </div>
                  <Badge tone={run.status === "completed" ? "good" : "neutral"}>
                    {run.status ?? "unknown"}
                  </Badge>
                  <span className="text-sm">
                    {run.verified_issues ?? "—"} issues
                  </span>
                </article>
              ))}
            </div>
          </Card>
        </>
      )}
    </>
  );
}

const settingsSchema = z.object({
  title: z.string().trim().min(1),
  description: z.string(),
  language: z.string().trim().min(1).max(16),
});
type SettingsValues = z.infer<typeof settingsSchema>;

export function SettingsScreen({ projectId }: { projectId: string }) {
  const project = useProject(projectId);
  const update = useProjectUpdate(projectId);
  const [saved, setSaved] = useState(false);
  const [developer, setDeveloper] = useState(
    () =>
      typeof window !== "undefined" &&
      localStorage.getItem("storyguard:developer-mode") === "1",
  );
  const form = useForm<SettingsValues>({
    resolver: zodResolver(settingsSchema),
    values: project.data
      ? {
          title: project.data.title,
          description: project.data.description,
          language: project.data.language,
        }
      : undefined,
  });
  function toggle(value: boolean) {
    setDeveloper(value);
    localStorage.setItem("storyguard:developer-mode", value ? "1" : "0");
  }
  async function save(values: SettingsValues) {
    setSaved(false);
    await update.mutateAsync(values);
    setSaved(true);
  }
  return (
    <>
      <PageHeader
        eyebrow="Project"
        title="Settings"
        description="Manage project metadata and local developer UI preferences."
      />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card className="p-6">
          <h2 className="page-title text-xl font-semibold">Story details</h2>
          {project.isLoading && <LoadingState />}
          {project.error && (
            <ErrorState error={project.error} retry={() => project.refetch()} />
          )}
          {project.data && (
            <form onSubmit={form.handleSubmit(save)} className="mt-6 space-y-5">
              <Field label="Title" error={form.formState.errors.title?.message}>
                <input className={inputClass} {...form.register("title")} />
              </Field>
              <Field label="Description">
                <textarea
                  className={inputClass}
                  rows={4}
                  {...form.register("description")}
                />
              </Field>
              <Field
                label="Language"
                hint="Language catalog endpoint is not available; enter a BCP 47 code."
              >
                <input className={inputClass} {...form.register("language")} />
              </Field>
              {update.error && (
                <p className="text-sm text-[var(--danger)]">
                  {errorMessage(update.error)}
                </p>
              )}
              {saved && <SuccessNote>Project settings saved.</SuccessNote>}
              <Button disabled={update.isPending}>
                <Save className="size-4" />
                {update.isPending ? "Saving…" : "Save changes"}
              </Button>
            </form>
          )}
        </Card>
        <Card className="h-fit p-6">
          <h2 className="page-title text-xl font-semibold">Developer Mode</h2>
          <p className="mt-2 text-sm leading-6 text-muted">
            Shows safe execution metadata such as routing, retrieval, latency,
            cost, and verification. Hidden chain-of-thought is never displayed.
          </p>
          <label className="mt-5 flex cursor-pointer items-center justify-between gap-4">
            <span className="text-sm font-semibold">
              Enable on this browser
            </span>
            <input
              type="checkbox"
              checked={developer}
              onChange={(event) => toggle(event.target.checked)}
              className="size-5 accent-[var(--brand)]"
            />
          </label>
          {developer && (
            <ButtonLink
              href={`/projects/${projectId}/developer`}
              className="mt-5 w-full"
              variant="secondary"
            >
              <Code2 className="size-4" />
              Open developer tools
            </ButtonLink>
          )}
        </Card>
      </div>
    </>
  );
}

export function CheckTextScreen({ projectId }: { projectId: string }) {
  const [text, setText] = useState("");
  const check = useMutation({
    mutationFn: () =>
      api<CheckResult>(`/projects/${projectId}/check-text`, {
        method: "POST",
        body: JSON.stringify({ text }),
      }),
  });
  return (
    <>
      <PageHeader
        eyebrow="Advanced"
        title="Check New Text"
        description="Compare a passage against established manuscript facts without adding it to the manuscript."
      />
      <div className="grid gap-5 xl:grid-cols-2">
        <Card className="p-6">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              check.mutate();
            }}
          >
            <label className="text-sm font-semibold" htmlFor="new-text">
              Paste new text
            </label>
            <textarea
              id="new-text"
              value={text}
              onChange={(event) => setText(event.target.value)}
              className={`${inputClass} mt-3 min-h-72 font-serif leading-7`}
              placeholder="Daniel stepped onto French soil for the first time…"
            />
            <Button className="mt-4" disabled={!text.trim() || check.isPending}>
              <FileCheck2 className="size-4" />
              {check.isPending ? "Checking…" : "Check against story"}
            </Button>
          </form>
        </Card>
        <Card className="p-6">
          <h2 className="page-title text-xl font-semibold">Result</h2>
          {!check.data && !check.error && !check.isPending && (
            <EmptyState
              title="No passage checked"
              description="Results will identify possible issues and show supporting manuscript evidence."
            />
          )}
          {check.isPending && (
            <LoadingState label="Searching and verifying evidence…" />
          )}
          {check.error && (
            <ErrorState error={check.error} retry={() => check.mutate()} />
          )}
          {check.data && (
            <div className="mt-5 space-y-3">
              <Badge tone={check.data.issues?.length ? "warn" : "good"}>
                {check.data.status ??
                  (check.data.issues?.length
                    ? "Possible issue"
                    : "No issue found")}
              </Badge>
              {check.data.summary && (
                <p className="text-sm leading-6">{check.data.summary}</p>
              )}
              {check.data.issues?.map((issue, index) => (
                <article
                  key={issue.id ?? index}
                  className="rounded-xl border border-[var(--line)] bg-[#fafbf9] p-4"
                >
                  <Badge tone="warn">{issue.severity ?? "Possible"}</Badge>
                  <h3 className="mt-3 font-semibold">
                    {issue.title ?? "Possible continuity issue"}
                  </h3>
                  <p className="mt-2 text-sm leading-6 text-muted">
                    {issue.description}
                  </p>
                  {issue.evidence?.map((source) => (
                    <blockquote
                      key={source.id}
                      className="mt-3 border-l-2 border-[var(--amber)] pl-3 font-serif text-sm"
                    >
                      {source.chapter && <strong>{source.chapter}: </strong>}
                      {source.text}
                    </blockquote>
                  ))}
                </article>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}

export function DeveloperScreen({ projectId }: { projectId: string }) {
  return (
    <>
      <PageHeader
        eyebrow="Internal tools"
        title="Developer Mode"
        description="Inspect safe AI workflow metadata without exposing hidden reasoning or provider secrets."
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <Link href={`/projects/${projectId}/developer/experiments`}>
          <Card className="h-full p-6 transition hover:shadow-md">
            <FlaskConical className="size-7 text-[var(--brand)]" />
            <h2 className="page-title mt-5 text-2xl font-semibold">
              AI Experiment Lab
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted">
              Compare controlled baseline and candidate configurations, then
              inspect failures.
            </p>
            <span className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-[var(--brand)]">
              Open lab <ArrowRight className="size-4" />
            </span>
          </Card>
        </Link>
        <Card className="p-6">
          <Gauge className="size-7 text-[var(--brand)]" />
          <h2 className="page-title mt-5 text-2xl font-semibold">
            Execution metadata
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted">
            Chat answers show intent, complexity, retrieval strategy, model
            alias, latency, cost, and verification when supplied by the backend.
          </p>
        </Card>
      </div>
    </>
  );
}

type ExperimentConfig = {
  id: string;
  name?: string;
  version?: string;
  [key: string]: unknown;
};
type Experiment = {
  id: string;
  status?: string;
  baseline?: string;
  candidate?: string;
  created_at?: string;
  metrics?: Record<string, { baseline?: number; candidate?: number }>;
};
type ExperimentFailure = {
  id: string;
  type?: string;
  question?: string;
  summary?: string;
  baseline_output?: string;
  candidate_output?: string;
  trace_id?: string;
};

export function ExperimentLabScreen() {
  const datasets = useEndpoint<
    ExperimentConfig[] | { items?: ExperimentConfig[] }
  >(["developer", "datasets"], "/developer/datasets");
  const configs = useEndpoint<
    ExperimentConfig[] | { items?: ExperimentConfig[] }
  >(["developer", "configs"], "/developer/experiment-configs");
  const experiments = useEndpoint<Experiment[] | { items?: Experiment[] }>(
    ["developer", "experiments"],
    "/developer/experiments",
  );
  const [dataset, setDataset] = useState("");
  const [baseline, setBaseline] = useState("");
  const [candidate, setCandidate] = useState("");
  const [failureType, setFailureType] = useState("");
  const run = useMutation({
    mutationFn: () =>
      api<Experiment>("/developer/experiments", {
        method: "POST",
        body: JSON.stringify({
          dataset_id: dataset,
          baseline_config_id: baseline,
          candidate_config_id: candidate,
        }),
      }),
    onSuccess: () => void experiments.refetch(),
  });
  const datasetItems = listOf(datasets.data);
  const configItems = listOf(configs.data);
  const history = listOf(experiments.data);
  const latest = history[0];
  const failures = useEndpoint<
    ExperimentFailure[] | { items?: ExperimentFailure[] }
  >(
    ["developer", "experiment-failures", latest?.id],
    `/developer/experiments/${latest?.id ?? "pending"}/failures`,
    !!latest,
  );
  const failureItems = listOf(failures.data);
  const visibleFailures = failureItems.filter(
    (failure) => !failureType || failure.type === failureType,
  );
  const failureTypes = [
    ...new Set(failureItems.map((failure) => failure.type).filter(Boolean)),
  ] as string[];
  const baselineConfig = configItems.find((item) => item.id === baseline);
  const candidateConfig = configItems.find((item) => item.id === candidate);
  return (
    <>
      <PageHeader
        eyebrow="Developer Mode"
        title="AI Experiment Lab"
        description="Run controlled, reproducible comparisons. Candidate promotion always remains an explicit developer decision."
      />
      <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
        <Card className="h-fit p-6">
          <h2 className="page-title text-xl font-semibold">Configuration</h2>
          {datasets.error || configs.error ? (
            <ErrorState
              error={datasets.error ?? configs.error}
              retry={() => {
                void datasets.refetch();
                void configs.refetch();
              }}
            />
          ) : datasets.isLoading || configs.isLoading ? (
            <LoadingState />
          ) : (
            <div className="mt-5 space-y-4">
              <label className="block text-sm font-semibold">
                Dataset
                <select
                  className={`${inputClass} mt-2`}
                  value={dataset}
                  onChange={(event) => setDataset(event.target.value)}
                >
                  <option value="">Select dataset</option>
                  {datasetItems.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name ?? item.id}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm font-semibold">
                Baseline
                <select
                  className={`${inputClass} mt-2`}
                  value={baseline}
                  onChange={(event) => setBaseline(event.target.value)}
                >
                  <option value="">Select baseline</option>
                  {configItems.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name ?? item.id}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm font-semibold">
                Candidate
                <select
                  className={`${inputClass} mt-2`}
                  value={candidate}
                  onChange={(event) => setCandidate(event.target.value)}
                >
                  <option value="">Select candidate</option>
                  {configItems.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name ?? item.id}
                    </option>
                  ))}
                </select>
              </label>
              {(baselineConfig || candidateConfig) && (
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                  {[
                    ["Baseline", baselineConfig],
                    ["Candidate", candidateConfig],
                  ].map(
                    ([label, config]) =>
                      config && (
                        <div
                          key={label as string}
                          className="rounded-xl bg-[#f5f7f5] p-3"
                        >
                          <p className="text-xs font-bold uppercase tracking-wider text-muted">
                            {label as string} controls
                          </p>
                          <dl className="mt-2 space-y-1 text-xs">
                            {Object.entries(config as ExperimentConfig)
                              .filter(
                                ([key, value]) =>
                                  !["id", "name"].includes(key) &&
                                  value !== null &&
                                  typeof value !== "object",
                              )
                              .map(([key, value]) => (
                                <div
                                  key={key}
                                  className="flex justify-between gap-3"
                                >
                                  <dt className="text-muted">
                                    {key.replaceAll("_", " ")}
                                  </dt>
                                  <dd className="text-right font-semibold">
                                    {String(value)}
                                  </dd>
                                </div>
                              ))}
                          </dl>
                        </div>
                      ),
                  )}
                </div>
              )}
              <Button
                className="w-full"
                disabled={!dataset || !baseline || !candidate || run.isPending}
                onClick={() => run.mutate()}
              >
                <Beaker className="size-4" />
                {run.isPending ? "Queueing…" : "Run experiment"}
              </Button>
              {run.error && (
                <p className="text-sm text-[var(--danger)]">
                  {errorMessage(run.error)}
                </p>
              )}
            </div>
          )}
        </Card>
        <div className="space-y-5">
          <Card className="p-6">
            <h2 className="page-title text-xl font-semibold">
              Latest comparison
            </h2>
            {experiments.isLoading && <LoadingState />}
            {experiments.error && (
              <ErrorState
                error={experiments.error}
                retry={() => experiments.refetch()}
              />
            )}
            {!experiments.isLoading && !experiments.error && !latest && (
              <EmptyState
                title="No experiments yet"
                description="Choose server-known configurations to create a real background experiment."
              />
            )}
            {latest && (
              <>
                <div className="mt-3 flex items-center gap-3">
                  <Badge
                    tone={
                      latest.status === "completed"
                        ? "good"
                        : latest.status === "failed"
                          ? "danger"
                          : "info"
                    }
                  >
                    {latest.status ?? "unknown"}
                  </Badge>
                  <span className="text-xs text-muted">{latest.id}</span>
                </div>
                <div className="mt-6 overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-[var(--line)] text-muted">
                        <th className="py-3">Metric</th>
                        <th>Baseline</th>
                        <th>Candidate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(latest.metrics ?? {}).map(
                        ([metric, values]) => (
                          <tr
                            key={metric}
                            className="border-b border-[var(--line)]"
                          >
                            <th className="py-3 font-medium">
                              {metric.replaceAll("_", " ")}
                            </th>
                            <td>{values.baseline ?? "—"}</td>
                            <td>{values.candidate ?? "—"}</td>
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </Card>
          <Card className="p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="page-title text-xl font-semibold">
                  Failure browser
                </h2>
                <p className="mt-2 text-sm text-muted">
                  Inspect retrieval, routing, grounding, citation, continuity,
                  and fallback failures.
                </p>
              </div>
              {!!failureTypes.length && (
                <select
                  aria-label="Failure type"
                  className={`${inputClass} w-auto`}
                  value={failureType}
                  onChange={(event) => setFailureType(event.target.value)}
                >
                  <option value="">All failures</option>
                  {failureTypes.map((type) => (
                    <option key={type}>{type}</option>
                  ))}
                </select>
              )}
            </div>
            {failures.isLoading && <LoadingState label="Loading failures…" />}
            {failures.error && (
              <ErrorState
                error={failures.error}
                retry={() => failures.refetch()}
              />
            )}
            {!failures.isLoading &&
              !failures.error &&
              !visibleFailures.length && (
                <EmptyState
                  title="No failures to inspect"
                  description="Completed experiments expose representative failures here."
                />
              )}
            <div className="mt-4 space-y-3">
              {visibleFailures.map((failure) => (
                <details
                  key={failure.id}
                  className="rounded-xl border border-[var(--line)] p-4"
                >
                  <summary className="cursor-pointer list-none">
                    <div className="flex items-center gap-3">
                      <Badge tone="warn">{failure.type ?? "Failure"}</Badge>
                      <span className="font-semibold">
                        {failure.question ?? failure.summary ?? failure.id}
                      </span>
                    </div>
                  </summary>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-lg bg-[#f5f7f5] p-3 text-sm">
                      <strong>Baseline</strong>
                      <p className="mt-2 whitespace-pre-wrap text-muted">
                        {failure.baseline_output ?? "No output recorded"}
                      </p>
                    </div>
                    <div className="rounded-lg bg-[#f5f7f5] p-3 text-sm">
                      <strong>Candidate</strong>
                      <p className="mt-2 whitespace-pre-wrap text-muted">
                        {failure.candidate_output ?? "No output recorded"}
                      </p>
                    </div>
                  </div>
                  {failure.trace_id && (
                    <p className="mt-3 text-xs text-muted">
                      Safe trace ID: {failure.trace_id}
                    </p>
                  )}
                </details>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
