import { describe, expect, it } from 'vitest'

import {
  createRng,
  createSeededRng,
  nextChance,
  nextFloat,
  nextInt,
  pick,
} from './rng.ts'

/**
 * The golden sequence for seed 12345, captured from the *existing* konbini-67
 * and sims3-clone implementations before extraction.
 *
 * This is the load-bearing test in the package. These repos guarantee "same
 * seed -> identical world"; if the shared core ever stops reproducing this
 * exact sequence, every saved seed in every consumer silently generates a
 * different world. Regenerating these numbers to make a failure go away
 * would defeat the entire point of the test.
 */
const GOLDEN_12345 = [
  0.979_728_267_760_947_3, 0.306_752_264_499_664_3, 0.484_205_421_525_985,
  0.817_934_412_509_203, 0.509_428_369_347_006_1,
]

describe('mulberry32 core', () => {
  it('reproduces the pre-extraction sequence for a known seed', () => {
    const rng = createRng(12_345)
    const seen = Array.from({ length: 5 }, () => nextFloat(rng))
    expect(seen).toEqual(GOLDEN_12345)
  })

  it('gives both interfaces the same sequence', () => {
    const free = createRng(999)
    const closure = createSeededRng(999)
    const a = Array.from({ length: 8 }, () => nextFloat(free))
    const b = Array.from({ length: 8 }, () => closure.float())
    expect(a).toEqual(b)
  })

  it('is reproducible: same seed, same draws', () => {
    const a = createRng(7)
    const b = createRng(7)
    expect(nextFloat(a)).toBe(nextFloat(b))
  })

  it('differs between seeds', () => {
    expect(nextFloat(createRng(1))).not.toBe(nextFloat(createRng(2)))
  })

  it('stays within [0, 1) across many draws', () => {
    const rng = createRng(42)
    for (let i = 0; i < 1000; i += 1) {
      const value = nextFloat(rng)
      expect(value).toBeGreaterThanOrEqual(0)
      expect(value).toBeLessThan(1)
    }
  })

  it('handles a seed of 0 and a negative seed', () => {
    expect(nextFloat(createRng(0))).toBeGreaterThanOrEqual(0)
    expect(nextFloat(createRng(-1))).toBeGreaterThanOrEqual(0)
  })
})

describe('nextInt', () => {
  it('is inclusive of both bounds', () => {
    const rng = createRng(3)
    const seen = new Set<number>()
    for (let i = 0; i < 500; i += 1) {
      seen.add(nextInt(rng, 1, 3))
    }
    expect([...seen].sort()).toEqual([1, 2, 3])
  })

  it('returns the only value when min equals max', () => {
    expect(nextInt(createRng(5), 4, 4)).toBe(4)
  })

  it('consumes exactly one step, like a raw float draw', () => {
    const a = createRng(11)
    const b = createRng(11)
    nextInt(a, 0, 9)
    nextFloat(b)
    expect(nextFloat(a)).toBe(nextFloat(b))
  })
})

describe('nextChance', () => {
  it('is always true at probability 1 and never at 0', () => {
    const rng = createRng(8)
    expect(nextChance(rng, 1)).toBe(true)
    expect(nextChance(rng, 0)).toBe(false)
  })

  it('lands near the requested probability over many draws', () => {
    const rng = createRng(2024)
    let hits = 0
    for (let i = 0; i < 4000; i += 1) {
      if (nextChance(rng, 0.25)) {
        hits += 1
      }
    }
    expect(hits / 4000).toBeGreaterThan(0.2)
    expect(hits / 4000).toBeLessThan(0.3)
  })
})

describe('pick', () => {
  it('returns the single element of a one-item tuple', () => {
    expect(pick(createRng(1), ['only'])).toBe('only')
  })

  it('eventually returns every element', () => {
    const rng = createRng(4)
    const seen = new Set<string>()
    for (let i = 0; i < 500; i += 1) {
      seen.add(pick(rng, ['a', 'b', 'c']))
    }
    expect([...seen].sort()).toEqual(['a', 'b', 'c'])
  })

  it('is deterministic for a given seed', () => {
    const items: readonly [string, ...string[]] = ['w', 'x', 'y', 'z']
    expect(pick(createRng(77), items)).toBe(pick(createRng(77), items))
  })
})

describe('createSeededRng', () => {
  it('picks uniformly and deterministically', () => {
    expect(createSeededRng(5).pick(['p', 'q', 'r'])).toBe(
      createSeededRng(5).pick(['p', 'q', 'r']),
    )
  })

  it('throws rather than returning undefined on an empty array', () => {
    expect(() => createSeededRng(1).pick([])).toThrow('pick() on an empty array')
  })

  it('matches europe-county-map: pick indexes by floor(float * len)', () => {
    // The old local implementation indexed directly off the float rather than
    // going through int(). Same step count, and algebraically identical for
    // 0..len-1 -- pinned here so a future "simplification" to int() cannot
    // silently shift every pick by an off-by-one.
    const probe = createRng(31)
    const expectedIndex = Math.floor(nextFloat(probe) * 5)
    const items = ['a', 'b', 'c', 'd', 'e']
    expect(createSeededRng(31).pick(items)).toBe(items[expectedIndex])
  })

  it('exposes int and chance over the same stream', () => {
    const rng = createSeededRng(64)
    expect(rng.int(10, 10)).toBe(10)
    expect(typeof rng.chance(0.5)).toBe('boolean')
  })
})
