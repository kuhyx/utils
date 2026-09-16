// One call for the common case, the pieces for everything else.
//
//   import { defineConfig } from "@kuhyx/ts-config";
//   export default defineConfig({
//     tsconfigRootDir: import.meta.dirname,
//     react: true,
//     boundaries: { elements: folderElements(["components", "services"]) },
//   });
import { base } from "./base.js";
import { boundaries } from "./boundaries.js";
import { playwrightConfig } from "./playwright.js";
import { react } from "./react.js";
import { vitestConfig } from "./vitest.js";

export { base } from "./base.js";
export { boundaries, DEFAULT_ALLOW, folderElements } from "./boundaries.js";
export { playwrightConfig } from "./playwright.js";
export { react } from "./react.js";
export { vitestConfig } from "./vitest.js";

/**
 * @param {object} options
 * @param {string} options.tsconfigRootDir `import.meta.dirname` of the
 *   consumer's eslint.config.js.
 * @param {string[]} [options.ignores]
 * @param {boolean} [options.aliasOnly]
 * @param {string[]} [options.project] See base().
 * @param {boolean} [options.react] Stack the React layer.
 * @param {boolean} [options.vitest] Stack the vitest rules (default true).
 * @param {boolean} [options.playwright] Stack the Playwright rules.
 * @param {object} [options.boundaries] Options for boundaries(); omitted
 *   means no layer enforcement (a repo that has not declared its layers).
 * @param {import("eslint").Linter.Config[]} [options.overrides] Repo-specific
 *   config objects appended last, so they win. Each needs a reason comment.
 */
export function defineConfig({
  aliasOnly,
  boundaries: boundariesOptions,
  ignores,
  overrides = [],
  playwright = false,
  project,
  react: withReact = false,
  tsconfigRootDir,
  vitest = true,
}) {
  return [
    ...base({ aliasOnly, ignores, project, tsconfigRootDir }),
    ...(withReact ? react : []),
    ...(vitest ? vitestConfig : []),
    ...(playwright ? playwrightConfig : []),
    ...(boundariesOptions ? boundaries({ tsconfigRootDir, ...boundariesOptions }) : []),
    ...overrides,
  ];
}
