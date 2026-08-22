// @vitest-environment node
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("tokens.css", import.meta.url), "utf8");

/**
 * tokens.css is the executable form of unified-design-system/tokens.md. These
 * assertions are the gate against silent drift between the two: the palette is
 * frozen, so a changed hex here is either a deliberate design-system change
 * (update both, plus the Dart side) or a bug.
 */

function declared(name: string): string[] {
  return [...css.matchAll(new RegExp(`--${name}:\\s*([^;]+);`, "g"))].map((m) =>
    (m[1] ?? "").trim(),
  );
}

describe("tokens.css", () => {
  it.each([
    ["bg", "#211d1b"],
    ["surface-1", "#2b2624"],
    ["surface-2", "#38312e"],
    ["border", "#463e3a"],
    ["text", "#eceae9"],
    ["text-muted", "#aaa09a"],
    ["accent", "#b8862e"],
    ["success", "#8a9a3c"],
    ["warning", "#e0a63c"],
    ["danger", "#e2585f"],
  ])("declares --%s with the frozen dark value first", (name, value) => {
    expect(declared(name)[0]).toBe(value);
  });

  it.each([
    ["bg", "#f6f4f3"],
    ["surface-1", "#fcfbfb"],
    ["border", "#e0dad7"],
    ["text", "#211d1b"],
    ["text-muted", "#70625b"],
  ])("overrides --%s for the light theme", (name, value) => {
    expect(declared(name)).toContain(value);
  });

  it("keeps on-fill dark, never near-white", () => {
    // Every semantic fill sits in the same mid-light band, where near-white
    // text measures 2.2:1-3.6:1 against a 4.5:1 floor.
    expect(declared("on-fill")).toEqual(["#211d1b"]);
  });

  it("keeps on-scrim fixed regardless of page theme", () => {
    expect(declared("on-scrim")).toEqual(["#eceae9"]);
  });

  it("ships the full categorical ramp", () => {
    expect([1, 2, 3, 4, 5, 6].map((n) => declared(`cat-${String(n)}`)[0])).toEqual([
      "#c57293",
      "#398fc0",
      "#c85a32",
      "#228736",
      "#8d58bb",
      "#686d2c",
    ]);
  });

  it("does not re-theme the categorical ramp", () => {
    // The ramp must hold on both backgrounds rather than flipping with the
    // page theme; a second declaration would mean someone themed it.
    for (const n of [1, 2, 3, 4, 5, 6]) {
      expect(declared(`cat-${String(n)}`)).toHaveLength(1);
    }
  });

  it("declares the spacing scale on the 4px base", () => {
    expect([1, 2, 3, 4, 5, 6].map((n) => declared(`space-${String(n)}`)[0])).toEqual([
      "4px",
      "8px",
      "16px",
      "24px",
      "32px",
      "48px",
    ]);
  });

  it("declares the radius scale", () => {
    expect(["sm", "md", "lg"].map((s) => declared(`radius-${s}`)[0])).toEqual([
      "8px",
      "12px",
      "16px",
    ]);
  });

  it("declares the type scale", () => {
    expect(
      ["display", "title", "subtitle", "body", "label", "caption"].map(
        (s) => declared(`text-${s}`)[0],
      ),
    ).toEqual(["32px", "24px", "20px", "16px", "14px", "12px"]);
  });

  it("styles :focus-visible, so no consumer has to remember to", () => {
    expect(css).toMatch(/:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--focus-ring\)/);
  });

  it("declares the duration scale", () => {
    expect(
      ["instant", "fast", "base", "slow"].map((s) => declared(`duration-${s}`)[0]),
    ).toEqual(["0ms", "120ms", "200ms", "320ms"]);
  });

  it("declares the three easing curves", () => {
    expect(["standard", "decelerate", "accelerate"].map((s) => declared(`ease-${s}`)[0])).toEqual([
      "cubic-bezier(0.2, 0, 0, 1)",
      "cubic-bezier(0, 0, 0, 1)",
      "cubic-bezier(0.3, 0, 1, 1)",
    ]);
  });

  it("collapses every non-zero duration under prefers-reduced-motion", () => {
    // The collapse happens on the tokens themselves so no consumer has to
    // branch. Missing one step here is the whole bug this guards.
    const block = /@media \(prefers-reduced-motion: reduce\)\s*\{([\s\S]*?)\n\}/.exec(css)?.[1];
    expect(block).toBeDefined();
    for (const step of ["fast", "base", "slow"]) {
      expect(block).toMatch(new RegExp(`--duration-${step}:\\s*0ms;`));
    }
  });

  it("does not silence sound or haptics along with motion", () => {
    // Reduced motion is not a request to lose confirmation that a tap landed;
    // the sound opt-out is a separate, user-facing setting.
    const block = /@media \(prefers-reduced-motion: reduce\)\s*\{([\s\S]*?)\n\}/.exec(css)?.[1];
    expect(block).not.toMatch(/sound|haptic|volume|mute/i);
  });

  it("uses no raw black or white literals", () => {
    // Shadows are ink-tinted rgba; neutrals are never pure.
    expect(css).not.toMatch(/#fff\b|#ffffff\b|#000\b|#000000\b|rgba\(0,\s*0,\s*0/i);
  });
});
