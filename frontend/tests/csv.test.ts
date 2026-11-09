import test from "node:test";
import assert from "node:assert/strict";
import { csvOf } from "../src/lib/csv.ts";

test("csvOf quotes separators, quotes and newlines", () => {
  assert.equal(csvOf([["a;b", 'x"y', 3, null]]), '"a;b";"x""y";3;');
});
