import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { isDbConfigured, createServiceClient } from "../dist/index.js";

describe("db configuration", () => {
  it("reports unconfigured without env and refuses service client", () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.SUPABASE_URL;
    delete process.env.SUPABASE_SERVICE_ROLE_KEY;
    assert.equal(isDbConfigured(), false);
    assert.throws(() => createServiceClient(), /not configured/);
  });
});
