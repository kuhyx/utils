// The factories: what each option adds, and what a bad call refuses.
import { describe, expect, it } from "vitest";

import { base, DEFAULT_IGNORES } from "../eslint/base.js";
import { boundaries, DEFAULT_ALLOW, folderElements } from "../eslint/boundaries.js";
import fast from "../eslint/fast.js";
import { defineConfig } from "../eslint/index.js";

const ROOT = import.meta.dirname;

/** Rule ids that appear anywhere in a flat config array. */
function ruleIds(config) {
  return new Set(config.flatMap((entry) => Object.keys(entry.rules ?? {})));
}

/** Plugin names registered anywhere in a flat config array. */
function pluginNames(config) {
  return new Set(config.flatMap((entry) => Object.keys(entry.plugins ?? {})));
}

describe("base()", () => {
  it("refuses to run without a tsconfigRootDir", () => {
    expect(() => base({})).toThrow(/tsconfigRootDir/);
    expect(() => base({ tsconfigRootDir: "" })).toThrow(/tsconfigRootDir/);
  });

  it("prepends the default ignores and keeps the caller's", () => {
    const [ignores] = base({ ignores: ["public"], tsconfigRootDir: ROOT });
    expect(ignores.ignores).toEqual([...DEFAULT_IGNORES, "public"]);
  });

  it("wires the type-aware parser at the given root", () => {
    const entry = base({ tsconfigRootDir: ROOT }).find(
      (candidate) => candidate.languageOptions?.parserOptions?.projectService === true,
    );
    expect(entry?.languageOptions.parserOptions.tsconfigRootDir).toBe(ROOT);
  });

  it("uses an explicit project list instead of the project service when given", () => {
    const entry = base({ project: ["./tsconfig.lint.json"], tsconfigRootDir: ROOT }).find(
      (candidate) => candidate.languageOptions?.parserOptions?.project,
    );
    expect(entry.languageOptions.parserOptions).toEqual({
      project: ["./tsconfig.lint.json"],
      tsconfigRootDir: ROOT,
    });
    expect(entry.languageOptions.parserOptions.projectService).toBeUndefined();
  });

  it("drops the alias-only import ban when asked", () => {
    expect(ruleIds(base({ tsconfigRootDir: ROOT }))).toContain("no-restricted-imports");
    expect(ruleIds(base({ aliasOnly: false, tsconfigRootDir: ROOT }))).not.toContain(
      "no-restricted-imports",
    );
  });
});

describe("boundaries()", () => {
  it("refuses an empty element list", () => {
    expect(() => boundaries({ elements: [], tsconfigRootDir: ROOT })).toThrow(/elements/);
    expect(() => boundaries({ tsconfigRootDir: ROOT })).toThrow(/elements/);
  });

  it("refuses to run without a tsconfigRootDir", () => {
    expect(() => boundaries({ elements: folderElements(["utils"]) })).toThrow(/tsconfigRootDir/);
  });

  it("emits a policy only for element types the repo declared", () => {
    const [entry] = boundaries({
      elements: folderElements(["components", "services"]),
      tsconfigRootDir: ROOT,
    });
    const { policies } = entry.rules["boundaries/dependencies"][1];
    const froms = policies.filter((p) => p.from.element).map((p) => p.from.element.type);
    expect(froms.toSorted((a, b) => a.localeCompare(b))).toEqual(["components", "services"]);
    const components = policies.find((p) => p.from.element?.type === "components");
    // utils/types are not declared here, so they are filtered out of the
    // allow list rather than left dangling.
    expect(components.allow.to.element.types.anyOf).toEqual(["services", "components"]);
  });

  it("merges a repo's allow override over one layer only", () => {
    const [entry] = boundaries({
      allow: { services: ["components"] },
      elements: folderElements(["components", "services"]),
      tsconfigRootDir: ROOT,
    });
    const { policies } = entry.rules["boundaries/dependencies"][1];
    const services = policies.find((p) => p.from.element?.type === "services");
    expect(services.allow.to.element.types.anyOf).toEqual(["components"]);
    expect(DEFAULT_ALLOW.services).toEqual(["utils", "types", "services"]);
  });

  it("points the TS resolver at the repo root and marks tests", () => {
    const [entry] = boundaries({
      elements: folderElements(["utils"], "lib"),
      testFiles: ["**/*.spec.ts"],
      tsconfigRootDir: ROOT,
    });
    expect(entry.settings["boundaries/elements"]).toEqual([{ pattern: "lib/utils", type: "utils" }]);
    expect(entry.settings["boundaries/files"]).toEqual([{ category: "test", pattern: ["**/*.spec.ts"] }]);
    expect(entry.settings["import/resolver"].typescript.project).toBe(ROOT);
    expect(entry.settings["boundaries/root-path"]).toBe(ROOT);
  });
});

describe("defineConfig()", () => {
  it("stacks nothing optional by default except vitest", () => {
    const plugins = pluginNames(defineConfig({ tsconfigRootDir: ROOT }));
    expect(plugins).toContain("vitest");
    expect(plugins).not.toContain("boundaries");
    expect(plugins).not.toContain("react-hooks");
    expect(plugins).not.toContain("playwright");
  });

  it("stacks every layer when asked and appends overrides last", () => {
    const override = { rules: { "unicorn/no-null": "error" } };
    const config = defineConfig({
      boundaries: { elements: folderElements(["components"]) },
      overrides: [override],
      playwright: true,
      react: true,
      tsconfigRootDir: ROOT,
      vitest: false,
    });
    const plugins = pluginNames(config);
    for (const name of ["boundaries", "react-hooks", "playwright", "jsx-a11y"]) {
      expect(plugins).toContain(name);
    }
    expect(plugins).not.toContain("vitest");
    expect(config.at(-1)).toBe(override);
  });
});

describe("fast", () => {
  it("is type-free: no projectService anywhere", () => {
    const typeAware = fast.some((entry) => entry.languageOptions?.parserOptions?.projectService);
    expect(typeAware).toBe(false);
    expect(ruleIds(fast)).toContain("@typescript-eslint/no-explicit-any");
  });
});
