/**
 * Cloudflare R2 adapter (S3-compatible). Activates only with R2_* env;
 * otherwise construction throws a typed error instead of failing later.
 */
import {
  DeleteObjectCommand,
  GetObjectCommand,
  HeadObjectCommand,
  PutObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import type { ObjectStorage, PutOptions, StoredObject } from "./index.js";

export interface R2Config {
  accountId: string;
  accessKeyId: string;
  secretAccessKey: string;
  bucket: string;
}

export function r2ConfigFromEnv(env: NodeJS.ProcessEnv = process.env): R2Config | null {
  const accountId = env.CLOUDFLARE_ACCOUNT_ID ?? "";
  const accessKeyId = env.R2_ACCESS_KEY_ID ?? "";
  const secretAccessKey = env.R2_SECRET_ACCESS_KEY ?? "";
  const bucket = env.R2_BUCKET_NAME ?? "";
  if (!accountId || !accessKeyId || !secretAccessKey || !bucket) return null;
  return { accountId, accessKeyId, secretAccessKey, bucket };
}

export function isR2Configured(env: NodeJS.ProcessEnv = process.env): boolean {
  return r2ConfigFromEnv(env) !== null;
}

export class R2Storage implements ObjectStorage {
  private client: S3Client;
  private bucket: string;

  constructor(config?: R2Config) {
    const cfg = config ?? r2ConfigFromEnv();
    if (!cfg) throw new Error("R2 is not configured (R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET_NAME / CLOUDFLARE_ACCOUNT_ID).");
    this.bucket = cfg.bucket;
    this.client = new S3Client({
      region: "auto",
      endpoint: `https://${cfg.accountId}.r2.cloudflarestorage.com`,
      credentials: { accessKeyId: cfg.accessKeyId, secretAccessKey: cfg.secretAccessKey },
    });
  }

  async put(key: string, body: Uint8Array, options?: PutOptions): Promise<StoredObject> {
    const res = await this.client.send(
      new PutObjectCommand({ Bucket: this.bucket, Key: key, Body: body, ContentType: options?.contentType }),
    );
    return { key, size: body.length, etag: res.ETag };
  }

  async get(key: string): Promise<Uint8Array> {
    const res = await this.client.send(new GetObjectCommand({ Bucket: this.bucket, Key: key }));
    if (!res.Body) throw Object.assign(new Error(`not found: ${key}`), { code: "NOT_FOUND" });
    return res.Body.transformToByteArray();
  }

  async delete(key: string): Promise<void> {
    await this.client.send(new DeleteObjectCommand({ Bucket: this.bucket, Key: key }));
  }

  async exists(key: string): Promise<boolean> {
    try {
      await this.client.send(new HeadObjectCommand({ Bucket: this.bucket, Key: key }));
      return true;
    } catch {
      return false;
    }
  }

  async presignedDownloadUrl(key: string, expiresSeconds = 3600): Promise<string> {
    return getSignedUrl(this.client, new GetObjectCommand({ Bucket: this.bucket, Key: key }), {
      expiresIn: expiresSeconds,
    });
  }
}
