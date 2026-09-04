"use client";

import {
  AlertTriangle,
  CalendarDays,
  ChevronRight,
  Eye,
  MapPin,
  Play,
  Search,
  ShieldCheck,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useRef, useState } from "react";

import { EvidenceDrawer } from "@/components/evidence-drawer";
import { EntityResolutionPanel } from "@/components/entity-resolution";
import {
  Badge,
  Button,
  ButtonLink,
  Card,
  Dialog,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  inputClass,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useEndpoint, useProject } from "@/lib/hooks";
import type { Evidence } from "@/lib/types";

type Chapter = {
  id: string;
  number?: number;
  title?: string;
  issue_count?: number;
  status?: string;
};
type Paragraph = {
  id: string;
  text: string;
  scene_id?: string;
  evidence_ids?: string[];
};
type ChapterDetail = Chapter & {
  paragraphs?: Paragraph[];
  scenes?: { id: string; title?: string; paragraphs?: Paragraph[] }[];
  text?: string;
};
type Entity = {
  id: string;
  name: string;
  type?: string;
  role?: string;
  aliases?: string[];
  description?: string;
  facts?: Fact[];
  evidence?: Evidence[];
  [key: string]: unknown;
};
type Fact = {
  id?: string;
  subject?: string;
  predicate?: string;
  value?: string;
  confidence?: string;
  source?: string;
  status?: string;
  evidence?: Evidence[];
};
type StoryEvent = {
  id: string;
  type?: string;
  title?: string;
  description?: string;
  chronological_time?: string;
  narrative_position?: string;
  chapter?: string;
  location?: string;
  participants?: string[];
  evidence?: Evidence[];
};
type Issue = {
  id: string;
  title?: string;
  summary?: string;
  description?: string;
  severity?: string;
  type?: string;
  status?: string;
  confidence?: string;
  chapter?: string;
  entity?: string;
  evidence?: Evidence[];
  evidence_a?: Evidence;
  evidence_b?: Evidence;
  reason?: string;
  analysis_run_id?: string;
};

function getList<T>(data: T[] | { items?: T[] } | undefined): T[] {
  return Array.isArray(data) ? data : (data?.items ?? []);
}

function toneFor(
  value?: string,
): "neutral" | "good" | "warn" | "danger" | "info" {
  const normalized = value?.toLowerCase() ?? "";
  if (normalized.includes("likely") || normalized.includes("high"))
    return "danger";
  if (
    normalized.includes("possible") ||
    normalized.includes("review") ||
    normalized.includes("medium")
  )
    return "warn";
  if (
    normalized.includes("active") ||
    normalized.includes("complete") ||
    normalized.includes("valid")
  )
    return "good";
  return "neutral";
}

export function OverviewScreen({ projectId }: { projectId: string }) {
  const project = useProject(projectId);
  const characters = useEndpoint<Entity[]>(
    ["characters", projectId],
    `/projects/${projectId}/characters`,
  );
  const locations = useEndpoint<Entity[]>(
    ["locations", projectId],
    `/projects/${projectId}/locations`,
  );
  const events = useEndpoint<StoryEvent[]>(
    ["events", projectId],
    `/projects/${projectId}/events`,
  );
  const issues = useEndpoint<Issue[]>(
    ["issues", projectId],
    `/projects/${projectId}/issues`,
  );
  const analysis = useEndpoint<
    { items?: Record<string, unknown>[] } | Record<string, unknown>[]
  >(["analysis", projectId], `/projects/${projectId}/analysis`);
  const metrics = [
    [
      "Characters",
      project.data?.character_count ??
        (characters.data ? getList(characters.data).length : undefined),
      Users,
      "/story-bible?tab=characters",
    ],
    [
      "Locations",
      locations.data ? getList(locations.data).length : undefined,
      MapPin,
      "/story-bible?tab=locations",
    ],
    [
      "Events",
      events.data ? getList(events.data).length : undefined,
      CalendarDays,
      "/timeline",
    ],
    [
      "Continuity Issues",
      project.data?.issue_count ??
        (issues.data ? getList(issues.data).length : undefined),
      AlertTriangle,
      "/issues",
    ],
  ] as const;
  const issueList = getList(issues.data);
  const likely = issueList.filter(
    (issue) => issue.severity?.toLowerCase() === "likely",
  ).length;
  const possible = issueList.filter(
    (issue) => issue.severity?.toLowerCase() === "possible",
  ).length;
  const runs = getList(analysis.data);
  const latest = runs[0] ?? {};

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title={project.data?.title ?? "Story overview"}
        description={
          project.data?.description ||
          "Your manuscript, story memory, and continuity health at a glance."
        }
        actions={
          <ButtonLink
            href={`/projects/${projectId}/versions`}
            variant="secondary"
          >
            Upload new version
          </ButtonLink>
        }
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map(([label, value, Icon, href]) => (
          <Link key={label} href={`/projects/${projectId}${href}`}>
            <Card className="p-5 transition hover:-translate-y-0.5 hover:shadow-md">
              <div className="flex items-center justify-between">
                <span className="rounded-lg bg-[var(--brand-soft)] p-2 text-[var(--brand)]">
                  <Icon className="size-5" />
                </span>
                <ChevronRight className="size-4 text-muted" />
              </div>
              <p className="mt-5 text-sm text-muted">{label}</p>
              <p className="page-title mt-1 text-3xl font-semibold">
                {value ?? "—"}
              </p>
            </Card>
          </Link>
        ))}
      </div>
      <div className="mt-5 grid gap-5 xl:grid-cols-[1.3fr_1fr]">
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <h2 className="page-title text-xl font-semibold">
              Continuity health
            </h2>
            <ShieldCheck className="size-5 text-[var(--brand)]" />
          </div>
          {issues.isLoading ? (
            <LoadingState label="Loading continuity…" />
          ) : issues.error ? (
            <ErrorState error={issues.error} retry={() => issues.refetch()} />
          ) : issueList.length ? (
            <div className="mt-6 grid gap-6 sm:grid-cols-[160px_1fr]">
              <div className="relative mx-auto grid size-36 place-items-center rounded-full bg-[conic-gradient(var(--danger)_0_20%,var(--amber)_20_52%,#7db7a3_52_100%)]">
                <div className="grid size-24 place-items-center rounded-full bg-white">
                  <ShieldCheck className="size-8 text-[var(--brand)]" />
                </div>
              </div>
              <div className="space-y-4">
                <p>
                  <strong className="text-[var(--danger)]">{likely}</strong>{" "}
                  likely issues
                  <br />
                  <span className="text-sm text-muted">
                    High-confidence contradictions or timeline conflicts.
                  </span>
                </p>
                <p>
                  <strong className="text-[var(--amber)]">{possible}</strong>{" "}
                  possible issues
                  <br />
                  <span className="text-sm text-muted">
                    Potential inconsistencies that need review.
                  </span>
                </p>
                <Link
                  href={`/projects/${projectId}/issues`}
                  className="inline-flex text-sm font-semibold text-[var(--brand)]"
                >
                  View all issues →
                </Link>
              </div>
            </div>
          ) : (
            <EmptyState
              title="No continuity issues"
              description="No issues have been returned for the current manuscript."
            />
          )}
        </Card>
        <Card className="p-6">
          <h2 className="page-title text-xl font-semibold">Analysis status</h2>
          {analysis.isLoading ? (
            <LoadingState label="Loading analysis…" />
          ) : analysis.error ? (
            <ErrorState
              error={analysis.error}
              retry={() => analysis.refetch()}
            />
          ) : runs.length ? (
            <div className="mt-5">
              <Badge tone={toneFor(String(latest.status))}>
                {String(latest.status ?? "Unknown")}
              </Badge>
              <dl className="mt-5 space-y-3 text-sm">
                <div className="flex justify-between">
                  <dt className="text-muted">Chapters</dt>
                  <dd>
                    {String(latest.completed_chapters ?? "—")} /{" "}
                    {String(latest.total_chapters ?? "—")}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted">Duration</dt>
                  <dd>{String(latest.duration ?? "—")}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted">Last run</dt>
                  <dd>{String(latest.created_at ?? "—")}</dd>
                </div>
              </dl>
            </div>
          ) : (
            <EmptyState
              title="No analysis yet"
              description="Run continuity analysis after the manuscript is processed."
            />
          )}
          <ButtonLink
            href={`/projects/${projectId}/analysis`}
            className="mt-5 w-full"
          >
            <Play className="size-4" />
            View analysis
          </ButtonLink>
        </Card>
      </div>
      <Card className="mt-5 p-6">
        <h2 className="page-title text-xl font-semibold">Recent activity</h2>
        <p className="mt-4 text-sm text-muted">
          Activity requires analysis and manuscript history from the backend.
        </p>
      </Card>
    </>
  );
}

export function ManuscriptScreen({ projectId }: { projectId: string }) {
  const query = useSearchParams();
  const router = useRouter();
  const selected = query.get("chapter") ?? "";
  const evidenceId = query.get("evidence") ?? "";
  const [filter, setFilter] = useState("");
  const chapters = useEndpoint<Chapter[] | { items?: Chapter[] }>(
    ["chapters", projectId],
    `/projects/${projectId}/chapters`,
  );
  const detail = useEndpoint<ChapterDetail>(
    ["chapter", projectId, selected],
    `/projects/${projectId}/chapters/${selected}`,
    !!selected,
  );
  const list = getList(chapters.data).filter((chapter) =>
    `${chapter.number ?? ""} ${chapter.title ?? ""}`
      .toLowerCase()
      .includes(filter.toLowerCase()),
  );
  function select(id: string) {
    const next = new URLSearchParams(query.toString());
    next.set("chapter", id);
    next.delete("evidence");
    router.replace(`?${next}`);
  }
  const paragraphs =
    detail.data?.paragraphs ??
    detail.data?.scenes?.flatMap((scene) => scene.paragraphs ?? []) ??
    (detail.data?.text ? [{ id: "chapter-text", text: detail.data.text }] : []);
  return (
    <>
      <PageHeader
        eyebrow="Read-only"
        title="Manuscript"
        description="Inspect parsed chapters and follow evidence back to exact source text."
      />
      <Card className="min-h-[680px] overflow-hidden lg:grid lg:grid-cols-[250px_minmax(0,1fr)]">
        <aside className="border-b border-[var(--line)] bg-[#fafbf9] lg:border-b-0 lg:border-r">
          <div className="border-b border-[var(--line)] p-4">
            <label className="relative block">
              <span className="sr-only">Search chapters</span>
              <Search className="absolute left-3 top-3 size-4 text-muted" />
              <input
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
                className={`${inputClass} pl-9`}
                placeholder="Search chapters…"
              />
            </label>
          </div>
          {chapters.isLoading && <LoadingState label="Loading chapters…" />}
          {chapters.error && (
            <ErrorState
              error={chapters.error}
              retry={() => chapters.refetch()}
            />
          )}
          {!chapters.isLoading && !chapters.error && !list.length && (
            <EmptyState
              title="No chapters"
              description="Upload and process a manuscript to detect chapters."
            />
          )}
          <nav
            className="max-h-[620px] overflow-y-auto p-2"
            aria-label="Chapters"
          >
            {list.map((chapter) => (
              <button
                key={chapter.id}
                onClick={() => select(chapter.id)}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-sm ${selected === chapter.id ? "bg-[var(--brand-soft)] text-[var(--brand)]" : "hover:bg-[#eef1ef]"}`}
              >
                <span className="w-5 text-xs text-muted">{chapter.number}</span>
                <span className="min-w-0 flex-1 truncate font-medium">
                  {chapter.title ?? `Chapter ${chapter.number}`}
                </span>
                {chapter.issue_count ? (
                  <Badge tone="warn">{chapter.issue_count}</Badge>
                ) : null}
              </button>
            ))}
          </nav>
        </aside>
        <article className="min-w-0 p-5 sm:p-8 lg:p-10">
          {!selected && (
            <EmptyState
              title="Select a chapter"
              description="Choose a chapter to inspect the read-only manuscript text."
            />
          )}
          {detail.isLoading && <LoadingState label="Opening chapter…" />}
          {detail.error && (
            <ErrorState error={detail.error} retry={() => detail.refetch()} />
          )}
          {detail.data && (
            <>
              <div className="flex items-center gap-3">
                <h2 className="page-title text-2xl font-semibold">
                  {detail.data.title ?? `Chapter ${detail.data.number}`}
                </h2>
                <Badge>Read-only</Badge>
              </div>
              <div className="mx-auto mt-8 max-w-3xl space-y-5 font-serif text-[17px] leading-8">
                {paragraphs.map((paragraph) => {
                  const highlighted =
                    paragraph.evidence_ids?.includes(evidenceId) ||
                    paragraph.id === evidenceId;
                  return (
                    <p
                      id={paragraph.id}
                      key={paragraph.id}
                      className={
                        highlighted
                          ? "rounded bg-[var(--amber-soft)] px-2 py-1 ring-1 ring-[#efd594]"
                          : ""
                      }
                    >
                      {paragraph.text}
                    </p>
                  );
                })}
              </div>
            </>
          )}
        </article>
      </Card>
    </>
  );
}

const entityTabTypes: Record<string, string> = {
  characters: "character",
  facilities: "facility",
  settlements: "gpe",
  locations: "location",
  organizations: "organization",
  vehicles: "vehicle",
};

const bibleTabs = [
  "characters",
  "facilities",
  "settlements",
  "locations",
  "organizations",
  "vehicles",
  "relationships",
  "facts",
  "events",
] as const;

export function StoryBibleScreen({ projectId }: { projectId: string }) {
  const params = useSearchParams();
  const router = useRouter();
  const tab = bibleTabs.includes(
    params.get("tab") as (typeof bibleTabs)[number],
  )
    ? params.get("tab")!
    : "characters";
  const selected = params.get("selected") ?? "";
  const [search, setSearch] = useState("");
  const [factEntity, setFactEntity] = useState("");
  const [factType, setFactType] = useState("");
  const [factChapter, setFactChapter] = useState("");
  const [factConfidence, setFactConfidence] = useState("");
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const detailPane = useRef<HTMLElement>(null);
  const entityType = entityTabTypes[tab];
  const endpoint = entityType && tab !== "characters" ? `entities?type=${entityType}` : tab;
  const result = useEndpoint<
    Entity[] | Fact[] | StoryEvent[] | { items?: Entity[] }
  >(["story-bible", projectId, tab], `/projects/${projectId}/${endpoint}`);
  const detail = useEndpoint<Entity>(
    ["entity", projectId, tab, selected],
    `/projects/${projectId}/${tab === "characters" ? "characters" : "entities"}/${selected}`,
    !!selected && !!entityType,
  );
  const rawItems = getList(result.data as Entity[] | { items?: Entity[] });
  const items = rawItems.filter((item) => {
    const matchesSearch = String(
      item.name ?? item.subject ?? item.title ?? item.value ?? "",
    )
      .toLowerCase()
      .includes(search.toLowerCase());
    if (tab !== "facts") return matchesSearch;
    return (
      matchesSearch &&
      (!factEntity ||
        String(item.subject ?? item.entity ?? "") === factEntity) &&
      (!factType || String(item.predicate ?? "") === factType) &&
      (!factChapter ||
        String(item.chapter ?? item.source ?? "") === factChapter) &&
      (!factConfidence || String(item.confidence ?? "") === factConfidence)
    );
  });
  const factOptions = (field: string) => [
    ...new Set(
      rawItems.map((item) => String(item[field] ?? "")).filter(Boolean),
    ),
  ];
  function navigate(nextTab: string, id?: string) {
    const next = new URLSearchParams();
    next.set("tab", nextTab);
    if (id) next.set("selected", id);
    router.replace(`?${next}`);
  }
  function selectEntity(id: string) {
    detailPane.current?.scrollTo({ top: 0 });
    navigate(tab, id);
  }
  return (
    <>
      <PageHeader
        eyebrow="Structured memory"
        title="Story Bible"
        description="AI-extracted entities and facts remain traceable to manuscript evidence."
      />
      <Card className="overflow-hidden">
        <div className="flex overflow-x-auto border-b border-[var(--line)] px-3">
          {bibleTabs.map((item) => (
            <button
              key={item}
              onClick={() => navigate(item)}
              className={`whitespace-nowrap border-b-2 px-4 py-4 text-sm font-semibold capitalize ${tab === item ? "border-[var(--brand)] text-[var(--brand)]" : "border-transparent text-muted"}`}
            >
              {item === "settlements" ? "Countries & cities" : item}
            </button>
          ))}
        </div>
        <div className="grid min-h-[600px] lg:h-[calc(100vh-10rem)] lg:grid-cols-[300px_minmax(0,1fr)]">
          <section
            aria-label={`${tab} list`}
            className="border-b border-[var(--line)] bg-[#fafbf9] lg:min-h-0 lg:overflow-y-auto lg:border-b-0 lg:border-r"
          >
            <div className="sticky top-0 z-10 bg-[#fafbf9] p-4">
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className={inputClass}
                placeholder={`Search ${tab}…`}
              />
              {tab === "facts" && (
                <div className="mt-2 grid grid-cols-2 gap-2">
                  {[
                    [
                      "Entity",
                      factEntity,
                      setFactEntity,
                      factOptions("subject"),
                    ],
                    [
                      "Fact type",
                      factType,
                      setFactType,
                      factOptions("predicate"),
                    ],
                    [
                      "Chapter",
                      factChapter,
                      setFactChapter,
                      factOptions("source"),
                    ],
                    [
                      "Confidence",
                      factConfidence,
                      setFactConfidence,
                      factOptions("confidence"),
                    ],
                  ].map(([label, value, setter, options]) => (
                    <label key={label as string} className="text-xs text-muted">
                      {label as string}
                      <select
                        className={`${inputClass} mt-1 px-2 py-2 text-xs`}
                        value={value as string}
                        onChange={(event) =>
                          (setter as (value: string) => void)(
                            event.target.value,
                          )
                        }
                      >
                        <option value="">All</option>
                        {(options as string[]).map((option) => (
                          <option key={option}>{option}</option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
              )}
            </div>
            {result.isLoading && <LoadingState />}
            {result.error && (
              <ErrorState error={result.error} retry={() => result.refetch()} />
            )}
            {!result.isLoading && !result.error && !items.length && (
              <EmptyState
                title={`No ${tab} yet`}
                description={
                  entityType
                    ? "Run Resolve entities to initialize identities from the extracted mentions."
                    : "This part of the Story Bible depends on a later course capability."
                }
              />
            )}
            <div className="space-y-1 p-2">
              {items.map((item) => {
                const id = String(item.id ?? "");
                const label = String(
                  item.name ??
                    item.subject ??
                    item.title ??
                    item.value ??
                    "Untitled",
                );
                return (
                  <button
                    key={id || label}
                    onClick={() => selectEntity(id)}
                    aria-current={selected === id ? "true" : undefined}
                    className={`w-full rounded-lg px-3 py-3 text-left ${selected === id ? "bg-[var(--brand-soft)]" : "hover:bg-[#eef1ef]"}`}
                  >
                    <p className="font-semibold">{label}</p>
                    <p className="mt-1 truncate text-xs text-muted">
                      {String(
                        item.role ??
                          item.predicate ??
                          item.description ??
                          item.chronological_time ??
                          "",
                      )}
                    </p>
                  </button>
                );
              })}
            </div>
          </section>
          <section
            ref={detailPane}
            aria-label="Story Bible details"
            className="p-5 sm:p-8 lg:min-h-0 lg:overflow-y-auto"
          >
            {!selected && (
              <EmptyState
                title={`Select ${tab === "facts" ? "a fact" : "an item"}`}
                description="Choose an item to inspect details and evidence."
              />
            )}
            {detail.isLoading && <LoadingState />}
            {detail.error && (
              <ErrorState error={detail.error} retry={() => detail.refetch()} />
            )}
            {selected &&
              (detail.data ??
                items.find((item) => String(item.id) === selected)) && (
                <EntityDetail
                  entity={
                    (detail.data ??
                      items.find((item) => String(item.id) === selected))!
                  }
                  onEvidence={setEvidence}
                />
              )}
            {entityType && (
              <div className={selected ? "mt-8 border-t border-[var(--line)] pt-8" : "mt-8"}>
                <EntityResolutionPanel
                  projectId={projectId}
                  onEvidence={setEvidence}
                />
              </div>
            )}
          </section>
        </div>
      </Card>
      <EvidenceDrawer
        projectId={projectId}
        evidence={evidence}
        onClose={() => setEvidence(null)}
      />
    </>
  );
}

function EntityDetail({
  entity,
  onEvidence,
}: {
  entity: Entity;
  onEvidence: (evidence: Evidence) => void;
}) {
  const reserved = new Set(["id", "name", "facts", "evidence", "description"]);
  const attributes = Object.entries(entity).filter(
    ([key, value]) =>
      !reserved.has(key) &&
      value !== null &&
      value !== undefined &&
      !Array.isArray(value) &&
      typeof value !== "object",
  );
  return (
    <div>
      <p className="text-xs font-bold uppercase tracking-wider text-[var(--brand)]">
        {entity.type ?? "Story entity"}
      </p>
      <h2 className="page-title mt-2 text-3xl font-semibold">{entity.name}</h2>
      {entity.description && (
        <p className="mt-3 text-sm leading-6 text-muted">
          {entity.description}
        </p>
      )}
      {!!entity.aliases?.length && (
        <div className="mt-4 flex gap-2">
          <span className="text-sm text-muted">Aliases</span>
          {entity.aliases.map((alias) => (
            <Badge key={alias}>{alias}</Badge>
          ))}
        </div>
      )}
      {!!entity.evidence?.length && (
        <div className="mt-4 flex flex-wrap gap-2">
          {entity.evidence.map((evidence, index) => (
            <Button
              key={evidence.id}
              variant="ghost"
              onClick={() => onEvidence(evidence)}
            >
              Source evidence {index + 1}
            </Button>
          ))}
        </div>
      )}
      <dl className="mt-7 divide-y divide-[var(--line)] border-y border-[var(--line)]">
        {attributes.map(([key, value]) => (
          <div
            key={key}
            className="grid grid-cols-[150px_1fr] gap-4 py-3 text-sm"
          >
            <dt className="capitalize text-muted">
              {key.replaceAll("_", " ")}
            </dt>
            <dd>{String(value)}</dd>
          </div>
        ))}
      </dl>
      {!!entity.facts?.length && (
        <div className="mt-7">
          <h3 className="font-semibold">Key facts</h3>
          <div className="mt-3 divide-y divide-[var(--line)] rounded-xl border border-[var(--line)]">
            {entity.facts.map((fact, index) => (
              <div
                key={fact.id ?? index}
                className="flex items-start justify-between gap-4 p-4"
              >
                <p className="text-sm">{fact.value}</p>
                {fact.evidence?.[0] && (
                  <button
                    onClick={() => onEvidence(fact.evidence![0])}
                    className="shrink-0 text-xs font-semibold text-[var(--brand)]"
                  >
                    Show evidence
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function TimelineScreen({ projectId }: { projectId: string }) {
  const [order, setOrder] = useState<"chronological" | "narrative">(
    "chronological",
  );
  const [character, setCharacter] = useState("");
  const [location, setLocation] = useState("");
  const [eventType, setEventType] = useState("");
  const events = useEndpoint<StoryEvent[] | { items?: StoryEvent[] }>(
    ["events", projectId],
    `/projects/${projectId}/events`,
  );
  const allEvents = useMemo(() => getList(events.data), [events.data]);
  const list = allEvents.filter(
    (event) =>
      (!character || event.participants?.includes(character)) &&
      (!location || event.location === location) &&
      (!eventType || event.type === eventType),
  );
  const eventOptions = (values: (string | undefined)[]) => [
    ...new Set(values.filter((value): value is string => !!value)),
  ];
  return (
    <>
      <PageHeader
        eyebrow="Story time"
        title="Timeline"
        description="Keep chronological time distinct from the order in which the reader encounters events."
        actions={
          <div className="rounded-lg border border-[var(--line)] bg-white p-1">
            <Button
              variant={order === "chronological" ? "primary" : "ghost"}
              onClick={() => setOrder("chronological")}
            >
              Chronological
            </Button>
            <Button
              variant={order === "narrative" ? "primary" : "ghost"}
              onClick={() => setOrder("narrative")}
            >
              Narrative
            </Button>
          </div>
        }
      />
      <div className="mb-4 grid gap-2 sm:grid-cols-3">
        {[
          [
            "Character",
            character,
            setCharacter,
            eventOptions(
              allEvents.flatMap((event) => event.participants ?? []),
            ),
          ],
          [
            "Location",
            location,
            setLocation,
            eventOptions(allEvents.map((event) => event.location)),
          ],
          [
            "Event type",
            eventType,
            setEventType,
            eventOptions(allEvents.map((event) => event.type)),
          ],
        ].map(([label, value, setter, options]) => (
          <label key={label as string} className="text-xs font-bold text-muted">
            {label as string}
            <select
              className={`${inputClass} mt-1 font-normal`}
              value={value as string}
              onChange={(event) =>
                (setter as (value: string) => void)(event.target.value)
              }
            >
              <option value="">All</option>
              {(options as string[]).map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <Card className="p-5 sm:p-8">
        {events.isLoading && <LoadingState label="Building timeline…" />}
        {events.error && (
          <ErrorState error={events.error} retry={() => events.refetch()} />
        )}
        {!events.isLoading && !events.error && !list.length && (
          <EmptyState
            title="No timeline yet"
            description="Events appear after StoryGuard extracts them from a manuscript."
          />
        )}
        {list.map((event, index) => (
          <article
            key={event.id}
            className="relative grid gap-2 border-l-2 border-[#b9d2c9] pb-9 pl-7 sm:grid-cols-[180px_1fr]"
          >
            <span className="absolute -left-[7px] top-1 size-3 rounded-full bg-[var(--brand)] ring-4 ring-[var(--brand-soft)]" />
            <p className="text-sm font-semibold text-[var(--brand)]">
              {order === "chronological"
                ? (event.chronological_time ?? "Time unknown")
                : (event.narrative_position ??
                  event.chapter ??
                  `Event ${index + 1}`)}
            </p>
            <div>
              <h2 className="page-title text-xl font-semibold">
                {event.title ?? "Untitled event"}
              </h2>
              {event.description && (
                <p className="mt-2 text-sm leading-6 text-muted">
                  {event.description}
                </p>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                {event.location && <Badge tone="info">{event.location}</Badge>}
                {event.narrative_position && (
                  <Badge>{event.narrative_position}</Badge>
                )}
              </div>
            </div>
          </article>
        ))}
      </Card>
    </>
  );
}

export function IssuesScreen({ projectId }: { projectId: string }) {
  const params = useSearchParams();
  const router = useRouter();
  const selected = params.get("selected") ?? "";
  const [severity, setSeverity] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [character, setCharacter] = useState("");
  const [chapter, setChapter] = useState("");
  const [feedback, setFeedback] = useState<
    "valid_issue" | "not_an_issue" | "note" | null
  >(null);
  const [reason, setReason] = useState("intentional_contradiction");
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [feedbackError, setFeedbackError] = useState("");
  const query = new URLSearchParams();
  if (severity) query.set("severity", severity);
  if (type) query.set("type", type);
  if (status) query.set("status", status);
  if (character) query.set("entity_id", character);
  if (chapter) query.set("chapter_id", chapter);
  const issues = useEndpoint<Issue[] | { items?: Issue[] }>(
    ["issues", projectId, severity, type, status, character, chapter],
    `/projects/${projectId}/issues${query.size ? `?${query}` : ""}`,
  );
  const detail = useEndpoint<Issue>(
    ["issue", projectId, selected],
    `/projects/${projectId}/issues/${selected}`,
    !!selected,
  );
  const list = getList(issues.data);
  function select(id: string) {
    const next = new URLSearchParams(params.toString());
    next.set("selected", id);
    router.replace(`?${next}`);
  }
  async function submitFeedback() {
    if (!selected || !feedback) return;
    setSaving(true);
    setFeedbackError("");
    try {
      await api(`/projects/${projectId}/issues/${selected}/feedback`, {
        method: "POST",
        body: JSON.stringify({
          verdict: feedback === "note" ? "needs_review" : feedback,
          reason: feedback === "not_an_issue" ? reason : undefined,
          comment,
        }),
      });
      setFeedback(null);
      setComment("");
      await Promise.all([issues.refetch(), detail.refetch()]);
    } catch (error) {
      setFeedbackError(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="Evidence review"
        title="Continuity Issues"
        description="Potential inconsistencies are review items, not automatic errors."
      />
      <div className="mb-4 grid gap-2 sm:grid-cols-3 xl:grid-cols-5">
        {[
          [
            "Severity",
            severity,
            setSeverity,
            ["Likely", "Possible", "Needs review"],
          ],
          [
            "Type",
            type,
            setType,
            [
              "Character attribute",
              "Timeline",
              "Relationship",
              "Entity state",
              "Location",
              "World rule",
              "Other",
            ],
          ],
          [
            "Status",
            status,
            setStatus,
            ["Open", "Valid issue", "Not an issue"],
          ],
        ].map(([label, value, setter, options]) => (
          <label key={label as string} className="text-xs font-bold text-muted">
            {label as string}
            <select
              value={value as string}
              onChange={(event) =>
                (setter as (value: string) => void)(event.target.value)
              }
              className={`${inputClass} mt-1 font-normal`}
            >
              <option value="">All</option>
              {(options as string[]).map((option) => (
                <option
                  key={option}
                  value={option.toLowerCase().replaceAll(" ", "_")}
                >
                  {option}
                </option>
              ))}
            </select>
          </label>
        ))}
        <label className="text-xs font-bold text-muted">
          Character
          <input
            value={character}
            onChange={(event) => setCharacter(event.target.value)}
            className={`${inputClass} mt-1 font-normal`}
            placeholder="Entity ID"
          />
        </label>
        <label className="text-xs font-bold text-muted">
          Chapter
          <input
            value={chapter}
            onChange={(event) => setChapter(event.target.value)}
            className={`${inputClass} mt-1 font-normal`}
            placeholder="Chapter ID"
          />
        </label>
      </div>
      <Card className="min-h-[650px] overflow-hidden lg:grid lg:grid-cols-[340px_minmax(0,1fr)]">
        <section className="border-b border-[var(--line)] bg-[#fafbf9] lg:border-b-0 lg:border-r">
          {issues.isLoading && <LoadingState />}
          {issues.error && (
            <ErrorState error={issues.error} retry={() => issues.refetch()} />
          )}
          {!issues.isLoading && !issues.error && !list.length && (
            <EmptyState
              title="No continuity issues"
              description="Run analysis to look for evidence-backed inconsistencies."
            />
          )}
          <div className="space-y-1 p-2">
            {list.map((issue) => (
              <button
                key={issue.id}
                onClick={() => select(issue.id)}
                className={`w-full rounded-lg p-3 text-left ${selected === issue.id ? "bg-white shadow-sm ring-1 ring-[var(--line)]" : "hover:bg-[#eef1ef]"}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <Badge tone={toneFor(issue.severity)}>
                    {issue.severity ?? "Needs review"}
                  </Badge>
                  <span className="text-xs text-muted">{issue.chapter}</span>
                </div>
                <h2 className="mt-2 font-semibold">
                  {issue.title ?? "Continuity issue"}
                </h2>
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted">
                  {issue.summary ?? issue.description}
                </p>
              </button>
            ))}
          </div>
        </section>
        <section className="p-5 sm:p-8">
          {!selected && (
            <EmptyState
              title="Select an issue"
              description="Compare evidence and record a review decision."
            />
          )}
          {detail.isLoading && <LoadingState />}
          {detail.error && (
            <ErrorState error={detail.error} retry={() => detail.refetch()} />
          )}
          {detail.data && (
            <IssueDetail
              issue={detail.data}
              projectId={projectId}
              onFeedback={setFeedback}
            />
          )}
        </section>
      </Card>
      <Dialog
        open={!!feedback}
        title={
          feedback === "not_an_issue"
            ? "Why is this not an issue?"
            : feedback === "valid_issue"
              ? "Confirm valid issue"
              : "Add review note"
        }
        onClose={() => setFeedback(null)}
      >
        {feedback === "not_an_issue" && (
          <label className="block text-sm font-semibold">
            Reason
            <select
              className={`${inputClass} mt-2`}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            >
              {[
                "intentional_contradiction",
                "character_is_lying",
                "flashback_timeline_nuance",
                "wrong_entity_resolution",
                "ai_misunderstood_context",
                "other",
              ].map((item) => (
                <option key={item} value={item}>
                  {item.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="mt-4 block text-sm font-semibold">
          Comment
          <textarea
            className={`${inputClass} mt-2`}
            rows={4}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            placeholder="Optional context for evaluation"
          />
        </label>
        {feedbackError && (
          <p className="mt-3 text-sm text-[var(--danger)]">{feedbackError}</p>
        )}
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setFeedback(null)}>
            Cancel
          </Button>
          <Button disabled={saving} onClick={submitFeedback}>
            {saving ? "Saving…" : "Save review"}
          </Button>
        </div>
      </Dialog>
    </>
  );
}

function IssueDetail({
  issue,
  projectId,
  onFeedback,
}: {
  issue: Issue;
  projectId: string;
  onFeedback: (value: "valid_issue" | "not_an_issue" | "note") => void;
}) {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const sources =
    issue.evidence ??
    ([issue.evidence_a, issue.evidence_b].filter(Boolean) as Evidence[]);
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={toneFor(issue.severity)}>
          {issue.severity ?? "Needs review"}
        </Badge>
        {issue.type && <Badge>{issue.type}</Badge>}
        {issue.confidence && (
          <span className="ml-auto text-sm text-muted">
            Confidence:{" "}
            <strong className="text-[var(--ink)]">{issue.confidence}</strong>
          </span>
        )}
      </div>
      <h2 className="page-title mt-4 text-3xl font-semibold">
        {issue.title ?? "Continuity issue"}
      </h2>
      <p className="mt-3 text-sm leading-6 text-muted">
        {issue.description ?? issue.summary}
      </p>
      {issue.reason && (
        <div className="mt-5 rounded-xl bg-[#f5f7f5] p-4">
          <p className="text-xs font-bold uppercase tracking-wider text-muted">
            Reason
          </p>
          <p className="mt-2 text-sm">{issue.reason}</p>
        </div>
      )}
      <h3 className="mt-7 font-semibold">Evidence comparison</h3>
      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        {sources.map((source, index) => (
          <button
            key={source.id}
            onClick={() => setEvidence(source)}
            className="rounded-xl border border-[var(--line)] bg-[#fafbf9] p-4 text-left hover:border-[#9db8ae]"
          >
            <p className="text-xs font-bold text-[var(--brand)]">
              {source.chapter ?? `Evidence ${index + 1}`}
            </p>
            <blockquote className="mt-3 font-serif text-sm leading-6">
              “{source.text}”
            </blockquote>
            <span className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-[var(--brand)]">
              <Eye className="size-3" />
              Open evidence
            </span>
          </button>
        ))}
      </div>
      {!sources.length && (
        <p className="mt-3 text-sm text-muted">
          No evidence was included in the issue response.
        </p>
      )}
      <div className="mt-8 flex flex-wrap gap-2 border-t border-[var(--line)] pt-5">
        <Button onClick={() => onFeedback("valid_issue")}>Valid issue</Button>
        <Button variant="secondary" onClick={() => onFeedback("not_an_issue")}>
          Not an issue
        </Button>
        <Button variant="ghost" onClick={() => onFeedback("note")}>
          Add note
        </Button>
      </div>
      <EvidenceDrawer
        projectId={projectId}
        evidence={evidence}
        onClose={() => setEvidence(null)}
      />
    </>
  );
}
