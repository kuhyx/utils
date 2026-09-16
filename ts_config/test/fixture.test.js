// Runs the real preset over the fixture mini-repo and checks that every
// planted violation is caught by the rule the table names, and that the
// clean files stay clean.
//
// The lint runs as the CLI in a child process, exactly as a consumer's
// pre-commit hook runs it. It also keeps the preset modules out of this
// process: v8 coverage merges the natively-loaded copies ESLint imports with
// the vitest-transformed ones the unit tests import, and the merge reports
// executed lines as uncovered.
import { execFileSync } from "node:child_process";
import path from "node:path";
import { beforeAll, describe, expect, it } from "vitest";

import { CLEAN, EXPECTED } from "./expected.js";

const FIXTURE = path.join(import.meta.dirname, "fixture");
const ESLINT_BIN = path.join(import.meta.dirname, "..", "node_modules", "eslint", "bin", "eslint.js");

/** @type {Map<string, Set<string>>} relative path -> rule ids reported */
const found = new Map();

beforeAll(() => {
  let stdout;
  try {
    stdout = execFileSync(process.execPath, [ESLINT_BIN, ".", "--format", "json"], {
      cwd: FIXTURE,
      encoding: "utf8",
    });
  } catch (error) {
    // Planted violations make ESLint exit 1; the JSON report is still on stdout.
    stdout = error.stdout;
  }
  const results = JSON.parse(stdout.slice(stdout.indexOf("[")));
  for (const result of results) {
    const relative = path.relative(FIXTURE, result.filePath);
    found.set(relative, new Set(result.messages.map((m) => m.ruleId)));
  }
}, 120_000);

describe("planted violations", () => {
  for (const [file, rules] of Object.entries(EXPECTED)) {
    for (const rule of rules) {
      it(`${file}: ${rule}`, () => {
        expect([...(found.get(file) ?? [])]).toContain(rule);
      });
    }
  }
});

describe("clean files", () => {
  for (const file of CLEAN) {
    it(`${file} reports nothing`, () => {
      expect([...(found.get(file) ?? [])]).toEqual([]);
    });
  }
});

it("every fixture file is accounted for", () => {
  const expectedFiles = new Set(Object.keys(EXPECTED));
  const known = expectedFiles.union(new Set(CLEAN));
  for (const file of found.keys()) {
    expect(known.has(file), `unlisted fixture file: ${file}`).toBe(true);
  }
});
