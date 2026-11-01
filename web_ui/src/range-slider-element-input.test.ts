import { fireEvent } from "@testing-library/dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mount, thumb, track, TRACK_WIDTH } from "./test/slider-helpers.ts";

afterEach(() => {
  document.body.replaceChildren();
});

describe("keyboard", () => {
  it.each([
    ["ArrowRight", 10],
    ["ArrowUp", 10],
  ])("%s steps the low thumb up", (key, expected) => {
    const { changes, element } = mount();
    fireEvent.keyDown(thumb(element, "lo"), { key });
    expect(changes).toEqual([{ hi: 90, lo: expected }]);
    expect(element.lo).toBe(expected);
  });

  it.each([
    ["ArrowLeft", 80],
    ["ArrowDown", 80],
  ])("%s steps the high thumb down", (key, expected) => {
    const { changes, element } = mount();
    fireEvent.keyDown(thumb(element, "hi"), { key });
    expect(changes).toEqual([{ hi: expected, lo: 0 }]);
  });

  it("PageUp jumps ten samples", () => {
    const { changes, element } = mount();
    fireEvent.keyDown(thumb(element, "lo"), { key: "PageUp" });
    expect(changes).toEqual([{ hi: 90, lo: 90 }]);
  });

  it("PageDown jumps ten samples down", () => {
    const { changes, element } = mount();
    fireEvent.keyDown(thumb(element, "hi"), { key: "PageDown" });
    expect(changes).toEqual([{ hi: 0, lo: 0 }]);
  });

  it("Home sends a thumb to the floor", () => {
    const { changes, element } = mount({ lo: "50" });
    fireEvent.keyDown(thumb(element, "lo"), { key: "Home" });
    expect(changes).toEqual([{ hi: 90, lo: 0 }]);
  });

  it("End sends a thumb to the ceiling", () => {
    const { changes, element } = mount({ hi: "50" });
    fireEvent.keyDown(thumb(element, "hi"), { key: "End" });
    expect(changes).toEqual([{ hi: 90, lo: 0 }]);
  });

  it("prevents the default of a handled key and ignores the rest", () => {
    const { changes, element } = mount();
    expect(fireEvent.keyDown(thumb(element, "lo"), { cancelable: true, key: "ArrowRight" })).toBe(false);
    expect(fireEvent.keyDown(thumb(element, "lo"), { cancelable: true, key: "a" })).toBe(true);
    expect(changes).toHaveLength(1);
  });

  it("does not let the low thumb cross the high one", () => {
    const { changes, element } = mount({ hi: "10", lo: "10" });
    fireEvent.keyDown(thumb(element, "lo"), { key: "ArrowRight" });
    expect(changes).toEqual([{ hi: 10, lo: 10 }]);
  });

  it("does not let the high thumb cross the low one", () => {
    const { changes, element } = mount({ hi: "10", lo: "10" });
    fireEvent.keyDown(thumb(element, "hi"), { key: "ArrowLeft" });
    expect(changes).toEqual([{ hi: 10, lo: 10 }]);
  });

  it("bubbles the change event to ancestors", () => {
    const { element } = mount();
    const heard = vi.fn();
    document.body.addEventListener("change", heard);
    fireEvent.keyDown(thumb(element, "lo"), { key: "ArrowRight" });
    expect(heard).toHaveBeenCalledOnce();
    document.body.removeEventListener("change", heard);
  });
});

describe("pointer", () => {
  it("grabs the nearer thumb when pressed anywhere on the track", () => {
    const { changes, element } = mount();
    // The track is quantile-mapped over n-1 intervals: 0.1 lands on 9.
    fireEvent.pointerDown(track(element), { clientX: TRACK_WIDTH * 0.1, pointerId: 1 });
    expect(changes).toEqual([{ hi: 90, lo: 9 }]);
  });

  it("grabs the high thumb when the press is nearer to it", () => {
    const { changes, element } = mount();
    fireEvent.pointerDown(track(element), { clientX: TRACK_WIDTH * 0.9, pointerId: 1 });
    expect(changes).toEqual([{ hi: 81, lo: 0 }]);
  });

  it("follows the pointer while dragging", () => {
    const { changes, element } = mount();
    fireEvent.pointerDown(track(element), { clientX: 0, pointerId: 1 });
    fireEvent.pointerMove(track(element), { clientX: TRACK_WIDTH * 0.3, pointerId: 1 });
    expect(changes.at(-1)).toEqual({ hi: 90, lo: 27 });
  });

  it("ignores movement when no thumb is held", () => {
    const { changes, element } = mount();
    fireEvent.pointerMove(track(element), { clientX: TRACK_WIDTH * 0.3, pointerId: 1 });
    expect(changes).toEqual([]);
  });

  it("stops dragging on pointer up", () => {
    const { changes, element } = mount();
    fireEvent.pointerDown(track(element), { clientX: 0, pointerId: 1 });
    fireEvent.pointerUp(track(element), { pointerId: 1 });
    changes.length = 0;
    fireEvent.pointerMove(track(element), { clientX: TRACK_WIDTH * 0.5, pointerId: 1 });
    expect(changes).toEqual([]);
  });

  it("ignores a pointer up that was never preceded by a press", () => {
    const { changes, element } = mount();
    fireEvent.pointerUp(track(element), { pointerId: 1 });
    expect(changes).toEqual([]);
  });
});

