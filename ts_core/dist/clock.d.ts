/**
 * Injectable time source.
 *
 * All elapsed-time reads flow through this interface instead of calling
 * `performance.now()`/`Date.now()` directly (banned by lint everywhere except
 * this file), so real-time mechanics can be driven by a scripted clock in
 * tests rather than racing the wall clock.
 */
export interface Clock {
    /** Current time in milliseconds. Not comparable across different clocks. */
    now: () => number;
}
/** A {@link Clock} backed by the browser's monotonic performance timer. */
export declare const createRealClock: () => Clock;
/**
 * The one real clock instance UI code should pass around.
 *
 * A single shared instance (rather than calling {@link createRealClock} per
 * component) keeps its identity stable across renders, which matters for
 * hooks that take it as an effect dependency -- a fresh object each render
 * re-fires the effect every time.
 */
export declare const realClock: Clock;
/** A {@link Clock} test double whose time only moves when told to. */
export interface ManualClock extends Clock {
    /** Moves the clock forward by the given number of milliseconds. */
    advance: (deltaMs: number) => void;
    /** Jumps the clock to an absolute time in milliseconds. */
    set: (timeMs: number) => void;
}
/** Creates a {@link ManualClock} starting at `startMs` (default 0). */
export declare const createManualClock: (startMs?: number) => ManualClock;
//# sourceMappingURL=clock.d.ts.map