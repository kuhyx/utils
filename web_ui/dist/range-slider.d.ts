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
export declare function RangeSlider({ format, hi, label, lo, onChange, values, }: RangeSliderProps): null | React.JSX.Element;
//# sourceMappingURL=range-slider.d.ts.map