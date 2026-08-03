/**
 * The small pieces every page is set from.
 *
 * All of them draw with borders and rules — no filled blocks, no solid accent
 * (CLAUDE.md §1). Photographs always go through `<Plate>`, which supplies the
 * archival grade and the mat.
 */

import { Bookmark, Loader } from "lucide-react";
import type { ReactNode } from "react";

export function Plate({
  src,
  alt,
  placeholder = "No image",
}: {
  src?: string | null;
  alt: string;
  placeholder?: string;
}) {
  return (
    <div className="plate plate-frame">
      {src ? (
        // `alt` is required by the caller: a poster carries the act's name and
        // a screen-reader user needs it as much as anyone.
        <img src={src} alt={alt} loading="lazy" />
      ) : (
        <span className="plate-empty">{placeholder}</span>
      )}
    </div>
  );
}

export function Rule({ strong = false }: { strong?: boolean }) {
  return strong ? <div className="rule-strong" /> : <hr className="hr" />;
}

export function SectionHead({ title, count }: { title: string; count?: string }) {
  return (
    <>
      <div className="section-head">
        <h2>{title}</h2>
        {count ? <span className="section-count">{count}</span> : null}
      </div>
      <Rule strong />
    </>
  );
}

export function Spinner({ label = "Setting the page" }: { label?: string }) {
  return (
    <p className="spinner" role="status">
      <Loader size={14} aria-hidden style={{ verticalAlign: "-2px" }} /> {label}…
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function Notice({
  children,
  tone = "info",
}: {
  children: ReactNode;
  tone?: "info" | "error";
}) {
  return (
    <p
      className={tone === "error" ? "notice notice-error" : "notice"}
      // Errors are announced; ordinary notices are not, so a screen reader is
      // not interrupted by incidental copy.
      role={tone === "error" ? "alert" : undefined}
    >
      {children}
    </p>
  );
}

export function SaveButton({
  saved,
  onToggle,
  label = "Keep for later",
}: {
  saved: boolean;
  onToggle: () => void;
  label?: string;
}) {
  return (
    <button
      type="button"
      className="btn btn-secondary"
      onClick={onToggle}
      aria-pressed={saved}
      aria-label={saved ? "Remove from your list" : label}
    >
      <Bookmark size={16} fill={saved ? "currentColor" : "none"} aria-hidden />
    </button>
  );
}

export function Tag({ children }: { children: ReactNode }) {
  return <span className="tag tag-outline">{children}</span>;
}
