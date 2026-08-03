/**
 * Direct-to-R2 upload, shared by web and mobile.
 *
 * The file never passes through the API. The server issues a presigned POST
 * scoped to one key, one content type and one size cap; the client submits the
 * bytes straight to R2 and then asks the server to verify and record it.
 *
 * The field order in the form matters: S3-compatible storage requires every
 * policy field to precede `file`, and silently rejects the request otherwise.
 */

import type { ApiClient, ApiResult } from "./client";
import type { UploadPurpose, UploadTicket } from "./types";

export interface UploadRequest {
  purpose: UploadPurpose;
  targetId: string;
  contentType: string;
  sizeBytes?: number;
}

/** What a platform hands us to upload: a browser File/Blob, or an RN file ref. */
export type UploadableFile =
  | Blob
  | { uri: string; name: string; type: string };

export interface UploadOptions {
  /** Metadata recorded on completion (a sample title, a duration). */
  completion?: Record<string, unknown>;
  onProgress?: (fraction: number) => void;
}

export class UploadError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code = "UPLOAD_FAILED", status = 0) {
    super(message);
    this.name = "UploadError";
    this.code = code;
    this.status = status;
  }
}

async function requestTicket(
  api: ApiClient,
  request: UploadRequest,
): Promise<UploadTicket> {
  const result = await api.post<UploadTicket>("/api/v1/uploads", {
    purpose: request.purpose,
    target_id: request.targetId,
    content_type: request.contentType,
    size_bytes: request.sizeBytes,
  });
  if (!result.ok || !result.data) {
    throw new UploadError(
      result.ok ? "The upload could not be started." : result.error,
      result.ok ? "UPLOAD_FAILED" : (result.code ?? "UPLOAD_FAILED"),
      result.status,
    );
  }
  return result.data;
}

function buildForm(ticket: UploadTicket, file: UploadableFile): FormData {
  const form = new FormData();
  // Policy fields first — `file` must be last.
  for (const [key, value] of Object.entries(ticket.fields)) {
    form.append(key, value);
  }
  // React Native's FormData accepts a {uri, name, type} descriptor; the web's
  // takes a Blob. Both are correct for their platform.
  form.append("file", file as Blob);
  return form;
}

async function putToStorage(ticket: UploadTicket, file: UploadableFile): Promise<void> {
  const response = await fetch(ticket.url, {
    method: "POST",
    body: buildForm(ticket, file),
    // No Authorization, no cookies: the signature IS the credential, and
    // sending ours to a third-party origin would leak it.
    credentials: "omit",
  });

  if (!response.ok) {
    // R2 enforces the size cap through the policy's content-length-range, so
    // an oversized file fails here rather than at completion.
    if (response.status === 400 || response.status === 413) {
      throw new UploadError(
        "That file is larger than we accept, or is not the format you chose.",
        "FILE_REJECTED",
        response.status,
      );
    }
    throw new UploadError("The file could not be uploaded.", "UPLOAD_FAILED", response.status);
  }
}

/**
 * Run the full flow: request a ticket, push the bytes, confirm.
 *
 * If the confirm step fails the ticket is abandoned so the orphaned object is
 * swept promptly rather than sitting in the bucket until it expires.
 */
export async function uploadDirect<T>(
  api: ApiClient,
  request: UploadRequest,
  file: UploadableFile,
  options: UploadOptions = {},
): Promise<T> {
  const ticket = await requestTicket(api, request);
  options.onProgress?.(0.1);

  try {
    await putToStorage(ticket, file);
  } catch (error) {
    await api.delete(`/api/v1/uploads/${ticket.upload_id}`).catch(() => undefined);
    throw error;
  }
  options.onProgress?.(0.8);

  const completed: ApiResult<T> = await api.post<T>(
    `/api/v1/uploads/${ticket.upload_id}/complete`,
    options.completion ?? {},
  );

  if (!completed.ok || completed.data === undefined) {
    throw new UploadError(
      completed.ok ? "The upload could not be finished." : completed.error,
      completed.ok ? "UPLOAD_FAILED" : (completed.code ?? "UPLOAD_FAILED"),
      completed.status,
    );
  }

  options.onProgress?.(1);
  return completed.data;
}

/** Content types the server will sign for. Mirrors `services/r2_storage.py`. */
export const ACCEPTED_AUDIO_TYPES = [
  "audio/mpeg",
  "audio/mp4",
  "audio/aac",
  "audio/ogg",
  "audio/opus",
  "audio/wav",
  "audio/x-wav",
  "audio/flac",
  "audio/webm",
] as const;

export const ACCEPTED_IMAGE_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/avif",
] as const;

/**
 * Best-effort content type for a file whose `type` the platform left blank —
 * a known browser quirk for some audio formats. The server re-checks against
 * its own allowlist regardless, so a wrong guess is refused, not trusted.
 */
export function inferContentType(name: string, declared?: string): string | null {
  if (declared) return declared.split(";")[0]!.trim().toLowerCase();
  const extension = name.split(".").pop()?.toLowerCase();
  const byExtension: Record<string, string> = {
    mp3: "audio/mpeg",
    m4a: "audio/mp4",
    aac: "audio/aac",
    ogg: "audio/ogg",
    opus: "audio/opus",
    wav: "audio/wav",
    flac: "audio/flac",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    png: "image/png",
    webp: "image/webp",
    avif: "image/avif",
  };
  return extension ? (byExtension[extension] ?? null) : null;
}
