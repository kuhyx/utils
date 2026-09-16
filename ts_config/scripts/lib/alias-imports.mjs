// Rewrite parent-relative imports under src/ to the `@/` alias.
//
// The preset bans `../` specifiers (imports.js): they encode the importer's
// depth, and a model that guesses the depth wrong lands on the wrong module.
// Turning the rule on in a repo with dozens of them by hand is the kind of
// mechanical step that gets done slightly differently each time, so it is a
// script: every `import`/`export … from "../x"` (and dynamic `import("../x")`)
// whose target resolves under src/ becomes `@/<path from src>`. `./sibling`
// and package imports are left alone, and so is a `../` that resolves OUTSIDE
// src/ -- there is no alias for it, and the lint report is the right place
// for that one to surface.
//
// The extension is carried over untouched: a repo on NodeNext resolution
// needs its `.js` suffixes, a bundler repo has none, and this script has no
// business changing which of the two it is.
import fs from "node:fs";
import path from "node:path";

const SOURCE_EXTENSIONS = new Set([".cts", ".js", ".jsx", ".mts", ".ts", ".tsx"]);

// A string literal that is an import/export specifier: preceded by `from`,
// by `import` (side-effect form), or by `import(` (dynamic form).
const SPECIFIER = /(\bfrom\s*|\bimport\s*\(\s*|\bimport\s+)(['"])(\.\.\/[^'"\n]*)\2/g;

/** Every source file below `directory`, depth-first, sorted for a stable report. */
export function listSourceFiles(directory) {
  const out = [];
  const entries = fs.readdirSync(directory, { withFileTypes: true }).toSorted((a, b) => a.name.localeCompare(b.name));
  for (const entry of entries) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      out.push(...listSourceFiles(full));
    } else if (SOURCE_EXTENSIONS.has(path.extname(entry.name))) {
      out.push(full);
    }
  }
  return out;
}

/**
 * The alias form of one specifier, or null when it must stay as written.
 *
 * @param {string} file Absolute path of the importing file.
 * @param {string} specifier The `../…` string as it appears in the source.
 * @param {string} sourceDirectory Absolute path of the aliased directory.
 */
export function aliasFor(file, specifier, sourceDirectory) {
  const resolved = path.resolve(path.dirname(file), specifier);
  const fromSource = path.relative(sourceDirectory, resolved);
  const outside = fromSource === "" || fromSource.startsWith("..") || path.isAbsolute(fromSource);
  return outside ? null : `@/${fromSource.split(path.sep).join("/")}`;
}

/**
 * Rewrite one file's text. Pure: returns the new text and how many
 * specifiers changed, touches nothing on disk.
 */
export function rewriteSource(file, text, sourceDirectory) {
  let count = 0;
  const rewritten = text.replaceAll(SPECIFIER, (match, lead, quote, specifier) => {
    const alias = aliasFor(file, specifier, sourceDirectory);
    if (alias === null) {
      return match;
    }
    count += 1;
    return `${lead}${quote}${alias}${quote}`;
  });
  return { count, text: rewritten };
}

/**
 * Rewrite every source file under `<root>/<source>` in place.
 *
 * @param {string} root Repo root.
 * @param {string} [source] Aliased directory, relative to root.
 * @returns {{ files: number, imports: number }} What changed.
 */
export function aliasImports(root, source = "src") {
  const sourceDirectory = path.resolve(root, source);
  if (!fs.existsSync(sourceDirectory)) {
    throw new Error(`alias-imports: no such directory ${sourceDirectory}`);
  }
  let files = 0;
  let imports = 0;
  for (const file of listSourceFiles(sourceDirectory)) {
    const before = fs.readFileSync(file, "utf8");
    const { count, text } = rewriteSource(file, before, sourceDirectory);
    if (count === 0) {
      continue;
    }
    fs.writeFileSync(file, text);
    files += 1;
    imports += count;
  }
  return { files, imports };
}

/**
 * CLI body: `alias-imports <repo-root> [src-dir]`. Returns the exit code
 * and writes the one-line report, so the shim stays at two lines.
 *
 * @param {string[]} argv Arguments after the script name.
 * @param {{ log: (line: string) => void }} [io]
 */
export function main(argv, io = console) {
  const [root, source] = argv;
  if (root === undefined) {
    io.log("usage: alias-imports <repo-root> [src-dir=src]");
    return 2;
  }
  const { files, imports } = aliasImports(root, source);
  io.log(`alias-imports: rewrote ${imports} import(s) in ${files} file(s) under ${path.resolve(root, source ?? "src")}`);
  return 0;
}
