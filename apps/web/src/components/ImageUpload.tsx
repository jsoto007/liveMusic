/**
 * The picture control: pick an image, push it straight to R2, tell the caller.
 *
 * One implementation, used by the band photo and the show poster. They had
 * drifted — the poster could only ever be attached during the post flow, so a
 * band whose upload failed was told "you can add it later" with nothing
 * anywhere that let them. Sharing the control is what makes that sentence
 * true.
 *
 * The bytes never touch our API (CLAUDE.md §4): the server signs a PUT scoped
 * to one key and one type, and the browser submits to storage directly.
 * Everything here is the wrapper around `uploadDirect`.
 *
 * The type check below is a courtesy to the reader, not a control. The server
 * re-checks against its own allowlist, and the size cap is enforced when the
 * upload is completed — a client that skipped this entirely would still be
 * refused.
 */

import { useId, useRef, useState } from "react";
import { ImagePlus } from "lucide-react";
import {
  ACCEPTED_IMAGE_TYPES,
  inferContentType,
  uploadDirect,
  type UploadPurpose,
} from "@live-msc/shared";

import { api } from "../lib/api";

interface ImageUploadProps {
  purpose: UploadPurpose;
  targetId: string;
  /** True once there is an image, so the button reads "replace" not "add". */
  hasImage: boolean;
  addLabel: string;
  replaceLabel: string;
  /** Ran after a successful upload — usually a reload of the owning resource. */
  onUploaded: () => void | Promise<void>;
  /** Surfaced by the caller, which owns the page's error region. */
  onError: (message: string | null) => void;
}

export function ImageUpload({
  purpose,
  targetId,
  hasImage,
  addLabel,
  replaceLabel,
  onUploaded,
  onError,
}: ImageUploadProps) {
  const input = useRef<HTMLInputElement | null>(null);
  const [uploading, setUploading] = useState(false);
  const inputId = useId();

  async function send(file: File) {
    onError(null);
    const contentType = inferContentType(file.name, file.type);
    if (!contentType || !ACCEPTED_IMAGE_TYPES.includes(contentType as never)) {
      onError("That is not an image format we accept. Use a JPEG, PNG, WebP or AVIF.");
      return;
    }

    setUploading(true);
    try {
      await uploadDirect(api, { purpose, targetId, contentType, sizeBytes: file.size }, file);
      await onUploaded();
    } catch (error) {
      // `uploadDirect` throws an UploadError carrying the server's own
      // message, which is written to be shown — including the one that says
      // storage is unavailable. Swallowing it for a generic string is how a
      // misconfigured deployment looks like a broken button.
      onError(error instanceof Error ? error.message : "The upload failed.");
    } finally {
      setUploading(false);
      // Cleared so choosing the same file twice fires `change` again — after a
      // failed attempt the obvious thing to do is retry with the same file.
      if (input.current) input.current.value = "";
    }
  }

  return (
    <>
      <input
        ref={input}
        id={inputId}
        type="file"
        accept={ACCEPTED_IMAGE_TYPES.join(",")}
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void send(file);
        }}
      />
      <button
        type="button"
        className="btn btn-secondary btn-block"
        onClick={() => input.current?.click()}
        disabled={uploading}
        style={{ marginTop: "var(--space-2)" }}
      >
        <ImagePlus size={15} aria-hidden />
        {uploading ? "Uploading…" : hasImage ? replaceLabel : addLabel}
      </button>
    </>
  );
}
