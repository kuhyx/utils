/**
 * Seeded, deterministic PRNG (mulberry32).
 *
 * A given seed must always reproduce the exact same world, so consumers ban
 * `Math.random` by lint outside this file.
 *
 * ## Why there are two interfaces
 *
 * The four repos that had grown their own copy did not agree on shape:
 * konbini-67 used mutable state plus free functions (`nextFloat(rng)`),
 * while sims3-clone and europe-county-map returned an object of closures
 * (`rng.next()` / `rng.float()`). Both are exported here rather than
 * reconciled into one, because the *sequence* is the contract: these repos
 * have seeded tests and "same seed -> identical world" guarantees, and
 * changing how many times a helper advances the generator silently changes
 * every generated world. A shared package that quietly re-rolled saved
 * worlds would be worse than the duplication it replaced.
 *
 * The generator core is identical in both, so a given seed produces the same
 * float sequence whichever interface you use -- verified in the tests.
 *
 * Note `int` is inclusive of both bounds, matching sims3-clone and
 * europe-county-map. konbini-67's local helper took a single *exclusive*
 * max; it maps to `int(rng, 0, max - 1)`.
 */
/** Creates mutable generator state from a seed. */
export const createRng = (seed) => ({ s: seed >>> 0 });
/**
 * Deterministic float in [0, 1). Advances the generator.
 *
 * This is the mulberry32 core; every other helper here is defined in terms
 * of it, so they all consume exactly one step per call.
 */
export const nextFloat = (rng) => {
    rng.s = (rng.s + 0x6d_2b_79_f5) >>> 0;
    let t = rng.s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4_294_967_296;
};
/** Deterministic integer in [minInclusive, maxInclusive]. One step. */
export const nextInt = (rng, minInclusive, maxInclusive) => minInclusive + Math.floor(nextFloat(rng) * (maxInclusive - minInclusive + 1));
/** True with the given probability in [0, 1]. One step. */
export const nextChance = (rng, probability) => nextFloat(rng) < probability;
/**
 * Deterministic pick from a non-empty tuple. One step.
 *
 * Iterates rather than indexing: under `noUncheckedIndexedAccess` an index
 * read is `T | undefined`, and the undefined arm is unreachable here, so it
 * could never be covered by a test.
 */
export const pick = (rng, items) => {
    const target = nextInt(rng, 0, items.length - 1);
    let out = items[0];
    let seen = 0;
    for (const item of items) {
        if (seen === target) {
            out = item;
        }
        seen += 1;
    }
    return out;
};
/**
 * Creates a {@link SeededRng} over the same mulberry32 core.
 *
 * `pick` throws on an empty array rather than returning `undefined`: the
 * callers all treat their input as non-empty, and a silent `undefined`
 * propagates into generated data where it is far harder to trace.
 */
export const createSeededRng = (seed) => {
    const state = createRng(seed);
    const float = () => nextFloat(state);
    return {
        float,
        int: (minInclusive, maxInclusive) => nextInt(state, minInclusive, maxInclusive),
        pick: (items) => {
            const chosen = items[Math.floor(float() * items.length)];
            if (chosen === undefined) {
                throw new Error('pick() on an empty array');
            }
            return chosen;
        },
        chance: (probability) => float() < probability,
    };
};
//# sourceMappingURL=rng.js.map