import { afterEach, describe, expect, it, vi } from "vitest";

import { RangeSliderElement } from "./range-slider-element.ts";
import { mount, thumb, VALUES } from "./test/slider-helpers.ts";

afterEach(() => {
  document.body.replaceChildren();
});

describe("registration", () => {
  it("registers range-slider", () => {
    expect(customElements.get("range-slider")).toBe(RangeSliderElement);
  });

  it("tolerates a second copy of the module loading", async () => {
    vi.resetModules();
    const second = await import("./range-slider-element.ts");
    expect(second.RangeSliderElement).not.toBe(RangeSliderElement);
    expect(customElements.get("range-slider")).toBe(RangeSliderElement);
  });
});

describe("rendering", () => {
  it("renders a hidden slider when there is nothing to range over", () => {
    const { element } = mount({}, [1]);
    expect(element.querySelector<HTMLElement>(".slider")?.hidden).toBe(true);
  });

  it("builds nothing before it has a value to show", () => {
    const element = new RangeSliderElement();
    element.setAttribute("lo", "1");
    expect(element.querySelector(".slider")).toBeNull();
  });

  it("exposes both thumbs as sliders with the value trio", () => {
    const { element } = mount();
    const low = thumb(element, "lo");
    expect(low.getAttribute("role")).toBe("slider");
    expect(low.getAttribute("aria-valuemin")).toBe("0");
    expect(low.getAttribute("aria-valuemax")).toBe("90");
    expect(low.getAttribute("aria-valuenow")).toBe("0");
    expect(thumb(element, "hi").getAttribute("aria-valuenow")).toBe("90");
    expect(element.querySelector<HTMLElement>(".slider")?.hidden).toBe(false);
  });

  it("positions the thumbs and the fill from lo and hi", () => {
    const { element } = mount({ hi: "70", lo: "20" });
    // jsdom 31 rounds serialized style numbers to 4 decimals, so compare numerically.
    const percent = (value: string): number => Number(value.replace("%", ""));
    expect(percent(thumb(element, "lo").style.left)).toBeCloseTo((2 / 9) * 100, 3);
    expect(percent(thumb(element, "hi").style.left)).toBeCloseTo((7 / 9) * 100, 3);
    expect(
      percent(element.querySelector<HTMLElement>(".slider-fill")?.style.left ?? ""),
    ).toBeCloseTo((2 / 9) * 100, 3);
  });

  it("reports lo and hi as the distribution bounds when unconstrained", () => {
    const { element } = mount();
    expect([element.lo, element.hi]).toEqual([0, 90]);
  });

  it("reports zero bounds with no values", () => {
    const element = new RangeSliderElement();
    expect([element.lo, element.hi]).toEqual([0, 0]);
  });

  it("falls back to the bounds for a non-numeric attribute", () => {
    const { element } = mount({ hi: "x", lo: "y" });
    expect([element.lo, element.hi]).toEqual([0, 90]);
  });

  it("names the thumbs from the label", () => {
    const { element } = mount({ label: "Stars" });
    expect(thumb(element, "lo").getAttribute("aria-label")).toBe("Stars minimum");
    expect(thumb(element, "hi").getAttribute("aria-label")).toBe("Stars maximum");
  });

  it("falls back to a generic name without a label", () => {
    const { element } = mount();
    expect(thumb(element, "lo").getAttribute("aria-label")).toBe("Range minimum");
  });

  it("re-renders when an attribute changes", () => {
    const { element } = mount();
    element.setAttribute("lo", "30");
    expect(thumb(element, "lo").getAttribute("aria-valuenow")).toBe("30");
  });

  it("is focusable, so the control is a keyboard stop", () => {
    const { element } = mount();
    thumb(element, "lo").focus();
    expect(document.activeElement).toBe(thumb(element, "lo"));
  });

  it("keeps a single slider across re-renders", () => {
    const { element } = mount();
    element.values = VALUES;
    expect(element.querySelectorAll(".slider")).toHaveLength(1);
  });

  it("returns the values it was given", () => {
    const { element } = mount();
    expect(element.values).toBe(VALUES);
  });
});

describe("head", () => {
  const format = (value: number): string => `${String(value)}*`;

  it("draws the head only when both label and format are given", () => {
    const { element } = mount({ label: "Stars" });
    expect(element.querySelector(".slider-head")).toBeNull();
    element.format = format;
    expect(element.format).toBe(format);
    expect(element.querySelector(":scope .slider-head > span")?.textContent).toBe("Stars");
    expect(element.querySelector(".slider-value")?.textContent).toBe("0* – 90*");
  });

  it("omits the head without a label even with a format", () => {
    const { element } = mount();
    element.format = format;
    expect(element.querySelector(".slider-head")).toBeNull();
  });

  it("updates the readout when the bounds move", () => {
    const { element } = mount({ label: "Stars" });
    element.format = format;
    element.setAttribute("hi", "40");
    expect(element.querySelector(".slider-value")?.textContent).toBe("0* – 40*");
  });
});

