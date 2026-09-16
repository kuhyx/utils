// Argument guards for the factories. A preset that silently accepts a missing
// repo root lints with the wrong project and reports nothing -- the worst
// failure mode for a gate -- so the factories refuse loudly instead.

/**
 * @param {unknown} value
 * @param {string} what Name used in the error message.
 * @returns {string}
 */
export function requireNonEmptyString(value, what) {
  const isPresent = typeof value === "string" && value !== "";
  if (!isPresent) {
    throw new TypeError(`@kuhyx/ts-config: ${what} is required (pass import.meta.dirname)`);
  }
  return value;
}

/**
 * @template T
 * @param {unknown} value
 * @param {string} what
 * @returns {T[]}
 */
export function requireNonEmptyArray(value, what) {
  const isPresent = Array.isArray(value) && value.length > 0;
  if (!isPresent) {
    throw new TypeError(`@kuhyx/ts-config: ${what} needs a non-empty list`);
  }
  return value;
}
