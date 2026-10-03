import { defineConfig } from "@hey-api/openapi-ts";

// One OpenAPI spec (exported by `keel openapi`) → one generated, typed client. Regenerated in CI.
export default defineConfig({
  input: "../openapi.json",
  output: "lib/api/gen",
  plugins: ["@hey-api/client-fetch", "@hey-api/typescript", "@hey-api/sdk"],
});
