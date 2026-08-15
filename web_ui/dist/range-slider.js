import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * A dual-thumb slider whose track maps through a value *distribution* rather
 * than a linear min..max ramp (see `./quantile.ts` for why).
 *
 * Reconciled from the two drifted copies in dufs-cloud and
 * awesome-mcp-explorer. It takes the accessible DOM from awesome-mcp-explorer
 * (real `<button>` thumbs carrying `role="slider"` and the `aria-value*` trio,
 * so the control is a focus stop) and the grab-the-nearer-thumb pointer
 * behaviour from dufs-cloud (pressing anywhere on the track moves the closer
 * handle, instead of requiring a direct hit on an
 * 8px target).
 *
 * Keyboard support is new in the shared version. Both donors were pointer-only,
 * which the design system rules out outright: every action must be reachable
 * with the keyboard alone, and a `role="slider"` that does not respond to arrow
 * keys is an ARIA role that lies. Arrow keys step by one item through the
 * distribution, Home/End jump to the bounds.
 *
 * The component deals only in raw values; callers translate the extremes into
 * "no filter".
 */
import { useCallback, useState } from "react";
import { fractionFromPointer, nth, quantileValue, valueQuantile } from "./quantile.js";
/**
 * Steps one thumb by `delta` positions through the distribution. Pure, so the
 * keyboard contract is testable without layout.
 *
 * Steps to the next *distinct* value rather than the next index. Real
 * distributions are lumpy -- awesome-mcp-explorer's star counts hold ~1500
 * duplicate zeros -- and an index step inside a run of equal values changes the
 * index while leaving the value (and therefore the thumb, and the filter)
 * exactly where it was. That reads as a dead arrow key.
 */
export function steppedValue(values, current, delta) {
    const last = values.length - 1;
    // Round to a real sample index so a thumb sitting between two samples still
    // advances rather than stalling on a fractional step.
    const index = Math.round(valueQuantile(values, current) * last);
    const direction = Math.sign(delta);
    if (direction === 0)
        return nth(values, index);
    let cursor = index;
    for (let taken = 0; taken < Math.abs(delta); taken++) {
        let next = cursor + direction;
        while (next >= 0 && next <= last && nth(values, next) === nth(values, cursor)) {
            next += direction;
        }
        if (next < 0 || next > last)
            break;
        cursor = next;
    }
    return nth(values, cursor);
}
export function RangeSlider({ format, hi, label, lo, onChange, values, }) {
    const [drag, setDrag] = useState(null);
    const apply = useCallback((thumb, value) => {
        if (thumb === "lo")
            onChange(Math.min(value, hi), hi);
        else
            onChange(lo, Math.max(value, lo));
    }, [hi, lo, onChange]);
    // Reads the rect off the event's own target rather than a ref: the pointer
    // handlers are bound to the track, so currentTarget *is* the track. A ref
    // would add a null branch that cannot happen once the element is mounted.
    const valueAt = useCallback((track, clientX) => quantileValue(values, fractionFromPointer(track.getBoundingClientRect(), clientX)), [values]);
    const onKeyDown = useCallback((thumb, event) => {
        const current = thumb === "lo" ? lo : hi;
        const step = (delta) => {
            event.preventDefault();
            apply(thumb, steppedValue(values, current, delta));
        };
        if (event.key === "ArrowLeft" || event.key === "ArrowDown")
            step(-1);
        else if (event.key === "ArrowRight" || event.key === "ArrowUp")
            step(1);
        else if (event.key === "PageDown")
            step(-10);
        else if (event.key === "PageUp")
            step(10);
        else if (event.key === "Home") {
            event.preventDefault();
            apply(thumb, nth(values, 0));
        }
        else if (event.key === "End") {
            event.preventDefault();
            apply(thumb, nth(values, values.length - 1));
        }
    }, [apply, hi, lo, values]);
    // Fewer than two values means there is nothing to range over.
    if (values.length < 2)
        return null;
    const lowest = nth(values, 0);
    const highest = nth(values, values.length - 1);
    const loFraction = valueQuantile(values, lo) * 100;
    const hiFraction = valueQuantile(values, hi) * 100;
    const name = label ?? "Range";
    const thumbProps = (thumb) => ({
        "aria-valuemax": highest,
        "aria-valuemin": lowest,
        "aria-valuenow": thumb === "lo" ? lo : hi,
        className: `slider-thumb slider-${thumb}`,
        onKeyDown: (event) => {
            onKeyDown(thumb, event);
        },
        role: "slider",
        style: { left: `${String(thumb === "lo" ? loFraction : hiFraction)}%` },
        tabIndex: 0,
        type: "button",
    });
    return (_jsxs("div", { className: "slider", children: [label !== undefined && format !== undefined && (_jsxs("div", { className: "slider-head", children: [_jsx("span", { children: label }), _jsxs("span", { className: "slider-value", children: [format(lo), " \u2013 ", format(hi)] })] })), _jsxs("div", { className: "slider-track", onPointerDown: (event) => {
                    const value = valueAt(event.currentTarget, event.clientX);
                    // Grab whichever thumb is nearer, so a press anywhere on the track
                    // does something sensible instead of requiring a direct hit.
                    const thumb = Math.abs(value - lo) <= Math.abs(value - hi) ? "lo" : "hi";
                    setDrag(thumb);
                    event.currentTarget.setPointerCapture(event.pointerId);
                    apply(thumb, value);
                }, onPointerMove: (event) => {
                    if (drag === null)
                        return;
                    apply(drag, valueAt(event.currentTarget, event.clientX));
                }, onPointerUp: (event) => {
                    if (drag === null)
                        return;
                    setDrag(null);
                    event.currentTarget.releasePointerCapture(event.pointerId);
                }, children: [_jsx("div", { className: "slider-fill", style: { left: `${String(loFraction)}%`, width: `${String(hiFraction - loFraction)}%` } }), _jsx("button", { "aria-label": `${name} minimum`, ...thumbProps("lo") }), _jsx("button", { "aria-label": `${name} maximum`, ...thumbProps("hi") })] })] }));
}
//# sourceMappingURL=range-slider.js.map
