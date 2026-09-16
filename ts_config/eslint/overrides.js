// House overrides, applied to every file including the consumer's own config.
//
// Each rule below is switched off deliberately: these are the cases where
// "more aggressive" makes the code worse rather than safer. A rule you must
// disable at every use site is worse than no rule at all, because
// reportUnusedDisableDirectives then turns the disables into their own debt.
//
// Anything a single repo needs beyond this list stays in THAT repo's
// eslint.config.js with its own reason comment; it moves here only once three
// repos carry the same override.

/** @type {import("eslint").Linter.Config[]} */
export const overrides = [
  {
    rules: {
      // Directly contradicts unicorn/consistent-class-member-order: one wants
      // a private field before the getter that reads it, the other wants the
      // getter first, and satisfying either re-triggers the other. unicorn's
      // wins because "declare the field before the code that uses it" is a
      // reason, whereas alphabetical order within a class is not.
      "perfectionist/sort-classes": "off",

      // Alphabetises declarations within a file, which actively fights reading
      // order: it would scatter `GRADES -> gradeRank -> isTripleA` into
      // `compositeRank -> GRADES -> gradeCoverage`. Alphabetical order is not
      // narrative order. Every *other* perfectionist rule stays on -- sorting
      // imports, union members and object keys destroys no narrative.
      "perfectionist/sort-modules": "off",

      // Wants JSDoc blocks written without leading `*`, which is neither the
      // TypeScript convention nor what editors/typedoc render.
      "unicorn/no-asterisk-prefix-in-documentation-comments": "off",

      // Flags hand-wrapped comment prose. Comments are wrapped to 80 columns
      // on purpose; the rule would force one long line per paragraph.
      "unicorn/no-manually-wrapped-comments": "off",

      // `null` is load-bearing wherever JSON crosses a boundary: JSON has no
      // `undefined`, and "the API sent null" and "the field was absent" are
      // different facts that UIs render differently. Collapsing them loses
      // information.
      "unicorn/no-null": "off",

      // `Temporal` does not exist in the runtimes these repos target (Node 26
      // reports `typeof Temporal === "undefined"`); the rule is unfollowable
      // until it ships. Inputs are ISO-8601 strings, which Date.parse handles
      // identically across engines -- the cross-engine inconsistency the rule
      // warns about is for non-ISO strings.
      "unicorn/prefer-temporal": "off",

      // The domain vocabulary is abbreviated on purpose: `os`, `spdx`, `repo`,
      // `env`, `rng` are the names the source data and the maths use, and
      // expanding them would obscure the mapping.
      "unicorn/prevent-abbreviations": "off",

      // Rewrites `/** @type {X} */` into a `//` comment, which strips the type
      // annotation TypeScript reads from JSDoc in plain-JS files. This package
      // and every consumer's config file are plain JS.
      "unicorn/single-line-block-comment-style": "off",

      // Caps a try block at ONE statement. Unfollowable where the whole point
      // is that several steps can throw: getItem (throws in private
      // browsing), JSON.parse (throws on junk) and a shape check belong in one
      // try because any of them failing means the same thing. The rule has no
      // maximum option, so it is all or nothing.
      "unicorn/try-complexity": "off",
    },
  },
];
