import { afterEach, describe, expect, it } from "vitest";

import { RangeSliderElement } from "./range-slider-element.ts";
import { thumb, VALUES } from "./test/slider-helpers.ts";

afterEach(() => {
  document.body.replaceChildren();
});

describe("server-rendered markup", () => {
  const HEAD = '<div class="slider-head"><span></span><span class="slider-value"></span></div>';

  function server(beforeTrack = ""): string {
    return `<range-slider lo="20" hi="70" label="Stars"><div class="slider">${beforeTrack}
    <div class="slider-track"><div class="slider-fill"></div>
    <button class="slider-thumb slider-lo" type="button" role="slider"></button>
    <button class="slider-thumb slider-hi" type="button" role="slider"></button></div></div></range-slider>`;
  }

  /** Parses markup into a detached, upgraded element (no connectedCallback yet). */
  function parse(markup: string): RangeSliderElement {
    const parser = new DOMParser();
    const parsed = parser.parseFromString(markup, "text/html").body.firstElementChild;
    if (parsed === null) throw new TypeError("no markup");
    const element = document.importNode(parsed, true);
    customElements.upgrade(element);
    if (!(element instanceof RangeSliderElement)) throw new TypeError("not upgraded");
    return element;
  }

  it("adopts the markup instead of adding a second slider", () => {
    const element = parse(server());
    const original = element.querySelector(".slider-lo");
    element.values = VALUES;
    expect(element.querySelectorAll(".slider")).toHaveLength(1);
    expect(element.querySelector(".slider-lo")).toBe(original);
    expect(thumb(element, "lo").getAttribute("aria-valuenow")).toBe("20");
  });

  it("keeps a server-rendered head when no format is set", () => {
    const element = parse(server('<div class="slider-head">kept</div>'));
    element.values = VALUES;
    expect(element.querySelector(".slider-head")?.textContent).toBe("kept");
  });

  it("fills an existing head when a format arrives", () => {
    const element = parse(server(HEAD));
    element.values = VALUES;
    element.format = String;
    expect(element.querySelector(".slider-value")?.textContent).toBe("20 – 70");
  });

  it("tolerates a head with no spans", () => {
    const element = parse(server('<div class="slider-head"></div>'));
    element.values = VALUES;
    element.format = String;
    expect(element.querySelector(".slider-head")?.textContent).toBe("");
  });

  it.each([
    ['<range-slider><div class="slider"></div></range-slider>', /missing \.slider-fill/u],
    [
      '<range-slider><div class="slider"><div class="slider-fill"></div></div></range-slider>',
      /missing \.slider-hi/u,
    ],
    [
      '<range-slider><div class="slider"><div class="slider-fill"></div><button class="slider-hi"></button></div></range-slider>',
      /missing \.slider-lo/u,
    ],
    [
      '<range-slider><div class="slider"><div class="slider-fill"></div><button class="slider-hi"></button><button class="slider-lo"></button></div></range-slider>',
      /missing \.slider-track/u,
    ],
  ])("fails loudly when the server markup lacks a part: %#", (markup, message) => {
    const element = parse(markup);
    expect(() => {
      element.values = VALUES;
    }).toThrow(message);
  });
});

describe("upgrade", () => {
  it("takes properties assigned before the element was upgraded", () => {
    const element = document.createElement("range-slider");
    const prototype = Object.getPrototypeOf(element) as object;
    Object.setPrototypeOf(element, HTMLElement.prototype);
    Object.assign(element, { format: String, values: VALUES });
    Object.setPrototypeOf(element, prototype);
    document.body.append(element);
    expect(thumb(element, "hi").getAttribute("aria-valuenow")).toBe("90");
  });
});
