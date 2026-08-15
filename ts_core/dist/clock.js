/** A {@link Clock} backed by the browser's monotonic performance timer. */
export const createRealClock = () => ({
    now: () => performance.now(),
});
/**
 * The one real clock instance UI code should pass around.
 *
 * A single shared instance (rather than calling {@link createRealClock} per
 * component) keeps its identity stable across renders, which matters for
 * hooks that take it as an effect dependency -- a fresh object each render
 * re-fires the effect every time.
 */
export const realClock = createRealClock();
/** Creates a {@link ManualClock} starting at `startMs` (default 0). */
export const createManualClock = (startMs = 0) => {
    let current = startMs;
    return {
        now: () => current,
        advance: (deltaMs) => {
            current += deltaMs;
        },
        set: (timeMs) => {
            current = timeMs;
        },
    };
};
//# sourceMappingURL=clock.js.map