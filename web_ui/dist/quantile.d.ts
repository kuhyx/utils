/**
 * Distribution-aware slider maths.
 *
 * A linear min..max track is useless on skewed data, which is the normal case
 * in both consumers: dufs-cloud's file sizes span bytes to gigabytes, and
 * awesome-mcp-explorer's star counts run 0..166,785 with a median of 8, so a
 * linear midpoint sits above 99.9% of all rows. Mapping the track through the
 * actual distribution puts the middle of the track at the median, which makes
 * equal track distance mean roughly equal numbers of items.
 *
 * This was duplicated in dufs-cloud and awesome-mcp-explorer before it moved
 * here; both now import it.
 */
/**
 * Bounds-checked array access (callers guarantee the index is valid). Keeps the
 * quantile helpers free of scattered non-null assertions or dead undefined
 * guards while still satisfying `noUncheckedIndexedAccess`.
 */
export declare function nth(values: readonly number[], index: number): number;
/** Clamp to the unit interval. */
export declare function clamp01(x: number): number;
/**
 * The value at quantile `f` (0..1) of an ascending, non-empty array, with linear
 * interpolation between the two straddling samples. This is what makes the
 * sliders distribution-aware: f = 0.5 returns the *median*, so the middle of the
 * track sits where half the items are — not the arithmetic midpoint of the
 * range. Empty input yields 0 (callers hide the slider in that case).
 */
export declare function quantileValue(sorted: readonly number[], f: number): number;
/**
 * The quantile (0..1) of `value` within `sorted` — the inverse of
 * {@link quantileValue}, used to place a thumb at the right spot on the track.
 * Values at or beyond the ends map to 0/1.
 */
export declare function valueQuantile(sorted: readonly number[], value: number): number;
/**
 * Pointer x to a 0..1 fraction of a track.
 *
 * Extracted as pure geometry so slider behaviour is testable without layout,
 * which jsdom does not implement.
 */
export declare function fractionFromPointer(rect: DOMRect, clientX: number): number;
//# sourceMappingURL=quantile.d.ts.map
