// @vitest-environment node
import { experimental_AstroContainer as AstroContainer } from "astro/container";
import { describe, expect, it } from "vitest";

import RangeSlider from "./RangeSlider.astro";

const VALUES = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90];

async function render(props: Record<string, unknown>): Promise<string> {
  const container = await AstroContainer.create();
  return container.renderToString(RangeSlider, { props });
}

describe("RangeSlider.astro", () => {
  it("wraps the markup in a range-slider element", async () => {
    const html = await render({ values: VALUES });
    expect(html).toContain("<range-slider");
    expect(html).toContain('class="slider-track"');
    expect(html).toContain('class="slider-fill"');
  });

  it("renders two slider thumbs carrying the value trio", async () => {
    const html = await render({ hi: 70, label: "Stars", lo: 20, values: VALUES });
    expect(html.match(/role="slider"/gu)).toHaveLength(2);
    expect(html).toContain('aria-label="Stars minimum"');
    expect(html).toContain('aria-label="Stars maximum"');
    expect(html).toContain('aria-valuemin="0"');
    expect(html).toContain('aria-valuemax="90"');
    expect(html).toContain('aria-valuenow="20"');
    expect(html).toContain('aria-valuenow="70"');
  });

  it("positions the thumbs from the value distribution", async () => {
    const html = await render({ hi: 70, lo: 20, values: VALUES });
    expect(html).toContain(`left: ${String((2 / 9) * 100)}%`);
    expect(html).toContain(`left: ${String((7 / 9) * 100)}%`);
  });

  it("defaults the bounds to the distribution ends", async () => {
    const html = await render({ values: VALUES });
    expect(html).toContain('aria-valuenow="0"');
    expect(html).toContain('aria-valuenow="90"');
  });

  it("falls back to a generic name without a label", async () => {
    expect(await render({ values: VALUES })).toContain('aria-label="Range minimum"');
  });

  it("renders the head only with a label and a format", async () => {
    const withHead = await render({ format: (v: number) => `${String(v)}*`, label: "Stars", values: VALUES });
    expect(withHead).toContain("slider-head");
    expect(withHead).toContain("0* – 90*");
    expect(await render({ label: "Stars", values: VALUES })).not.toContain("slider-head");
    expect(await render({ format: String, values: VALUES })).not.toContain("slider-head");
  });

  it("hides the slider until there are values to range over", async () => {
    const html = await render({});
    expect(html).toMatch(/class="slider"[^>]*hidden/u);
    expect(html).not.toContain("slider-head");
  });

  it("does not hide it once there are values", async () => {
    expect(await render({ values: VALUES })).not.toMatch(/class="slider"[^>]*hidden/u);
  });

  it("forwards lo, hi and label to the element as attributes", async () => {
    const html = await render({ hi: 70, label: "Stars", lo: 20, values: VALUES });
    expect(html).toMatch(/<range-slider[^>]*lo="20"/u);
    expect(html).toMatch(/<range-slider[^>]*hi="70"/u);
    expect(html).toMatch(/<range-slider[^>]*label="Stars"/u);
  });
});
