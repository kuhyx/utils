import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RangeSlider, steppedValue } from "./range-slider.tsx";

/** Ten evenly spaced values, so a quantile fraction maps to a predictable value. */
const VALUES = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90];

/** The track width the jsdom rect stub reports (see src/test/setup.ts). */
const TRACK_WIDTH = 1000;

function renderSlider(
  properties: Partial<React.ComponentProps<typeof RangeSlider>> = {},
): { onChange: ReturnType<typeof vi.fn> } {
  const onChange = vi.fn();
  render(
    <RangeSlider
      hi={90}
      lo={0}
      onChange={onChange}
      values={VALUES}
      {...properties}
    />,
  );
  return { onChange };
}

function thumbs(): HTMLElement[] {
  return screen.getAllByRole("slider");
}

describe("steppedValue", () => {
  it("advances one sample at a time", () => {
    expect(steppedValue(VALUES, 30, 1)).toBe(40);
  });

  it("moves backwards for a negative delta", () => {
    expect(steppedValue(VALUES, 30, -1)).toBe(20);
  });

  it("clamps at the top", () => {
    expect(steppedValue(VALUES, 90, 5)).toBe(90);
  });

  it("clamps at the bottom", () => {
    expect(steppedValue(VALUES, 0, -5)).toBe(0);
  });

  it("rounds a between-samples value to a real sample", () => {
    expect(steppedValue(VALUES, 34, 1)).toBe(40);
  });
});

describe("RangeSlider", () => {
  it("renders nothing when there is nothing to range over", () => {
    const { container } = render(<RangeSlider hi={1} lo={1} onChange={vi.fn()} values={[1]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("exposes both thumbs as sliders with the value trio", () => {
    renderSlider();
    const [low, high] = thumbs();
    expect(low).toHaveAttribute("aria-valuemin", "0");
    expect(low).toHaveAttribute("aria-valuemax", "90");
    expect(low).toHaveAttribute("aria-valuenow", "0");
    expect(high).toHaveAttribute("aria-valuenow", "90");
  });

  it("names the thumbs from the label", () => {
    renderSlider({ label: "Stars" });
    expect(screen.getByLabelText("Stars minimum")).toBeInTheDocument();
    expect(screen.getByLabelText("Stars maximum")).toBeInTheDocument();
  });

  it("falls back to a generic name without a label", () => {
    renderSlider();
    expect(screen.getByLabelText("Range minimum")).toBeInTheDocument();
  });

  it("draws the head only when both label and format are given", () => {
    renderSlider({ format: (v): string => `${String(v)}*`, label: "Stars" });
    expect(screen.getByText("Stars")).toBeInTheDocument();
    expect(screen.getByText("0* – 90*")).toBeInTheDocument();
  });

  it("omits the head when the caller draws its own chrome", () => {
    renderSlider({ label: "Stars" });
    expect(screen.queryByText("Stars")).not.toBeInTheDocument();
  });

  it("is focusable, so the control is a keyboard stop", () => {
    renderSlider();
    const [low] = thumbs();
    low?.focus();
    expect(low).toHaveFocus();
  });

  describe("keyboard", () => {
    it.each([
      ["ArrowRight", 10],
      ["ArrowUp", 10],
    ])("%s steps the low thumb up", (key, expected) => {
      const { onChange } = renderSlider();
      fireEvent.keyDown(thumbs()[0] as HTMLElement, { key });
      expect(onChange).toHaveBeenCalledWith(expected, 90);
    });

    it.each([
      ["ArrowLeft", 80],
      ["ArrowDown", 80],
    ])("%s steps the high thumb down", (key, expected) => {
      const { onChange } = renderSlider();
      fireEvent.keyDown(thumbs()[1] as HTMLElement, { key });
      expect(onChange).toHaveBeenCalledWith(0, expected);
    });

    it("PageUp jumps ten samples", () => {
      const { onChange } = renderSlider({ lo: 0 });
      fireEvent.keyDown(thumbs()[0] as HTMLElement, { key: "PageUp" });
      expect(onChange).toHaveBeenCalledWith(90, 90);
    });

    it("PageDown jumps ten samples down", () => {
      const { onChange } = renderSlider({ hi: 90 });
      fireEvent.keyDown(thumbs()[1] as HTMLElement, { key: "PageDown" });
      expect(onChange).toHaveBeenCalledWith(0, 0);
    });

    it("Home sends a thumb to the floor", () => {
      const { onChange } = renderSlider({ lo: 50 });
      fireEvent.keyDown(thumbs()[0] as HTMLElement, { key: "Home" });
      expect(onChange).toHaveBeenCalledWith(0, 90);
    });

    it("End sends a thumb to the ceiling", () => {
      const { onChange } = renderSlider({ hi: 50 });
      fireEvent.keyDown(thumbs()[1] as HTMLElement, { key: "End" });
      expect(onChange).toHaveBeenCalledWith(0, 90);
    });

    it("ignores keys it does not handle", () => {
      const { onChange } = renderSlider();
      fireEvent.keyDown(thumbs()[0] as HTMLElement, { key: "a" });
      expect(onChange).not.toHaveBeenCalled();
    });

    it("does not let the low thumb cross the high one", () => {
      const { onChange } = renderSlider({ hi: 10, lo: 10 });
      fireEvent.keyDown(thumbs()[0] as HTMLElement, { key: "ArrowRight" });
      expect(onChange).toHaveBeenCalledWith(10, 10);
    });

    it("does not let the high thumb cross the low one", () => {
      const { onChange } = renderSlider({ hi: 10, lo: 10 });
      fireEvent.keyDown(thumbs()[1] as HTMLElement, { key: "ArrowLeft" });
      expect(onChange).toHaveBeenCalledWith(10, 10);
    });
  });

  describe("pointer", () => {
    function track(): HTMLElement {
      // eslint-disable-next-line testing-library/no-node-access -- the track is
      // presentational; there is no role or text to query it by.
      return document.querySelector(".slider-track") as HTMLElement;
    }

    it("grabs the nearer thumb when pressed anywhere on the track", () => {
      const { onChange } = renderSlider();
      // 10% along: nearer the low thumb, which sits at 0. The track is
      // quantile-mapped over n-1 intervals, so 0.1 lands on 9, not 10.
      fireEvent.pointerDown(track(), { clientX: TRACK_WIDTH * 0.1, pointerId: 1 });
      expect(onChange).toHaveBeenCalledWith(9, 90);
    });

    it("grabs the high thumb when the press is nearer to it", () => {
      const { onChange } = renderSlider();
      fireEvent.pointerDown(track(), { clientX: TRACK_WIDTH * 0.9, pointerId: 1 });
      expect(onChange).toHaveBeenCalledWith(0, 81);
    });

    it("follows the pointer while dragging", () => {
      const { onChange } = renderSlider();
      fireEvent.pointerDown(track(), { clientX: 0, pointerId: 1 });
      fireEvent.pointerMove(track(), { clientX: TRACK_WIDTH * 0.3, pointerId: 1 });
      expect(onChange).toHaveBeenLastCalledWith(27, 90);
    });

    it("ignores movement when no thumb is held", () => {
      const { onChange } = renderSlider();
      fireEvent.pointerMove(track(), { clientX: TRACK_WIDTH * 0.3, pointerId: 1 });
      expect(onChange).not.toHaveBeenCalled();
    });

    it("stops dragging on pointer up", () => {
      const { onChange } = renderSlider();
      fireEvent.pointerDown(track(), { clientX: 0, pointerId: 1 });
      fireEvent.pointerUp(track(), { pointerId: 1 });
      onChange.mockClear();
      fireEvent.pointerMove(track(), { clientX: TRACK_WIDTH * 0.5, pointerId: 1 });
      expect(onChange).not.toHaveBeenCalled();
    });

    it("ignores a pointer up that was never preceded by a press", () => {
      const { onChange } = renderSlider();
      fireEvent.pointerUp(track(), { pointerId: 1 });
      expect(onChange).not.toHaveBeenCalled();
    });
  });
});
