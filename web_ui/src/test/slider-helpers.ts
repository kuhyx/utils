import { RangeSliderElement } from "../range-slider-element.ts";

export const VALUES = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90];
export const TRACK_WIDTH = 1000;

export interface Mounted {
  readonly changes: { hi: number; lo: number }[];
  readonly element: RangeSliderElement;
}

export function mount(
  attributes: Record<string, string> = {},
  values: readonly number[] = VALUES,
): Mounted {
  const element = new RangeSliderElement();
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  const changes: { hi: number; lo: number }[] = [];
  element.addEventListener("change", (event) => {
    if (event instanceof CustomEvent) changes.push(event.detail as { hi: number; lo: number });
  });
  document.body.append(element);
  element.values = values;
  return { changes, element };
}

export function thumb(element: Element, which: "hi" | "lo"): HTMLElement {
  const found = element.querySelector<HTMLElement>(`.slider-${which}`);
  if (found === null) throw new Error(`no ${which} thumb`);
  return found;
}

export function track(element: Element): HTMLElement {
  const found = element.querySelector<HTMLElement>(".slider-track");
  if (found === null) throw new Error("no track");
  return found;
}
