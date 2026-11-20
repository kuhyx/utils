/**
 * `<kuhy-credit>`: the shared kuhy credit, dependency-free.
 *
 * Shows only the M1 logo. Click/Enter/Space on it opens a small panel (logo +
 * the credit text); a click on the panel opens the website in a new tab.
 * Escape, a click anywhere else and a second logo click close the panel.
 * Nothing loads over the network: the logo is inlined from credit-data.js,
 * which the generator writes from kuhy_credit/credit.json and the M1 art.
 *
 * Attributes: `placement="above|below"` (default above), `align="end|start"`
 * (default end), `theme="light|dark"` (default: follow the page). Size via the
 * `--kuhy-credit-size` custom property (default 48px).
 */
import { CREDIT_TEXT, CREDIT_URL, LOGO_SVG, TOKENS } from "./credit-data.js";

const { dark, light } = TOKENS;
const palette = (p, usePage) =>
  ["surface", "border", "text"]
    .map((k) => {
      const page = { surface: "--surface-1", border: "--border", text: "--text" }[k];
      return `--kc-${k}: ${usePage ? `var(${page}, ${p[k]})` : p[k]};`;
    })
    .join(" ");

const STYLE = `
:host { position: relative; display: inline-block; ${palette(dark, true)}
  --kc-size: var(--kuhy-credit-size, 48px); }
@media (prefers-color-scheme: light) { :host { ${palette(light, true)} } }
:host([theme="dark"]) { ${palette(dark, false)} }
:host([theme="light"]) { ${palette(light, false)} }
button, a { cursor: pointer; border-radius: var(--radius-sm, 8px); }
button { display: block; padding: 0; border: 0; background: none;
  width: var(--kc-size); height: var(--kc-size); }
svg { display: block; width: 100%; height: 100%; border-radius: inherit; }
button:focus-visible, a:focus-visible {
  outline: 2px solid var(--focus-ring, ${TOKENS.focus}); outline-offset: 2px; }
a { position: absolute; bottom: calc(100% + ${TOKENS.spaceSm}px); right: 0; z-index: 1000;
  display: flex; align-items: center; gap: ${TOKENS.spaceSm}px; padding: ${TOKENS.spaceMd}px;
  white-space: nowrap; text-decoration: none; color: var(--kc-text);
  background: var(--kc-surface); border: 1px solid var(--kc-border);
  border-radius: ${TOKENS.radius}px; box-shadow: var(--shadow-1, none);
  font: ${TOKENS.textBody}px/1.5 var(--font-sans, system-ui, sans-serif); }
a[hidden] { display: none; }
a svg { width: var(--kc-size); height: var(--kc-size); flex: none; }
:host([placement="below"]) a { bottom: auto; top: calc(100% + ${TOKENS.spaceSm}px); }
:host([align="start"]) a { right: auto; left: 0; }
`;

export class KuhyCredit extends HTMLElement {
  #logo;
  #panel;
  #onDocClick = (event) => {
    if (this.open && !event.composedPath().includes(this)) this.close();
  };
  #onKey = (event) => {
    if (this.open && event.key === "Escape") {
      this.close();
      this.#logo.focus();
    }
  };

  connectedCallback() {
    if (!this.shadowRoot) this.#build();
    document.addEventListener("click", this.#onDocClick);
    document.addEventListener("keydown", this.#onKey);
  }

  disconnectedCallback() {
    document.removeEventListener("click", this.#onDocClick);
    document.removeEventListener("keydown", this.#onKey);
  }

  /** True while the panel is showing. */
  get open() {
    return !this.#panel.hidden;
  }

  /** Hide the panel. */
  close() {
    this.#panel.hidden = true;
    this.#logo.setAttribute("aria-expanded", "false");
  }

  #show() {
    this.#panel.hidden = false;
    this.#logo.setAttribute("aria-expanded", "true");
    this.#panel.focus();
  }

  #build() {
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `<style>${STYLE}</style>
<button type="button" aria-expanded="false" aria-controls="panel"></button>
<a id="panel" hidden target="_blank" rel="noopener noreferrer"><span></span></a>`;
    this.#logo = root.querySelector("button");
    this.#panel = root.querySelector("a");
    this.#logo.setAttribute("aria-label", CREDIT_TEXT);
    this.#logo.innerHTML = LOGO_SVG;
    this.#panel.href = CREDIT_URL;
    this.#panel.insertAdjacentHTML("afterbegin", LOGO_SVG);
    this.#panel.querySelector("span").textContent = CREDIT_TEXT;
    for (const svg of root.querySelectorAll("svg")) svg.setAttribute("aria-hidden", "true");
    this.#logo.addEventListener("click", () => (this.open ? this.close() : this.#show()));
    // Holding Enter on the logo opens the panel and focuses it; the key's
    // autorepeat must not then activate the link and open the site.
    this.#panel.addEventListener("keydown", (event) => {
      if (event.repeat && (event.key === "Enter" || event.key === " ")) event.preventDefault();
    });
    this.#panel.addEventListener("click", (event) => {
      event.preventDefault();
      this.close();
      window.open(CREDIT_URL, "_blank", "noopener,noreferrer");
    });
  }
}

if (!customElements.get("kuhy-credit")) customElements.define("kuhy-credit", KuhyCredit);
