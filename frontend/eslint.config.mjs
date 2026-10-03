import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // An effect's return value is its cleanup. `useEffect(() => el.scrollIntoView())` returns a Promise in
    // newer browsers, which React then calls and crashes on. Always use a block body.
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.name=/^use(Layout|Insertion)?Effect$/] > ArrowFunctionExpression[expression=true]",
          message: "Use a block body in effects: an expression body becomes the effect's cleanup.",
        },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "lib/api/gen/**", // generated from the backend OpenAPI spec
  ]),
]);

export default eslintConfig;
