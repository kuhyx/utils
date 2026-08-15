import { describe, expect, it } from "vitest";

import {
  clamp01,
  fractionFromPointer,
  nth,
  quantileValue,
  valueQuantile,
} from "./quantile.ts";

describe("nth", () => {
  it("reads a value", () => {
    expect(nth([5, 6, 7], 1)).toBe(6);
  });

  it("throws for an index out of range", () => {
    expect(() => nth([1], 5)).toThrow(RangeError);
  });
});

describe("clamp01", () => {
  it("passes a value already in range", () => {
    expect(clamp01(0.5)).toBe(0.5);
  });

  it("clamps both ends", () => {
    expect(clamp01(-1)).toBe(0);
    expect(clamp01(2)).toBe(1);
  });
});

describe("quantileValue", () => {
  it("returns 0 for an empty distribution", () => {
    expect(quantileValue([], 0.5)).toBe(0);
  });

  it("returns the ends at f=0 and f=1", () => {
    expect(quantileValue([1, 2, 100], 0)).toBe(1);
    expect(quantileValue([1, 2, 100], 1)).toBe(100);
  });

  it("returns the MEDIAN at f=0.5, not the linear midpoint", () => {
    // The whole point of the quantile mapping, on a distribution shaped like
    // the real star counts (1 .. 59k, long tail). The linear midpoint of that
    // range is ~29,500 — above every server but one, which is exactly why a
    // plain min..max slider is useless here. The median is 3.
    expect(quantileValue([1, 2, 3, 4, 59_000], 0.5)).toBe(3);
  });

  it("interpolates between samples", () => {
    expect(quantileValue([0, 10], 0.5)).toBe(5);
  });

  it("clamps an out-of-range fraction", () => {
    expect(quantileValue([1, 5], -1)).toBe(1);
    expect(quantileValue([1, 5], 9)).toBe(5);
  });
});

describe("valueQuantile", () => {
  it("returns 0 for a distribution with fewer than two samples", () => {
    expect(valueQuantile([], 5)).toBe(0);
    expect(valueQuantile([5], 5)).toBe(0);
  });

  it("maps the ends to 0 and 1", () => {
    expect(valueQuantile([1, 2, 100], 1)).toBe(0);
    expect(valueQuantile([1, 2, 100], 100)).toBe(1);
  });

  it("clamps values beyond the ends", () => {
    expect(valueQuantile([1, 2, 100], -5)).toBe(0);
    expect(valueQuantile([1, 2, 100], 1000)).toBe(1);
  });

  it("inverts quantileValue", () => {
    const sorted = [1, 4, 9, 16, 25];
    for (const f of [0.25, 0.5, 0.75]) {
      const value = quantileValue(sorted, f);
      expect(valueQuantile(sorted, value)).toBeCloseTo(f, 1);
    }
  });

  it("interpolates strictly inside the range", () => {
    expect(valueQuantile([0, 10], 5)).toBeCloseTo(0.5);
  });
});

/** jsdom has no layout, so the rect is supplied rather than measured. */
const rect = (over: Partial<DOMRect> = {}): DOMRect =>
  ({ left: 100, width: 200, ...over }) as DOMRect;

describe("fractionFromPointer", () => {
  it("maps the pointer to a fraction of the track", () => {
    expect(fractionFromPointer(rect(), 200)).toBe(0.5);
  });

  it("clamps outside the track", () => {
    expect(fractionFromPointer(rect(), 0)).toBe(0);
    expect(fractionFromPointer(rect(), 9999)).toBe(1);
  });

  it("returns 0 for a zero-width track rather than dividing by zero", () => {
    // jsdom reports zero-sized rects for everything, so this is the common
    // case in tests rather than an exotic one.
    expect(fractionFromPointer(rect({ width: 0 }), 150)).toBe(0);
  });
});
