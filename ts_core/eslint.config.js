// Type-aware flat config, mirroring web_ui's so the two shared TS packages
// hold an identical bar.
import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "coverage", "eslint.config.js"] },
  { linterOptions: { reportUnusedDisableDirectives: "error" } },

  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,

  {
    files: ["**/*.ts"],
    languageOptions: {
      parserOptions: {
        project: ["./tsconfig.lint.json"],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // Every exported symbol crosses a package boundary, so an explicit
      // return type is documentation, not ceremony.
      "@typescript-eslint/explicit-function-return-type": "error",
    },
  },
);
