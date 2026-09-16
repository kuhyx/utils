/**
 * The keyboard contract of the range slider, kept pure and in its own module
 * so range-slider.tsx exports only the component (react-refresh needs that
 * for HMR to keep working) and the contract is testable without layout.
 */
import { nth, valueQuantile } from "./quantile.ts";

/**
 * Steps one thumb by `delta` positions through the distribution. Pure, so the
 * keyboard contract is testable without layout.
 *
 * Steps to the next *distinct* value rather than the next index. Real
 * distributions are lumpy -- awesome-mcp-explorer's star counts hold ~1500
 * duplicate zeros -- and an index step inside a run of equal values changes the
 * index while leaving the value (and therefore the thumb, and the filter)
 * exactly where it was. That reads as a dead arrow key.
 */
export function steppedValue(
  values: readonly number[],
  current: number,
  delta: number,
): number {
  const last = values.length - 1;
  // Round to a real sample index so a thumb sitting between two samples still
  // advances rather than stalling on a fractional step.
  const index = Math.round(valueQuantile(values, current) * last);
  const direction = Math.sign(delta);
  if (direction === 0) return nth(values, index);

  let cursor = index;
  for (let taken = 0; taken < Math.abs(delta); taken++) {
    let next = cursor + direction;
    while (next >= 0 && next <= last && nth(values, next) === nth(values, cursor)) {
      next += direction;
    }
    if (next < 0 || next > last) break;
    cursor = next;
  }
  return nth(values, cursor);
}

/**
 * The value a thumb at `current` moves to for a key, or `undefined` when the
 * key is not one the slider handles (so the event is left to the browser).
 * Arrow keys step one distinct value, Page keys ten, Home/End jump to the
 * bounds.
 */
export function keyTarget(
  key: string,
  values: readonly number[],
  current: number,
): number | undefined {
  switch (key) {
    case "ArrowDown":
    case "ArrowLeft": {
      return steppedValue(values, current, -1);
    }
    case "ArrowRight":
    case "ArrowUp": {
      return steppedValue(values, current, 1);
    }
    case "End": {
      return nth(values, values.length - 1);
    }
    case "Home": {
      return nth(values, 0);
    }
    case "PageDown": {
      return steppedValue(values, current, -10);
    }
    case "PageUp": {
      return steppedValue(values, current, 10);
    }
    default: {
      return undefined;
    }
  }
}
