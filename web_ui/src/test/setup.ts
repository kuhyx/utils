import "@testing-library/jest-dom/vitest";

// jsdom implements no layout engine (every rect is zero-sized) and no pointer
// capture. The slider needs a non-zero track width for fractionFromPointer to
// mean anything, and needs the capture calls to not throw.
const TRACK_WIDTH = 1000;

Object.defineProperty(Element.prototype, "getBoundingClientRect", {
  configurable: true,
  value(): DOMRect {
    return {
      bottom: 20,
      height: 20,
      left: 0,
      right: TRACK_WIDTH,
      toJSON: () => ({}),
      top: 0,
      width: TRACK_WIDTH,
      x: 0,
      y: 0,
    };
  },
});

Object.defineProperties(Element.prototype, {
  releasePointerCapture: {
    configurable: true,
    value: (): void => {
      // No pointer capture in jsdom; the slider only needs the call to not throw.
    },
  },
  setPointerCapture: {
    configurable: true,
    value: (): void => {
      // As above.
    },
  },
});
