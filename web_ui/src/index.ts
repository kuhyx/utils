/**
 * The shared web token + component layer.
 *
 * Only the pure helpers live here, so this entry point is safe to import in
 * Astro frontmatter (no DOM at module load). The component is imported by path:
 * `import RangeSlider from "@kuhyx/web-ui/RangeSlider.astro";` in frontmatter,
 * `import "@kuhyx/web-ui/range-slider";` in a client script, and the CSS as
 * `import "@kuhyx/web-ui/tokens.css";`.
 */
export { clamp01, fractionFromPointer, nth, quantileValue, valueQuantile } from "./quantile.ts";
export { keyTarget, steppedValue } from "./stepped-value.ts";
export { fuzzyMatch } from "./text.ts";
