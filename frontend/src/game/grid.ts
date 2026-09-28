// Grid helpers. No React in here, so they are easy to reason about and to test.
//
// A grid is 81 numbers, row by row, 0 for an empty cell — the same layout as
// the 81-character strings the API sends (DATA_MODEL.md). Cell `i` is in row
// `Math.floor(i / 9)` and column `i % 9`.

export type Grid = readonly number[];

export const CELL_COUNT = 81;

export function parseGrid(text: string): number[] {
  if (!/^[0-9]{81}$/.test(text)) {
    throw new Error("A grid is exactly 81 characters, each 0-9.");
  }
  return Array.from(text, Number);
}

export const rowOf = (cell: number): number => Math.floor(cell / 9);
export const colOf = (cell: number): number => cell % 9;

/**
 * The grid with `value` written into `cell` (0 clears it).
 *
 * Givens cannot be changed: the same grid comes back untouched. The backend
 * enforces this as well (`409 cell_is_given`); the check here only keeps the
 * interface from pretending otherwise.
 */
export function setCell(values: Grid, givens: Grid, cell: number, value: number): Grid {
  if (givens[cell] !== 0 || values[cell] === value) return values;
  const next = values.slice();
  next[cell] = value;
  return next;
}

/** The cell reached by moving from `cell` by the given rows and columns,
 * stopping at the edge of the board. */
export function moveFrom(cell: number, rows: number, cols: number): number {
  const row = Math.min(8, Math.max(0, rowOf(cell) + rows));
  const col = Math.min(8, Math.max(0, colOf(cell) + cols));
  return row * 9 + col;
}
