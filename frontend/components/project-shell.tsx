"use client";

import {
  Activity,
  Beaker,
  BookOpen,
  Bot,
  CheckSquare,
  ChevronDown,
  Clock3,
  FileSearch,
  FolderOpen,
  Menu,
  Search,
  Settings,
  ShieldAlert,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState, type FormEvent, type ReactNode } from "react";

import { ChatWorkspace } from "@/components/chat";
import {
  Badge,
  Button,
  Dialog,
  ErrorState,
  LoadingState,
  inputClass,
} from "@/components/ui";
import { useEndpoint, useProject, useProjects } from "@/lib/hooks";
import type { Dictionary, UiContext } from "@/lib/types";

const navigation = [
  ["Overview", "", FolderOpen],
  ["Manuscript", "/manuscript", BookOpen],
  ["Story Bible", "/story-bible", FileSearch],
  ["Timeline", "/timeline", Clock3],
  ["Continuity", "/issues", ShieldAlert],
  ["Ask StoryGuard", "/ask", Sparkles],
  ["Analysis", "/analysis", Activity],
  ["Settings", "/settings", Settings],
] as const;

export function ProjectMark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2 font-bold tracking-tight">
      <span className="grid size-8 place-items-center rounded-lg bg-[var(--brand)] text-white">
        <ShieldAlert className="size-4" />
      </span>
      {!compact && "StoryGuard"}
    </span>
  );
}

function contextFromLocation(
  pathname: string,
  query: URLSearchParams,
): UiContext {
  const selected = query.get("selected") ?? "";
  if (pathname.endsWith("/manuscript") && query.get("chapter"))
    return { type: "chapter", chapter_id: query.get("chapter")! };
  if (pathname.endsWith("/story-bible") && selected)
    return { type: "character", entity_id: selected };
  if (pathname.endsWith("/issues") && selected)
    return { type: "issue", issue_id: selected };
  return { type: "project" };
}

export function ProjectShell({
  projectId,
  children,
}: {
  projectId: string;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const project = useProject(projectId);
  const projects = useProjects();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const context = useMemo(
    () => contextFromLocation(pathname, searchParams),
    [pathname, searchParams],
  );

  if (project.isLoading) return <LoadingState label="Opening story…" />;
  if (project.error)
    return (
      <main className="mx-auto max-w-xl p-8">
        <ErrorState error={project.error} retry={() => project.refetch()} />
      </main>
    );

  const base = `/projects/${projectId}`;
  const aside = (
    <aside className="flex h-full flex-col bg-white">
      <div className="flex h-16 items-center justify-between border-b border-[var(--line)] px-4">
        <Link href="/projects">
          <ProjectMark />
        </Link>
        <button
          className="rounded-lg p-2 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-label="Close navigation"
        >
          <X className="size-5" />
        </button>
      </div>
      <nav className="flex-1 space-y-1 p-3" aria-label="Project navigation">
        {navigation.map(([label, suffix, Icon]) => {
          const href = `${base}${suffix}`;
          const active = suffix ? pathname.startsWith(href) : pathname === href;
          return (
            <Link
              key={label}
              href={href}
              onClick={() => setSidebarOpen(false)}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${active ? "bg-[var(--brand-soft)] text-[var(--brand)]" : "text-[#52605b] hover:bg-[#f2f4f2]"}`}
            >
              <Icon className="size-4" aria-hidden />
              {label}
              {label === "Continuity" &&
                project.data?.issue_count !== undefined && (
                  <Badge tone="warn">{project.data.issue_count}</Badge>
                )}
            </Link>
          );
        })}
        <div className="my-3 border-t border-[var(--line)]" />
        <Link
          href={`${base}/check`}
          className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-muted hover:bg-[#f2f4f2]"
        >
          <CheckSquare className="size-4" />
          Check new text
        </Link>
        <Link
          href={`${base}/versions`}
          className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-muted hover:bg-[#f2f4f2]"
        >
          <Upload className="size-4" />
          Versions
        </Link>
        <Link
          href={`${base}/developer`}
          className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-muted hover:bg-[#f2f4f2]"
        >
          <Beaker className="size-4" />
          Developer
        </Link>
      </nav>
      <div className="border-t border-[var(--line)] p-3">
        <label className="sr-only" htmlFor="project-switcher">
          Switch project
        </label>
        <div className="relative">
          <select
            id="project-switcher"
            value={projectId}
            onChange={(event) => router.push(`/projects/${event.target.value}`)}
            className={`${inputClass} appearance-none pr-8 font-semibold`}
          >
            {(projects.data ?? [project.data!]).map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2.5 top-3 size-4 text-muted" />
        </div>
      </div>
    </aside>
  );

  return (
    <div className="min-h-screen bg-[var(--paper)] lg:grid lg:grid-cols-[220px_minmax(0,1fr)]">
      <div className="desktop-only sticky top-0 h-screen border-r border-[var(--line)]">
        {aside}
      </div>
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 grid grid-cols-[minmax(0,280px)_1fr] lg:hidden">
          <div className="shadow-2xl">{aside}</div>
          <button
            aria-label="Close navigation"
            className="bg-[#10221b]/35"
            onClick={() => setSidebarOpen(false)}
          />
        </div>
      )}
      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-[var(--line)] bg-white/95 px-4 backdrop-blur sm:px-6">
          <button
            className="rounded-lg p-2 lg:hidden"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open navigation"
          >
            <Menu className="size-5" />
          </button>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-bold">{project.data?.title}</p>
            <p className="truncate text-xs text-muted">
              {project.data?.current_manuscript_version ??
                (project.data?.current_manuscript_version_id
                  ? "Current manuscript"
                  : "No manuscript yet")}
            </p>
          </div>
          <Button
            variant="ghost"
            className="hidden sm:inline-flex"
            onClick={() => setSearchOpen(true)}
          >
            <Search className="size-4" />
            Search
          </Button>
          <Button
            variant="secondary"
            onClick={() => setAiOpen((open) => !open)}
          >
            <Bot className="size-4" />
            <span className="hidden sm:inline">Ask StoryGuard</span>
          </Button>
        </header>
        <main
          className={`mx-auto min-h-[calc(100vh-4rem)] max-w-[1500px] p-4 sm:p-6 xl:p-8 ${aiOpen ? "xl:mr-[380px]" : ""}`}
        >
          {children}
        </main>
      </div>
      {aiOpen && (
        <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-[380px] flex-col border-l border-[var(--line)] bg-white shadow-2xl">
          <div className="flex h-16 items-center justify-between border-b border-[var(--line)] px-4">
            <h2 className="font-semibold">Ask StoryGuard</h2>
            <button
              className="rounded-lg p-2 hover:bg-[#eef1ef]"
              onClick={() => setAiOpen(false)}
              aria-label="Close AI panel"
            >
              <X className="size-5" />
            </button>
          </div>
          <ChatWorkspace projectId={projectId} context={context} compact />
        </aside>
      )}
      <ProjectSearchDialog
        projectId={projectId}
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
      />
    </div>
  );
}

function ProjectSearchDialog({
  projectId,
  open,
  onClose,
}: {
  projectId: string;
  open: boolean;
  onClose: () => void;
}) {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [rerank, setRerank] = useState(true);
  const results = useEndpoint<Dictionary>(
    ["search", projectId, query, rerank],
    `/projects/${projectId}/search?q=${encodeURIComponent(query)}&rerank=${rerank}`,
    !!query,
  );
  function submit(event: FormEvent) {
    event.preventDefault();
    setQuery(input.trim());
  }
  return (
    <Dialog open={open} title="Search this story" onClose={onClose}>
      <form className="flex gap-2" onSubmit={submit}>
        <input
          autoFocus
          value={input}
          onChange={(event) => setInput(event.target.value)}
          className={inputClass}
          placeholder="Character, location, phrase…"
        />
        <Button aria-label="Search">
          <Search className="size-4" />
        </Button>
      </form>
      <label className="mt-3 flex items-center gap-2 text-sm text-muted">
        <input
          type="checkbox"
          checked={rerank}
          onChange={(event) => setRerank(event.target.checked)}
        />
        Use cross-encoder reranker
      </label>
      <div className="mt-5">
        {!query && (
          <p className="text-sm text-muted">
            Search is direct manuscript retrieval, separate from AI questions.
          </p>
        )}
        {results.isFetching && <LoadingState label="Searching story…" />}
        {results.error && (
          <ErrorState error={results.error} retry={() => results.refetch()} />
        )}
        {results.data && (
          <div className="space-y-4">
            {Object.entries(results.data).map(([group, items]) => (
              <section key={group}>
                <h3 className="text-xs font-bold uppercase tracking-wider text-muted">
                  {group.replaceAll("_", " ")}
                </h3>
                <p className="mt-2 text-sm">
                  {Array.isArray(items) && items.length
                    ? `${items.length} result${items.length === 1 ? "" : "s"}`
                    : "No matches"}
                </p>
              </section>
            ))}
          </div>
        )}
      </div>
    </Dialog>
  );
}
