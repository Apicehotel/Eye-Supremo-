export type SortDirection = "asc" | "desc";
export type SortKey = string;

export function sortIndicator(sort: {key: SortKey; direction: SortDirection}, key: SortKey) {
  return sort.key === key ? (sort.direction === "asc" ? " ↑" : " ↓") : "";
}

export function compareValues(left: unknown, right: unknown, direction: SortDirection) {
  if (left == null || left === "") return right == null || right === "" ? 0 : 1;
  if (right == null || right === "") return -1;
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  const numeric = typeof left === "number" || typeof right === "number" || (!Number.isNaN(leftNumber) && !Number.isNaN(rightNumber));
  const result = numeric
    ? leftNumber - rightNumber
    : String(left).localeCompare(String(right), "it", {numeric: true, sensitivity: "base"});
  return direction === "asc" ? result : -result;
}

export function SortHeader({label, sort, sortKey, onSort}: {label: string; sort: {key: SortKey; direction: SortDirection}; sortKey: SortKey; onSort: (key: SortKey) => void}) {
  return <button type="button" className="table-sort-button" onClick={() => onSort(sortKey)}>{label}{sortIndicator(sort, sortKey)}</button>;
}
