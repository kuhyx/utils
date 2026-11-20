/** `<kuhy-credit>`: the shared "Created by kuhy" logo credit. */
export declare class KuhyCredit extends HTMLElement {
  /** True while the panel is showing. */
  readonly open: boolean;
  /** Hide the panel. */
  close(): void;
}

/** Attributes the element reads. */
export interface KuhyCreditAttributes {
  align?: "end" | "start";
  placement?: "above" | "below";
  theme?: "dark" | "light";
}

declare global {
  interface HTMLElementTagNameMap {
    "kuhy-credit": KuhyCredit;
  }
  // React 19 / Vite: <kuhy-credit /> in JSX.
  namespace JSX {
    interface IntrinsicElements {
      "kuhy-credit": KuhyCreditAttributes & { class?: string; className?: string };
    }
  }
}
