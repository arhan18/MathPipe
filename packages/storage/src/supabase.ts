/**
 * Supabase Storage adapter — same project and keys as the database.
 * Bucket is private; downloads go through short-lived signed URLs.
 * RLS on storage.objects mirrors the table policies: users touch only
 * their own `users/{userId}/...` prefix, service role bypasses.
 */
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import type { ObjectStorage, PutOptions, StoredObject } from "./index.js";

export const DOCUMENTS_BUCKET = "mathpipe-files";

export class SupabaseStorage implements ObjectStorage {
  private db: SupabaseClient;
  private bucket: string;

  constructor(bucket: string = DOCUMENTS_BUCKET, client?: SupabaseClient) {
    this.bucket = bucket;
    this.db =
      client ??
      (() => {
        const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
        const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
        if (!url || !key) throw new Error("Supabase storage is not configured.");
        return createClient(url, key, { auth: { persistSession: false } });
      })();
  }

  async put(key: string, body: Uint8Array, options?: PutOptions): Promise<StoredObject> {
    const { error } = await this.db.storage
      .from(this.bucket)
      .upload(key, body, { contentType: options?.contentType ?? "application/octet-stream", upsert: true });
    if (error) throw new Error(`storage put failed: ${error.message}`);
    return { key, size: body.length };
  }

  async get(key: string): Promise<Uint8Array> {
    const { data, error } = await this.db.storage.from(this.bucket).download(key);
    if (error || !data) throw Object.assign(new Error(`not found: ${key}`), { code: "NOT_FOUND" });
    return new Uint8Array(await data.arrayBuffer());
  }

  async delete(key: string): Promise<void> {
    const { error } = await this.db.storage.from(this.bucket).remove([key]);
    if (error) throw new Error(`storage delete failed: ${error.message}`);
  }

  async exists(key: string): Promise<boolean> {
    const dir = key.includes("/") ? key.slice(0, key.lastIndexOf("/")) : "";
    const name = key.slice(key.lastIndexOf("/") + 1);
    const { data } = await this.db.storage.from(this.bucket).list(dir || undefined, { search: name });
    return (data ?? []).some((f) => f.name === name);
  }

  async presignedDownloadUrl(key: string, expiresSeconds = 3600): Promise<string> {
    const { data, error } = await this.db.storage.from(this.bucket).createSignedUrl(key, expiresSeconds);
    if (error || !data?.signedUrl) throw new Error(`signed URL failed: ${error?.message ?? "unknown"}`);
    return data.signedUrl;
  }
}
