// The JSON/MJS bases are data, but data a consumer's tool parses: a typo in
// one is a broken lint/knip/jscpd run in every repo at once.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { strykerBase } from "../stryker.base.mjs";

const ROOT = path.join(import.meta.dirname, "..");

describe("bases", () => {
  it("stryker never breaks the build on score", () => {
    expect(strykerBase.thresholds.break).toBeNull();
    expect(strykerBase.testRunner).toBe("vitest");
    expect(strykerBase.mutate).toContain("!src/**/*.test.*");
  });

  it("tsconfig base carries the two flags the article names", () => {
    const raw = fs.readFileSync(path.join(ROOT, "tsconfig.base.json"), "utf8");
    // JSONC: strip the comment lines before parsing.
    const json = JSON.parse(raw.split("\n").filter((line) => !line.trimStart().startsWith("//")).join("\n"));
    expect(json.compilerOptions.strict).toBe(true);
    expect(json.compilerOptions.noUncheckedIndexedAccess).toBe(true);
    expect(json.compilerOptions.exactOptionalPropertyTypes).toBe(true);
    expect(json.compilerOptions.outDir).toBeUndefined();
  });

  it("knip and jscpd bases are valid JSON with exit-1 semantics", () => {
    const knip = JSON.parse(fs.readFileSync(path.join(ROOT, "knip.base.json"), "utf8"));
    expect(Object.values(knip.rules).every((level) => level === "error")).toBe(true);
    const jscpd = JSON.parse(fs.readFileSync(path.join(ROOT, "jscpd.base.json"), "utf8"));
    expect(jscpd.exitCode).toBe(1);
    expect(jscpd.threshold).toBe(0);
  });

  it("every export in package.json points at a shipped file", () => {
    const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8"));
    for (const target of Object.values(manifest.exports)) {
      expect(fs.existsSync(path.join(ROOT, target)), target).toBe(true);
      const [, top] = target.split("/", 2);
      expect(manifest.files, `${top} missing from "files"`).toContain(top);
    }
  });
});
