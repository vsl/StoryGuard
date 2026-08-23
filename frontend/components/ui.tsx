"use client";

import {
  AlertCircle,
  CheckCircle2,
  Inbox,
  LoaderCircle,
  X,
} from "lucide-react";
import Link from "next/link";
import {
  useEffect,
  useRef,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type ReactNode,
} from "react";

import { ApiError, errorMessage } from "@/lib/api";

const buttonStyles = {
  primary: "bg-[var(--brand)] text-white hover:bg-[#064b3c]",
  secondary:
    "border border-[var(--line)] bg-white text-[var(--ink)] hover:bg-[#f3f5f3]",
  ghost: "text-[var(--muted)] hover:bg-[#eef1ee] hover:text-[var(--ink)]",
  danger: "bg-[var(--danger)] text-white hover:bg-[#963523]",
};

function buttonClass(variant: keyof typeof buttonStyles, className = "") {
  return `inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${buttonStyles[variant]} ${className}`;
}

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof buttonStyles;
}) {
  return <button className={buttonClass(variant, className)} {...props} />;
}

export function ButtonLink({
  href,
  children,
  variant = "primary",
  className = "",
  ariaLabel,
}: {
  href: string;
  children: ReactNode;
  variant?: keyof typeof buttonStyles;
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <Link
      href={href}
      className={buttonClass(variant, className)}
      aria-label={ariaLabel}
    >
      {children}
    </Link>
  );
}

export function Card({
  className = "",
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={`surface ${className}`} {...props} />;
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "good" | "warn" | "danger" | "info";
}) {
  const tones = {
    neutral: "bg-[#eef1ef] text-[#53605b]",
    good: "bg-[var(--brand-soft)] text-[var(--brand)]",
    warn: "bg-[var(--amber-soft)] text-[var(--amber)]",
    danger: "bg-[var(--danger-soft)] text-[var(--danger)]",
    info: "bg-[#eaf1f8] text-[var(--info)]",
  };
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        {eyebrow && (
          <p className="mb-1 text-xs font-bold uppercase tracking-[0.16em] text-[var(--brand)]">
            {eyebrow}
          </p>
        )}
        <h1 className="page-title text-3xl font-semibold sm:text-4xl">
          {title}
        </h1>
        {description && (
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div
      className="flex min-h-52 items-center justify-center gap-3 text-sm text-muted"
      role="status"
    >
      <LoaderCircle className="size-5 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex min-h-52 flex-col items-center justify-center px-6 text-center">
      <span className="mb-4 rounded-full bg-[#eef1ef] p-3 text-muted">
        <Inbox className="size-5" aria-hidden />
      </span>
      <h2 className="font-semibold">{title}</h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-muted">
        {description}
      </p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorState({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  const unavailable = error instanceof ApiError && error.status === 404;
  return (
    <div
      className="flex min-h-52 flex-col items-center justify-center px-6 text-center"
      role="alert"
    >
      <span className="mb-4 rounded-full bg-[var(--danger-soft)] p-3 text-[var(--danger)]">
        <AlertCircle className="size-5" aria-hidden />
      </span>
      <h2 className="font-semibold">
        {unavailable
          ? "This view is waiting for its API"
          : "We couldn’t load this view"}
      </h2>
      <p className="mt-2 max-w-lg text-sm leading-6 text-muted">
        {unavailable
          ? "The interface is ready, but the required backend endpoint has not been implemented yet."
          : errorMessage(error)}
      </p>
      {retry && (
        <Button className="mt-5" variant="secondary" onClick={retry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function SuccessNote({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-center gap-2 text-sm text-[var(--brand)]">
      <CheckCircle2 className="size-4" />
      {children}
    </p>
  );
}

export function Dialog({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (open) ref.current?.showModal();
    else ref.current?.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onCancel={onClose}
      onClose={onClose}
      className="m-auto w-[min(92vw,560px)] rounded-2xl border border-[var(--line)] bg-white p-0 text-[var(--ink)] shadow-2xl backdrop:bg-[#10221b]/40"
    >
      <div className="flex items-center justify-between border-b border-[var(--line)] px-6 py-4">
        <h2 className="page-title text-xl font-semibold">{title}</h2>
        <button
          className="rounded-lg p-2 text-muted hover:bg-[#eef1ef]"
          onClick={onClose}
          aria-label="Close dialog"
        >
          <X className="size-5" />
        </button>
      </div>
      <div className="p-6">{children}</div>
    </dialog>
  );
}

export function Field({
  label,
  error,
  children,
  hint,
}: {
  label: string;
  error?: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="block text-sm font-semibold">
      {label}
      <span className="mt-2 block">{children}</span>
      {hint && (
        <span className="mt-1 block text-xs font-normal text-muted">
          {hint}
        </span>
      )}
      {error && (
        <span className="mt-1 block text-xs font-normal text-[var(--danger)]">
          {error}
        </span>
      )}
    </label>
  );
}

export const inputClass =
  "w-full rounded-lg border border-[var(--line)] bg-white px-3 py-2.5 text-sm text-[var(--ink)] placeholder:text-[#98a39f]";
