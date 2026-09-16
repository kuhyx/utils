#!/usr/bin/env node
// CLI shim; the logic and its tests live in lib/alias-imports.mjs.
import { main } from "./lib/alias-imports.mjs";

process.exitCode = main(process.argv.slice(2));
