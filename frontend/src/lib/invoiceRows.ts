export const rowDescription = (row: any): string => String(row?.original_description || row?.normalized_description || "").trim().toLowerCase();

/** La riga di fattura è quella cercata: descrizione uguale, o testo contenuto (in un senso o nell'altro, solo se non troppo corto). */
export function isHighlighted(row: any, highlight?: string): boolean {
  const needle = (highlight || "").trim().toLowerCase();
  if (!needle) return false;
  const text = rowDescription(row);
  return text === needle || (text.length > 0 && text.includes(needle)) || (text.length > 5 && needle.includes(text));
}

/** Filtro di ricerca sulle righe: testo contenuto nella descrizione (vuoto = tutte). */
export function filterRows<T>(rows: T[], query: string): T[] {
  const q = query.trim().toLowerCase();
  return q ? rows.filter((row) => rowDescription(row).includes(q)) : rows;
}
