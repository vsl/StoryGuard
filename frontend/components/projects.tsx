"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  ArrowLeft,
  BookOpen,
  Plus,
  ShieldAlert,
  Trash2,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ProjectMark } from "@/components/project-shell";
import {
  Button,
  ButtonLink,
  Card,
  Dialog,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  PageHeader,
  inputClass,
} from "@/components/ui";
import { errorMessage, projectsApi, type Project } from "@/lib/api";
import { useProjects } from "@/lib/hooks";

const createSchema = z.object({
  title: z.string().trim().min(1, "Enter a story title"),
  description: z.string(),
  language: z.string().trim().min(1, "Enter a language code").max(16),
});
type CreateValues = z.infer<typeof createSchema>;

function valueOrDash(value?: string | number | null) {
  return value === undefined || value === null || value === ""
    ? "—"
    : String(value);
}

export function ProjectsScreen() {
  const router = useRouter();
  const projects = useProjects();
  const [deleting, setDeleting] = useState<Project | null>(null);
  const [deleteError, setDeleteError] = useState("");
  const [busy, setBusy] = useState(false);

  async function remove() {
    if (!deleting) return;
    setBusy(true);
    setDeleteError("");
    try {
      await projectsApi.remove(deleting.id);
      setDeleting(null);
      await projects.refetch();
    } catch (error) {
      setDeleteError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-[var(--paper)]">
      <header className="border-b border-[var(--line)] bg-white">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
          <ProjectMark />
          <Button onClick={() => router.push("/projects/new")}>
            <Plus className="size-4" />
            New Story
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-5 py-10">
        <PageHeader
          eyebrow="StoryGuard"
          title="Your Stories"
          description="All your manuscripts, analysis, and evidence in one place."
        />
        {projects.isLoading && <LoadingState label="Loading stories…" />}
        {projects.error && (
          <Card>
            <ErrorState
              error={projects.error}
              retry={() => projects.refetch()}
            />
          </Card>
        )}
        {projects.data?.length === 0 && (
          <Card>
            <EmptyState
              title="No stories yet"
              description="Create your first story, then upload a .docx, .md, or .txt manuscript."
              action={
                <ButtonLink href="/projects/new">
                  <Plus className="size-4" />
                  Create your first story
                </ButtonLink>
              }
            />
          </Card>
        )}
        {!!projects.data?.length && (
          <div className="grid gap-4">
            {projects.data.map((project, index) => (
              <Card
                key={project.id}
                className="group overflow-hidden p-4 sm:grid sm:grid-cols-[132px_minmax(0,1fr)_auto] sm:gap-5"
              >
                <Link
                  href={`/projects/${project.id}`}
                  className="hidden min-h-36 place-items-center rounded-xl bg-gradient-to-br from-[#173d36] to-[#071c19] text-white sm:grid"
                >
                  <div className="text-center">
                    <ShieldAlert className="mx-auto size-8 text-[#9fc7ba]" />
                    <p className="mt-3 max-w-24 font-serif text-lg leading-5">
                      {project.title}
                    </p>
                  </div>
                </Link>
                <div className="py-1">
                  <Link
                    href={`/projects/${project.id}`}
                    className="page-title text-xl font-semibold hover:text-[var(--brand)]"
                  >
                    {project.title}
                  </Link>
                  {project.description && (
                    <p className="mt-1 line-clamp-2 text-sm text-muted">
                      {project.description}
                    </p>
                  )}
                  <dl className="mt-5 grid grid-cols-2 gap-x-8 gap-y-2 text-sm sm:max-w-lg">
                    <dt className="text-muted">Manuscript version</dt>
                    <dd className="font-semibold">
                      {valueOrDash(project.current_manuscript_version)}
                    </dd>
                    <dt className="text-muted">Chapters</dt>
                    <dd>{valueOrDash(project.chapter_count)}</dd>
                    <dt className="text-muted">Characters</dt>
                    <dd>{valueOrDash(project.character_count)}</dd>
                    <dt className="text-muted">Issues</dt>
                    <dd
                      className={
                        project.issue_count ? "text-[var(--danger)]" : ""
                      }
                    >
                      {valueOrDash(project.issue_count)}
                    </dd>
                    <dt className="text-muted">Last analyzed</dt>
                    <dd>
                      {project.last_analyzed_at
                        ? new Date(
                            project.last_analyzed_at,
                          ).toLocaleDateString()
                        : "—"}
                    </dd>
                  </dl>
                </div>
                <div className="mt-4 flex items-start gap-2 sm:mt-0">
                  <ButtonLink
                    href={`/projects/${project.id}`}
                    variant="secondary"
                  >
                    Open
                  </ButtonLink>
                  <ButtonLink
                    href={`/projects/${project.id}/versions`}
                    variant="ghost"
                    ariaLabel={`Upload a new version for ${project.title}`}
                  >
                    <Upload className="size-4" />
                  </ButtonLink>
                  <Button
                    variant="ghost"
                    onClick={() => setDeleting(project)}
                    aria-label={`Delete ${project.title}`}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                  <span className="sr-only">Project {index + 1}</span>
                </div>
              </Card>
            ))}
          </div>
        )}
      </main>
      <Dialog
        open={!!deleting}
        title="Delete story?"
        onClose={() => setDeleting(null)}
      >
        <p className="text-sm leading-6">
          This permanently deletes <strong>{deleting?.title}</strong> and all
          project-scoped data. There is no authentication or undo in v1.
        </p>
        {deleteError && (
          <p className="mt-3 text-sm text-[var(--danger)]" role="alert">
            {deleteError}
          </p>
        )}
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setDeleting(null)}>
            Cancel
          </Button>
          <Button variant="danger" disabled={busy} onClick={remove}>
            {busy ? "Deleting…" : "Delete story"}
          </Button>
        </div>
      </Dialog>
    </div>
  );
}

export function CreateProjectScreen() {
  const router = useRouter();
  const [submitError, setSubmitError] = useState("");
  const form = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: { title: "", description: "", language: "en" },
  });

  async function submit(values: CreateValues) {
    setSubmitError("");
    try {
      const project = await projectsApi.create(values);
      router.push(`/projects/${project.id}/versions?welcome=1`);
    } catch (error) {
      setSubmitError(errorMessage(error));
    }
  }

  return (
    <div className="min-h-screen bg-[var(--paper)]">
      <header className="border-b border-[var(--line)] bg-white">
        <div className="mx-auto flex h-16 max-w-4xl items-center px-5">
          <Link
            href="/projects"
            className="mr-5 rounded-lg p-2 hover:bg-[#eef1ef]"
            aria-label="Back to projects"
          >
            <ArrowLeft className="size-5" />
          </Link>
          <ProjectMark />
        </div>
      </header>
      <main className="mx-auto max-w-2xl px-5 py-12">
        <PageHeader
          eyebrow="New story"
          title="Create your workspace"
          description="Start with the story details. Manuscript upload comes next."
        />
        <Card className="p-6 sm:p-8">
          <form onSubmit={form.handleSubmit(submit)} className="space-y-6">
            <Field
              label="Story title"
              error={form.formState.errors.title?.message}
            >
              <input
                autoFocus
                className={inputClass}
                placeholder="The Last Signal"
                {...form.register("title")}
              />
            </Field>
            <Field
              label="Description"
              error={form.formState.errors.description?.message}
            >
              <textarea
                className={inputClass}
                rows={4}
                placeholder="Optional short description"
                {...form.register("description")}
              />
            </Field>
            <Field
              label="Language"
              hint="BCP 47 language code. A backend-supported language catalog is not available yet."
              error={form.formState.errors.language?.message}
            >
              <input
                className={inputClass}
                placeholder="en"
                {...form.register("language")}
              />
            </Field>
            {submitError && (
              <p className="text-sm text-[var(--danger)]" role="alert">
                {submitError}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <ButtonLink href="/projects" variant="secondary">
                Cancel
              </ButtonLink>
              <Button disabled={form.formState.isSubmitting}>
                <BookOpen className="size-4" />
                {form.formState.isSubmitting ? "Creating…" : "Create Story"}
              </Button>
            </div>
          </form>
        </Card>
      </main>
    </div>
  );
}
