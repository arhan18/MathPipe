import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { MemoryStorage, storageKey } from "../dist/index.js";
import { R2Storage, isR2Configured, r2ConfigFromEnv } from "../dist/r2.js";

describe("storage", () => {
  it("builds safe storage keys", () => {
    assert.equal(storageKey("u1", "j1", "source.pdf"), "users/u1/jobs/j1/source.pdf");
    assert.equal(storageKey("../../etc", "j1", "source.pdf"), "users/etc/jobs/j1/source.pdf");
  });

  it("memory store round-trips", async () => {
    const s = new MemoryStorage();
    await s.put("k", new Uint8Array([1, 2, 3]), { contentType: "application/pdf" });
    assert.equal((await s.get("k")).length, 3);
    assert.equal(await s.exists("k"), true);
    await s.delete("k");
    assert.equal(await s.exists("k"), false);
    await assert.rejects(() => s.get("k"));
  });

  it("R2 refuses without configuration", () => {
    assert.equal(isR2Configured({}), false);
    assert.equal(r2ConfigFromEnv({}), null);
    assert.throws(() => new R2Storage(), /not configured/);
  });
});
