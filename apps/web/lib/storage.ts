import { MemoryStorage, SupabaseStorage, R2Storage, isR2Configured, type ObjectStorage } from "@mathpipe/storage";

let memory: ObjectStorage | null = null;

/**
 * Storage priority: R2 when configured, Supabase Storage when the database
 * is configured, in-memory scaffold otherwise. Callers never branch.
 */
export function getObjectStorage(): ObjectStorage {
  if (isR2Configured()) return new R2Storage();
  if (process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL) {
    try {
      return new SupabaseStorage();
    } catch {
      // fall through to memory
    }
  }
  memory ??= new MemoryStorage();
  return memory;
}
