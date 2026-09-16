import { describe, expect, it } from "vitest";

import { keyTarget, steppedValue } from "./stepped-value.ts";

/** Ten evenly spaced values, so a quantile fraction maps to a predictable value. */
const VALUES = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90];

describe("keyTarget", () => {
  it("leaves keys the slider does not own to the browser", () => {
    expect(keyTarget("Tab", VALUES, 30)).toBeUndefined();
    expect(keyTarget("a", VALUES, 30)).toBeUndefined();
  });

  it("maps every owned key onto the distribution", () => {
    expect(keyTarget("ArrowLeft", VALUES, 30)).toBe(20);
    expect(keyTarget("ArrowDown", VALUES, 30)).toBe(20);
    expect(keyTarget("ArrowRight", VALUES, 30)).toBe(40);
    expect(keyTarget("ArrowUp", VALUES, 30)).toBe(40);
    expect(keyTarget("Home", VALUES, 30)).toBe(0);
    expect(keyTarget("End", VALUES, 30)).toBe(90);
  });
});

describe("steppedValue", () => {
  it("advances one sample at a time", () => {
    expect(steppedValue(VALUES, 30, 1)).toBe(40);
  });

  it("moves backwards for a negative delta", () => {
    expect(steppedValue(VALUES, 30, -1)).toBe(20);
  });

  it("clamps at the top", () => {
    expect(steppedValue(VALUES, 90, 5)).toBe(90);
  });

  it("clamps at the bottom", () => {
    expect(steppedValue(VALUES, 0, -5)).toBe(0);
  });

  it("rounds a between-samples value to a real sample", () => {
    expect(steppedValue(VALUES, 34, 1)).toBe(40);
  });

  it("returns the current sample for a zero delta", () => {
    expect(steppedValue(VALUES, 30, 0)).toBe(30);
  });

  describe("on a lumpy distribution", () => {
    // The shape that actually broke in the browser: awesome-mcp-explorer's
    // star counts hold ~1500 duplicate zeros, so an index step inside the run
    // moved the index but not the value, and the arrow key looked dead.
    const LUMPY = [...Array.from({ length: 50 }, () => 0), 5, 5, 5, 100, 5000];

    it("escapes a run of duplicates instead of stalling", () => {
      expect(steppedValue(LUMPY, 0, 1)).toBe(5);
    });

    it("keeps stepping past the second run", () => {
      expect(steppedValue(LUMPY, 5, 1)).toBe(100);
    });

    it("steps back out of a run", () => {
      expect(steppedValue(LUMPY, 5, -1)).toBe(0);
    });

    it("counts distinct values for a multi-step jump", () => {
      expect(steppedValue(LUMPY, 0, 2)).toBe(100);
    });

    it("clamps at the top rather than running off the end", () => {
      expect(steppedValue(LUMPY, 5000, 1)).toBe(5000);
    });

    it("clamps at the bottom", () => {
      expect(steppedValue(LUMPY, 0, -1)).toBe(0);
    });
  });
});
