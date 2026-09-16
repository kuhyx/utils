// Structural rules: a file's name tells you what it exports.
//
// The article's "filenames matching exports" move. Kebab-case files exporting
// PascalCase components is the house convention across every kuhyx web repo;
// a model that invents `UserCard.tsx` next to `user-list.tsx` has not read the
// tree, and the rule says so before review has to.

/** @type {import("eslint").Linter.Config[]} */
export const naming = [
  {
    rules: {
      // Keep the rule, widen its vocabulary. `passesFilters(server, filter)`
      // and `matchesQuery(...)` are predicates that read as English; forcing
      // them to `isPassingFilters` would be worse prose in service of a prefix
      // list. `passes`/`matches` are added, nothing is removed.
      "unicorn/consistent-boolean-name": [
        "error",
        { prefixes: { matches: true, passes: true } },
      ],

      // Kebab-case files exporting PascalCase components: house convention.
      "unicorn/filename-case": ["error", { case: "kebabCase" }],

      // Keep the rule, drop one replacement: `props` is React's own word.
      // `interface FilterBarProps` is the convention every React codebase and
      // every reader expects; `FilterBarProperties` would be unidiomatic in
      // service of a generic dictionary. Every other replacement stays on.
      "unicorn/name-replacements": ["error", { replacements: { props: false } }],
    },
  },
];
