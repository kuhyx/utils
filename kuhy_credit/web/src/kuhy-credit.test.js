import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CREDIT_TEXT, CREDIT_URL, TOKENS } from "./credit-data.js";
import { KuhyCredit } from "./kuhy-credit.js";

let host;
let open;

const parts = () => ({
  logo: host.shadowRoot.querySelector("button"),
  panel: host.shadowRoot.querySelector("a"),
});
const click = (el) => el.dispatchEvent(new MouseEvent("click", { bubbles: true, composed: true, cancelable: true }));
const key = (el, k) => el.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, composed: true }));

beforeEach(() => {
  open = vi.spyOn(window, "open").mockImplementation(() => null);
  host = document.createElement("kuhy-credit");
  document.body.append(host);
});

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("<kuhy-credit>", () => {
  it("registers once and shows only the logo", () => {
    expect(customElements.get("kuhy-credit")).toBe(KuhyCredit);
    const { logo, panel } = parts();
    expect(logo.querySelector("svg")).not.toBeNull();
    expect(logo.textContent.trim()).toBe("");
    expect(panel.hidden).toBe(true);
    expect(open).not.toHaveBeenCalled();
  });

  it("names the logo and the panel, and wires aria-expanded", () => {
    const { logo, panel } = parts();
    expect(logo.getAttribute("aria-label")).toBe(CREDIT_TEXT);
    expect(logo.getAttribute("aria-expanded")).toBe("false");
    expect(logo.getAttribute("aria-controls")).toBe(panel.id);
    expect(panel.textContent.trim()).toBe(CREDIT_TEXT);
    expect(panel.getAttribute("href")).toBe(CREDIT_URL);
    expect(panel.querySelector("svg").getAttribute("aria-hidden")).toBe("true");
  });

  it("opens the panel on a logo click and the website on a panel click", () => {
    const { logo, panel } = parts();
    click(logo);
    expect(panel.hidden).toBe(false);
    expect(logo.getAttribute("aria-expanded")).toBe("true");
    expect(host.open).toBe(true);
    expect(open).not.toHaveBeenCalled();
    click(panel.querySelector("span"));
    expect(open).toHaveBeenCalledExactlyOnceWith(CREDIT_URL, "_blank", "noopener,noreferrer");
    expect(panel.hidden).toBe(true);
  });

  it("closes on Escape and returns focus to the logo", () => {
    const { logo, panel } = parts();
    click(logo);
    key(document, "Escape");
    expect(panel.hidden).toBe(true);
    expect(host.shadowRoot.activeElement).toBe(logo);
    expect(open).not.toHaveBeenCalled();
  });

  it("ignores a held (repeating) Enter or Space on the panel", () => {
    const { logo, panel } = parts();
    click(logo);
    for (const k of ["Enter", " "]) {
      const held = new KeyboardEvent("keydown", { key: k, repeat: true, bubbles: true, cancelable: true });
      panel.dispatchEvent(held);
      expect(held.defaultPrevented).toBe(true);
    }
    const fresh = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    panel.dispatchEvent(fresh);
    expect(fresh.defaultPrevented).toBe(false);
    const heldOther = new KeyboardEvent("keydown", { key: "a", repeat: true, bubbles: true, cancelable: true });
    panel.dispatchEvent(heldOther);
    expect(heldOther.defaultPrevented).toBe(false);
  });

  it("ignores other keys and Escape while closed", () => {
    const { logo, panel } = parts();
    key(document, "Escape");
    click(logo);
    key(document, "Enter");
    expect(panel.hidden).toBe(false);
  });

  it("closes on a click outside", () => {
    const { logo, panel } = parts();
    click(logo);
    click(document.body);
    expect(panel.hidden).toBe(true);
    expect(open).not.toHaveBeenCalled();
  });

  it("ignores outside clicks while closed", () => {
    click(document.body);
    expect(parts().panel.hidden).toBe(true);
  });

  it("closes on a second logo click and stays closed", () => {
    const { logo, panel } = parts();
    click(logo);
    click(logo);
    expect(panel.hidden).toBe(true);
    expect(open).not.toHaveBeenCalled();
  });

  it("focuses the panel link when it opens", () => {
    const { logo, panel } = parts();
    click(logo);
    expect(host.shadowRoot.activeElement).toBe(panel);
  });

  it("stops listening once removed from the page", () => {
    const { logo, panel } = parts();
    click(logo);
    host.remove();
    click(document.body);
    expect(panel.hidden).toBe(false);
  });

  it("does not redefine the element when loaded twice", async () => {
    const again = await import("./kuhy-credit.js?again");
    expect(customElements.get("kuhy-credit")).toBe(KuhyCredit);
    expect(again.KuhyCredit).not.toBe(KuhyCredit);
  });

  it("builds its shadow DOM only once when re-attached", () => {
    host.remove();
    document.body.append(host);
    expect(host.shadowRoot.querySelectorAll("button")).toHaveLength(1);
  });

  it("styles from the design tokens with dark and light fallbacks", () => {
    const css = host.shadowRoot.querySelector("style").textContent;
    for (const value of [TOKENS.dark.surface, TOKENS.light.surface, TOKENS.dark.text, TOKENS.light.text, TOKENS.focus]) {
      expect(css).toContain(value);
    }
    expect(css).toContain("var(--surface-1");
    expect(css).toContain("prefers-color-scheme: light");
    expect(css).toContain(`${TOKENS.radius}px`);
  });
});
