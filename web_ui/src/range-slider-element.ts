/**
 * `<range-slider>`: a dual-thumb slider whose track maps through a value
 * distribution rather than a linear ramp (see `./quantile.ts`).
 *
 * Inputs: `values` (property, ascending), `lo` / `hi` / `label` (attributes),
 * `format` (property, enables the head readout). Output: a bubbling `change`
 * CustomEvent with `{ lo, hi }`. The element writes `lo` / `hi` itself, so it
 * works uncontrolled. It adopts the markup `RangeSlider.astro` renders, or
 * builds it when used from plain HTML.
 */
import { fractionFromPointer, nth, quantileValue, valueQuantile } from "./quantile.ts";
import { keyTarget } from "./stepped-value.ts";

export interface RangeChange {
  readonly hi: number;
  readonly lo: number;
}

type Thumb = "hi" | "lo";

interface Parts {
  readonly fill: HTMLElement;
  readonly hi: HTMLButtonElement;
  readonly lo: HTMLButtonElement;
  readonly root: HTMLElement;
  readonly track: HTMLElement;
}

function make<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  classes: string,
): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  element.setAttribute("class", classes);
  return element;
}

function thumbButton(thumb: Thumb): HTMLButtonElement {
  const button = make("button", `slider-thumb slider-${thumb}`);
  button.type = "button";
  button.setAttribute("role", "slider");
  return button;
}

function buildParts(): Parts {
  const root = make("div", "slider");
  const track = make("div", "slider-track");
  const fill = make("div", "slider-fill");
  const lo = thumbButton("lo");
  const hi = thumbButton("hi");
  track.append(fill, lo, hi);
  root.append(track);
  return { fill, hi, lo, root, track };
}

function required<T extends Element>(found: null | T, selector: string): T {
  if (found === null) throw new Error(`<range-slider> markup is missing ${selector}`);
  return found;
}

function adoptParts(host: Element): Parts {
  const root = required(host.querySelector<HTMLElement>(".slider"), ".slider");
  return {
    fill: required(root.querySelector<HTMLElement>(".slider-fill"), ".slider-fill"),
    hi: required(root.querySelector<HTMLButtonElement>(".slider-hi"), ".slider-hi"),
    lo: required(root.querySelector<HTMLButtonElement>(".slider-lo"), ".slider-lo"),
    root,
    track: required(root.querySelector<HTMLElement>(".slider-track"), ".slider-track"),
  };
}

export class RangeSliderElement extends HTMLElement {
  static readonly observedAttributes = ["hi", "label", "lo"];

  #drag: null | Thumb = null;
  #format: ((value: number) => string) | undefined;
  #parts: Parts | undefined;
  #values: readonly number[] = [];

  #apply(thumb: Thumb, value: number): void {
    const lo = thumb === "lo" ? Math.min(value, this.hi) : this.lo;
    const hi = thumb === "hi" ? Math.max(value, this.lo) : this.hi;
    this.setAttribute("lo", String(lo));
    this.setAttribute("hi", String(hi));
    const detail: RangeChange = { hi, lo };
    this.dispatchEvent(new CustomEvent<RangeChange>("change", { bubbles: true, detail }));
  }

  #bound(name: Thumb, fallback: number): number {
    const raw = this.getAttribute(name);
    const parsed = raw === null ? NaN : Number(raw);
    return Number.isNaN(parsed) ? fallback : parsed;
  }

  #build(): Parts {
    const parts = buildParts();
    this.append(parts.root);
    return parts;
  }

  #mount(): Parts {
    if (this.#parts !== undefined) return this.#parts;
    const parts = this.querySelector(".slider") === null ? this.#build() : adoptParts(this);

    for (const thumb of ["lo", "hi"] as const) {
      parts[thumb].addEventListener("keydown", (event) => {
        const target = keyTarget(event.key, this.#values, thumb === "lo" ? this.lo : this.hi);
        if (target === undefined) return;
        event.preventDefault();
        this.#apply(thumb, target);
      });
    }

    const valueAt = (event: PointerEvent): number => {
      return quantileValue(
        this.#values,
        fractionFromPointer(parts.track.getBoundingClientRect(), event.clientX),
      );
    };

    parts.track.addEventListener("pointerdown", (event) => {
      const value = valueAt(event);
      // Pressing anywhere on the track grabs the nearer thumb.
      const thumb: Thumb = Math.abs(value - this.lo) <= Math.abs(value - this.hi) ? "lo" : "hi";
      this.#drag = thumb;
      parts.track.setPointerCapture(event.pointerId);
      this.#apply(thumb, value);
    });
    parts.track.addEventListener("pointermove", (event) => {
      if (this.#drag === null) return;
      this.#apply(this.#drag, valueAt(event));
    });
    parts.track.addEventListener("pointerup", (event) => {
      if (this.#drag === null) return;
      this.#drag = null;
      parts.track.releasePointerCapture(event.pointerId);
    });

    this.#parts = parts;
    return parts;
  }

  #renderHead(root: HTMLElement, label: null | string): void {
    const format = this.#format;
    if (label === null || format === undefined) return;
    let head = root.querySelector<HTMLElement>(".slider-head");
    if (head === null) {
      head = make("div", "slider-head");
      head.append(document.createElement("span"), make("span", "slider-value"));
      root.prepend(head);
    }
    const [name, value] = head.children;
    if (name !== undefined) name.textContent = label;
    if (value !== undefined) value.textContent = `${format(this.lo)} – ${format(this.hi)}`;
  }

  #render(): void {
    const { fill, hi, lo, root } = this.#mount();
    const values = this.#values;
    root.hidden = values.length < 2;
    if (root.hidden) return;

    const label = this.getAttribute("label");
    const name = label ?? "Range";
    const low = this.lo;
    const high = this.hi;
    const loFraction = valueQuantile(values, low) * 100;
    const hiFraction = valueQuantile(values, high) * 100;

    fill.style.left = `${String(loFraction)}%`;
    fill.style.width = `${String(hiFraction - loFraction)}%`;
    for (const [thumb, button, now, fraction] of [
      ["minimum", lo, low, loFraction],
      ["maximum", hi, high, hiFraction],
    ] as const) {
      button.setAttribute("aria-label", `${name} ${thumb}`);
      button.setAttribute("aria-valuemin", String(nth(values, 0)));
      button.setAttribute("aria-valuemax", String(nth(values, values.length - 1)));
      button.setAttribute("aria-valuenow", String(now));
      button.style.left = `${String(fraction)}%`;
    }
    this.#renderHead(root, label);
  }

  get format(): ((value: number) => string) | undefined {
    return this.#format;
  }

  set format(format: ((value: number) => string) | undefined) {
    this.#format = format;
    this.#render();
  }

  /** The upper bound; the distribution max when the attribute is absent. */
  get hi(): number {
    return this.#bound("hi", this.#values.length === 0 ? 0 : nth(this.#values, this.#values.length - 1));
  }

  /** The lower bound; the distribution min when the attribute is absent. */
  get lo(): number {
    return this.#bound("lo", this.#values.length === 0 ? 0 : nth(this.#values, 0));
  }

  get values(): readonly number[] {
    return this.#values;
  }

  set values(values: readonly number[]) {
    this.#values = values;
    this.#render();
  }

  attributeChangedCallback(): void {
    if (this.#parts !== undefined) this.#render();
  }

  connectedCallback(): void {
    // A property set before the element upgraded shadows the accessor.
    for (const name of ["format", "values"] as const) {
      if (!Object.hasOwn(this, name)) continue;
      const early: unknown = Reflect.get(this, name);
      Reflect.deleteProperty(this, name);
      Reflect.set(this, name, early);
    }
    this.#render();
  }
}

if (customElements.get("range-slider") === undefined) {
  customElements.define("range-slider", RangeSliderElement);
}
