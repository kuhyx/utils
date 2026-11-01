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
import { fractionFromPointer, nth, quantileValue, valueQuantile } from "./quantile.js";
import { keyTarget } from "./stepped-value.js";
function make(tag, classes) {
    const element = document.createElement(tag);
    element.setAttribute("class", classes);
    return element;
}
function thumbButton(thumb) {
    const button = make("button", `slider-thumb slider-${thumb}`);
    button.type = "button";
    button.setAttribute("role", "slider");
    return button;
}
function buildParts() {
    const root = make("div", "slider");
    const track = make("div", "slider-track");
    const fill = make("div", "slider-fill");
    const lo = thumbButton("lo");
    const hi = thumbButton("hi");
    track.append(fill, lo, hi);
    root.append(track);
    return { fill, hi, lo, root, track };
}
function required(found, selector) {
    if (found === null)
        throw new Error(`<range-slider> markup is missing ${selector}`);
    return found;
}
function adoptParts(host) {
    const root = required(host.querySelector(".slider"), ".slider");
    return {
        fill: required(root.querySelector(".slider-fill"), ".slider-fill"),
        hi: required(root.querySelector(".slider-hi"), ".slider-hi"),
        lo: required(root.querySelector(".slider-lo"), ".slider-lo"),
        root,
        track: required(root.querySelector(".slider-track"), ".slider-track"),
    };
}
export class RangeSliderElement extends HTMLElement {
    static observedAttributes = ["hi", "label", "lo"];
    #drag = null;
    #format;
    #parts;
    #values = [];
    #apply(thumb, value) {
        const lo = thumb === "lo" ? Math.min(value, this.hi) : this.lo;
        const hi = thumb === "hi" ? Math.max(value, this.lo) : this.hi;
        this.setAttribute("lo", String(lo));
        this.setAttribute("hi", String(hi));
        const detail = { hi, lo };
        this.dispatchEvent(new CustomEvent("change", { bubbles: true, detail }));
    }
    #bound(name, fallback) {
        const raw = this.getAttribute(name);
        const parsed = raw === null ? NaN : Number(raw);
        return Number.isNaN(parsed) ? fallback : parsed;
    }
    #build() {
        const parts = buildParts();
        this.append(parts.root);
        return parts;
    }
    #mount() {
        if (this.#parts !== undefined)
            return this.#parts;
        const parts = this.querySelector(".slider") === null ? this.#build() : adoptParts(this);
        for (const thumb of ["lo", "hi"]) {
            parts[thumb].addEventListener("keydown", (event) => {
                const target = keyTarget(event.key, this.#values, thumb === "lo" ? this.lo : this.hi);
                if (target === undefined)
                    return;
                event.preventDefault();
                this.#apply(thumb, target);
            });
        }
        const valueAt = (event) => {
            return quantileValue(this.#values, fractionFromPointer(parts.track.getBoundingClientRect(), event.clientX));
        };
        parts.track.addEventListener("pointerdown", (event) => {
            const value = valueAt(event);
            // Pressing anywhere on the track grabs the nearer thumb.
            const thumb = Math.abs(value - this.lo) <= Math.abs(value - this.hi) ? "lo" : "hi";
            this.#drag = thumb;
            parts.track.setPointerCapture(event.pointerId);
            this.#apply(thumb, value);
        });
        parts.track.addEventListener("pointermove", (event) => {
            if (this.#drag === null)
                return;
            this.#apply(this.#drag, valueAt(event));
        });
        parts.track.addEventListener("pointerup", (event) => {
            if (this.#drag === null)
                return;
            this.#drag = null;
            parts.track.releasePointerCapture(event.pointerId);
        });
        this.#parts = parts;
        return parts;
    }
    #renderHead(root, label) {
        const format = this.#format;
        if (label === null || format === undefined)
            return;
        let head = root.querySelector(".slider-head");
        if (head === null) {
            head = make("div", "slider-head");
            head.append(document.createElement("span"), make("span", "slider-value"));
            root.prepend(head);
        }
        const [name, value] = head.children;
        if (name !== undefined)
            name.textContent = label;
        if (value !== undefined)
            value.textContent = `${format(this.lo)} – ${format(this.hi)}`;
    }
    #render() {
        const { fill, hi, lo, root } = this.#mount();
        const values = this.#values;
        root.hidden = values.length < 2;
        if (root.hidden)
            return;
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
        ]) {
            button.setAttribute("aria-label", `${name} ${thumb}`);
            button.setAttribute("aria-valuemin", String(nth(values, 0)));
            button.setAttribute("aria-valuemax", String(nth(values, values.length - 1)));
            button.setAttribute("aria-valuenow", String(now));
            button.style.left = `${String(fraction)}%`;
        }
        this.#renderHead(root, label);
    }
    get format() {
        return this.#format;
    }
    set format(format) {
        this.#format = format;
        this.#render();
    }
    /** The upper bound; the distribution max when the attribute is absent. */
    get hi() {
        return this.#bound("hi", this.#values.length === 0 ? 0 : nth(this.#values, this.#values.length - 1));
    }
    /** The lower bound; the distribution min when the attribute is absent. */
    get lo() {
        return this.#bound("lo", this.#values.length === 0 ? 0 : nth(this.#values, 0));
    }
    get values() {
        return this.#values;
    }
    set values(values) {
        this.#values = values;
        this.#render();
    }
    attributeChangedCallback() {
        if (this.#parts !== undefined)
            this.#render();
    }
    connectedCallback() {
        // A property set before the element upgraded shadows the accessor.
        for (const name of ["format", "values"]) {
            if (!Object.hasOwn(this, name))
                continue;
            const early = Reflect.get(this, name);
            Reflect.deleteProperty(this, name);
            Reflect.set(this, name, early);
        }
        this.#render();
    }
}
if (customElements.get("range-slider") === undefined) {
    customElements.define("range-slider", RangeSliderElement);
}
//# sourceMappingURL=range-slider-element.js.map