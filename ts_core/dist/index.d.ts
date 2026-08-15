/**
 * Framework-free TypeScript utilities shared across kuhy's games and web apps.
 *
 * Deliberately no React and no CSS: those live in `@kuhyx/web-ui`. A game
 * that needs a seeded RNG should not have to install a UI package to get one
 * -- that is the coupling that makes people vendor their own copy instead,
 * which is how these ended up duplicated four ways to begin with.
 */
export { createManualClock, createRealClock, realClock, type Clock, type ManualClock, } from './clock.ts';
export { createRng, createSeededRng, nextChance, nextFloat, nextInt, pick, type Rng, type SeededRng, } from './rng.ts';
//# sourceMappingURL=index.d.ts.map