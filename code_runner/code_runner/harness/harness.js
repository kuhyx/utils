"use strict";
// Runs inside the sandbox: call the solution once, write result.json.
const fs = require("node:fs");
const path = require("node:path");

const root = process.argv[2];
const spec = JSON.parse(fs.readFileSync(path.join(root, "input.json"), "utf8"));
const IDENT = /^[A-Za-z_$][\w$]*$/;

function describe(e) {
  const name = e && typeof e.name === "string" ? e.name : "Error";
  const message = e && e.message !== undefined ? e.message : String(e);
  return `${name}: ${message}`.slice(0, 300);
}

function writeResult(payload) {
  // Unique name + rename: a symlink planted at result.json is replaced, never followed.
  const unique = path.join(root, `.result-${process.pid}-${Math.random().toString(36).slice(2)}`);
  fs.writeFileSync(unique, JSON.stringify(payload), { flag: "wx" });
  fs.renameSync(unique, path.join(root, "result.json"));
}

function load(target) {
  if (!IDENT.test(target)) throw new TypeError("bad entry name");
  if (spec.typescript) return require(path.join(root, "solution.cts")).__entry;
  const source = fs.readFileSync(path.join(root, "solution.js"), "utf8");
  return new Function(`${source}\n;return ${target};`)();
}

function call() {
  const entry = load(spec.cls || spec.fn);
  if (spec.cls) return new entry()[spec.fn](...spec.args);
  return entry(...spec.args);
}

const started = process.hrtime.bigint();
let payload;
try {
  const value = call();
  payload = { ok: true, value: value === undefined ? null : JSON.parse(JSON.stringify(value)) };
} catch (e) {
  payload = { ok: false, error: describe(e) };
}
payload.ms = Number(process.hrtime.bigint() - started) / 1e6;
writeResult(payload);
