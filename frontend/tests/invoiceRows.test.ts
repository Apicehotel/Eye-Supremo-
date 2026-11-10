import test from "node:test";
import assert from "node:assert/strict";
import { filterRows, isHighlighted } from "../src/lib/invoiceRows.ts";

const rows = [
  { original_description: 'SUCCHI YOGA OPTIMUM 200ML-BOT-ALBICOCCA' },
  { original_description: 'YOGURT MAGRO 0,1 "VIPITENO" VETRO GR 150' },
  { normalized_description: "Te twinig arancia" },
];

test("evidenzia la riga con la stessa descrizione, senza badare a maiuscole", () => {
  assert.deepEqual(rows.map((r) => isHighlighted(r, "succhi yoga optimum 200ml-bot-albicocca")), [true, false, false]);
});

test("senza testo cercato non evidenzia nulla", () => {
  assert.deepEqual(rows.map((r) => isHighlighted(r, "")), [false, false, false]);
});

test("il testo cercato può essere una parte della descrizione", () => {
  assert.equal(isHighlighted(rows[1], "vipiteno"), true);
});

test("la ricerca filtra le righe e vuota = tutte", () => {
  assert.equal(filterRows(rows, "yog").length, 2);
  assert.equal(filterRows(rows, "  ").length, 3);
  assert.equal(filterRows(rows, "zzz").length, 0);
});
