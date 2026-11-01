export interface RangeChange {
    readonly hi: number;
    readonly lo: number;
}
export declare class RangeSliderElement extends HTMLElement {
    #private;
    static readonly observedAttributes: string[];
    get format(): ((value: number) => string) | undefined;
    set format(format: ((value: number) => string) | undefined);
    /** The upper bound; the distribution max when the attribute is absent. */
    get hi(): number;
    /** The lower bound; the distribution min when the attribute is absent. */
    get lo(): number;
    get values(): readonly number[];
    set values(values: readonly number[]);
    attributeChangedCallback(): void;
    connectedCallback(): void;
}
//# sourceMappingURL=range-slider-element.d.ts.map