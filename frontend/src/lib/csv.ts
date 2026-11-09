/** CSV con «;» e BOM (Excel italiano). */
export function csvOf(rows: (string | number | null | undefined)[][]): string {
  return rows.map((r) => r.map((c) => { const t = c == null ? "" : String(c); return /[";\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t; }).join(";")).join("\n");
}
