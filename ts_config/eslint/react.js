// React layer, stacked on base().
//
// Four plugins, each covering ground the others do not:
//   - react-hooks: the rules of hooks + exhaustive deps, plus React 19's
//     compiler-derived checks (`recommended` in 7.x).
//   - @eslint-react: component/JSX correctness, type-checked variant, and the
//     replacement for eslint-plugin-react (which crashes under ESLint 10).
//   - react-refresh: a file that mixes a component with a non-component
//     export silently breaks Vite HMR for the whole module.
//   - react-you-might-not-need-an-effect: the article names "an effect that
//     derives state from props" as the single most frequent AI edit. The
//     fixture's Button does exactly that, and this is the rule that sees it.
//   - jsx-a11y: accessibility is "the first thing to go" when a model
//     optimises for how the screen looks. Its 6.10.2 peer range stops at
//     ESLint ^9, but under 10 it runs cleanly (verified by the fixture test),
//     so the `strict` preset is on.
import eslintReact from "@eslint-react/eslint-plugin";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import youMightNotNeedAnEffect from "eslint-plugin-react-you-might-not-need-an-effect";

import { TS_FILES } from "./base.js";

/** @type {import("eslint").Linter.Config[]} */
export const react = [
  {
    ...eslintReact.configs["recommended-type-checked"],
    files: TS_FILES,
  },
  {
    files: TS_FILES,
    plugins: { "react-hooks": reactHooks },
    rules: reactHooks.configs.recommended.rules,
  },
  {
    files: ["**/*.tsx", "**/*.jsx"],
    ...jsxA11y.flatConfigs.strict,
  },
  {
    files: TS_FILES,
    ...youMightNotNeedAnEffect.configs.recommended,
  },
  {
    files: ["**/*.tsx", "**/*.jsx"],
    ...reactRefresh.configs.vite,
  },
  {
    files: TS_FILES,
    rules: {
      // Same list as naming.js, minus `ref`: @eslint-react's
      // naming-convention-ref-name wants every useRef() named `ref` or
      // `*Ref`, and unicorn's `ref -> reference` replacement contradicts it
      // on every one. `ref` is React's own word, like `props`.
      "unicorn/name-replacements": ["error", { replacements: { props: false, ref: false } }],

      // `className` is React's own prop name; in a React codebase the rule
      // fires on every styled element and cannot be satisfied.
      "unicorn/no-keyword-prefix": "off",
    },
  },
  {
    files: ["**/*.tsx", "**/*.jsx"],
    rules: {
      // `items.map((item) => (<li>…</li>))` is the JSX idiom in every React
      // codebase and what Prettier formats to; the rule would rewrite each
      // one to `{ return (…); }`, and cannot even autofix the ones with
      // multi-line text. It has no option to exempt JSX, so it is off for
      // JSX files only -- .ts files keep it.
      "unicorn/consistent-arrow-return-style": "off",
    },
  },
];
