// The alias codemod against a fixture tree built in a temp dir: one-level,
// two-level, `export … from`, dynamic import, single AND double quotes, a
// `./sibling` that must stay, and a `../` that resolves OUTSIDE src/ (no
// alias exists for it, so it must be left for the lint report).
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { aliasFor, aliasImports, listSourceFiles, main, rewriteSource } from "../scripts/lib/alias-imports.mjs";

const CLI = path.join(import.meta.dirname, "..", "scripts", "alias-imports.mjs");

const FIXTURE = {
  "src/components/deep/card.tsx": [
    'import { api } from "../../services/api";',
    "import type { User } from '../../types/user';",
    'import { helper } from "./helper";',
    'export { format } from "../../utils/format";',
    'const lazy = () => import("../../utils/lazy");',
    'import "../../styles/global.css";',
    'import { outside } from "../../../tooling/outside";',
    "export const card = { api, helper, lazy, outside };",
  ].join("\n"),
  "src/components/deep/helper.ts": 'export const helper = 1;\nimport "./nothing-to-do";\n',
  "src/services/api.test.ts": 'import { api } from "./api";\nexport const t = api;\n',
  "src/services/api.ts": 'import { format } from "../utils/format";\nexport const api = format;\n',
  "src/services/notes.md": "not source: [x](../utils/format)\n",
  "src/utils/format.ts": "export const format = 1;\n",
  "tooling/outside.ts": "export const outside = 1;\n",
};

// One fixture tree per test, so a rewriting test cannot leak into the next.
const state = { root: "" };
const rootOf = () => state.root;
const sourceOf = () => path.join(rootOf(), "src");
const read = (relative) => fs.readFileSync(path.join(rootOf(), relative), "utf8");
const collect = (lines) => ({ log: (line) => { lines.push(line); } });

beforeEach(() => {
  state.root = fs.mkdtempSync(path.join(os.tmpdir(), "alias-imports-"));
  for (const [relative, content] of Object.entries(FIXTURE)) {
    const full = path.join(rootOf(), relative);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, content);
  }
});

afterEach(() => {
  fs.rmSync(rootOf(), { force: true, recursive: true });
});

describe("aliasFor", () => {
  const from = (relative, specifier) => aliasFor(path.join(sourceOf(), relative), specifier, sourceOf());

  it("maps a parent-relative target under src to @/", () => {
    expect(from("a/b/c.ts", "../../x/y")).toBe("@/x/y");
    expect(from("a/b/c.ts", "../../x/y.js")).toBe("@/x/y.js");
  });

  it("refuses targets outside src and src itself", () => {
    expect(from("a/c.ts", "../../tooling/x")).toBeNull();
    expect(from("a/c.ts", "..")).toBeNull();
  });
});

describe("rewriteSource", () => {
  it("rewrites every import form and keeps the quote style", () => {
    const file = path.join(sourceOf(), "components/deep/card.tsx");
    const { count, text } = rewriteSource(file, FIXTURE["src/components/deep/card.tsx"], sourceOf());
    expect(count).toBe(5);
    expect(text).toContain('import { api } from "@/services/api";');
    expect(text).toContain("import type { User } from '@/types/user';");
    expect(text).toContain('export { format } from "@/utils/format";');
    expect(text).toContain('import("@/utils/lazy")');
    expect(text).toContain('import "@/styles/global.css";');
    // Untouched: the sibling and the import that leaves src/.
    expect(text).toContain('from "./helper"');
    expect(text).toContain('from "../../../tooling/outside"');
  });

  it("reports zero for a file with nothing to do", () => {
    const file = path.join(sourceOf(), "components/deep/helper.ts");
    expect(rewriteSource(file, FIXTURE["src/components/deep/helper.ts"], sourceOf())).toEqual({
      count: 0,
      text: FIXTURE["src/components/deep/helper.ts"],
    });
  });
});

describe("aliasImports", () => {
  it("walks only source files and writes only changed ones", () => {
    expect(listSourceFiles(sourceOf()).map((file) => path.relative(rootOf(), file))).toEqual([
      "src/components/deep/card.tsx",
      "src/components/deep/helper.ts",
      "src/services/api.test.ts",
      "src/services/api.ts",
      "src/utils/format.ts",
    ]);
    expect(aliasImports(rootOf())).toEqual({ files: 2, imports: 6 });
    expect(read("src/services/api.ts")).toContain('from "@/utils/format"');
    expect(read("src/services/api.test.ts")).toBe(FIXTURE["src/services/api.test.ts"]);
    expect(read("src/services/notes.md")).toBe(FIXTURE["src/services/notes.md"]);
    // Idempotent: a second pass finds nothing.
    expect(aliasImports(rootOf())).toEqual({ files: 0, imports: 0 });
  });

  it("honours a non-default source dir", () => {
    fs.renameSync(sourceOf(), path.join(rootOf(), "lib"));
    expect(aliasImports(rootOf(), "lib")).toEqual({ files: 2, imports: 6 });
  });

  it("fails loudly on a missing source dir", () => {
    expect(() => aliasImports(rootOf(), "nope")).toThrow(/no such directory/);
  });
});

describe("main", () => {
  it("prints usage and exits 2 without a root", () => {
    const lines = [];
    expect(main([], collect(lines))).toBe(2);
    expect(lines[0]).toMatch(/^usage:/);
  });

  it("reports the count and exits 0", () => {
    const lines = [];
    expect(main([rootOf()], collect(lines))).toBe(0);
    expect(lines[0]).toBe(`alias-imports: rewrote 6 import(s) in 2 file(s) under ${sourceOf()}`);
  });

  it("runs as a CLI", () => {
    const stdout = execFileSync(process.execPath, [CLI, rootOf()], { encoding: "utf8" });
    expect(stdout).toContain("rewrote 6 import(s) in 2 file(s)");
    expect(read("src/services/api.ts")).toContain("@/utils/format");
  });
});
