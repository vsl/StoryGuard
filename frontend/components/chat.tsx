"use client";

import {
  Bot,
  ChevronRight,
  CircleCheck,
  LoaderCircle,
  Send,
  ShieldCheck,
} from "lucide-react";
import { useState, type FormEvent } from "react";

import { EvidenceDrawer } from "@/components/evidence-drawer";
import { Badge, Button, Card, EmptyState } from "@/components/ui";
import { ApiError, errorMessage, readSse } from "@/lib/api";
import type { Evidence, UiContext } from "@/lib/types";

type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations?: Evidence[];
  metadata?: Record<string, unknown>;
  failed?: boolean;
};

const stages: Record<string, string> = {
  "run.started": "Understanding question…",
  "route.completed": "Choosing the safest route…",
  "plan.completed": "Planning evidence search…",
  "retrieval.started": "Searching story…",
  "retrieval.completed": "Reviewing passages…",
  "rerank.completed": "Reranking evidence…",
  "verification.completed": "Verifying citations…",
};

export function ChatWorkspace({
  projectId,
  context = { type: "project" },
  compact = false,
}: {
  projectId: string;
  context?: UiContext;
  compact?: boolean;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [stage, setStage] = useState("");
  const [sending, setSending] = useState(false);
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(
    null,
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    const question = input.trim();
    if (!question || sending) return;
    setInput("");
    setSending(true);
    setStage("Understanding question…");
    const user: Message = {
      id: crypto.randomUUID(),
      role: "user",
      text: question,
    };
    const assistantId = crypto.randomUUID();
    setMessages((current) => [
      ...current,
      user,
      { id: assistantId, role: "assistant", text: "" },
    ]);

    try {
      const response = await fetch(`/api/projects/${projectId}/chat/stream`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          accept: "text/event-stream",
        },
        body: JSON.stringify({ message: question, thread_id: null, context }),
      });
      const contentType = response.headers.get("content-type") ?? "";
      if (response.ok && contentType.includes("application/json")) {
        const result = await response.json();
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantId
              ? {
                  ...message,
                  text: result.answer,
                  citations: result.citations,
                  metadata: result.metadata,
                }
              : message,
          ),
        );
      } else {
        await readSse(response, (name, raw) => {
          const data = raw as Record<string, unknown>;
          if (stages[name]) setStage(stages[name]);
          if (name === "answer.delta") {
            const delta = String(data.delta ?? data.text ?? "");
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? { ...message, text: message.text + delta }
                  : message,
              ),
            );
          }
          if (name === "answer.completed") {
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? {
                      ...message,
                      text: String(data.answer ?? message.text),
                      citations:
                        (data.citations as Evidence[]) ?? message.citations,
                      metadata:
                        (data.metadata as Record<string, unknown>) ??
                        message.metadata,
                    }
                  : message,
              ),
            );
          }
          if (name === "run.abstained") {
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? {
                      ...message,
                      text: "I couldn’t find enough manuscript evidence to answer this reliably.",
                    }
                  : message,
              ),
            );
          }
        });
      }
    } catch (error) {
      const unavailable = error instanceof ApiError && error.status === 404;
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                failed: true,
                text: unavailable
                  ? "Chat is ready in the UI, but the streaming backend endpoint is not available yet."
                  : errorMessage(error),
              }
            : message,
        ),
      );
    } finally {
      setSending(false);
      setStage("");
    }
  }

  return (
    <div
      className={`flex min-h-0 flex-1 flex-col ${compact ? "h-full" : "min-h-[640px]"}`}
    >
      <div
        className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4 sm:p-6"
        aria-live="polite"
      >
        {!messages.length ? (
          <EmptyState
            title="Ask about your story"
            description="Explore characters, events, relationships, or continuity. Every supported claim should point back to manuscript evidence."
          />
        ) : (
          messages.map((message) => (
            <article
              key={message.id}
              className={
                message.role === "user" ? "ml-auto max-w-[82%]" : "max-w-[92%]"
              }
            >
              <div
                className={`rounded-2xl px-4 py-3 text-sm leading-6 ${
                  message.role === "user"
                    ? "bg-[#e7edf4] text-[#1f344a]"
                    : message.failed
                      ? "border border-[#f0c7bd] bg-[var(--danger-soft)]"
                      : "border border-[var(--line)] bg-white"
                }`}
              >
                {message.role === "assistant" && (
                  <Bot
                    className="mb-2 size-5 text-[var(--brand)]"
                    aria-hidden
                  />
                )}
                <p className="whitespace-pre-wrap">{message.text || "…"}</p>
              </div>
              {!!message.citations?.length && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {message.citations.map((evidence, index) => (
                    <button
                      key={evidence.id}
                      className="rounded-lg border border-[var(--line)] bg-white px-3 py-2 text-left text-xs hover:border-[#9db8ae]"
                      onClick={() => setSelectedEvidence(evidence)}
                    >
                      [{index + 1}] {evidence.chapter ?? "Source"}{" "}
                      <ChevronRight className="ml-1 inline size-3" />
                    </button>
                  ))}
                </div>
              )}
              {message.metadata && (
                <details className="mt-3 rounded-lg bg-[#f5f7f5] px-3 py-2 text-xs text-muted">
                  <summary className="cursor-pointer font-semibold">
                    Execution metadata
                  </summary>
                  <dl className="mt-2 grid grid-cols-2 gap-2">
                    {Object.entries(message.metadata).map(([key, value]) => (
                      <div key={key}>
                        <dt>{key.replaceAll("_", " ")}</dt>
                        <dd className="font-semibold text-[var(--ink)]">
                          {String(value)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </details>
              )}
            </article>
          ))
        )}
        {sending && (
          <p className="flex items-center gap-2 text-sm text-muted">
            <LoaderCircle className="size-4 animate-spin" />
            {stage}
          </p>
        )}
      </div>
      <form
        onSubmit={submit}
        className="border-t border-[var(--line)] bg-white p-4"
      >
        <label
          className="sr-only"
          htmlFor={`ask-${compact ? "panel" : "page"}`}
        >
          Ask StoryGuard
        </label>
        <div className="flex gap-2 rounded-xl border border-[var(--line)] bg-white p-2 focus-within:border-[#8aac9f]">
          <textarea
            id={`ask-${compact ? "panel" : "page"}`}
            rows={compact ? 2 : 3}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask anything about this story…"
            className="min-w-0 flex-1 resize-none border-0 bg-transparent px-2 py-1 text-sm outline-none"
          />
          <Button
            className="self-end px-3"
            disabled={!input.trim() || sending}
            aria-label="Send question"
          >
            <Send className="size-4" />
          </Button>
        </div>
        <p className="mt-2 flex items-center gap-1.5 text-xs text-muted">
          <ShieldCheck className="size-3.5" />
          Answers should be grounded in manuscript evidence.
        </p>
      </form>
      <EvidenceDrawer
        projectId={projectId}
        evidence={selectedEvidence}
        onClose={() => setSelectedEvidence(null)}
      />
    </div>
  );
}

export function AskOverview({ projectId }: { projectId: string }) {
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_280px]">
      <Card className="overflow-hidden">
        <ChatWorkspace projectId={projectId} />
      </Card>
      <Card className="h-fit p-5">
        <h2 className="font-semibold">How it works</h2>
        <ol className="mt-5 space-y-5 text-sm">
          {[
            "Classifies your question",
            "Searches the manuscript",
            "Reranks evidence",
            "Verifies every citation",
          ].map((item, index) => (
            <li key={item} className="flex gap-3">
              <CircleCheck className="mt-0.5 size-4 shrink-0 text-[var(--brand)]" />
              <span>
                <Badge tone="good">{index + 1}</Badge>
                <span className="ml-2">{item}</span>
              </span>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
