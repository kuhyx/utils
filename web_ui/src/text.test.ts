import { describe, expect, it } from "vitest";

import { fuzzyMatch } from "./text.ts";

describe("fuzzyMatch", () => {
  it("matches everything on an empty query", () => {
    expect(fuzzyMatch("", "anything")).toBe(true);
  });

  it("matches an exact substring", () => {
    expect(fuzzyMatch("cat", "concatenate")).toBe(true);
  });

  it("matches a non-adjacent subsequence", () => {
    expect(fuzzyMatch("cne", "concatenate")).toBe(true);
  });

  it("ignores case on both sides", () => {
    expect(fuzzyMatch("CaT", "concatenate")).toBe(true);
  });

  it("rejects characters that appear out of order", () => {
    expect(fuzzyMatch("tac", "cat")).toBe(false);
  });

  it("rejects a query with a character the target lacks", () => {
    expect(fuzzyMatch("dog", "concatenate")).toBe(false);
  });

  it("rejects a query longer than the target", () => {
    expect(fuzzyMatch("catalogue", "cat")).toBe(false);
  });
});
