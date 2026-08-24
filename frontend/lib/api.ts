import { z } from "zod";

export const projectSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string().default(""),
  language: z.string().default("en"),
  current_manuscript_version_id: z.string().nullable(),
  current_manuscript_version: z.string().nullable().optional(),
  chapter_count: z.number().nullable().optional(),
  character_count: z.number().optional(),
  issue_count: z.number().optional(),
  last_analyzed_at: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type Project = z.infer<typeof projectSchema>;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  init?: RequestInit,
  schema?: z.ZodType<T>,
) {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers:
      init?.body instanceof FormData
        ? init.headers
        : { "content-type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const error = body?.error ?? body;
    throw new ApiError(
      error?.message ?? error?.detail ?? `Request failed (${response.status})`,
      response.status,
      error?.code,
    );
  }

  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json();
  return schema ? schema.parse(data) : (data as T);
}

export const projectsApi = {
  list: () => api("/projects", undefined, z.array(projectSchema)),
  get: (id: string) => api(`/projects/${id}`, undefined, projectSchema),
  create: (body: { title: string; description: string; language: string }) =>
    api(
      "/projects",
      { method: "POST", body: JSON.stringify(body) },
      projectSchema,
    ),
  update: (
    id: string,
    body: Partial<Pick<Project, "title" | "description" | "language">>,
  ) =>
    api(
      `/projects/${id}`,
      { method: "PATCH", body: JSON.stringify(body) },
      projectSchema,
    ),
  remove: (id: string) => api<void>(`/projects/${id}`, { method: "DELETE" }),
};

export async function readSse(
  response: Response,
  onEvent: (event: string, data: unknown) => void,
) {
  if (!response.ok || !response.body) {
    throw new ApiError(`Request failed (${response.status})`, response.status);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += value;
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) data.push(line.slice(5).trim());
      }
      if (!data.length) continue;
      const raw = data.join("\n");
      try {
        onEvent(event, JSON.parse(raw));
      } catch {
        onEvent(event, raw);
      }
    }
  }
}

export function errorMessage(error: unknown) {
  if (error instanceof z.ZodError)
    return "The server returned an unexpected response.";
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}
