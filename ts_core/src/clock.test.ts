import { describe, expect, it, vi } from 'vitest'

import {
  createManualClock,
  createRealClock,
  realClock,
  type Clock,
} from './clock.ts'

describe('createRealClock', () => {
  it('reads from performance.now()', () => {
    const spy = vi.spyOn(performance, 'now').mockReturnValue(1234)
    expect(createRealClock().now()).toBe(1234)
    spy.mockRestore()
  })

  it('advances as real time passes', () => {
    const clock = createRealClock()
    const first = clock.now()
    expect(clock.now()).toBeGreaterThanOrEqual(first)
  })
})

describe('realClock', () => {
  it('is a stable shared instance', () => {
    // The whole reason this export exists: a fresh object per render would
    // re-fire every effect that takes the clock as a dependency.
    expect(realClock).toBe(realClock)
    expect(realClock).not.toBe(createRealClock())
  })

  it('satisfies the Clock interface', () => {
    const asClock: Clock = realClock
    expect(typeof asClock.now()).toBe('number')
  })
})

describe('createManualClock', () => {
  it('starts at 0 by default', () => {
    expect(createManualClock().now()).toBe(0)
  })

  it('starts at the given time', () => {
    expect(createManualClock(500).now()).toBe(500)
  })

  it('only moves when told to', () => {
    const clock = createManualClock(100)
    expect(clock.now()).toBe(100)
    expect(clock.now()).toBe(100)
    clock.advance(50)
    expect(clock.now()).toBe(150)
  })

  it('accumulates repeated advances', () => {
    const clock = createManualClock()
    clock.advance(10)
    clock.advance(15)
    expect(clock.now()).toBe(25)
  })

  it('moves backwards on a negative advance', () => {
    const clock = createManualClock(100)
    clock.advance(-40)
    expect(clock.now()).toBe(60)
  })

  it('jumps to an absolute time with set()', () => {
    const clock = createManualClock(100)
    clock.set(7)
    expect(clock.now()).toBe(7)
  })

  it('keeps two instances independent', () => {
    const a = createManualClock()
    const b = createManualClock()
    a.advance(99)
    expect(b.now()).toBe(0)
  })
})
