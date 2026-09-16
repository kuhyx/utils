// Structural rules: imports only through aliases.
//
// `../../services/api` encodes the importing file's depth in every consumer;
// move the file and every one of them breaks, and a model that guesses the
// depth wrong produces an import that resolves to the wrong module or to
// nothing. `@/services/api` is location-independent. Same-directory `./x`
// stays allowed: that is a sibling, not a traversal.

/** @type {import("eslint").Linter.Config[]} */
export const imports = [
  {
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["../*"],
              message:
                "Import through the repo alias (`@/…`) instead of a parent-relative path.",
            },
          ],
        },
      ],
    },
  },
];
