/**
 * @mathpipe/storage — object storage seam (§22, §63).
 *
 * R2 implementation speaks S3. Never expose raw keys: downloads go through
 * short-lived presigned URLs checked against the requesting user. Never use
 * user filenames as storage keys — stable IDs only.
 */

export interface PutOptions {
  contentType?: string;
  expiresAt?: string;
}

export interface StoredObject {
  key: string;
  size: number;
  etag?: string;
}

export interface ObjectStorage {
  put(key: string, body: Uint8Array, options?: PutOptions): Promise<StoredObject>;
  get(key: string): Promise<Uint8Array>;
  delete(key: string): Promise<void>;
  exists(key: string): Promise<boolean>;
  presignedDownloadUrl(key: string, expiresSeconds?: number): Promise<string>;
}

/** Storage key layout: users/{userId}/jobs/{jobId}/{purpose}[...]. */
export function storageKey(userId: string, jobId: string, purpose: "source.pdf" | "output.docx" | string, suffix = ""): string {
  const safe = (s: string) => s.replace(/[^a-zA-Z0-9_-]/g, "");
  return `users/${safe(userId)}/jobs/${safe(jobId)}/${purpose}${suffix}`;
}

/** In-memory implementation. Tests and local dev only. */
export { R2Storage, isR2Configured, r2ConfigFromEnv } from "./r2.js";
export type { R2Config } from "./r2.js";
export { SupabaseStorage, DOCUMENTS_BUCKET } from "./supabase.js";export class MemoryStorage implements ObjectStorage {
  private blobs = new Map<string, { data: Uint8Array; contentType?: string }>();

  async put(key: string, body: Uint8Array, options?: PutOptions): Promise<StoredObject> {
    this.blobs.set(key, { data: body.slice(), contentType: options?.contentType });
    return { key, size: body.length, etag: `mem-${body.length}` };
  }

  async get(key: string): Promise<Uint8Array> {
    const found = this.blobs.get(key);
    if (!found) throw Object.assign(new Error(`not found: ${key}`), { code: "NOT_FOUND" });
    return found.data.slice();
  }

  async delete(key: string): Promise<void> {
    this.blobs.delete(key);
  }

  async exists(key: string): Promise<boolean> {
    return this.blobs.has(key);
  }

  async presignedDownloadUrl(key: string): Promise<string> {
    if (!this.blobs.has(key)) throw Object.assign(new Error(`not found: ${key}`), { code: "NOT_FOUND" });
    return `memory://${key}`;
  }
}
