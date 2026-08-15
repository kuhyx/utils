export interface RangeSliderProps {
    /**
     * Formats a value for the head readout. Omit it (with `label`) to render a
     * bare track — dufs-cloud's wrappers draw their own labels and value notes,
     * so a built-in head would duplicate them.
     */
    readonly format?: (value: number) => string;
    /** Current upper bound; equal to the distribution max when unconstrained. */
    readonly hi: number;
    /** Accessible name. Falls back to a generic one when omitted. */
    readonly label?: string;
    /** Current lower bound; equal to the distribution min when unconstrained. */
    readonly lo: number;
    /** Reports both thumb values (raw, clamped so lo <= hi) on every change. */
    readonly onChange: (lo: number, hi: number) => void;
    /** The full ascending distribution — not just its endpoints. */
    readonly values: readonly number[];
}
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
export declare function steppedValue(values: readonly number[], current: number, delta: number): number;
export declare function RangeSlider({ format, hi, label, lo, onChange, values, }: RangeSliderProps): null | React.JSX.Element;
//# sourceMappingURL=range-slider.d.ts.map
